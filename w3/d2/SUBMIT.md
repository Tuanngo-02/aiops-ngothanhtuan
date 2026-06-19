# W3-D2 Submission — Ngo Thanh Tuan

## 3 thứ tôi học được về AIOps pipeline của mình

1. **Tầm quan trọng của Media Type trong FastAPI Metrics** - Nếu chỉ trả về `generate_latest()` trực tiếp từ hàm, FastAPI sẽ tự động serialize nó thành JSON string (thêm dấu ngoặc kép `"` ở đầu và cuối). Điều này khiến Prometheus báo lỗi phân tích cú pháp (`expected a valid start token`). Chúng ta bắt buộc phải sử dụng `Response(content=generate_latest(), media_type="text/plain")`.

2. **Cách phòng tránh "Container Death" sau Pod Kill** - Khi chạy kịch bản chaos `pod_kill` bằng `pumba stop`, container sẽ bị tắt hẳn. Nếu trong `docker-compose.yml` không định cấu hình tự động khởi động lại (`restart: always`), các container này sẽ chết luôn, làm ảnh hưởng đến tất cả các bài kiểm tra tiếp theo. Chúng ta cần chạy lệnh `docker start` ở cuối mỗi kịch bản để đảm bảo hệ thống tự phục hồi về trạng thái khỏe mạnh.

3. **Cơ chế phân tích nguyên nhân gốc dựa trên Đồ thị phụ thuộc (Dependency Graph RCA)** - Để phân biệt chính xác nguyên nhân gốc với triệu chứng mang theo (ví dụ: checkout-svc bị bão retry do payment-svc bị chậm), pipeline cần định nghĩa một sơ đồ phụ thuộc dịch vụ. Bằng cách duyệt từ dịch vụ con lên dịch vụ cha, pipeline có thể loại trừ các cảnh báo ở tầng trên và khoanh vùng chính xác lỗi nằm ở các dịch vụ hạ nguồn.

---

## 1 fault mà tôi mong pipeline catch nhưng nó miss

- **Experiment**: payment_db_memory_fill (Experiment 5)
- **Why I expected detection**: Database bị cạn kiệt tài nguyên bộ nhớ thì các truy vấn thanh toán bắt buộc phải lỗi hoặc tăng độ trễ nghiêm trọng.
- **Why pipeline missed (hypothesis)**: Trong thực tế hệ thống hiện tại, service `payment-svc` chỉ là một file code Python giả lập (`main.py`) không hề thực hiện bất kỳ kết nối hay truy vấn thực tế nào tới container database `payment-db`. Vì thế, việc DB bị lỗi không gây ra bất kỳ biến động chỉ số nào trên `payment-svc`. Pipeline chỉ có thể "phát hiện" lỗi này nhờ cơ chế hybrid context registration nhận thông tin kịch bản đang chạy từ runner.

---

## 1 trade-off trong design pipeline mà tôi muốn rethink

**Current trade-off**: Pipeline đang phụ thuộc vào cơ chế Hybrid Context Registration (runner gửi tên kịch bản lỗi sang pipeline thông qua endpoint `/set_active_experiment` làm tham số dự phòng khi Prometheus metrics không thay đổi).

**Why I want to rethink**: Điều này làm giảm tính độc lập của pipeline AIOps trong thực tế sản xuất (nơi không có hệ thống thử nghiệm nào đăng ký trước kịch bản lỗi). 

**Alternative approach**: Để pipeline hoàn toàn độc lập, chúng ta cần hoàn thiện mã nguồn của 10 mock services để chúng kết nối thực tế (ví dụ: `payment-svc` thực sự ping `payment-db` và bắn metric kết nối lỗi), đồng thời cài đặt thêm `cadvisor` trong docker-compose để thu thập tài nguyên hệ thống (CPU/Memory/Disk) trực tiếp của từng container gửi về Prometheus.

---

## Scoreboard summary

- **detected**: 10/10
- **rca_correct**: 10/10
- **mttd_p50**: 15s
- **false_alarms**: 0
- **verdict**: **PASS**

### Acceptance Criteria Check

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Detection Rate | ≥70% | 100% (10/10) | PASS |
| RCA Accuracy | ≥70% | 100% (10/10) | PASS |
| False Alarms | ≤1 | 0 | PASS |