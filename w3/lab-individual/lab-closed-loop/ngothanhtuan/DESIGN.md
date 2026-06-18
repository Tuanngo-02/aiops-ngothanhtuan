# Thiết kế hệ thống Closed-Loop Orchestrator

## 1. Lựa chọn Decision Engine (Rule-based hay LLM-based)
Tôi chọn sử dụng **Rule-based (Dựa trên luật định sẵn)** kết hợp với cơ chế **Registry Validation**.
- **Lý do**: Bài toán yêu cầu xử lý các cảnh báo có pattern rõ ràng (như HighLatency, HighErrorRate, InstanceDown). Việc ánh xạ trực tiếp từ `alertname` sang runbook bằng file config (Rule-based) đảm bảo tính tất định, độ trễ cực thấp (gần như tức thời), và không bị phụ thuộc vào tính khả dụng của API bên ngoài (như Anthropic API).
- **Đánh đổi**: Rule-based thiếu tính linh hoạt khi gặp các cảnh báo hoàn toàn mới không có trong config, trong khi LLM có thể phân tích ngữ cảnh để đề xuất action. Tuy nhiên, bằng cách bổ sung cơ chế kiểm tra (Registry Validation), hệ thống khắc phục triệt để vấn đề "hallucination" (ảo giác) của LLM – nếu dùng LLM nhưng script do LLM tạo ra không có trong registry, nó vẫn bị chặn. Trong kịch bản này, rule-based là đủ đáp ứng 100% yêu cầu nghiệm thu và stress test.

## 2. Cấu hình Blast-radius
- **max_actions_per_minute**: `5`. Lý do: Trong môi trường e-commerce, hệ thống có thể gặp đợt bùng nổ cảnh báo. Cho phép 5 action/phút giúp xử lý song song nhiều cụm dịch vụ lỗi cùng lúc, nhưng cũng đủ nhỏ để hệ thống không bị quá tải do restart liên tục toàn hệ thống.
- **max_restarts_per_service_per_hour**: `3`. Lý do: Nếu một service phải restart quá 3 lần/giờ, có nghĩa là việc restart không giải quyết triệt để vấn đề cốt lõi (như code lỗi, database sập). Việc ngưng restart để escalate cho con người xử lý sẽ ngăn chặn thảm họa gián đoạn (cascade failures) do downtime restart cộng dồn.

## 3. Verify step: Metric, Threshold và Timeout
- **Metric**: Phụ thuộc vào `alertname` đã được lấy từ Alertmanager. Cụ thể:
    - `HighLatency`: Sử dụng truy vấn `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service))` để lấy P99 latency.
    - `HighErrorRate`: Sử dụng tỷ lệ lỗi `5xx / tổng request`.
    - `InstanceDown`: Truy vấn metric `up`.
- **Threshold**:
    - `HighLatency`: < 0.200 (200ms)
    - `HighErrorRate`: < 0.01 (1%)
    - `InstanceDown`: == 1.0 (UP)
- **Timeout & Poll Interval**: Timeout là 60 giây, khoảng thời gian poll là mỗi 5 giây. 
- **Yêu cầu (Required Successes)**: Hệ thống phải nhận được 3 lần liên tiếp kết quả đạt ngưỡng (tương đương 15s trạng thái ổn định liên tục) thì mới coi là Verify thành công, giúp chống lại hiện tượng chập chờn (flapping).

## 4. Circuit Breaker
- **Cơ chế**: Mỗi service có một bộ đếm `failure_count`. Bộ đếm này tăng lên 1 khi action (runbook execute) thất bại hoặc verify thất bại.
- **Ngưỡng**: Nếu `failure_count >= 3`, Circuit Breaker chuyển sang trạng thái `OPEN` (ngắt tự động hóa hoàn toàn cho service đó).
- **Reset**: Tự động reset bộ đếm về `0` nếu Verify thành công (trường hợp dịch vụ đã tự hồi phục hoặc được vá thủ công và hoạt động ổn định). Nếu đang ở trạng thái `OPEN`, hiện tại chỉ có thể reset thủ công bằng cách khởi động lại orchestrator hoặc thông qua API can thiệp (chưa public), vì khi đã `OPEN`, hệ thống không còn tin tưởng các hành động tự động nữa và cần con người can thiệp.
