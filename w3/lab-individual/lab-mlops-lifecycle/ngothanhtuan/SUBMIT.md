# SUBMIT.md — Bài Thu Hoạch: MLOps Lifecycle Lab

Dưới đây là phần trả lời chi tiết cho 5 câu hỏi phản định (reflection) dựa trên kiến trúc và mã nguồn của hệ thống đã triển khai.

---

## Câu 1: Drift threshold bạn chọn là bao nhiêu và tại sao? Bạn có xác minh ngưỡng đó với dữ liệu thực tế không?

* **Ngưỡng lựa chọn:** **0.15** (15% số lượng feature bị lệch).
* **Lý do lựa chọn:** Tôi đã chạy thử nghiệm kiểm tra drift trên chính tập dữ liệu `data/baseline.csv` bằng cách chia tỷ lệ 70% đầu làm dữ liệu tham chiếu (reference) và 30% sau làm dữ liệu hiện tại (current). Khi không có biến động thực sự, điểm drift đo được là **0.04** (đây là nhiễu nền bình thường của hệ thống). Tôi chọn ngưỡng 0.15, cao gấp 3.75 lần mức nhiễu này, nhằm tránh các cảnh báo giả do biến động thời tiết hoặc seasonal sinh ra hàng ngày.
* **Xác minh thực tế:** Khi chạy thử nghiệm với `data/drifted.csv` (dữ liệu sản xuất có biến động sau chiến dịch marketing), điểm drift thực tế đo được là **0.67** (2 trên 3 đặc trưng bị lệch rõ rệt là `latency_p99` và `rps`). Mức 0.67 vượt xa ngưỡng 0.15, xác nhận ngưỡng đã chọn hoạt động rất chính xác trên dữ liệu thực tế.

---

## Câu 2: Điều gì xảy ra nếu mô hình v2 sau khi huấn luyện lại hoạt động tệ hơn v1 trong thực tế? Pipeline của bạn xử lý trường hợp này như thế nào?

* **Cơ chế kiểm soát trước khi triển khai (Staging Gate):** 
  * Mô hình v2 sau khi train sẽ được ghi lại trong MLflow Registry dưới alias `staging`. Trước khi được thăng cấp, pipeline thực hiện đánh giá v2 trên tập dữ liệu kiểm thử `data/holdout.csv` và in ra kết quả precision/recall.
  * Pipeline cung cấp một **cổng phê duyệt thủ công (Approval Gate)** bằng cách hỏi người vận hành: `Promote staging → production? [y/N]`. Nếu kỹ sư ML phát hiện các chỉ số của v2 tệ hơn v1, họ có thể từ chối thăng cấp (chọn `N`).
* **Cơ chế tự động khôi phục sau triển khai (Auto-rollback):**
  * Nếu người dùng thăng cấp v2 hoặc truyền tham số `--auto-approve`, pipeline sẽ kích hoạt giám sát sau triển khai (`post_deploy_monitor`) trên tập dữ liệu thực tế `data/post_deploy_eval.csv` trong **24 chu kỳ**.
  * Nếu precision của v2 rơi xuống dưới **0.65** ở bất kỳ chu kỳ nào, hệ thống sẽ tự động thực hiện **auto-rollback**: hạ cấp v2 xuống `@archived`, khôi phục v1 về `@production`, gọi `POST /reload` để FastAPI phục vụ lại v1 tức thì, và ghi nhật ký chi tiết vào `outputs/audit_log.jsonl` dưới khóa sự kiện `auto_rollback_v2_to_v1`.

---

## Câu 3: Sự khác biệt giữa data drift và concept drift là gì? Loại nào được Evidently phát hiện trong bài lab này?

* **Sự khác biệt:**
  * **Data Drift (Lệch dữ liệu):** Là sự dịch chuyển phân phối xác suất của các đặc trưng đầu vào $P(X)$ trong khi mối quan hệ ánh xạ từ đặc trưng sang nhãn $P(Y|X)$ không thay đổi. Ví dụ: latency trung bình tăng do cấu hình mạng mới, nhưng định nghĩa về hành vi lỗi vẫn giữ nguyên.
  * **Concept Drift (Lệch khái niệm):** Là sự thay đổi trong mối quan hệ giữa đặc trưng đầu vào và nhãn thực tế $P(Y|X)$ trong khi phân phối đầu vào có thể không đổi nhiều. Ví dụ: cùng một mức latency 150ms trước đây là bình thường, nhưng nay trở thành lỗi nghiêm trọng do yêu cầu SLA mới của cổng thanh toán.
