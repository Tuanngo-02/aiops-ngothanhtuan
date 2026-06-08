# SUBMIT.md

### Câu 1: 

Trong bài này tôi chọn `gap_sec = 120`. Lý do là notebook đang dùng ngưỡng 120 giây trong hàm `session_groups`, và với bộ dữ liệu mẫu thì các alert của sự cố chính xảy ra khá dày trong khoảng từ `2026-06-12T09:42:01Z` đến `2026-06-12T09:48:30Z`. Mức 120 giây đủ rộng để giữ các alert liên tiếp trong cùng một phiên sự cố, nhưng vẫn đủ chặt để tách một alert xuất hiện quá xa về thời gian.

### Câu 2:

Tôi chọn `max_hop = 2` vì graph service cho thấy nhiều thành phần trong luồng checkout có quan hệ trực tiếp hoặc cách nhau 1–2 bước, ví dụ `edge-lb -> checkout-svc -> payment-svc` hoặc `checkout-svc -> notification-svc`. Ngưỡng 2 hop giúp gom các alert có liên quan vận hành mà không lan quá xa sang các service chỉ liên quan gián tiếp.

### Câu 3:

Tôi tạo giả định 1 alert khác với timestamp là `2026-07-12T09:43:18Z` 

Một alert ID bị “miss” theo nghĩa không match vào cluster lớn là `a-0008`. Thực ra nó vẫn tạo thành một cluster riêng (`c-001-000`), nhưng không nhập vào cluster chính gồm 19 alert. Nguyên nhân là timestamp của nó là `2026-07-12T09:43:18Z`, lệch hẳn một tháng so với phần còn lại ở `2026-06-12`. Vì vậy nó bị tách session trước cả khi xét topology. Dù fingerprint của nó giống các alert `payment-svc latency_p99_ms crit` khác, điều kiện thời gian đã chặn việc ghép cụm.

### Câu 4: 

Nếu có 10000 alert thay vì 20, code sẽ chậm nhất ở hai chỗ. Thứ nhất là `session_groups` vì phải sort toàn bộ alert theo thời gian và gọi `dateutil.parse` lặp lại nhiều lần. Thứ hai, và đáng lo hơn, là `topology_group`: code đang duyệt từng cặp service rồi gọi `nx.shortest_path_length` cho mỗi cặp. Với dữ liệu lớn hoặc số service tăng, bước này dễ thành nút thắt cổ chai do chi phí gần kiểu so sánh cặp đôi. Ngoài ra việc lặp qua từng session rồi lại grouping topology cũng làm tổng thời gian tăng thêm đáng kể.

# EOD Checkpoint

### Câu 1:

Fingerprint không include timestamp hay value vì fingerprint dùng để nhận diện loại alert/symptom ổn định, không phải từng lần đo cụ thể, nhận diện trên 3 tham số `service`, `metric`, `severity` . Nếu thêm timestamp, hai alert cùng bản chất nhưng xảy ra cách nhau vài giây sẽ thành hai fingerprint khác nhau, làm hệ thống không dedupe được. Ví dụ các alert của `payment-svc` về `latency_p99_ms` hoặc pool exhaustion trong cùng incident sẽ bị tách nhỏ chỉ vì thời điểm khác nhau. Nếu thêm value, cùng một metric nhưng giá trị dao động như `0.85`, `0.99`, `1.00` cũng tạo ra nhiều fingerprint khác nhau, khiến cluster bị vỡ và số lượng alert sau gom không giảm nhiều.

### Câu 2:

“Duplicate” alert là các alert gần như lặp lại cùng một symptom, thường cùng service, metric và severity. Ví dụ `a-0002` và `a-0011` đều là `payment-svc|db_connection_pool_used_ratio|crit`, nên có thể xem là duplicate về fingerprint. “Correlated” alert là các alert khác nhau nhưng có liên quan đến cùng một nguyên nhân gốc. Ví dụ trong dataset, `payment-svc` bị pool exhaustion, sau đó `checkout-svc` có downstream payment error, `edge-lb` có upstream 5xx, và `notification-svc` có queue lag/depth; chúng không duplicate nhau nhưng correlated trong cùng incident.

### Câu 3:

Với `gap_sec = 30`, output sẽ bị chia thành nhiều session/cluster hơn vì nhiều alert trong dataset cách nhau trên 30 giây sẽ không còn nằm chung session.  
Với `gap_sec = 600`, output sẽ gom rộng hơn, nhiều alert cách xa nhau trong vòng 10 phút vẫn vào cùng session, giảm số cluster nhưng tăng rủi ro gom nhầm noise.

### Câu 4:

Trong scenario chính `payment-svc` pool exhaustion, correlator hiện tại có gom `recommender-svc` vào cluster chính theo output `cluster_summary.json`: cluster `c-000-000` chứa cả `recommender-svc` và alert `a-0013`. Lý do là thuật toán chỉ xét session time window và khoảng cách topology `max_hop=2`; `recommender-svc` nằm đủ gần trong graph thông qua vùng `catalog-svc/catalog-db`, và timestamp của `a-0013` cũng nằm trong cùng session. Tuy nhiên về nghiệp vụ đây là gom sai, vì dataset ghi chú `a-0013` là `unrelated — concurrent batch retrain`, tức là batch retrain độc lập chứ không phải hậu quả của sự cố payment.

### Câu 5:

Limitation lớn nhất của topology grouping là nó giả định service gần nhau trên graph thì có khả năng cùng incident, nhưng không kiểm tra quan hệ nhân quả thật. Điều này dễ over-correlate các alert noise hoặc các job độc lập như `recommender-svc` batch retrain. Cách khắc phục là thêm scoring trước khi merge: kết hợp khoảng cách topology, độ gần timestamp, loại metric, hướng dependency, critical path, log/trace evidence và nhãn noise/unrelated nếu có. Ngoài ra có thể precompute shortest path và đặt rule loại trừ các service low-criticality hoặc batch workload nếu metric không khớp với incident chính.
