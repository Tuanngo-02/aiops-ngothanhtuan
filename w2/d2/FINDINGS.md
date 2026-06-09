# FINDINGS

## 1) Cluster chính: root cause là gì + lý do

**Cluster chính là `c-000-000`** và hiện tại cũng là **cluster duy nhất**, vì `dataset/cluster_summary.json` cho thấy:
- `input_alerts = 20`
- `output_clusters = 1`
- cluster `c-000-000` chứa **20/20 alerts**

**Root cause service hợp lý nhất là `payment-svc`**, nhưng **root cause class tôi tin hơn là `connection_pool_exhaustion`**, không phải `infinite_retry` như trong `results/rca_output.json`.

### Lý do
- **Tín hiệu sớm nhất và mạnh nhất đều xuất hiện ở `payment-svc`**:
  - `db_connection_pool_used_ratio` tăng từ warn `0.85 > 0.80` lên crit `0.99 > 0.95`, rồi `1.00`
  - `latency_p99_ms` crit `1840 > 800`
  - `error_rate` tăng từ warn lên crit
- **`checkout-svc` nhìn giống downstream symptom hơn là điểm phát sinh đầu tiên**
  - có `downstream_payment_error_rate`
  - sau đó mới có `latency_p99_ms` và `request_drop_rate`
- **`edge-lb` là propagation ở tầng edge**
  - `upstream_5xx_rate` và `p99_latency_ms` tăng sau payment/checkout
  - `services.json` ghi rõ alert ở `edge-lb` thường là downstream propagation
- **`notification-svc` backlog cũng là hậu quả dây chuyền**
  - queue lag/depth tăng muộn hơn
  - topology note nói đây là async layer, không phải blocker chính của checkout
- **Lịch sử incident khớp mạnh với `connection_pool_exhaustion`**
  - `INC-2025-11-08`: payment-svc leak DB pool, checkout cascade, notification queue backlog
  - `INC-2026-05-10`: lặp lại pattern pool exhaustion
  - `_meta.note` trong `incidents_history.json` còn nói rõ scenario chính match closest với `INC-2025-11-08`

### Kết luận
Tôi đồng ý với output ở phần **service = `payment-svc`**, nhưng chưa đồng ý hoàn toàn với phần **class = `infinite_retry`**. Nếu nhìn toàn bộ dữ liệu trong `w2/d2`, kết luận đáng tin hơn là:

**`payment-svc` → `connection_pool_exhaustion`**

---

## 2) Confidence — có dám deploy auto-remediation dựa trên output này không?

**Chưa nên deploy auto-remediation fully automatic dựa trên output hiện tại.**

### Lý do
- `results/rca_output.json` cho cluster chính có **confidence = `0.5`**, vẫn chỉ ở mức trung bình.
- Output hiện tại đã sửa đúng hơn ở phần **root cause service = `payment-svc`**, nhưng **incident class vẫn có dấu hiệu lệch**:
  - output nói `infinite_retry`
  - raw alerts + incident history lại nghiêng nhiều về `connection_pool_exhaustion`
- Nếu auto-remediation theo output hiện tại, hành động được đề xuất là:
  - thêm circuit breaker
  - cap retry = 3
- Nhưng nếu nguyên nhân thật là pool DB cạn, remediation đúng hơn phải là:
  - rollback bản deploy gây leak
  - tăng pool cushion
  - thêm pool monitor / leak detection

### Đánh giá thực tế
- **Auto-remediation fully automatic:** **không dám deploy**
- **Human-in-the-loop / approval gate:** **dùng được**
- **Low-risk automation** như enrich ticket, attach similar incidents, page đúng team payments: **nên dùng**

---

## 3) 1 case mà tôi không chắc — vì sao

**Case tôi không chắc nhất là việc `a-0008` vẫn bị gom vào cluster `c-000-000`.**

### Vì sao
- Trong `alerts_sample.jsonl`, `a-0008` có timestamp:
  - `2026-07-12T09:43:18Z`
- Trong khi toàn bộ alert còn lại của incident chính nằm ở:
  - `2026-06-12T09:42:01Z` → `2026-06-12T09:48:30Z`
- Nghĩa là `a-0008` **lệch đúng 1 tháng**, nhưng `cluster_summary.json` hiện tại vẫn cho nó vào cluster chính 20/20 alerts.

### Điều này làm tôi không chắc ở điểm nào
- Nếu timestamp của `a-0008` là **đúng**, thì clustering hiện tại đang **gom sai theo thời gian**
- Nếu clustering là **đúng**, thì có khả năng:
  - dữ liệu timestamp của `a-0008` bị dirty / typo
  - hoặc notebook/code đã normalize / bỏ qua một phần điều kiện thời gian
- Vì tôi chỉ thấy output cuối cùng chứ chưa audit lại từng cell xử lý trong notebook, tôi không dám khẳng định 100% lỗi nằm ở data hay logic.

### Kết luận
Case chưa chắc nhất không còn là một cluster riêng như lần trước, mà là **sự bất nhất giữa raw alert `a-0008` và kết quả clustering**. Đây là dấu hiệu cho thấy pipeline correlation vẫn cần thêm data validation trước khi dùng cho quyết định tự động.

---

## Tổng kết ngắn

- **Cluster chính:** `c-000-000`
- **Số cluster hiện tại:** `1`
- **Root cause service tôi tin hơn:** `payment-svc`
- **Root cause class tôi tin hơn:** `connection_pool_exhaustion`
- **Có deploy auto-remediation theo output hiện tại không?** **Không**
- **Case chưa chắc:** alert `a-0008` bị gom vào cluster chính dù timestamp lệch 1 tháng