* **Evidently detect loại nào:** Trong bài lab này, gói `DataDriftPreset` của Evidently thực hiện phát hiện **Data Drift** thông qua các kiểm định thống kê trên dữ liệu đầu vào. Concept drift không được Evidently phát hiện trực tiếp do dữ liệu sản xuất không có sẵn nhãn. Tuy nhiên, trong pipeline cải tiến của chúng ta, chúng tôi đã sử dụng chế độ check kết hợp (`--check-mode combined`) để tính toán cả precision/recall trên dữ liệu có nhãn, giúp bắt được cả concept drift khi độ chính xác của mô hình suy giảm.

---

## Câu 4: Tại sao cơ chế blue-green swap lại quan trọng hơn việc thay thế trực tiếp file mô hình?

* **Rủi ro khi ghi đè file trực tiếp:**
  * Gây ra hiện tượng tranh chấp tài nguyên (race condition): Khi server FastAPI đang xử lý request đọc mô hình từ đĩa, cùng lúc đó script ghi đè file mô hình mới lên đĩa $\rightarrow$ Dẫn tới lỗi đọc file hỏng (corrupted read) làm server crash hoặc trả về kết quả lỗi.
  * Không có đường lui (rollback path): Phiên bản cũ đã bị ghi đè hoàn toàn, nếu mô hình mới hoạt động lỗi, ta không thể quay lại ngay lập tức mà phải chạy lại quá trình download/redeploy phức tạp.
* **Tầm quan trọng của Blue-Green Swap (qua MLflow Registry):**
  * **Không gián đoạn dịch vụ (Zero downtime):** Cả mô hình v1 và v2 đều tồn tại độc lập trong Registry. Khi swap alias, cổng `production` được chuyển hướng atomically từ v1 sang v2. Server FastAPI chỉ tải mô hình mới khi nhận lệnh `POST /reload`. Các request đang xử lý dở dang sẽ tiếp tục chạy với v1 một cách an toàn.
  * **Rollback tức thì:** Nếu v2 có vấn đề, chỉ cần tráo đổi alias trên Registry về v1 và gọi reload, mô hình cũ sẽ được nạp lại trong vòng chưa đầy **5 giây** mà không cần khởi động lại container hay chỉnh sửa code.

---

## Câu 5: Nếu bạn phải tự động hóa cổng phê duyệt (không cần con người phê duyệt), bạn sẽ sử dụng metric nào và ngưỡng bao nhiêu?

Nếu tự động hóa hoàn toàn cổng phê duyệt, tôi sẽ sử dụng tổ hợp 3 điều kiện sau trên tập dữ liệu kiểm tra holdout (được trích xuất từ phân phối mới nhất):

1. **Hiệu năng mô hình mới trên tập holdout:** Mô hình v2 phải có độ chính xác và độ phủ đạt ngưỡng tối thiểu:
   $$\text{Precision}_{v2} \ge 0.70 \quad \text{và} \quad \text{Recall}_{v2} \ge 0.70$$
   Điều này đảm bảo mô hình mới không gặp lỗi suy giảm nghiêm trọng.
2. **Hiệu năng so sánh giữa v2 và v1:** Hiệu năng của v2 không được thấp hơn v1 trên tập holdout:
   $$\text{Precision}_{v2} \ge \text{Precision}_{v1} - 0.02$$
   Cho phép sai số tối đa 2% để chấp nhận sự đánh đổi phân phối, nhưng không được sụt giảm sâu.
3. **Tỷ lệ bất thường được dự đoán (Anomaly Rate):** Tỷ lệ bất thường do v2 dự đoán trên tập dữ liệu mới phải nằm trong khoảng hợp lý:
   $$0.01 \le \text{Anomaly Rate}_{v2} \le 0.10$$
   Nếu tỷ lệ này quá thấp (dưới 1%), mô hình quá lỏng lẻo; nếu quá cao (trên 10%), mô hình quá nhạy cảm gây bão alert giả cho đội on-call.

Nếu thỏa mãn cả 3 điều kiện trên, hệ thống sẽ tự động thăng cấp v2 lên `production`. Nếu không, hệ thống sẽ gửi alert đỏ yêu cầu kỹ sư ML phê duyệt thủ công.
