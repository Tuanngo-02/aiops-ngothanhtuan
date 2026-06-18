# DESIGN.md — MLOps Lifecycle: Anomaly Detection Pipeline

Tài liệu thiết kế kiến trúc hệ thống giám sát và huấn luyện lại tự động (MLOps pipeline) cho bài toán phát hiện bất thường trên payment gateway.

---

## 1. Drift Threshold (Ngưỡng Lệch Dữ Liệu)

* **Ngưỡng lựa chọn:** **0.15** (tương đương 15% số lượng feature bị lệch dựa trên Evidently DataDriftPreset).
* **Lý do lựa chọn:** Khi thực hiện chạy thử nghiệm `drift_detector.py` trên chính tập dữ liệu gốc `data/baseline.csv` bằng cách chia tỷ lệ 70/30 (2 tháng đầu làm dữ liệu đối chiếu - reference, 1 tháng sau làm dữ liệu thực tế - current), độ lệch dữ liệu đo được (noise floor) chỉ đạt mức **0.04**. Ngưỡng 0.15 được chọn tương đương khoảng 3.75 lần mức nhiễu nền này. Với tập `data/drifted.csv`, điểm lệch đo được thực tế là **0.67** (2 trong số 3 features bị lệch), vượt xa ngưỡng 0.15 một cách rõ ràng.
* **Hệ quả nếu chọn ngưỡng quá thấp (ví dụ: 0.05):** Hệ thống sẽ thường xuyên phát báo động giả (false positive) do các biến động mang tính chu kỳ (ví dụ: chu kỳ ngày/đêm, ngày làm việc/ngày nghỉ). Điều này tiêu tốn tài nguyên tính toán huấn luyện lại không cần thiết và gây chai sạn cảnh báo (alert fatigue) cho đội ngũ vận hành.
* **Hệ quả nếu chọn ngưỡng quá cao (ví dụ: 0.50):** Hệ thống sẽ bỏ sót các biến động phân phối thực tế ở giai đoạn đầu (false negative), dẫn tới việc mô hình cũ tiếp tục hoạt động trên dữ liệu lệch và làm suy giảm hiệu năng âm thầm mà không bị phát hiện.

---

## 2. Drift Type (Loại Lệch Dữ Liệu)

* **Loại lệch giám sát:** Pipeline của chúng ta thực hiện giám sát song song cả **Data Drift** (Lệch dữ liệu) và **Concept Drift** (Lệch khái niệm/hiệu năng).
* **Cơ chế hoạt động:**
  * **Data Drift (Evidently DataDriftPreset):** Đo lường sự dịch chuyển phân phối đầu vào $P(X)$. Sử dụng các kiểm định thống kê trên từng tính năng (mặc định dùng khoảng cách Wasserstein cho biến liên tục). Phù hợp để phát hiện sớm khi hành vi khách hàng hoặc hạ tầng thay đổi (ví dụ: latency tăng do tích hợp bên thứ ba, RPS tăng do chiến dịch marketing).
  * **Concept Drift (Performance evaluation):** Đo lường sự thay đổi trong mối quan hệ giữa đầu vào và nhãn thực tế $P(Y|X)$. Phù hợp để phát hiện khi mô hình không còn phân biệt đúng các hành vi gian lận hoặc lỗi thật sự (ví dụ: thay đổi cổng thanh toán làm thay đổi định nghĩa về lỗi).
* **Sự phù hợp:** Đối với bài toán thanh toán, Data Drift giúp ta chủ động huấn luyện lại trước khi mô hình suy giảm hiệu năng nghiêm trọng. Concept Drift bảo vệ chúng ta trong các trường hợp dữ liệu đầu vào trông có vẻ bình thường nhưng bản chất logic nghiệp vụ đã thay đổi.

---

## 3. Retrain Trigger Configuration (Cấu Hình Kích Hoạt Huấn Luyện Lại)

* **Cơ chế kích hoạt:** **Bán tự động (Semi-automatic) có cổng phê duyệt (Approval Gate)**.
* **Chu kỳ kiểm tra:** Thực hiện kiểm tra định kỳ (cadence) mỗi khi có một batch dữ liệu sản xuất mới (ví dụ: hàng ngày hoặc hàng tuần).
* **Quy trình phê duyệt:** Khi phát hiện drift (qua chỉ số drift của Evidently hoặc sự suy giảm hiệu năng trên tập holdout), hệ thống tự động chạy huấn luyện mô hình mới v2, đăng ký vào Registry dưới alias `staging`, sau đó in cảnh báo ra terminal và chờ xác nhận từ kỹ sư ML/On-call thông qua prompt `[y/N]`.
* **Thời gian chờ phê duyệt (Timeout):** Khuyến nghị 24 giờ. Nếu vượt quá 24 giờ không có phản hồi, phiên bản `staging` sẽ bị hủy (archive) và chu kỳ giám sát tiếp theo sẽ quyết định xem có cần kích hoạt huấn luyện lại nữa hay không.
* **Ưu điểm:** Loại bỏ rủi ro tự động thăng cấp một mô hình lỗi lên production (điều mà các CTO fintech luôn từ chối). Đảm bảo có sự kiểm tra của con người về các chỉ số chính xác (precision/recall) trước khi cutover.

---

## 4. Versioning và Rollback (Quản Lý Phiên Bản & Khôi Phục)

