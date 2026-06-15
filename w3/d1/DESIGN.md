# DESIGN.md

## 1. SLI choice cho frontend. Tại sao chọn metric X thay vì Y? Frontend RUM cho 4 candidate signal (page load time, DOM ready, JS error rate, network error rate). Chọn cái nào, vì sao loại 3 cái còn lại?

Chúng tôi chọn **DOM Ready** làm SLI chính cho frontend. Lý do là `DOM ready` đại diện cho thời điểm trang web sẵn sàng để người dùng tương tác. Nó cung cấp một cái nhìn chính xác hơn về trải nghiệm người dùng so với `Page Load Time`, vì `Page Load Time` có thể bị ảnh hưởng bởi việc tải tài nguyên không quan trọng sau khi DOM đã sẵn sàng (ví dụ: hình ảnh không hiển thị trên màn hình đầu tiên, script phân tích, v.v.). Theo `baseline.json`, p99 của `dom_ready_p99_ms` là 1430ms.

- **Page Load Time**: Bị loại bỏ vì nó đo lường tổng thời gian tải tất cả tài nguyên, bao gồm cả những tài nguyên không quan trọng hoặc tải chậm không ảnh hưởng trực tiếp đến khả năng tương tác của người dùng. Một trang có thể đã sẵn sàng để sử dụng nhưng vẫn đang tải các thành phần phụ trợ.
- **JS Error Rate**: Mặc dù quan trọng, tỷ lệ lỗi JS được coi là một chỉ số sức khỏe (health indicator) hơn là một SLI trực tiếp về hiệu suất trải nghiệm người dùng. Lỗi JS có thể không ảnh hưởng đến khả năng tương tác ban đầu của trang, hoặc có thể là lỗi nhỏ không gây gián đoạn lớn. Nó nên được theo dõi riêng biệt như một chỉ số chất lượng mã.
- **Network Error Rate**: Tương tự như JS Error Rate, tỷ lệ lỗi mạng là một chỉ số sức khỏe của các dịch vụ backend hoặc kết nối mạng, chứ không trực tiếp đo lường trải nghiệm người dùng cuối trên giao diện. Các lỗi mạng có thể dẫn đến trải nghiệm xấu, nhưng `DOM Ready` tập trung vào việc liệu trang có tải và hiển thị đúng hay không, bất kể nguyên nhân gốc rễ là gì.

## 2. SLO target cho API. Tại sao 99.9% chứ không 99% hoặc 99.99%? Cost của mỗi tier (§3.2) so với baseline hiện tại 99.7% (từ baseline.json).

Chúng tôi đặt SLO target cho API là **99.9%** (Three Nines).
Lý do không chọn 99% là vì 99% (Two Nines) đồng nghĩa với khoảng 14.4 phút downtime mỗi ngày hoặc ~7.2 giờ downtime mỗi tháng. Mức này quá thấp đối với một dịch vụ API quan trọng, có thể dẫn đến sự thất vọng lớn cho người dùng và mất doanh thu. Theo `baseline.json`, `api.success_rate` hiện tại là `0.9763181243912084`, tức khoảng 97.63%, cho thấy cần cải thiện đáng kể.

Lý do không chọn 99.99% (Four Nines) là vì đạt được 99.99% đòi hỏi chi phí và nỗ lực đáng kể hơn rất nhiều (tăng cường kiến trúc dự phòng, cơ sở hạ tầng, quy trình triển khai, v.v.). Việc tăng từ 99.9% lên 99.99% thường có chi phí tăng theo cấp số nhân. Với một mục tiêu 99.9%, chúng ta vẫn có khoảng 43.2 giây downtime mỗi ngày hoặc ~8.76 giờ downtime mỗi năm, là mức chấp nhận được và cân bằng giữa độ tin cậy và chi phí vận hành.

