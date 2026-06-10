# SUBMIT

## 1) Latency budget của endpoint `/incident` (p99)
Với workload batch nhỏ đến vừa, tôi kỳ vọng p99 của endpoint nằm trong khoảng **120–180ms** khi chạy ổn định và không có vấn đề ở downstream. Phân bổ hợp lý:

- **FastAPI + Pydantic validation**: 5–15ms
- **Correlation (`session_groups` + topology grouping)**: 10–30ms cho batch nhỏ, tăng theo số alert
- **RCA graph scoring**: 15–40ms
- **Historical retrieval / TF-IDF similarity**: 20–60ms
- **Serialization + middleware/logging**: 5–10ms

**Phase chiếm thời gian nhất** thường là **historical retrieval + RCA scoring**, đặc biệt khi `incidents_history` lớn hơn hoặc khi TF-IDF phải fit/transform lại. Trong code hiện tại, `TfidfVectorizer.fit_transform()` được gọi mỗi request trong `retrieve_similar_incidents()`, nên đây là phần dễ trở thành bottleneck nhất. Nếu tối ưu, nên cache vectorizer/matrix hoặc precompute index để giảm p99.

## 2) Endpoint xử lý 5 alert vs 500 alert — latency khác nhau thế nào?
Latency **không hoàn toàn tuyến tính**, nhưng có một phần **fixed cost** và một phần **variable cost**.

### Fixed cost
- Load request, validate schema
- Build response model
- Logging / middleware
- Graph/history đã load sẵn ở module level nên không tốn lại mỗi request

Phần fixed cost này gần như giống nhau giữa 5 và 500 alerts, nên với 5 alerts nó chiếm tỷ trọng lớn hơn.

### Variable cost
- `session_groups()` sort theo timestamp: gần **O(n log n)**
- `topology_group()` duyệt các service và shortest path trên graph: tăng theo số service unique trong batch
- RCA / scoring / retrieval: tăng theo số cluster và số fingerprints

### Kết luận
- Với **5 alerts**, latency chủ yếu là fixed cost + một chút variable cost, thường khá thấp.
- Với **500 alerts**, latency tăng rõ rệt vì sort, grouping, và scoring nhiều hơn.
- Không phải scale tuyến tính tuyệt đối theo số alert, nhưng **xấp xỉ tăng theo n log n + số service unique + số cluster**.
- Nếu 500 alerts vẫn thuộc cùng một session và ít service unique, latency tăng không quá khủng; nếu nhiều service và nhiều cluster, latency tăng mạnh hơn.

## 3) LLM provider down giữa lúc đang chạy — hệ thống behave ra sao? Phương án dự phòng?
Trong thiết kế này, LLM chỉ nên là **enrichment layer**, không phải dependency bắt buộc để endpoint trả kết quả. Nếu LLM provider down giữa lúc xử lý:

- Pipeline **không được fail toàn bộ request**
- Hệ thống phải trả về:
  - root cause từ graph/severity scoring
  - candidate actions fallback từ history hoặc rule-based default
  - similar incidents nếu có thể truy xuất từ history local/cache

### Hành vi mong muốn
1. Thử gọi LLM với timeout ngắn
2. Nếu timeout / provider error:
   - log warning/error
   - bỏ qua phần LLM enrichment
   - dùng fallback output đã chuẩn bị trước
3. Response vẫn `200 OK` nếu core pipeline chạy được

### Phương án dự phòng
- **Timeout ngắn** cho LLM call, ví dụ 1–2 giây
- **Circuit breaker** nếu provider lỗi liên tiếp
- **Cached prompt/result** cho incident tương tự
- **Rule-based fallback**:
  - actions từ incident history
  - template actions theo root cause class
- **Degraded mode**: trả một response ít “giàu ngữ nghĩa” hơn nhưng vẫn hữu ích

