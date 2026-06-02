# W1-D1: Metric Anomaly Detection - Tổng hợp kiến thức

## 1. Mục tiêu bài học

Metric Anomaly Detection là bước đầu trong pipeline AIOps: phát hiện "cái lạ" trong metric trước khi nó trở thành outage. Ví dụ production service có latency p99 tăng từ 200ms lên 1.2s và error rate tăng từ 0.1% lên 4%, trong khi CPU/memory vẫn bình thường. Threshold cứng error rate 5% sẽ chưa trigger, nhưng anomaly detection có thể bắt sớm hơn 15-20 phút.

Nguyên tắc chọn phương pháp:

- Bắt đầu từ cách đơn giản, dễ giải thích.
- Chỉ dùng ML/DL khi statistical methods không đủ.
- Production AIOps ưu tiên explainable và maintainable hơn việc tăng accuracy nhỏ.

Thứ tự thực tế nên thử:

1. 3-sigma / IQR / EWMA
2. STL decomposition nếu có seasonal pattern
3. Isolation Forest nếu cần nhìn nhiều metric hoặc data không theo distribution rõ ràng
4. Deep learning chỉ khi các cách trên fail

## 2. Nền tảng về phân phối dữ liệu

### 2.1 Normal distribution và standard deviation

Phân phối chuẩn có dạng chuông, data tập trung quanh mean `mu` và đối xứng hai bên.

- Khoảng 68% data nằm trong `mu +/- 1 sigma`
- Khoảng 95% data nằm trong `mu +/- 2 sigma`
- Khoảng 99.7% data nằm trong `mu +/- 3 sigma`

Nếu một điểm nằm ngoài `3 sigma`, xác suất xảy ra tự nhiên rất thấp, có thể coi là anomaly.

Ví dụ CPU trung bình 40%, standard deviation 10%:

- CPU 55%: z-score = 1.5, bình thường
- CPU 85%: z-score = 4.5, bất thường

### 2.2 Skewness

Nhiều metric không có phân phối chuẩn. Latency thường right-skewed: phần lớn request nhanh, nhưng có đuôi dài bên phải do GC pause, cache miss, slow query.

Ý nghĩa skewness:

- `skewness ~= 0`: gần Gaussian, có thể dùng 3-sigma
- `|skewness| 0.5-1`: skew vừa, cần cẩn thận
- `|skewness| > 1`: skew nặng, không nên dùng 3-sigma trực tiếp

Tại sao 3-sigma fail trên skewed data:

- Mean bị outlier ở đuôi kéo lệch.
- Standard deviation bị phóng to.
- Threshold bên phải quá xa nên miss anomaly.
- Threshold bên trái có thể vô nghĩa, vì latency không thể âm.

Cách xử lý skewed data:

- Log transform: `np.log1p(data)` để nén giá trị lớn, làm distribution đối xứng hơn.
- IQR: dùng percentile thay vì mean/std.
- Isolation Forest: không giả định phân phối.

### 2.3 Stationarity

Stationary series có mean và variance ổn định theo thời gian. Nếu data có trend hoặc seasonal pattern, tính mean/std trên toàn bộ lịch sử sẽ tạo threshold sai.

Vấn đề:

- Trend tăng dần: data đầu kỳ bị gọi là thấp bất thường, data cuối kỳ bị gọi là cao bất thường.
- Seasonal pattern: đỉnh/đáy của chu kỳ bị false alarm.

Cách xử lý:

- Dùng rolling window thay vì toàn bộ lịch sử.
- Tách trend và seasonal bằng STL decomposition.

## 3. Statistical methods

### 3.1 Rolling Z-score / 3-sigma

Ý tưởng: tính rolling mean và rolling standard deviation trên N điểm gần nhất. Nếu điểm mới có `|z-score| > threshold`, đánh dấu anomaly.

Công thức:

```python
z = (x - mean) / std
```

Dùng rolling window vì baseline hệ thống thay đổi theo thời gian. Nếu dùng toàn bộ lịch sử, data cũ sẽ làm mean/std lỗi thời.

Ưu điểm:

- Rất nhanh, O(n), phù hợp real-time.
- Dễ implement và dễ giải thích cho ops team.
- Không cần label hay training data.
- Deterministic.

Nhược điểm:

- Giả định data gần Gaussian.
- Không handle seasonal pattern tốt.
- Window size phải tune.
- Outlier có thể làm "ô nhiễm" rolling window.

Khi nên dùng:

- Metric ổn định, ít seasonal, gần Gaussian.
- Ví dụ: disk usage, memory usage, connection pool size, queue depth, CPU trong workload đều.

Không nên dùng trực tiếp:

- Request latency raw, vì latency thường right-skewed. Nên log transform, dùng IQR, STL + IQR, hoặc Isolation Forest.

Rule of thumb cho window:

- 10-30 điểm: detect nhanh, nhưng dễ false alarm.
- 60-120 điểm: cân bằng, thường là default tốt.
- 240-1440 điểm: ổn định hơn, nhưng detect chậm.

### 3.2 EWMA

EWMA phù hợp để detect drift/trend chậm, vì nó cho data mới weight cao hơn nhưng vẫn giữ "trí nhớ" với data cũ.

Công thức:

```text
EWMA_t = alpha * x_t + (1 - alpha) * EWMA_{t-1}
```

Ý nghĩa `alpha`:

- `alpha = 0.05-0.1`: nhớ xa, tốt cho memory leak/capacity trend.
- `alpha = 0.2-0.3`: cân bằng cho latency degradation.
- `alpha = 0.5-0.9`: phản ứng nhanh hơn, nhưng nhiều noise.

Tại sao EWMA bắt được drift mà rolling mean có thể miss:

- Rolling mean chỉ nhìn window gần nhất, nên khi metric tăng chậm, cả window cũng tăng theo.
- EWMA vẫn giữ ảnh hưởng của data cũ, nên thấy được metric đã drift xa baseline ban đầu.

Khi nên dùng:

- Memory leak.
- Disk filling.
- Gradual performance degradation.
- Connection pool exhaustion.

Common mistake:

- Dùng EWMA để bắt spike nhanh. EWMA sinh ra để bắt drift, nếu cần bắt spike nên dùng 3-sigma/STL.

### 3.3 STL decomposition

STL tách time series thành 3 phần:

- `Trend`: xu hướng dài hạn.
- `Seasonal`: pattern lặp lại theo chu kỳ.
- `Residual`: phần còn lại sau khi bỏ trend và seasonal.

Detect anomaly trên residual sẽ tốt hơn detect trên raw data, vì seasonal false alarm đã được loại bỏ.

Khi nên dùng:

- Metric có daily/weekly seasonal pattern.
- Traffic web service cao ban ngày, thấp ban đêm.
- Throughput có chu kỳ theo giờ/ngày/tuần.

Chọn `period`:

- Data 1-minute, daily pattern: `period = 1440`
- Data 5-minute, daily pattern: `period = 288`
- Data 1-hour, daily pattern: `period = 24`
- Data hourly, weekly pattern: `period = 168`

Nên dùng `robust=True` để outlier không kéo lệch quá trình fit trend/seasonal.

## 4. Machine learning methods

### 4.1 Isolation Forest

Ý tưởng cốt lõi: anomaly là điểm dễ tách khỏi đám đông.

Isolation Forest tạo nhiều cây bằng cách:

1. Random chọn feature.
2. Random chọn giá trị split.
3. Lặp lại cho đến khi điểm bị isolate.

Kết quả:

- Điểm bình thường nằm trong cluster cần nhiều split để tách ra, path length dài.
- Điểm anomaly nằm xa cluster, bị tách nhanh, path length ngắn.

Khi dùng:

- Multivariate anomaly: cần nhìn CPU + memory + latency + error rate + throughput cùng lúc.
- Data không có label.
- Data skewed hoặc không theo Gaussian.
- Dataset lớn, cần model nhanh.

Lưu ý quan trọng: không feed raw time series trực tiếp vào Isolation Forest. Model nhìn mỗi row độc lập, không biết context thời gian. Cần tạo feature trước.

Feature tối thiểu:

- Current value.
- Rolling mean.
- Rolling std.
- Rate of change.
- Lag features.
- Hour/day features nếu có seasonal.

Tham số cần tune:

- `n_estimators`: thường 100-500, default tốt là 200.
- `contamination`: tỉ lệ anomaly ước lượng, nên bắt đầu 0.01-0.02.
- `max_samples`: default 256 thường đủ.
- `max_features`: 1.0 nếu ít feature.