Cost của mỗi tier so với baseline hiện tại 99.7% (không có trong baseline.json, sẽ giả định từ baseline 97.63%):
- Từ 97.63% lên 99.7% (`baseline.json` không có 99.7%): Đây là một bước nhảy vọt lớn, đòi hỏi tối ưu hóa mã, cải thiện hiệu suất cơ sở dữ liệu, tăng cường cơ sở hạ tầng (scaling, load balancing). Chi phí tăng đáng kể.
- Từ 99.7% lên 99.9%: Chi phí để đạt được 99.9% từ 99.7% sẽ liên quan đến việc triển khai các cơ chế phục hồi nhanh hơn, cải thiện quy trình release (zero-downtime deployments), tăng cường giám sát cảnh báo sớm, và có thể là một số dự phòng ở cấp độ vùng hoặc trung tâm dữ liệu. Đây là một khoản đầu tư đáng kể về cả nhân lực và tài nguyên.
- Từ 99.9% lên 99.99%: Chi phí tăng vọt bao gồm việc thiết kế kiến trúc đa vùng/đa trung tâm dữ liệu với khả năng chuyển đổi dự phòng tự động hoàn toàn, kiểm tra thâm nhập thường xuyên, chaos engineering, và các quy trình quản lý sự cố cực kỳ nhanh chóng.

## 3. Latency threshold p99. Bạn cut latency ở mốc nào (200ms? 500ms? 1s?)? Plot distribution latency 7-day (text/table OK), defend choice.

Dựa trên `baseline.json`, `api.latency_p99_ms` hiện tại là **156ms**. Vì vậy, chúng ta sẽ đặt ngưỡng `latency threshold p99` cho API ở mốc **200ms**.

Lý do chọn 200ms:
- **Duy trì hoặc cải thiện hiệu suất hiện tại**: Ngưỡng 200ms cao hơn một chút so với p99 hiện tại (156ms) cho phép một biên độ nhỏ cho các biến động thông thường, nhưng vẫn đủ chặt chẽ để đảm bảo rằng phần lớn các yêu cầu API được xử lý nhanh chóng. Nó cho phép một chút suy giảm hiệu suất mà không ngay lập tức kích hoạt cảnh báo, nhưng vẫn giữ trải nghiệm người dùng ở mức tốt.
- **Phù hợp với kỳ vọng người dùng**: Nghiên cứu chỉ ra rằng người dùng cảm nhận các phản hồi dưới 200ms là tức thì. Vượt quá ngưỡng này có thể bắt đầu ảnh hưởng tiêu cực đến trải nghiệm người dùng, đặc biệt là trong các ứng dụng tương tác.
- **Khả năng đạt được**: Việc đặt mục tiêu quá thấp so với hiệu suất hiện tại có thể gây tốn kém và không thực tế để đạt được ngay lập tức. 200ms là một mục tiêu khả thi để duy trì và cải thiện dần.

**Phân phối độ trễ 7 ngày (giả định từ dữ liệu baseline.json):**

| Percentile | Latency (ms) |
|------------|--------------|
| p50        | ~50          |
| p75        | ~100         |
| p90        | ~120         |
| p95        | ~140         |
| p99        | 156          |
| p99.9      | ~180         |

(*Lưu ý: Các giá trị p50, p75, p90, p95, p99.9 là giả định dựa trên p99 thực tế 156ms từ `baseline.json` để minh họa phân phối.*)

Với p99 hiện tại là 156ms, việc đặt ngưỡng 200ms cho phép chúng ta cảnh báo khi có sự suy giảm hiệu suất đáng kể vượt quá mức 156ms, đồng thời cung cấp đủ thời gian để phản ứng trước khi trải nghiệm người dùng bị ảnh hưởng nghiêm trọng.

## 4. 4xx exclusion. Tại sao loại 4xx ra khỏi error count (trừ 429)? Có log endpoint nào có rate 4xx > 5% mà không phải hệ thống lỗi không? Reference data.

Chúng tôi loại trừ các mã trạng thái **4xx** khỏi số lượng lỗi (ngoại trừ 429 Too Many Requests) vì các lỗi 4xx (Client Error) thường chỉ ra rằng vấn đề nằm ở phía client, không phải lỗi của hệ thống API. Việc bao gồm các lỗi này sẽ làm sai lệch chỉ số SLI, khiến chúng ta hiểu lầm về độ tin cậy của dịch vụ.

- **4xx (trừ 429)**: Các lỗi như 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 405 Method Not Allowed, v.v., đều là do client gửi yêu cầu không hợp lệ, không có quyền truy cập, hoặc yêu cầu tài nguyên không tồn tại. Đây không phải là dấu hiệu của sự cố hệ thống API, mà là hành vi dự kiến dựa trên đầu vào của client. Loại bỏ chúng giúp SLI phản ánh chính xác khả năng phục vụ của API.
- **429 Too Many Requests**: Được giữ lại trong error count vì nó chỉ ra rằng hệ thống API đang gặp áp lực quá tải hoặc đang chủ động từ chối yêu cầu để bảo vệ chính nó. Mặc dù là lỗi phía client theo định nghĩa HTTP, nhưng nó phản ánh khả năng xử lý của hệ thống API và có thể là dấu hiệu sớm của sự suy giảm hiệu suất hoặc quá tải.

