# AIOps Mini-Platform Spec — Ngo Thanh Tuan

---

## 1. Platform Overview

The AIOps Mini-Platform monitors an e-commerce microservices stack consisting of 10 Docker Compose services (api-gateway, payment-svc, inventory-svc, checkout-svc, auth-svc, cache-svc, frontend, notification-svc, log-collector, dns-resolver). The platform scope covers automated anomaly detection, alert correlation, and root cause analysis for production reliability. Target users are SRE/on-call engineers who need to quickly identify and resolve incidents in a distributed microservices environment.

---

## 2. SLO Definition (from W3-D1)

Reference: `w3/d1/w3-d1-pack/slo_spec.yaml`

### 3 Services × SLI + SLO + Error Budget

| Service | SLI | SLO Target | Error Budget | Burn Rate (Fast) | Burn Rate (Slow) |
|---------|-----|------------|-------------|------------------|------------------|
| **api-gateway** | Availability (non-5xx ratio) | 99.9% (30d) | 0.1% requests | 14.4x → critical | 6.0x → warning |
| **api-gateway** | Latency p99 | ≤ 500ms (30d) | 5% windows | 14.4x → critical | 6.0x → warning |
| **payment-svc** | Availability (success ratio) | 99.99% (30d) | 0.01% requests | 14.4x → critical | 6.0x → warning |
| **payment-svc** | Correctness (debit/credit match) | 99.999% (30d) | 0.001% mismatch | 14.4x → critical | 6.0x → warning |
| **inventory-svc** | Availability (non-5xx ratio) | 99.9% (30d) | 0.1% requests | 14.4x → critical | 6.0x → warning |
| **inventory-svc** | Freshness (sync staleness) | ≤ 60s (30d) | 5% of time | 14.4x → warning | 6.0x → info |

**Key design choices:**
- Multi-window burn rate alerts (Google SRE approach): 5m/1h for fast burns, 30m/6h for slow burns
- Payment service has the tightest budget (99.99% availability, 99.999% correctness) reflecting zero tolerance for financial data corruption
- Inventory freshness uses a gauge-type SLI with eventual consistency acceptable up to 60 seconds

---

## 3. Detection + Correlation + RCA Stack (from W1+W2)

### Detection Layer
The detection layer uses Prometheus metric scraping at 15-second intervals combined with health check polling at 10-second intervals. Anomaly detection applies static thresholds on SLI metrics (availability ratio, latency percentiles) with multi-window burn rate evaluation. The pipeline evaluates both fast-burn (5m/1h windows, factor 14.4) and slow-burn (30m/6h windows, factor 6.0) conditions to distinguish between acute outages and gradual degradation. Current gap: no latency-specific percentile monitoring is implemented — only availability (up/down) is actively detected. See ADR-001 for planned improvements.

### Correlation Layer
Alert correlation currently operates on a per-service basis with temporal grouping. When multiple alerts fire within the same time window, the pipeline groups them by severity and service. However, there is no cross-service correlation — alerts from different services are treated as independent incidents even when they share a common root cause. This results in alert storms during cascading failures (observed: 7 alerts for 1 incident in the W3-D3 reproduction). ADR-001 proposes topology-aware correlation to address this gap.

### RCA Layer
Root cause analysis uses a count-based ranking algorithm: services are scored by (error_rate × severity_weight × temporal_priority), and the service with the highest score is identified as the probable root cause. The temporal priority component gives higher weight to the first service that exhibited anomalous behavior. This approach works for single-service failures (3/5 chaos experiments passed in W3-D2) but fails for cascading failures where the most impacted service is not the root cause. ADR-001 documents the decision to migrate to topology-aware RCA using a service dependency graph.

---

## 4. Reliability Validation (from W3-D2)

Reference: `w3/d2/w3-d2-pack/chaos_report.md`

### Chaos Experiment Scoreboard

| # | Experiment | Fault Type | Detected? | Detection Time | RCA Correct? | Notes |
|---|-----------|------------|-----------|---------------|-------------|-------|
| 1 | API Gateway Kill | availability | ✅ Yes | ~15s | ✅ Yes | Clean detection via health check failure |
| 2 | Payment Service Latency | latency | ❌ No | N/A | ❌ No | No latency-specific detector implemented |
| 3 | Inventory DB Connection Exhaustion | resource | ✅ Yes | ~25s | ⚠️ Partial | Detected failure, but RCA pointed to service not DB |
| 4 | Cache Service Crash Loop | crash-loop | ✅ Yes | ~20s | ✅ Yes | Detected via repeated health check failures |
| 5 | DNS Resolver Failure (Cascading) | cascading | ⚠️ Partial | ~45s | ❌ No | Detected downstream failures but missed DNS as root cause |

**Overall Score: 3/5 experiments detected correctly (60%)**

### Top 3 Gaps

