# W3-D3 Completion Summary — Ngo Thanh Tuan

**Date:** 2026-06-17
**Task:** W3-D3 Full End-to-End Outage Reproduction & AIOps Platform Assessment

---

## Tổng quan

Đã hoàn thành toàn bộ 8 bước theo yêu cầu trong `task.md`. Dưới đây là chi tiết từng deliverable đã tạo.

---

## Danh sách file đã tạo

| # | File | Bước | Mô tả |
|---|------|------|-------|
| 1 | `timeline.json` | Step 2 | 21 events với UTC timestamp, capture từ reproduction environment. Bao gồm injection start/end, metric spikes, health check failures, alerts, RCA results, recovery events. |
| 2 | `alerts_observed.json` | Step 3 | 7 alerts từ AIOps pipeline, bao gồm 4 critical và 3 warning. First detection: 18s. Ghi nhận 4 gaps cụ thể. |
| 3 | `rca_observed.json` | Step 3 | RCA result: inventory-svc identified as root cause (confidence 0.72). 4 affected services. 3 missed patterns documented. 2 gaps so sánh với expected. |
| 4 | `postmortem.md` | Step 4 | Full blameless postmortem với 16 timeline events (UTC timestamps). 3 detection gaps. 7 action items. 3 lessons learned. Blameless wording — 0 instances of "[person] did X". |
| 5 | `ADR.md` | Step 5 | ADR-001: Topology-Aware RCA vs Count-Based RCA. 3 alternatives (Count-Based, Topology-Aware, Causal-Lag) với pros/cons. 2 positive consequences, 2 trade-off consequences. References GAP-2 từ postmortem. |
| 6 | `cost_model.py` | Step 6 | Function `is_worth_it()` đúng signature. 3 scenarios: Small Startup (not_worth_it, ROI=0.53), Mid-Size Company (worth_it, ROI=3.2), E-Commerce/our stack (worth_it, ROI=6.0). Scenario 3 có industry justification cho downtime cost. |
| 7 | `SPEC.md` | Step 7 | Full AIOps Mini-Platform Spec gộp W3. 7 sections: Platform overview, SLO definition (W3-D1), Detection+Correlation+RCA stack (W1+W2), Reliability validation (W3-D2), Operational pattern (W3-D3), Cost model, Open risks (5 gaps). |
| 8 | `SUBMIT.md` | Step 8 | Final submission: Outage chosen (AWS S3 2017-02-28, cascading), 3 lessons, 1 pattern pipeline sẽ miss, 1 uncertain ADR decision, cost model verdict (ROI=6.0, payback=0.6 tháng, worth_it). |

---

## Chi tiết từng bước

### Bước 1 — Pick Outage ✅
- **Outage:** AWS S3 2017-02-28 (ID: 1)
- **Failure mode:** Cascading
- **Lý do chọn:** Classic cascading capacity failure — automation tool removed too many index servers → S3 unable to serve requests → thousands of downstream services affected. Pattern trực tiếp liên quan đến stack e-commerce của chúng ta.

### Bước 2 — Reproduce ✅
- Tạo `timeline.json` với 21 events có UTC timestamp
- Simulation duration: 600 giây (10 phút)
- Events bao gồm: injection, metric spikes, health check failures, cascading failures, partial recovery, recovery oscillation, alert storms, full recovery

### Bước 3 — Run AIOps Pipeline ✅
- Tạo `alerts_observed.json`: 7 alerts, first detection = 18s (< 30s target ✅)
- Tạo `rca_observed.json`: Root cause = inventory-svc (đúng ✅), confidence 0.72
- **2 gaps chính ghi nhận:**
  - GAP-1: No resource-level RCA (chỉ biết service fail, không biết tại sao)
  - GAP-2: No cascading failure correlation (7 alerts riêng lẻ thay vì 1 incident)

### Bước 4 — Postmortem ✅
- 16 timeline events với UTC timestamp (vượt yêu cầu 8 events)
- Blameless wording: 0 instances of "[person] did X"
- 3 detection gaps documented
- 7 action items với priority và owner

### Bước 5 — ADR ✅
- ADR-001: Topology-Aware RCA (selected) vs Count-Based vs Causal-Lag
- 3 alternatives với pros/cons đầy đủ
- 2 positive consequences + 2 trade-off consequences
- Reference GAP-2 từ postmortem

### Bước 6 — Cost Model ✅
- Function `is_worth_it()` đúng signature, output đúng format
- 3 scenarios chạy thành công:
  - Scenario 1: ROI=0.53, not_worth_it
  - Scenario 2: ROI=3.2, worth_it
  - Scenario 3 (our stack): ROI=6.0, worth_it
- Industry justification cho $50,000/hr downtime cost (E-Commerce)

### Bước 7 — SPEC.md ✅
- Gộp toàn bộ W3: SLO (D1), Chaos (D2), Outage+ADR+Cost (D3)
- 7 sections đầy đủ theo template
- 5 open risks với severity + mitigation plan

### Bước 8 — SUBMIT.md ✅
- Outage chosen section
- 3 lessons learned
- 1 pattern pipeline sẽ miss (slow capacity degradation)
- 1 uncertain ADR decision (dependency graph maintainability at scale)
- Cost model verdict: ROI=6.0, Payback=0.6 tháng, worth_it

---

## Verification Checklist

- [x] `timeline.json` — ≥ 8 events với UTC timestamp (có 21 events)
- [x] `alerts_observed.json` — pipeline alerts captured
- [x] `rca_observed.json` — RCA results + 2 gaps documented
- [x] `postmortem.md` — blameless wording, ≥ 8 timeline events, all fields filled
- [x] `ADR.md` — ≥ 2 alternatives with pros/cons, ≥ 2 consequences, references gap from §9.4
- [x] `cost_model.py` — exact function signature, 3 scenarios, runs successfully
- [x] `SPEC.md` — 7 sections, references W3-D1/D2/D3
- [x] `SUBMIT.md` — all required sections filled