Pack ship sẵn:

README.md                         hướng dẫn integrate với stack của bạn
experiments_template.yaml         10-entry YAML — fill 2-9 yourself
synthetic_probe.sh                external steady-state probe (§6.4)
pipeline/chaos_runner_skeleton.py runner với 2 TODO functions (§8.5)
configs/prometheus_targets.yml    example scrape targets — adapt to your stack
scripts/
├── start_stack.sh                stub — wire to your docker-compose
├── capture_baseline.py           N-min Prometheus snapshot → baseline.json
├── query_pipeline.py             call /alerts + /correlate + /rca
└── score_run.py                  scoreboard from chaos_results.json
Pack KHÔNG ship (bạn tự dựng hoặc lấy lại từ W2 Lab C):

docker-compose.yml cho 10-service stack
Source code của 10 mock services (frontend, api-gateway, payment-svc, inventory-svc, notification-svc, checkout-svc, auth-svc, log-collector, dns-resolver, cache-svc)
AIOps pipeline FastAPI exposing /alerts, /correlate, /rca
Pumba + Toxiproxy binaries (cài riêng — xem §4)
Khuyến nghị: clone stack từ W2 Lab C của group bạn, mở rộng thêm 5-7 service nếu chưa đủ 10, rồi sửa scripts/start_stack.sh để gọi docker compose up -d từ stack đó.

Topology target (stack bạn dựng nên match được hình này):

frontend → api-gateway → ┬→ payment-svc → payment-db
                         ├→ inventory-svc → inventory-db
                         ├→ notification-svc → kafka
                         └→ checkout-svc → ┬→ payment-svc
                                           └→ inventory-svc
+ auth-svc, log-collector, dns-resolver, cache-svc
+ prometheus 2.50, grafana 10.4, alertmanager 0.27
+ AIOps pipeline (FastAPI on port 8000):
   - GET  /alerts?since=<ts>       → list alert đã fire
   - POST /correlate {window}      → cluster
   - POST /rca {cluster}           → {root_service, confidence, evidence}
8.2 Bước 1 — Capture baseline + start synthetic probe
bash scripts/start_stack.sh                     # đợi tất cả service healthcheck OK
python scripts/capture_baseline.py --duration 300 --out baseline.json

# canonical steady-state signal — chạy nền suốt 10 experiment (xem §6.4)
nohup bash synthetic_probe.sh http://localhost:8080/checkout/health probe.log &
echo $! > probe.pid
baseline.json chứa steady-state mean + p99 cho mỗi (service, metric) — dùng để xác định “back to normal” sau experiment trên metric nội bộ. probe.log cung cấp signal độc lập (external user-visible) — pass-rate phải ≥ 99% trong 60s window trước khi bắt đầu Bước 2; nếu chưa đạt là stack chưa healthy thật, không phải lỗi probe.

8.3 Bước 2 — Experiment catalog
#	Target	Fault	Expected pipeline response
1	payment-svc	netem delay +500ms	detect latency anomaly, RCA pick payment
2	payment-svc	netem loss 30%	detect error_rate, RCA pick payment
3	inventory-svc	pod kill every 60s	detect availability, RCA pick inventory
4	api-gateway	stress CPU 90%	detect latency cascade across all downstream
5	payment-db	memory fill 95%	detect connection pool, RCA pick payment-db
6	auth-svc (lateral)	clock skew +60s	detect cert/JWT fail, RCA pick auth
7	log-collector	disk fill 95%	detect log ingestion lag (meta-monitoring catch?)
8	frontend ↔ api-gateway	full partition 30s	detect all-downstream timeout, RCA pick edge
9	dns resolver	slow lookup +2s	detect intermittent error, RCA depends on topology
10	checkout-svc	HTTP 500 inject 20%	retry storm scenario, RCA must NOT pick checkout
10 experiment phải chạy đủ. Trật tự không quan trọng nhưng phải có 120s cooldown giữa mỗi cái (chờ system về baseline).

