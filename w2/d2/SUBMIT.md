# W2 / RCA

### Câu 1:

Confidence của top-1 trong cluster lớn nhất tôi xử lý là **`0.43`** theo `w2/d2/results/rca_output.json` cho cluster `c-000-000`.

Nếu phải set threshold để **auto-rollback không cần SRE confirm**, tôi sẽ pick khoảng **`0.80`** và không dùng riêng confidence, mà còn cần guardrail kiểu:
- đúng service nằm trên critical path
- symptom khớp với runbook rollback đã biết
- có thêm tín hiệu xác nhận như pool/full, error rate tăng, hoặc deploy change gần đó

Lý do là ngay trong case tôi vừa đọc, top-1 có confidence `0.43` và còn **chọn lệch root cause**: output gán `checkout-svc / infinite_retry`, nhưng khi nhìn toàn bộ dữ liệu thì tôi tin hơn vào `payment-svc / connection_pool_exhaustion`. Raw alerts cho thấy `payment-svc` là nơi phát tín hiệu sớm nhất và mạnh nhất (`db_connection_pool_used_ratio`, `latency`, `error_rate`), còn `checkout-svc` và `edge-lb` chủ yếu là cascade. Vì vậy nếu threshold thấp, hệ thống rất dễ rollback hoặc remediate nhầm chỗ. Với auto-rollback kiểu no-human-confirm, tôi chỉ dám cho chạy khi confidence đủ cao và pattern khớp đúng một lớp incident đã lặp lại nhiều lần.

### Câu 2:

Tôi sẽ chọn **variant C — paid LLM** cho classifier.

Nhìn từ output thực tế hôm nay, phần classifier không chỉ gán class mà còn sinh được:
- `root_cause`
- `class`
- `reasoning`
- `actions`
- `similar_incidents`

Tức là nó đang làm nhiều hơn rule matching đơn giản; nó giống một bước reasoning trên top của graph + retrieval. Điểm mạnh tôi thấy khi chạy thực tế là nó **đọc được ngữ cảnh historical incident** và sinh action khá sát runbook cũ. Ví dụ cluster nhỏ `c-001-000` được map sang `payment-svc / connection_pool_exhaustion` với action rollback + scale pool + monitor. Tuy nhiên trade-off cũng lộ rõ: ở cluster lớn nhất nó bị **history bias**, kéo output về `checkout-svc / infinite_retry` dù raw signal nghiêng mạnh hơn về `payment-svc / connection_pool_exhaustion`.

Trade-off với các variant tôi không chọn:
- **A — rule-based**: rẻ, ổn định, dễ kiểm soát, rất hợp cho auto-remediation hẹp. Nhưng nó khó viết rule đủ tốt cho reasoning đa service, đặc biệt khi cần nối graph + temporal + historical incident.
- **B — free LLM**: chi phí thấp hơn C, thử nghiệm nhanh, nhưng tôi không tin bằng về độ ổn định output, latency và khả năng giữ format/quality khi đưa vào pipeline vận hành.
- **C — paid LLM**: tốn chi phí hơn nhưng hợp nhất nếu muốn classifier vừa gán nhãn vừa giải thích và đề xuất action. Dù vậy vẫn phải có guardrail vì model có thể “nói rất hợp lý nhưng sai service”, đúng như case tôi vừa thấy.

### Câu 3:

Nếu nhìn bảng Industry landscape (§6), pipeline tôi xây hôm nay (**graph + temporal + classifier**) gần nhất với **Dynatrace Davis**.

Lý do là pipeline này dựa khá mạnh vào **service graph tin được**:
- temporal step dùng time window để tạo session
- graph step dùng dependency để gom và đẩy suspicion về upstream/downstream quan trọng
- classifier đứng trên kết quả đó để map sang incident class và action

Nó **không giống Causely** ở chỗ tôi không học causal structure từ time-series dài; tôi đang dùng graph có sẵn để “shortcut” qua causal inference. Đổi lại, khi graph đúng và domain ổn định thì ra kết quả nhanh, dễ giải thích và dễ operationalize hơn.

Trong domain **GeekShop** thì lựa chọn này là **hợp lý**, chưa cần đổi:
- e-commerce alert volume cao
- service map tương đối ổn định
- critical path khá rõ (`edge-lb -> checkout-svc -> payment-svc`)
- historical incidents có pattern lặp lại

Với domain như vậy, tận dụng graph giống Davis là hợp lý hơn vì chi phí suy luận thấp hơn causal discovery và giải thích cũng dễ hơn cho on-call. Nhưng trade-off phải chấp nhận là **graph thiếu hoặc sai thì output lệch**. Case tôi vừa xử lý cho thấy lệch không chỉ do graph mà còn do classifier/retrieval bias, nên nếu đi theo hướng này thì nên bổ sung:
- confidence gate chặt cho remediation
- kiểm tra symptom-first (pool, error, downstream marker)
- rule loại trừ noise/async services
- human approval cho case confidence thấp hoặc multi-candidate
