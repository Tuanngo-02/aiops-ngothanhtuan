# Detection Approach — DESIGN.md

## Approach tôi dùng

Rule-based streaming anomaly detection với **sliding window baseline**.

Cụ thể:
- Giữ lịch sử các datapoint gần nhất trong memory
- Dùng **baseline window** để ước lượng trạng thái bình thường gần đây
- Dùng **recent window** để đo trạng thái hiện tại
- So sánh recent với baseline bằng các threshold theo domain knowledge
- Khi nhiều tín hiệu cùng vượt ngưỡng thì fire alert và gán loại fault phù hợp

## Tại sao chọn approach này

Approach này phù hợp cho streaming vì:

1. **Đơn giản và ổn định**  
   Không cần train model trước, phù hợp bài lab ngắn và dữ liệu vào liên tục.

2. **Giải thích được**  
   Mỗi alert đều có lý do rõ ràng: metric nào tăng, tăng bao nhiêu, log nào hỗ trợ.

3. **Phản ứng nhanh**  
   Chỉ cần một số tick gần nhất để phát hiện bất thường, không phải đợi batch lớn.

4. **Phù hợp dữ liệu đề bài**  
   Generator tạo ra 3 fault pattern khá rõ ràng, nên rule-based detection có thể nhận diện tốt:
   - `memory_leak`
   - `traffic_spike`
   - `dependency_timeout`

## Cách hoạt động

Pipeline nhận payload tại `POST /ingest` và xử lý theo luồng sau:

1. Parse `metrics`, `logs`, `timestamp`
2. Tính một số feature quan trọng:
   - memory utilization = `memory_usage_bytes / memory_limit_bytes`
   - CPU
   - RPS
   - p99 latency
   - 5xx rate
   - GC pause
   - queue depth
   - upstream timeout rate
3. Lưu datapoint vào history
4. Khi đủ dữ liệu warm-up:
   - `baseline window`: các điểm cũ hơn
   - `recent window`: 5 điểm gần nhất
5. Tính median của từng metric trong baseline và recent
6. Chạy 3 detector độc lập:
   - **Memory leak detector**
   - **Traffic spike detector**
   - **Dependency timeout detector**
7. Nếu có nhiều detector cùng match thì chọn detector có score cao nhất
8. Ghi một dòng JSON vào `alerts.jsonl`

Ngoài metrics, pipeline còn dùng log message làm tín hiệu hỗ trợ để tăng độ chắc chắn:
- `OutOfMemoryWarning`
- `GC pause exceeded threshold`
- `Queue depth high`
- `server overloaded`
- `Upstream timeout rate=...`
- `Circuit breaker OPEN`

## Logic phát hiện theo từng fault

### 1. Memory leak

Dấu hiệu chính:
- Memory utilization tăng cao
- GC pause tăng mạnh
- CPU tăng
- Có log liên quan GC hoặc OOM

Ý tưởng:
- Nếu memory tiến sát limit và GC pause tăng mạnh so với baseline thì nghi ngờ leak
- Nếu có `OutOfMemoryWarning` thì nâng mức tin cậy lên critical

### 2. Traffic spike

Dấu hiệu chính:
- RPS tăng mạnh so với baseline
- Queue depth tăng
- p99 latency tăng
- CPU tăng
- Timeout upstream vẫn thấp, giúp phân biệt với lỗi dependency

Ý tưởng:
- Nếu traffic tăng theo bội số lớn và hàng đợi/phản hồi xấu đi nhanh thì xem là overload do spike traffic

### 3. Dependency timeout

Dấu hiệu chính:
- Upstream timeout rate tăng mạnh
- 5xx rate tăng
- p99 latency tăng rất lớn
- Có log timeout hoặc circuit breaker

Ý tưởng:
- Nếu timeout từ upstream tăng rõ ràng thì ưu tiên classify là dependency fault thay vì traffic spike

## Parameters tôi chọn

### History size
- `maxlen = 120`

Lý do:
- Đủ giữ nhiều datapoint gần đây để làm baseline
- Không tốn nhiều memory

### Warm-up
- Cần ít nhất `12` datapoint trước khi detect

Lý do:
- Tránh alert quá sớm khi baseline chưa ổn định

### Recent window
- `5` datapoint gần nhất

Lý do:
- Đủ ngắn để phản ứng nhanh
- Đủ dài để giảm nhiễu từng tick

### Baseline statistic
- Dùng **median**

Lý do:
- Median chống nhiễu tốt hơn mean khi có spike ngắn hoặc outlier

### Cooldown alert
- Không bắn lại cùng `type` trong vòng `10` tick

Lý do:
- Tránh spam alert liên tục cho cùng một sự cố

### Một số threshold chính

#### Memory leak
- memory utilization >= 72% hoặc 82%
- GC pause tăng mạnh
- CPU tăng so với baseline

#### Traffic spike
- RPS >= 2x hoặc 3x baseline
- Queue depth tăng mạnh
- Latency tăng lớn

#### Dependency timeout
- upstream timeout rate >= 8% hoặc 12%
- 5xx rate tăng
- latency tăng lớn

Các ngưỡng này được chọn theo đúng shape của dữ liệu trong generator:
- `traffic_spike` làm RPS, queue, latency tăng nhanh
- `dependency_timeout` làm upstream timeout tăng rất rõ
- `memory_leak` làm memory + GC tăng dần trước, sau đó mới kéo theo latency/5xx

## Cải thiện nếu có thêm thời gian

1. **Adaptive baseline theo thời gian**
   - Tách baseline theo chu kỳ traffic ngày/đêm tốt hơn

2. **Dedup tốt hơn**
   - Gom nhiều tick cùng một incident thành 1 alert lifecycle với open/close

3. **Severity scoring tốt hơn**
   - Tính severity theo nhiều mức điểm thay vì rule cứng

4. **Persist state**
   - Lưu state detector ra file/redis để restart service không mất baseline

5. **Test tự động**
   - Viết test với payload giả lập cho 3 fault type

6. **Expose metrics**
   - Thêm endpoint `/metrics` để quan sát số alert đã bắn và trạng thái detector