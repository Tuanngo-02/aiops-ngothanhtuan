# W3-D3 Submission — Ngo Thanh Tuan

---

## Outage Chosen

- **ID:** 1
- **Name:** AWS S3 2017-02-28
- **Why this one:** The AWS S3 outage is one of the most well-documented cascading capacity failures in cloud history. A simple operational mistake (automation tool removing more servers than intended from the index subsystem) cascaded into a multi-hour outage affecting thousands of downstream services. This pattern — where a capacity reduction in one subsystem creates cascading failures that are harder to recover from than the original issue — is directly relevant to our e-commerce stack where inventory-svc failures cascade through checkout-svc to api-gateway.
- **Failure mode:** cascading

---

## 3 thứ tôi học từ outage này

1. **Capacity failures are fundamentally different from crash failures.** When a service loses capacity (e.g., index subsystem removed) rather than crashing entirely, it can remain "up" while serving errors intermittently. This makes detection harder because health checks may pass while the service is functionally broken. The AIOps pipeline needs to monitor not just "is the service alive?" but "can the service handle its expected load?"

2. **Recovery attempts can amplify the original failure.** In both the real AWS S3 incident and our reproduction, the initial recovery attempt made things worse. The index rebuild consumed excessive resources while the service was accepting traffic, causing a second failure wave. Runbooks must include "shed traffic before rebuilding" as a mandatory step for capacity-type failures, and auto-restart policies need backoff strategies.

3. **Cascading failures require dependency-aware detection.** When inventory-svc failed, our pipeline correctly identified it as the root cause — but only by luck (it happened to have the highest error rate). In a different topology where the downstream service handles more traffic, the pipeline would have picked the wrong root cause. Topology-aware RCA is essential, not optional, for any production AIOps platform.

---

## 1 thứ pipeline của tôi sẽ vẫn miss nếu outage này xảy ra real

- **Pattern:** Slow capacity degradation with partial availability
- **Why miss:** The real AWS S3 outage started with a gradual capacity reduction — the index subsystem lost servers progressively, not all at once. During the early phase (first 5-10 minutes), the service was still responding to most requests but with increasing latency and occasional errors. Our pipeline uses binary availability thresholds (healthy/unhealthy) and would not detect the gradual degradation until it crossed the SLO boundary. By that time, the cascading damage would already be significant. Additionally, the pipeline has no capacity-specific metrics (connection pool usage, queue depth, memory pressure) that would reveal the root cause before it becomes an availability incident.
- **Mitigation idea:** Implement a "capacity pressure" composite metric that combines connection pool utilization, memory usage, and request queue depth into a single early-warning signal. Set warning thresholds at 70% capacity utilization (before any availability impact), giving on-call engineers a 5-10 minute head start to intervene before cascading failures begin.

---

## 1 quyết định trong ADR mà tôi không hoàn toàn chắc

The decision to use **topology-aware RCA** (ADR-001) requires maintaining an accurate service dependency graph. I'm not fully confident this is maintainable at scale. In our current 10-service stack, the dependency graph is simple enough to maintain manually. But in a real production environment with 50-200 microservices, dependencies change frequently as teams add/remove services, introduce new communication patterns, or change routing rules. The graph could become stale within weeks, leading to incorrect RCA results that are *worse* than the simple count-based approach (because engineers would trust the "topology-aware" result more than a "highest error count" result, even when the topology is wrong).

The alternative — causal-lag RCA (Granger causality on time series) — would auto-discover dependencies from data, but requires significant historical data and has false positive risks. I chose topology-aware as the pragmatic middle ground, but the long-term solution may be a hybrid: topology-aware RCA with causal-lag validation, where the statistical model flags when the dependency graph appears outdated.

---

## Cost model verdict cho stack của tôi

- **ROI:** 6.0
- **Payback:** 0.6 tháng
- **Verdict:** worth_it

With 3 incidents/month at $50,000/hour downtime cost and 1.5 hours average duration, the AIOps platform generates $90,000/month in savings (40% MTTR reduction) against $15,000/month operating cost. The platform pays for itself in approximately 18 days. Even with conservative estimates (halving the downtime cost to $25,000/hour), the ROI remains 3.0 — still firmly in "worth_it" territory.