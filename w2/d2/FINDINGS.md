# FINDINGS

## 1) Cluster chính: root cause là gì + lý do

**Cluster chính là `c-000-000`** vì nó chứa **19/20 alerts**, trải rộng trên nhiều service trong khoảng thời gian `2026-06-12T09:42:01Z` → `2026-06-12T09:48:30Z`.

**Root cause hợp lý nhất: `payment-svc` với pattern `connection_pool_exhaustion`**, dù file `results/rca_output.json` đang dự đoán `checkout-svc / infinite_retry`.

### Lý do
- **Tín hiệu sớm nhất xuất hiện ở `payment-svc`**:
  - `db_connection_pool_used_ratio` warn `0.85 > 0.80` rồi crit `0.99 > 0.95`, sau đó lên `1.00`
  - `latency_p99_ms` crit `1840 > 800`
  - `error_rate` tăng từ warn lên crit
- **Triệu chứng ở `checkout-svc` là downstream symptom**, không phải tín hiệu gốc:
  - có alert `downstream_payment_error_rate`
  - sau đó mới thấy `latency_p99_ms` và `request_drop_rate`
- **`edge-lb` phù hợp với propagation ở tầng ngoài**:
  - `upstream_5xx_rate` và `p99_latency_ms` tăng sau khi payment/checkout đã lỗi
  - `services.json` ghi rõ `edge-lb` là entry point, alert tại đây thường là downstream propagation
- **`notification-svc` backlog cũng là hậu quả dây chuyền**
  - queue lag/depth tăng muộn hơn
  - topology note nói Kafka/notification là async layer, không phải nơi gây block checkout
- **Lịch sử incident khớp rất mạnh với `payment-svc / connection_pool_exhaustion`**
  - `INC-2025-11-08`: payment-svc leak DB pool, checkout bị cascade, notification queue backlog
  - `INC-2026-05-10`: lặp lại đúng pattern connection pool exhaustion
- Ngay trong `incidents_history.json` cũng có note của trainer rằng **scenario chính match closest với `INC-2025-11-08`**.

### Kết luận
`results/rca_output.json` đang **under-call** hoặc **mis-rank** root cause khi chọn `checkout-svc`. Nếu nhìn toàn bộ dữ liệu trong `w2/d2`, root cause đáng tin hơn là:

**`payment-svc` → `connection_pool_exhaustion`**

---

## 2) Confidence — có dám deploy auto-remediation dựa trên output này không?

**Không nên deploy auto-remediation trực tiếp dựa trên output hiện tại.**

### Lý do
- Output RCA cho cluster chính có **confidence chỉ `0.43`**, khá thấp.
- Quan trọng hơn, **kết luận của output có dấu hiệu sai root cause**:
  - output chọn `checkout-svc / infinite_retry`
  - nhưng raw alerts + topology + incident history lại nghiêng mạnh về `payment-svc / connection_pool_exhaustion`
- Nếu auto-remediation theo output hiện tại, hệ thống có thể:
  - thêm circuit breaker / cap retry ở `checkout-svc`
  - trong khi vấn đề thật là pool DB ở `payment-svc`
- Đây là loại remediation có thể **làm giảm symptom nhưng không xử lý nguyên nhân gốc**, thậm chí làm diagnosis chậm hơn.

### Đánh giá thực tế
- **Auto-remediation fully automatic:** **không dám deploy**
- **Human-in-the-loop / approval gate:** **có thể dùng**
- **Safe automation dạng low-risk** (chỉ enrich ticket, attach runbook, tăng priority, page đúng team): **nên dùng**

---

## 3) 1 case mà không chắc — vì sao

**Case không chắc nhất: cluster `c-001-000`.**

### Vì sao
- Cluster này chỉ có **1 alert duy nhất**:
  - `payment-svc | latency_p99_ms | crit`
- Dù `results/rca_output.json` gán:
  - root cause: `payment-svc`
  - class: `connection_pool_exhaustion`
  - confidence: `0.71`
- Nhưng với **chỉ 1 tín hiệu latency**, chưa đủ để kết luận chắc là connection pool exhaustion, vì nó cũng có thể đến từ:
  - thread starvation
  - downstream bank/API chậm
  - network issue
  - DB lock/contention
  - cold start / deploy regression
- Không có tín hiệu phụ trợ như:
  - `db_connection_pool_used_ratio`
  - `error_rate`
  - checkout cascade
  - edge-lb 5xx
  - notification backlog

### Kết luận
`c-001-000` là case mà tôi **không chắc**, vì evidence quá mỏng và RCA đang suy luận nhiều từ lịch sử hơn là từ observability signal hiện tại.

---

## Tổng kết ngắn

- **Cluster chính:** `c-000-000`
- **Root cause tôi tin hơn:** `payment-svc / connection_pool_exhaustion`
- **Có deploy auto-remediation theo output hiện tại không?** **Không**
- **Case không chắc:** `c-001-000`, vì chỉ có 1 alert latency nên evidence không đủ mạnh