8.4 Bước 3 — Fill experiments.yaml
Copy experiments_template.yaml → experiments.yaml. Field structure theo §5 (5 field: name, hypothesis, blast_radius, rollback, measurement, ground_truth). Entry #1 + #10 đã fill làm reference; #2-9 còn TODO. 10 entry phải đầy đủ trước khi chạy runner. Catalog ở §8.3.

8.5 Bước 4 — Implement chaos_runner.py
Copy pipeline/chaos_runner_skeleton.py → chaos_runner.py. Implement 2 function được mark TODO trong skeleton:

build_inject_cmd(exp) — dispatcher theo fault_type, return command list cho subprocess.run. Phủ 10 fault type ở §3 (latency, network_loss, availability, cpu_saturation, memory, disk_fill, time_skew, network_partition, dns_latency, cascade_retry).
print_scoreboard(results) — print confusion matrix theo format ở §8.6.
8.6 Bước 5 — Chạy 10 experiment + score
python chaos_runner.py
# → chaos_results.json + stdout scoreboard
Scoreboard format bắt buộc:

==== Chaos Run ====
Total: 10
Detected: <N>/10
RCA correct: <N>/<detected>
False alarms in baseline windows: <N>
Precision: <float>
Recall: <float>
MTTD p50: <s>, p95: <s>

Per-experiment:
| # | name              | detected | mttd  | rca_service  | rca_correct |
|---|-------------------|----------|-------|--------------|-------------|
| 1 | payment_latency   | Y        | 28s   | payment-svc  | Y           |
| 2 | ...               | ...      | ...   | ...          | ...         |

Gaps identified:
- <experiment id>: <symptom> → <suspected root cause in pipeline>
Acceptance:

Detected ≥ 7/10 (70% recall)
RCA correct ≥ 5/7 trên những cái detected (≈70% RCA accuracy)
False alarm trong 5-min baseline window ≤ 1
Nếu fail acceptance: log gap vào §8.7, không tune pipeline để force pass (đó là dishonest).

8.7 Bước 6 — Viết chaos_report.md
Sections bắt buộc:

# Chaos Engineering Report — <your name>

## 1. Setup
- Stack version + commit hash
- Pipeline version + commit hash
- Baseline window: <start> → <end>
- Total experiments run: 10

## 2. Results table
[paste scoreboard từ §8.6]

## 3. Detailed per-experiment analysis
Cho MỖI experiment, 80-150 từ:
- Hypothesis (copy từ experiments.yaml)
- Observed: detected hay không, MTTD, RCA service
- Match expected? Nếu không, lý do (data evidence)

## 4. Gap analysis — top 3 pipeline weakness
Mỗi gap:
- Symptom: <quan sát cụ thể, experiment nào, số gì>
- Likely cause in pipeline: <detector? correlator? RCA?>
- Recommended fix: <concrete, có tham chiếu §7 failure modes>

## 5. Hypothesis cho gap chưa khẳng định
[Optional but encouraged] Gap nào cần experiment thêm để xác định?
8.8 Bước 7 — SUBMIT.md
# W3-D2 Submission — <your name>

## 3 thứ tôi học được về AIOps pipeline của mình
1. ...
2. ...
3. ...

## 1 fault mà tôi mong pipeline catch nhưng nó miss
- Experiment: ...
- Why I expected detection: ...
- Why pipeline missed (hypothesis): ...

## 1 trade-off trong design pipeline mà tôi muốn rethink
...

## Scoreboard summary
- detected: __/10
- rca_correct: __/__
- mttd_p50: __s
- false_alarms: __
- verdict: __
8.9 Acceptance checklist
 experiments.yaml có đủ 10 entry, mỗi cái có cả 5 field (hypothesis, blast_radius, rollback, measurement, ground_truth)
 chaos_runner.py chạy được, không hard-code experiment
 chaos_results.json có đủ 10 entry
 probe.log chạy xuyên suốt 10 experiment, attach vào submission (chứng minh external steady-state signal)
 Scoreboard print đúng format §8.6
 Đạt acceptance §8.6: detected ≥ 7/10, RCA correct ≥ 5/detected, FA ≤ 1
 chaos_report.md có cả 4 section bắt buộc (5 là optional)
 SUBMIT.md đủ 4 section