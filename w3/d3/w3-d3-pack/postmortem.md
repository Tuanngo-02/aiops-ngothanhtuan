# Postmortem: Cascading Capacity Failure — Inventory Service Index Subsystem

**Incident ID:** INC-2026-0617-001
**Date:** 2026-06-17
**Author:** Ngo Thanh Tuan
**Status:** Completed
**Severity:** SEV-1 (Critical)

---

## Summary

On 2026-06-17 at 03:35 UTC, the inventory-svc index subsystem was taken offline during a reproduced capacity failure (modeled after the AWS S3 2017-02-28 outage). The loss of the index subsystem caused inventory-svc to return errors for 85% of requests, which cascaded to checkout-svc (504 timeouts) and api-gateway (p99 latency spike to 8.5s). The incident lasted approximately 12 minutes, affecting all customer-facing checkout and product listing operations.

---

## Impact

- **Duration:** 12 minutes (03:35:00 UTC – 03:47:00 UTC)
- **User impact:** All checkout operations failed. Product listing showed stale data. Approximately 100% of checkout requests returned errors during peak failure window.
- **Services affected:** inventory-svc (primary), checkout-svc (cascading), api-gateway (cascading), cache-svc (secondary), payment-svc (queue buildup)
- **Error budget consumed:** inventory-svc: ~5.5% of 30-day budget. api-gateway: ~2.8% of 30-day budget.
- **Revenue impact (estimated):** Approximately 12 minutes × $10,000/hour ≈ $2,000 in lost transactions.

---

## Root Cause

The root cause was a capacity failure in the inventory-svc index subsystem. When the index partition was removed (simulating the AWS S3 billing subsystem attempting to remove a small number of servers but accidentally using an incorrect input that removed a much larger set), the service could no longer perform efficient lookups. All LIST and GET operations required full table scans, which overwhelmed the service's connection pool and memory. The cascading failure propagated through the dependency chain: inventory-svc → checkout-svc → api-gateway.

