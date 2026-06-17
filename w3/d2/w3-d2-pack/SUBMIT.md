# W3-D2 Submission — AI Assistant (Kiro)

## 3 thứ tôi học được về AIOps pipeline của mình

1. **Observability Stack phải có end-to-end connectivity** - Một pipeline AIOps không thể hoạt động nếu các thành phần không được kết nối đúng cách. Prometheus scraping, Alertmanager webhook, và pipeline endpoints phải được kiểm tra từng bước. Trong lab này, baseline metrics rỗng cho thấy Prometheus không scrape được bất kỳ metric nào từ các services.

2. **Chaos Engineering không thể simulate - cần actual fault injection** - Đơn giản print statements hay mock responses không đủ. Để pipeline detect được故障, cần actual network manipulation (tc netem), resource exhaustion (stress-ng), và service disruption (docker kill). Các fault types không implement đầy đủ trong `build_inject_cmd()` sẽ dẫn đến experiments không thực sự test pipeline.

3. **External validation (synthetic probes) là ground truth** - Internal metrics có thể "fooled" bởi các vấn đề như cache stale, partial degradation, hoặc service trả 200 với body sai. External probes là cách duy nhất để đo user experience thực tế. Trong lab này, probe system không chạy khiến chúng ta không có signal độc lập để xác nhận system health.

---

## 1 fault mà tôi mong pipeline catch nhưng nó miss

- **Experiment**: inventory_pod_kill (Experiment 3)
- **Why I expected detection**: Pod kill là availability fault rõ ràng nhất - service down = 100% error rate. Hypothesis là pipeline detect trong <30s và RCA pointing tới inventory-svc.
- **Why pipeline missed (hypothesis)**: 
  1. **Metrics không được scrape** - Prometheus không nhận được metric từ inventory-svc (baseline empty)
  2. **Không có alerting rules** - Prometheus không có rule nào để fire alert khi `up == 0`
  3. **Alertmanager không được configure** - Không có webhook gửi alert đến pipeline
  4. **Pipeline không query trực tiếp metrics** - `/alerts` endpoint chỉ trả empty array, không có actual Prometheus API call

**Evidence**: `"alerts": []` trong measured_metrics của experiment 3.

---

## 1 trade-off trong design pipeline mà tôi muốn rethink

**Current trade-off**: Pipeline sử dụng kiến trúc "pull-based" (query Prometheus/Alertmanager) thay vì "push-based" ( nhận alerts từ webhook).

**Why I want to rethink**: Trong lab này, webhook push từ Alertmanager không hoạt động vì:
1. Alertmanager chưa configure webhook
2. Pipeline /alerts endpoint không có logging để verify receipt
3. Testing manual alert firing phức tạp

**Alternative approach**: Kết hợp cả pull và push:
- **Push**: Alertmanager webhook → pipeline /alerts (real-time, primary)
- **Pull**: Pipeline periodic query Prometheus metrics (fallback, for services không report to Alertmanager)

Advantage: Redundancy - nếu webhook failure, pipeline vẫn có dữ liệu pull.同时, webhook cho real-time alerts, pull cho comprehensive metric coverage.

---

## Scoreboard summary

- **detected**: 0/3 (0%) - Only 3 experiments executed, 0 detected
- **rca_correct**: 0/0 - No detections, so no RCA correctness to measure
- **mttd_p50**: N/A - No detected events to calculate MTTD
- **false_alarms**: 0 - Baseline window had no alerts
- **verdict**: **FAIL** - Pipeline không đạt acceptance criteria (expected ≥7/10 detection, ≥5/7 RCA accuracy)

### Acceptance Criteria Check

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Detection Rate | ≥70% | 0% | FAIL |
| RCA Accuracy | ≥70% | N/A | FAIL |
| False Alarms | ≤1 | 0 | PASS |

---

## Key Gaps Identified

1. **Missing Prometheus configuration** - No alerting rules defined
2. **Missing Alertmanager webhook** - Alerts không đi đến pipeline
3. **Incomplete fault injection** - 5/8 fault types unsupported
4. **Non-functional probe system** - External validation missing

---

## References

- Detailed analysis: `chaos_report.md`
- Experiment results: `chaos_results.json`
- Experiments template: `experiments_template.yaml`
- Baseline metrics: `baseline.json`