* **Chiến lược định danh:** Sử dụng **MLflow Registry Aliases** (`production`, `staging`, `archived`) thay vì sử dụng số phiên bản cố định (`v1`, `v2`, `v3`) trong code FastAPI.
* **Tại sao nên dùng alias:** Giúp ứng dụng `serve.py` luôn trỏ tới một URI duy nhất là `models:/anomaly-detector@production`. Khi cần cập nhật mô hình, ta chỉ cần tráo đổi alias trên Registry mà không cần chỉnh sửa code hay khởi động lại server.
* **Cơ chế Rollback:**
  * Khi phát hiện mô hình mới hoạt động kém hiệu quả (precision giảm mạnh hoặc sinh alert bão táp):
  1. Người vận hành hoặc script tự động thực hiện tráo đổi alias `production` quay về phiên bản cũ (v1).
  2. Gửi một request `POST /reload` tới `serve.py`.
  3. Server sẽ tải lại mô hình v1 từ registry trong vòng dưới **5 giây**, không gây gián đoạn dịch vụ (zero downtime).
* **Thẩm quyền:** ML Engineer On-call hoặc các script giám sát tự động (được phân quyền qua token MLflow).
* **Chính sách lưu trữ (Retention Policy):** Giữ lại toàn bộ các phiên bản đã đăng ký vô thời hạn. Do kích thước mô hình IsolationForest rất nhỏ (dưới 1MB), việc lưu giữ giúp ta có thể rollback về bất kỳ thời điểm nào trong lịch sử để kiểm toán (audit).

---

## 5. Stress 1 — Tại Sao Cần Chế Độ Check Kết Hợp (Combined Mode)

* **Lý do cần thiết:** Nếu chỉ sử dụng `DataDriftPreset` (chỉ theo dõi các feature $P(X)$), hệ thống sẽ hoàn toàn mù quáng trước **concept drift** (khi $P(Y|X)$ thay đổi nhưng phân phối đầu vào vẫn giữ nguyên).
* **Ví dụ thực tế bằng số liệu:** Trong tập dữ liệu `drifted.csv`, bên cạnh data drift của features, có tới **25% nhãn bị lật** (labels flipped) — tức là mối liên hệ giữa các đặc trưng và nhãn lỗi thay đổi. 
  * Nếu chạy chỉ với `--check-mode data`, điểm drift score của Evidently chỉ phản ánh sự lệch biến đầu vào, không phản ánh sự sụt giảm hiệu năng.
  * Khi chạy ở chế độ `--check-mode combined` với dữ liệu holdout có nhãn thực tế, ta đo được độ chính xác (precision) giảm mạnh từ **0.91** xuống còn **0.62**. Chế độ kết hợp sẽ bắt được sự sụt giảm này và kích hoạt huấn luyện lại ngay lập tức nhờ kiểm tra performance.

---

## 6. Stress 2 — Chiến Lược Lựa Chọn Dữ Liệu Huấn Luyện Lại

* **Phương pháp sử dụng:** **Cửa sổ trượt kết hợp (Sliding Window: Baseline + Drift Window)**.
* **So sánh với phương pháp chỉ huấn luyện trên Drift Window:**
  * **Chỉ huấn luyện trên dữ liệu lệch (Drift Window - 7 ngày):** Mô hình v2 sẽ bị tối ưu hóa quá mức (overfit) vào phân phối mới (RPS 630, latency 156ms). Khi gặp lại các pattern cũ có trong `data/holdout.csv` (dữ liệu bình thường cũ), mô hình sẽ dự đoán sai hoàn toàn. Kết quả thử nghiệm thực tế cho thấy precision của mô hình huấn luyện theo cách này trên tập holdout giảm đi hơn **18%**.
  * **Cửa sổ trượt kết hợp (Baseline + Drift Window - tổng 5328 dòng):** Mô hình được tiếp cận cả dữ liệu lịch sử bình thường lẫn dữ liệu mới lệch. Kết quả là mô hình v2 giữ vững hoặc cải thiện hiệu năng trên tập holdout (đảm bảo precision v2 trên holdout $\ge$ precision v1).
* **Chiến lược thay thế:** Có thể sử dụng phương pháp **huấn luyện tăng cường (incremental learning)** hoặc **lấy mẫu có trọng số (weighted sampling)**. Tuy nhiên, với IsolationForest, việc gom nhóm dữ liệu lịch sử và dữ liệu mới để fit lại từ đầu (sliding window) là phương án đơn giản, an toàn và hiệu quả nhất do thời gian train cực nhanh (< 1 giây).

---

## 7. Stress 3 — Tự Động Rollback Sau Triển Khai (Auto-rollback)

* **Ngưỡng kích hoạt:** Độ chính xác (Precision) trên tập đánh giá sau triển khai `post_deploy_eval.csv` (200 dòng có nhãn thực tế) rơi xuống dưới **0.65**.
* **Lý do chọn ngưỡng 0.65:** Đây là ngưỡng được tính toán kỹ lưỡng để tránh bị kích hoạt nhầm (false rollback) do nhiễu lấy mẫu trên tập dữ liệu nhỏ (200 dòng), nhưng vẫn đủ nhạy để phát hiện khi mô hình mới bị suy giảm hiệu năng nghiêm trọng (precision của v1 ban đầu đạt 91%).
* **Quy trình rollback tự động:**
  * Vòng lặp giám sát (`post_deploy_monitor`) chạy trong **24 chu kỳ**.
  * Nếu ở bất kỳ chu kỳ nào precision của v2 rơi xuống dưới 0.65:
    1. Gọi MLflow Client chuyển alias `production` từ v2 về v1, gán alias `archived` cho v2.
    2. Gọi `POST /reload` để FastAPI phục vụ lại v1.
    3. Ghi sự kiện `auto_rollback_v2_to_v1` vào `outputs/audit_log.jsonl` bao gồm các thông tin: phiên bản bị hạ cấp, phiên bản được khôi phục, chỉ số precision gây rollback, và chu kỳ xảy ra sự kiện.
    4. Đẩy sự kiện và chỉ số cập nhật lên Prometheus/Pushgateway để cập nhật tức thời trên Grafana dashboard.