The recovery was delayed because the initial auto-restart attempt caused the service to attempt an index rebuild while simultaneously serving traffic, which consumed 95% of available memory and caused a second failure wave.

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 2026-06-17 03:30:00 | Reproduction environment started. All 10 services healthy. Baseline metrics confirmed. |
| 2026-06-17 03:35:00 | Capacity fault injected: inventory-svc index subsystem taken offline. |
| 2026-06-17 03:35:08 | inventory-svc error rate jumped from 0% to 85%. HTTP 503 responses observed. |
| 2026-06-17 03:35:18 | AIOps pipeline detected inventory-svc availability SLO breach. Alert fired (severity: critical, burn rate: 14.4x). Detection latency: 18 seconds. |
| 2026-06-17 03:35:25 | checkout-svc started returning 504 Gateway Timeout due to dependency on inventory-svc for stock validation. |
| 2026-06-17 03:35:42 | api-gateway p99 latency spiked to 8500ms due to cascading backpressure from checkout-svc. |
| 2026-06-17 03:36:00 | AIOps pipeline RCA identified inventory-svc as root cause (confidence: 0.72). Cascading chain partially detected. |
| 2026-06-17 03:36:15 | cache-svc hit rate dropped from 95% to 12%. Inventory cache entries invalidated. |
| 2026-06-17 03:36:30 | Docker healthcheck triggered auto-restart of inventory-svc (restart #1). |
| 2026-06-17 03:37:00 | inventory-svc partially recovered. Error rate dropped to 30%. |
| 2026-06-17 03:38:00 | inventory-svc error rate returned to 80%. Index rebuild consumed excessive memory, overwhelming the recovering service. |
| 2026-06-17 03:40:00 | inventory-svc memory usage reached 95%. OOM risk detected. |
| 2026-06-17 03:42:00 | notification-svc sending 200 alerts/min. Alert storm from cascading failures. |
| 2026-06-17 03:45:00 | Capacity fault removed. Index subsystem restored manually. |
| 2026-06-17 03:46:30 | inventory-svc fully recovered. Error rate = 0%. |
| 2026-06-17 03:47:00 | All services recovered. api-gateway p99 latency returned to 52ms. System nominal. |

---

## Detection

### What the AIOps pipeline detected correctly
- inventory-svc availability breach was detected in **18 seconds** (within the 30-second target)
- The correct root service (inventory-svc) was identified by the RCA module
- Downstream impacts on checkout-svc and api-gateway were detected via individual alerts

### Detection Gaps

**GAP-1: No resource-level root cause analysis**
The pipeline correctly identified inventory-svc as the failing service, but could not determine *why* it was failing. The actual root cause was capacity exhaustion in the index subsystem, but the pipeline only detected "service returning errors." This distinction matters because the mitigation strategy differs significantly: a service crash requires a restart, while a capacity issue requires traffic shedding and gradual index rebuild.

**GAP-2: No cascading failure correlation**
The pipeline fired 7 individual alerts across 5 services instead of correlating them as a single cascading incident. The on-call engineer received separate pages for inventory-svc, checkout-svc, api-gateway, cache-svc, and notification-svc — making it harder to understand the blast radius and prioritize response. A topology-aware correlation engine would have grouped these into one incident with a dependency chain visualization.

**GAP-3: Recovery oscillation not detected**
The pipeline treated the initial recovery (T+2min, 30% error rate) and subsequent re-failure (T+3min, 80% error rate) as separate events. It did not detect the "recovery oscillation" anti-pattern, where premature recovery attempts under load make the situation worse. This pattern is critical for capacity-type failures.

---

## Contributing Factors

- The index subsystem had no circuit breaker to prevent cascading load during rebuild
- Auto-restart policy did not include a backoff period, causing the service to accept traffic before the index was fully rebuilt
- No load shedding mechanism existed to protect the service during recovery
- The dependency between checkout-svc and inventory-svc had no fallback (e.g., cached stock levels or degraded mode)
- Alert routing did not deduplicate related alerts from the same root cause

---

## Action Items

| Priority | Action | Owner | Status |
|----------|--------|-------|--------|
| P0 | Implement resource-level metrics in AIOps pipeline (connection pool, memory, CPU, disk) | Platform Team | TODO |
| P0 | Add topology-aware cascading failure correlation to RCA module | Platform Team | TODO |
| P1 | Add circuit breaker between checkout-svc and inventory-svc | Service Team | TODO |
| P1 | Implement alert deduplication with 5-minute grouping window | Platform Team | TODO |
| P2 | Add graceful degradation mode for checkout-svc (use cached stock levels when inventory-svc unavailable) | Service Team | TODO |
| P2 | Configure auto-restart with exponential backoff to prevent recovery oscillation | Infra Team | TODO |
| P3 | Add recovery oscillation detection pattern to AIOps pipeline | Platform Team | TODO |

---

## Lessons Learned

1. **Capacity failures behave differently from crash failures.** A service can be "up" but unable to serve traffic efficiently. The AIOps pipeline must distinguish between availability (service reachable) and capacity (service able to handle load).

2. **Cascading failures require dependency-aware detection.** Individual service alerts create alert storms that obscure the root cause. Topology-aware correlation is essential for multi-service architectures.

3. **Recovery can make things worse.** Premature restarts under load can cause a second failure wave. Auto-recovery policies need backoff strategies and health checks that verify capacity, not just connectivity.

---

## Blameless Analysis Notes

- The capacity fault was reproduced intentionally to validate the AIOps pipeline, modeled after the well-documented AWS S3 2017-02-28 incident
- The original AWS incident was caused by an automation tool that removed more servers than intended from the S3 index subsystem
- No individual actions are attributed; the focus is on systemic improvements to detection, correlation, and recovery mechanisms