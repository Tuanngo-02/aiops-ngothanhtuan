# W3-D1 Submission — Ngô Thanh Tuấn

## 3 thứ tôi học được
1.  **Tầm quan trọng của việc lựa chọn SLI chính xác**: Tôi học được cách phân tích các tín hiệu RUM (Real User Monitoring) để chọn ra SLI phù hợp nhất cho Frontend, cụ thể là `DOM Ready Time`. Điều này đảm bảo rằng chúng ta tập trung vào những gì thực sự ảnh hưởng đến trải nghiệm người dùng hơn là các metric tổng hợp có thể gây hiểu lầm như `Page Load Time`.
2.  **Cân bằng giữa độ tin cậy và chi phí trong SLO**: Tôi hiểu sâu hơn về việc thiết lập các mục tiêu SLO như 99.9% cho API không chỉ là một con số kỹ thuật mà còn là một quyết định kinh doanh. Việc tăng một "nine" đòi hỏi chi phí và nỗ lực tăng theo cấp số nhân, và mục tiêu 99.9% là một sự cân bằng tốt giữa độ tin cậy cao và chi phí vận hành hợp lý.
3.  **Tối ưu hóa cảnh báo với MWMBR**: Tôi đã thấy cách các tham số của MWMBR (Multi-Window, Multi-Burn-Rate) có thể được điều chỉnh để giảm đáng kể "noise" (false positives) trong hệ thống cảnh báo mà không làm tăng "false negatives". `validation_report.json` cho thấy việc tùy chỉnh MWMBR có thể mang lại hiệu quả cao hơn so với việc sử dụng các giá trị mặc định của Google.

## 1 thứ vẫn chưa rõ
Một điều tôi vẫn chưa rõ là cách xác định "cost" của mỗi tier SLO một cách định lượng rõ ràng hơn. Trong bài tập này, tôi đã mô tả chi phí một cách định tính (ví dụ: "chi phí tăng đáng kể", "chi phí tăng vọt"). Tuy nhiên, trong thực tế, việc có thể đưa ra các con số cụ thể về chi phí tài nguyên, nhân lực, và thời gian phát triển để đạt được mỗi tier SLO sẽ giúp đưa ra quyết định kinh doanh chính xác hơn.

## 1 trade-off trong SLO decision của tôi mà tôi không chắc
Trong quyết định về `SLO target cho API`, tôi đã chọn 99.9% thay vì 99.99%. Trade-off ở đây là việc chấp nhận một lượng downtime (khoảng 43.2 giây mỗi ngày) để tránh chi phí cực kỳ cao khi đạt được 99.99%. Tôi không chắc liệu mức 43.2 giây downtime hàng ngày này có thực sự chấp nhận được với tất cả các kịch bản kinh doanh hay không, đặc biệt nếu dịch vụ API đó phục vụ các giao dịch tài chính hoặc y tế, nơi ngay cả vài giây downtime cũng có thể gây ra hậu quả nghiêm trọng. Quyết định này đòi hỏi sự hiểu biết sâu sắc hơn về tác động kinh doanh của downtime ở các mức độ khác nhau.

## Validation report
- noise_reduction_pct: 86.4%
- mttd_delta_s: 60s
- false_negative: 0
- verdict: pass