Tune contamination:

- Quá nhiều false alarm: giảm contamination.
- Miss anomaly đã biết: tăng contamination.

### 4.2 One-Class SVM

One-Class SVM học boundary quanh data bình thường, điểm nằm ngoài boundary là anomaly.

So với Isolation Forest:

- Chậm hơn nhiều, có thể O(n^2) đến O(n^3).
- Cần data sạch chỉ gồm normal.
- Khó tune hơn: `kernel`, `nu`, `gamma`.
- Khó explain hơn.

Kết luận thực tế: trong AIOps production, Isolation Forest thường là lựa chọn tốt hơn. One-Class SVM chỉ nên dùng khi data nhỏ và có tập normal sạch.

## 5. Deep learning methods

### 5.1 Autoencoder

Autoencoder học nén data xuống latent space nhỏ hơn, rồi reconstruct lại. Train trên data bình thường. Khi gặp anomaly, model reconstruct kém, reconstruction error cao.

Khi nên dùng:

- Có 50+ metric đồng thời.
- Pattern phức tạp mà Isolation Forest miss.
- Có đủ data sạch và khả năng vận hành model DL.

### 5.2 LSTM Autoencoder

Giống Autoencoder nhưng có LSTM để hiểu thứ tự thời gian. Phù hợp khi temporal dependency mạnh.

Trade-off:

- Train chậm hơn 10-100 lần so với Isolation Forest.
- Cần nhiều data sạch, thường ít nhất 1-2 tuần.
- Khó debug vì black-box.
- Cần retrain khi hệ thống/traffic thay đổi.

Rule thực tế: chỉ tính DL khi 3-sigma, STL và Isolation Forest không đáp ứng được.

## 6. Univariate vs Multivariate

### Univariate

Input một metric, ví dụ chỉ CPU hoặc chỉ latency.

Phù hợp:

- Spike/drop trên một metric riêng lẻ.
- Cần debug nhanh, explain dễ.

Tool:

- 3-sigma
- EWMA
- STL
- IQR

Nhược điểm:

- Miss anomaly nằm trong correlation giữa nhiều metric.

### Multivariate

Input nhiều metric cùng lúc, ví dụ CPU + memory + GC pause + latency p99 + error rate.

Phù hợp:

- Detect correlation bất thường.
- Ví dụ memory leak: memory tăng, GC pause tăng, latency tăng nhưng CPU không tăng. Từng metric riêng lẻ có thể chưa vượt threshold, nhưng combination này là bất thường.

Tool:

- Isolation Forest
- Autoencoder

Nhược điểm:

- Khó explain hơn.
- Cần nhiều data hơn.

## 7. Feature engineering cho time series

ML model thường nhìn mỗi row độc lập. Vì vậy raw value không đủ, cần bổ sung context.

Feature nên có:

| Feature | Ví dụ code | Mục đích |
| --- | --- | --- |
| Rolling mean | `s.rolling(60).mean()` | Baseline gần đây |
| Rolling std | `s.rolling(60).std()` | Độ dao động gần đây |
| Rate of change | `s.diff()` | Tốc độ tăng/giảm |
| Lag features | `s.shift(1)`, `s.shift(60)` | Giá trị trước đó |
| Hour of day | `ts.dt.hour` | Daily pattern |
| Day of week | `ts.dt.dayofweek` | Weekly pattern |
| Rolling Z-score | `(x - roll_mean) / roll_std` | Độ lệch đã normalize |
| EMA ratio | `s / s.ewm(...).mean()` | So sánh với trend gần |

Window size cheat sheet:

| Granularity | 1h | 4h | 1 day |
| --- | ---: | ---: | ---: |
| 1 second | 3600 | 14400 | 86400 |
| 1 minute | 60 | 240 | 1440 |
| 5 minutes | 12 | 48 | 288 |
| 1 hour | 1 | 4 | 24 |

## 8. KPI đánh giá detector

Không nên nói "model tốt" chung chung, cần có metric cụ thể.

