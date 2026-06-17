9.2 Bước 1 — Pick outage
Chọn 1 outage từ outage_catalog.yaml (5 lựa chọn ở §5).

Trong SUBMIT.md Section 0, viết:

## Outage chosen
- ID: <1-5>
- Name: <ví dụ AWS S3 2017-02-28>
- Why this one: <2-3 câu — bạn quan tâm pattern gì>
- Failure mode: <pick từ §4: cascading | split-brain | regex | capacity | monitoring-loop | operator>
9.3 Bước 2 — Reproduce
cd reproduction_templates/<chosen_outage>/
bash ../scripts/start_reproduction.sh
# wait healthcheck
bash ../scripts/inject.sh
# capture
python ../scripts/capture_timeline.py --duration 600 --out timeline.json
timeline.json chứa event được capture từ Prometheus + container event + pipeline output, có UTC timestamp.

9.4 Bước 3 — Run AIOps pipeline trên reproduction
Pipeline đã chạy nền (port 8000). Query:

curl http://localhost:8000/alerts?since=<inject_start_ts> > alerts_observed.json
curl -X POST http://localhost:8000/rca \
     -d '{"window_start": <ts>, "window_end": <ts+600>}' \
     > rca_observed.json
So sánh với expected (theo original postmortem):

Pipeline detected sự cố trong < N giây? (target < 30s)
Pipeline pick đúng root service không?
Có pattern nào pipeline miss hoàn toàn không?
Note ít nhất 2 gap cụ thể vào postmortem.md Section “Detection”.

9.5 Bước 4 — Viết postmortem.md
Theo template §2. Mỗi field bắt buộc fill, không bỏ trống. Timeline phải có ít nhất 8 event với UTC timestamp (lấy từ timeline.json).

Required wording check: 0 instance của “ did X” — chỉ chấp nhận blameless wording (§2.1).

9.6 Bước 5 — Viết ADR.md
1 ADR cho 1 design decision của AIOps platform, theo template Nygard §7.1. Decision phải:

Có ít nhất 2 alternatives với pros/cons mỗi cái
Có ít nhất 2 consequences (1 positive, 1 trade-off)
Reference được gap đã quan sát ở §9.4
Ví dụ topic ADR phù hợp:

RCA: count-based vs topology-aware vs causal-lag — pick gì
Alert routing: page-everyone vs tier-based on-call rotation
Detector: single threshold vs ensemble (3σ + IF + LSTM-AE)
Storage: hot Prometheus 2 tuần vs S3+Athena cold long-term
LLM: GPT-style cloud API vs self-host Llama vs no LLM
9.7 Bước 6 — Viết cost_model.py
Implement function chính xác theo signature:

def is_worth_it(
    num_services: int,
    incidents_per_month: int,
    avg_incident_duration_hours: float,
    downtime_cost_per_hour: float,
    expected_mttr_reduction_pct: float = 0.4,
    aiops_monthly_cost: float = 15_000,
) -> dict:
    """
    Returns:
      {
        "monthly_value": float,
        "monthly_cost": float,
        "roi": float,
        "payback_months": float,  # or float('inf')
        "verdict": "worth_it" | "marginal" | "not_worth_it"
      }
    Verdict rule:
      roi > 1.5 → worth_it
      1.0 < roi ≤ 1.5 → marginal
      roi ≤ 1.0 → not_worth_it
    """
Plus 3 worked example scenario in cùng file (call function + print result):

if __name__ == "__main__":
    print(is_worth_it(num_services=20, incidents_per_month=2,
                      avg_incident_duration_hours=1, downtime_cost_per_hour=10_000,
                      aiops_monthly_cost=15_000))
    print(is_worth_it(num_services=100, incidents_per_month=5,
                      avg_incident_duration_hours=2, downtime_cost_per_hour=20_000,
                      aiops_monthly_cost=25_000))
    # 1 scenario của bạn — chọn industry, defend choice của downtime cost trong comment
9.8 Bước 7 — Viết SPEC.md (gộp W3 lại)
Outline:

# AIOps Mini-Platform Spec — <your name>

## 1. Platform overview
[2-3 câu: stack được monitor, scope, user của platform]

## 2. SLO definition (from W3-D1)
[paste/reference slo_spec.yaml — 3 service × SLI+SLO+budget]

## 3. Detection + Correlation + RCA stack (from W1+W2)
[1 paragraph mỗi layer — high-level approach + ADR reference]

## 4. Reliability validation (from W3-D2)
[paste chaos_report.md scoreboard + top 3 gap]

## 5. Operational pattern (from W3-D3)
[reproduced outage + key learning + ADR-001 reference]

## 6. Cost model (from W3-D3)
[paste cost_model.py output cho stack hiện tại + break-even point]

## 7. Open risks
[3-5 known gap chưa fix, mỗi cái có severity + mitigation plan]
9.9 Bước 8 — SUBMIT.md
# W3-D3 Submission — <your name>

## Outage chosen
[section §9.2]

## 3 thứ tôi học từ outage này
1. ...
2. ...
3. ...

## 1 thứ pipeline của tôi sẽ vẫn miss nếu outage này xảy ra real
- Pattern: ...
- Why miss: ...
- Mitigation idea: ...

## 1 quyết định trong ADR mà tôi không hoàn toàn chắc
...

## Cost model verdict cho stack của tôi
- ROI: __
- Payback: __ tháng
- Verdict: __