| Priority | Gap | Impact | Mitigation |
|----------|-----|--------|------------|
| 🔴 P0 | No latency degradation detection | Miss all latency-only incidents (Exp #2) | Implement histogram percentile monitoring with per-service thresholds |
| 🔴 P0 | No service dependency graph for RCA | Cannot trace cascading failures to root cause (Exp #5) | Build topology-aware RCA using service mesh or manual dependency config |
| 🟡 P1 | No alert deduplication | Alert fatigue during crash loops, 12 alerts for 1 root cause (Exp #4) | Implement alert grouping with configurable dedup window |

---

## 5. Operational Pattern (from W3-D3)

### Reproduced Outage: AWS S3 2017-02-28 (Cascading Capacity Failure)

The outage was reproduced by simulating a capacity failure in the inventory-svc index subsystem, modeled after the AWS S3 incident where an automation tool accidentally removed a larger-than-intended set of servers from the index subsystem. The reproduction demonstrated a cascading failure pattern: inventory-svc → checkout-svc → api-gateway, with secondary impact on cache-svc and payment-svc.

### Key Learnings

1. **Capacity failures look different from crash failures.** The service remained "up" (responding to health checks intermittently) but could not serve traffic efficiently. The pipeline detected the availability drop but could not identify the root cause as capacity exhaustion vs. service crash.

2. **Recovery can amplify failures.** The auto-restart attempt caused a second failure wave because the index rebuild consumed excessive memory while the service was simultaneously accepting traffic. The pipeline needs to detect recovery oscillation patterns.

3. **Alert storms obscure root causes.** 7 individual alerts across 5 services for a single cascading incident created confusion. Topology-aware correlation (ADR-001) would have reduced this to 1 correlated incident.

### ADR-001 Reference

Based on the gaps observed in both W3-D2 chaos experiments and the W3-D3 outage reproduction, ADR-001 documents the decision to adopt topology-aware RCA over the current count-based approach. The topology-aware approach uses a service dependency graph to trace cascading failures upstream and group related alerts into single correlated incidents.

---

## 6. Cost Model (from W3-D3)

Reference: `w3/d3/w3-d3-pack/cost_model.py`

### Cost Model Output for Current Stack (E-Commerce, 10 services)

```
Parameters:
  num_services: 10
  incidents_per_month: 3
  avg_incident_duration_hours: 1.5
  downtime_cost_per_hour: $50,000
  expected_mttr_reduction: 40%
  aiops_monthly_cost: $15,000

Result:
  monthly_value: $90,000.00
  monthly_cost: $15,000.00
  roi: 6.0
  payback_months: 0.6
  verdict: worth_it
```

### Break-Even Analysis

- **Break-even point:** The platform pays for itself when monthly savings exceed monthly cost. With current parameters, the break-even requires:
  - `incidents × duration × cost_per_hour × mttr_reduction > $15,000`
  - Minimum: 1 incident/month × 0.75 hours × $50,000/hr × 0.4 = $15,000 → **1 incident of 45 minutes per month breaks even**
- **Payback period:** 0.6 months (≈ 18 days) to recover the initial setup cost (3× monthly)
- **Sensitivity:** If downtime cost drops below $12,500/hr, the ROI falls below 1.5 and the verdict shifts to "marginal"

---

## 7. Open Risks

| # | Risk | Severity | Current Status | Mitigation Plan |
|---|------|----------|---------------|-----------------|
| 1 | **No latency degradation detection** — Pipeline only monitors availability, misses latency-only incidents entirely | 🔴 Critical | Unresolved | Implement histogram percentile monitoring (p50, p95, p99) with per-service SLO thresholds. Target: 2-week sprint. |
| 2 | **No service dependency graph** — RCA cannot trace cascading failures, leading to incorrect root cause identification in multi-service incidents | 🔴 Critical | ADR-001 accepted | Implement topology-aware RCA module with DAG traversal. Integrate with Docker Compose labels for auto-discovery. Target: 3-week sprint. |
| 3 | **Alert deduplication absent** — Cascading failures produce alert storms (7+ alerts for 1 incident), causing on-call fatigue | 🟡 High | Unresolved | Add alert grouping with configurable dedup window (default 5 minutes). Group by root cause service + time window. Target: 1-week sprint. |
| 4 | **No resource-level metrics** — Pipeline cannot distinguish between service crash, capacity exhaustion, and dependency failure within a service | 🟡 High | Unresolved | Add connection pool, memory, CPU, disk metrics to Prometheus scrape config. Extend RCA to consider resource-level signals. Target: 2-week sprint. |
| 5 | **Recovery oscillation undetected** — Pipeline treats restart-then-refailure as separate incidents, missing the anti-pattern where premature recovery amplifies failure | 🟢 Medium | Unresolved | Add state machine for service recovery tracking. Detect oscillation pattern (healthy → unhealthy → healthy → unhealthy within 5 min). Target: backlog. |