| KPI | Công thức | Target | Ý nghĩa |
| --- | --- | --- | --- |
| Precision | `TP / (TP + FP)` | > 0.7 | Trong alert model báo, bao nhiêu là thật |
| Recall | `TP / (TP + FN)` | > 0.8 | Trong anomaly thật, model bắt được bao nhiêu |
| F1 | `2PR / (P + R)` | > 0.75 | Cân bằng precision và recall |
| TTD | anomaly xảy ra -> model detect | < 5 phút | Time-to-detect, rất quan trọng trong AIOps |
| False alarm rate | `FP / (FP + TN)` | < 0.01 | Tỉ lệ data bình thường bị báo nhầm |

Trong AIOps, thường ưu tiên recall hơn precision:

- Miss anomaly thật có thể gây outage, SLA breach, revenue lost.
- False alarm tốn thời gian investigate, nhưng thường ít nguy hiểm hơn miss outage.
- Tune threshold nên nghiêng về bắt được anomaly, chấp nhận một mức false alarm hợp lý.

## 9. Chọn phương pháp theo scenario

| Scenario | Phương pháp | Lý do |
| --- | --- | --- |
| Disk usage tăng bất thường | 3-sigma | Univariate, ít seasonal, gần Gaussian |
| Request latency spike ban đêm | STL + IQR | Có seasonal và latency bị skew |
| CPU + memory + latency cùng lạ | Isolation Forest | Cần detect correlation nhiều metric |
| Memory leak chậm | EWMA alpha 0.1 | Detect drift, rolling 3-sigma dễ miss |
| Throughput có weekly pattern | STL period 168 với hourly data | Có seasonal theo tuần |
| 200 metric, pattern phức tạp | Autoencoder | Dùng khi Isolation Forest fail |

## 10. Assignment cần làm

### Phase 1: EDA và hiểu data

- Download 1 dataset từ NAB, gợi ý `realKnownCause/` vì có ground truth.
- Load data và plot raw time series.
- Tính mean, std, skewness, min, max.
- Plot histogram + density để xem Gaussian hay skewed.
- Plot ACF để xem có seasonal không và period là bao nhiêu.
- Kết luận data stationary/seasonal/skewed và chọn method phù hợp.

### Phase 2: Implement 2 detectors

Detector statistical, chọn theo EDA:

- Rolling Z-score nếu stationary và gần Gaussian.
- STL + 3-sigma nếu có seasonal.
- IQR nếu skew nặng.

Detector ML:

- Tạo feature table, ít nhất 5 features.
- Train Isolation Forest.
- Tune `contamination`: thử 0.01, 0.02, 0.05.
- Tính precision, recall, F1 theo ground truth label.
- Plot original series + anomalies highlighted cho cả 2 detector.

### Phase 3: So sánh và reflection

Cần có bảng so sánh:

- Precision
- Recall
- F1
- False alarms

Cần ghi lại ít nhất 3 lần tune threshold/window/contamination.

`SUBMIT.md` cần có:

- Screenshots plot kết quả anomaly detection.
- Bảng precision/recall.
- Log tune contamination.
- Model artifact `.pkl` hoặc `.joblib` của Isolation Forest.
- Reflection: data thuộc loại gì, tại sao chọn method, detector nào tốt hơn, trade-off, production choice.

## 11. Câu hỏi knowledge check cần nắm

1. Skewness là gì, tại sao data skewed làm 3-sigma sai, và 2 cách xử lý.
2. So sánh 3-sigma, EWMA, STL: detect loại anomaly nào, fail ở đâu, dùng khi nào.
3. Isolation Forest: giải thích "path length ngắn = anomaly" và tại sao cần feature engineering.
4. Univariate vs multivariate: ví dụ memory leak, tại sao univariate miss nhưng multivariate catch.
5. Precision vs recall: tại sao AIOps ưu tiên recall và trade-off khi tune threshold.

## 12. Kết luận ngắn

Metric anomaly detection không phải là việc chọn model phức tạp nhất. Điểm quan trọng là hiểu data:

- Gaussian, stationary: 3-sigma có thể đủ.
- Skewed: log transform hoặc IQR.
- Seasonal: STL rồi detect trên residual.
- Drift chậm: EWMA.
- Correlation nhiều metric: Isolation Forest.
- Pattern rất phức tạp với rất nhiều metric: Autoencoder/LSTM Autoencoder.

Trong production, hãy ưu tiên detector dễ giải thích, dễ tune, có KPI rõ ràng, và có khả năng detect sớm với recall cao.