Điểm quan trọng là **LLM không được nằm trên critical path** của availability. Nếu LLM chết, incident endpoint vẫn phải trả kết quả core.

## 4) `/healthz` và `/readyz` khác nhau gì? Khi nào dùng cái nào?
### `/healthz`
- Chỉ trả lời câu hỏi: **process còn sống không?**
- Dùng cho **liveness probe**
- Nếu app còn chạy event loop / process không crash, `/healthz` nên trả `200`
- Không nên kiểm tra dependency bên ngoài quá sâu ở đây

### `/readyz`
- Trả lời câu hỏi: **service đã sẵn sàng nhận traffic chưa?**
- Dùng cho **readiness probe**
- Có thể kiểm tra:
  - graph đã load chưa
  - history đã load chưa
  - dependency bắt buộc có sẵn chưa
- Không nên hard-block vì dependency optional như LLM provider nếu LLM chỉ là enrichment

### Khi nào dùng cái nào?
- Dùng **`/healthz`** để Kubernetes / load balancer biết instance còn sống hay đã chết
- Dùng **`/readyz`** để quyết định instance có được nhận request production hay chưa
- Nếu `/healthz` fail thì instance có thể bị restart
- Nếu `/readyz` fail thì instance nên bị loại khỏi traffic, nhưng không nhất thiết restart ngay

Trong code hiện tại, `/readyz` đã đi đúng hướng hơn vì nó kiểm tra graph/history. Nếu muốn production mature hơn, nên giữ `/healthz` cực nhẹ và để `/readyz` phản ánh readiness thật sự.

## 5) POST 4 request đồng thời — endpoint handle ổn không? Bottleneck đầu tiên?
Với **4 request đồng thời**, endpoint hiện tại **có thể handle ổn** nếu batch mỗi request không quá lớn. FastAPI có thể xử lý concurrent requests tốt ở mức application, nhưng bottleneck đầu tiên có khả năng không phải ở FastAPI mà là ở phần **CPU-bound processing** trong pipeline.

### Bottleneck đầu tiên có thể gặp
1. **TF-IDF retrieval trong `retrieve_similar_incidents()`**
   - `fit_transform()` trên toàn history mỗi request là tốn nhất
   - Nếu 4 request cùng lúc, CPU sẽ bị kéo mạnh

2. **Graph scoring / networkx PageRank**
   - NetworkX chạy trong Python, không phải engine tối ưu cao
   - Với nhiều cluster/service unique, chi phí tăng đáng kể

3. **JSON parsing / sorting / clustering**
   - Với payload lớn, `session_groups` và `topology_group` cũng tốn CPU

### 4 concurrent requests có ổn không?
- Nếu mỗi request chỉ có 5–20 alerts, thường vẫn ổn
- Nếu mỗi request có 500 alerts, 4 request đồng thời có thể làm p99 tăng rõ
- Vì đây là CPU-bound logic, concurrency không tự động giúp nhanh hơn; nó chủ yếu giúp IO-bound workloads

### Bottleneck đầu tiên về mặt hệ thống
- **CPU on worker** là bottleneck đầu tiên
- Nếu chạy 1 worker, 4 requests đồng thời sẽ tranh CPU
- Nếu deployment dùng nhiều worker/process, throughput tốt hơn nhưng memory tăng

### Khuyến nghị production
- Tách LLM call ra khỏi critical path
- Cache historical vector space / index
- Precompute graph-related structures
- Nếu cần throughput cao, chạy nhiều worker hoặc dùng background job cho enrichment nặng

## Kết luận ngắn
Endpoint này phù hợp cho **incident triage nhanh**, nhưng để production mature hơn cần:
- cache retrieval artifacts
- coi LLM là optional
- giữ `/healthz` nhẹ, `/readyz` kiểm tra readiness thật
- chuẩn bị fallback khi downstream/enrichment down
- tối ưu phần TF-IDF và graph scoring để p99 ổn định hơn