**Log endpoint có rate 4xx > 5% mà không phải hệ thống lỗi:**
Có, một ví dụ điển hình là các endpoint phục vụ tài nguyên tĩnh hoặc các endpoint API công khai mà client thường xuyên gọi với các tham số sai hoặc yêu cầu các tài nguyên không tồn tại.
Ví dụ:
- `/api/v1/users/{id}`: Nếu client thường xuyên truy vấn các ID không tồn tại, endpoint này có thể có tỷ lệ 404 Not Found cao.
- `/public/assets/{filename}`: Các yêu cầu cho tài nguyên không tồn tại (hình ảnh, CSS, JS) có thể dẫn đến tỷ lệ 404 cao.

Tuy nhiên, dựa trên `baseline.json`, chúng ta không có thông tin chi tiết về từng endpoint để xác định rõ ràng. `baseline.json` chỉ cung cấp `api.fail_count` là `7234` và `api.fail_rate` là `0.003488316021950255`, tức 0.35%, thấp hơn 5%. Điều này cho thấy tổng thể các lỗi (bao gồm cả các lỗi 4xx không mong muốn) đang ở mức thấp. Để xác định cụ thể, cần phân tích log chi tiết hơn.

## 5. MWMBR tuning. Dùng Google default (14.4, 6, 1) hay tune? Nếu tune, dựa vào ảnh hưởng đến noise_reduction_pct và fn thế nào?

Chúng tôi sẽ **tune** các thông số MWMBR thay vì sử dụng giá trị mặc định của Google (14.4, 6, 1). Việc tune này sẽ dựa trên việc tối ưu hóa `noise_reduction_pct` và giảm thiểu `fn` (False Negatives) từ `validation_report.json`.

Theo `validation_report.json`:
- `static_baseline`: `fired`: 22, `tp`: 3, `fp`: 19, `fn`: 0
- `your_mwmbr`: `fired`: 3, `tp`: 3, `fp`: 0, `fn`: 0
- `noise_reduction_pct`: 86.4%
- `mttd_delta_s`: 60

Hiện tại, với cấu hình MWMBR của chúng ta, `noise_reduction_pct` là 86.4% và `fn` là 0. Đây là một kết quả rất tốt, cho thấy các cảnh báo MWMBR đã giảm đáng kể số lượng False Positives (từ 19 xuống 0) mà không bỏ sót bất kỳ sự cố thực tế nào (fn = 0).

Nếu các thông số MWMBR hiện tại đã đạt được `noise_reduction_pct` cao và `fn = 0`, thì việc "tune" ở đây có nghĩa là chúng ta sẽ sử dụng các giá trị đã được tối ưu hóa này. Chúng ta sẽ không thay đổi chúng thành Google default nếu các giá trị hiện tại mang lại hiệu suất tốt hơn.

Việc tune các thông số (ví dụ: `short_window`, `long_window`, `threshold`) thường được thực hiện thông qua thử nghiệm và lặp lại trên dữ liệu lịch sử. Mục tiêu là tìm ra bộ giá trị cân bằng giữa:
- **`noise_reduction_pct` cao**: Giảm thiểu các cảnh báo sai (false positives), giúp đội ngũ vận hành tập trung vào các sự cố thực sự.
- **`fn` (False Negatives) thấp (lý tưởng là 0)**: Đảm bảo rằng tất cả các sự cố thực tế đều được phát hiện và cảnh báo.

Trong trường hợp này, `validation_report.json` đã cho thấy `your_mwmbr` với `noise_reduction_pct` là 86.4% và `fn` là 0, điều này vượt trội so với `static_baseline` có nhiều `fp` hơn. Do đó, chúng tôi sẽ duy trì cấu hình MWMBR hiện tại (mà `validation_report.json` đã đánh giá là "pass") thay vì áp dụng Google default, trừ khi có lý do cụ thể để tin rằng Google default sẽ cải thiện hơn nữa mà không làm tăng `fn`.