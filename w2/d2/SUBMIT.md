# W2 / RCA

### Câu 1:

Confidence của top-1 trong cluster lớn nhất tôi xử lý là **`0.5`** theo `w2/d2/results/rca_output.json` cho cluster `c-000-000`.

Nếu phải set threshold để **auto-remediation không cần SRE confirm**, tôi sẽ pick khoảng **`0.80`** trở lên, và vẫn **không dùng riêng confidence** mà cần thêm guardrail như:
- đúng service nằm trên critical path
- symptom khớp với runbook remediation đã biết
- có thêm tín hiệu xác nhận như pool saturation, error rate tăng, hoặc deploy/config change gần thời điểm incident
- không có dấu hiệu data inconsistency trong cluster

Lý do là ngay trong case hiện tại, dù output đã chọn **đúng service `payment-svc`**, tôi vẫn chưa tin hoàn toàn vào **class `infinite_retry`**. Khi nhìn toàn bộ dữ liệu, tôi tin hơn vào **`payment-svc / connection_pool_exhaustion`** vì raw alerts cho thấy tín hiệu đầu tiên và mạnh nhất đều nằm ở payment:
- `db_connection_pool_used_ratio` từ warn lên crit rồi full
- `latency_p99_ms` tăng mạnh
- `error_rate` tăng từ warn lên crit

Ngược lại, `checkout-svc` có `downstream_payment_error_rate`, `latency` và `request_drop_rate` giống **cascade symptom** hơn là nơi phát sinh đầu tiên. Lịch sử incident cũng nghiêng mạnh về `connection_pool_exhaustion`, đặc biệt `INC-2025-11-08` và `INC-2026-05-10`.

Vì vậy, với confidence chỉ `0.5` và còn lệch ở phần incident class, tôi **không dám cho auto-remediation fully automatic**. Tôi chỉ dám dùng output này cho:
- enrich incident ticket
- page đúng team payments
- gợi ý runbook
- hoặc human-in-the-loop approval

---

### Câu 2:

Tôi sẽ chọn **variant C — paid LLM** cho classifier.

Nhìn từ output thực tế hôm nay, phần classifier không chỉ gán class mà còn sinh được:
- `root_cause`
- `class`
- `reasoning`
- `actions`
- `similar_incidents`

Tức là nó đang làm nhiều hơn rule matching đơn giản; nó giống một bước reasoning đặt trên top của **graph + retrieval**. Điểm mạnh lớn nhất tôi thấy là nó tận dụng được **historical incidents** để đưa ra explanation và action khá gần runbook cũ.

Trong case hiện tại, điều này thể hiện khá rõ:
- output chọn **`payment-svc`** làm root-cause service, phù hợp hơn với raw signal
- reasoning kéo về các incident lịch sử như `INC-2025-10-15` và `INC-2025-11-08`
- action được sinh ra có cấu trúc và usable

Tuy nhiên trade-off cũng lộ rõ: model vẫn có thể **đúng service nhưng sai class**. Ở đây nó map sang `infinite_retry`, trong khi raw alert + incident note nghiêng hơn về `connection_pool_exhaustion`. Nghĩa là paid LLM giúp reasoning tốt hơn, nhưng vẫn có nguy cơ **retrieval bias / semantic overfit** vào incident history gần giống bề mặt.

Trade-off với các variant tôi không chọn:
- **A — rule-based**: rẻ, ổn định, dễ kiểm soát, hợp cho auto-remediation hẹp. Nhưng khó viết rule đủ tốt cho reasoning đa service, nhất là khi cần nối graph + temporal + history.
- **B — free LLM**: chi phí thấp hơn và thử nhanh được, nhưng tôi không tin bằng về độ ổn định output, latency và khả năng giữ format/quality trong pipeline vận hành.
- **C — paid LLM**: mạnh nhất nếu muốn classifier vừa gán nhãn vừa giải thích và đề xuất action. Dù vậy vẫn phải có guardrail trước khi đưa vào remediation tự động.

---

### Câu 3:

Nếu nhìn bảng Industry landscape (§6), pipeline tôi xây hôm nay (**graph + temporal + classifier**) gần nhất với **Dynatrace Davis**.

Lý do là pipeline này dựa khá mạnh vào **service graph có sẵn**:
- temporal step dùng time window để tạo session/cluster
- graph step dùng dependency để gom các service liên quan
- classifier đứng trên kết quả đó để map sang incident class, reasoning và action

Nó **không giống Causely** ở chỗ tôi không học causal structure từ time-series dài hạn; tôi đang dùng topology có sẵn để suy luận nhanh hơn. Đổi lại, khi graph đúng và domain ổn định thì ra kết quả nhanh, dễ giải thích và dễ operationalize hơn cho on-call.

Trong domain **GeekShop**, hướng này vẫn là **hợp lý** vì:
- e-commerce có critical path khá rõ: `edge-lb -> checkout-svc -> payment-svc`
- service map tương đối ổn định
- incident history có pattern lặp lại
- `payment-svc` là service criticality cao, đáng để ưu tiên suspicion

Tuy nhiên case hiện tại cũng cho thấy trade-off phải chấp nhận:
- classifier có thể **đúng service nhưng sai class**
- noise / async component vẫn có thể bị gom vào cluster
- dữ liệu có thể có inconsistency, ví dụ `a-0008` bị cluster chung dù timestamp lệch 1 tháng trong raw file

Vì vậy nếu tiếp tục đi theo hướng giống Davis, tôi sẽ bổ sung:
- confidence gate chặt cho remediation
- symptom-first validation cho các pattern quen thuộc như pool exhaustion
- data quality check trước bước correlation
- rule giảm trọng số cho low-criticality / async services
- human approval cho case confidence thấp hoặc có nhiều dấu hiệu mâu thuẫn