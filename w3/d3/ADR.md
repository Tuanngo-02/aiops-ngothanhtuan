# ADR-001: Topology-Aware RCA vs Count-Based RCA for Cascading Failure Detection

**Status:** Accepted
**Date:** 2026-06-17
**Author:** Ngo Thanh Tuan
**Context:** AIOps Mini-Platform — Root Cause Analysis Engine Design

---

## Context

During the W3-D3 outage reproduction (AWS S3 2017-02-28 cascading capacity failure), the current AIOps pipeline detected the correct root service (inventory-svc) but failed to:

1. Correlate 7 individual alerts into a single cascading incident (GAP-2 from postmortem)
2. Trace the dependency chain (inventory-svc → checkout-svc → api-gateway) as a unified failure path
3. Distinguish the root cause from downstream symptoms

The current RCA module uses a **count-based approach**: it ranks services by error count/rate and picks the service with the highest anomaly score as the root cause. This works for single-service failures but produces incorrect or incomplete results for cascading failures involving multiple services.

We need to decide on the RCA algorithm architecture for the next iteration of the platform.

---

## Decision

We will adopt a **topology-aware RCA approach** that uses a service dependency graph combined with temporal correlation to trace cascading failures back to their origin.

---

## Alternatives Considered

### Alternative 1: Count-Based RCA (Current Implementation)

**Description:** Rank all services by anomaly score (error rate × severity weight). The service with the highest score is identified as root cause.

**Pros:**
- Simple to implement and maintain
- Low computational cost — O(n) where n = number of services
- No dependency configuration required — works out of the box
- Fast detection time (~18s in current implementation)

**Cons:**
- Cannot trace cascading failures — picks "most impacted" service, not "first failed" service
- In the reproduced outage, it correctly picked inventory-svc only because it happened to have the highest error rate; in scenarios where a downstream service has higher impact (e.g., api-gateway handles more traffic), it would pick the wrong service
- Produces alert storms: 7 alerts for 1 incident in the reproduced outage
- No concept of blast radius or dependency chains
- Cannot handle split-brain or partial failure scenarios where multiple services fail independently

### Alternative 2: Topology-Aware RCA (Selected)

**Description:** Maintain a service dependency graph (DAG). When multiple services fail, trace the failure upstream through the dependency graph using temporal correlation (which service failed first?). Group related alerts into a single incident.

**Pros:**
- Correctly identifies root cause in cascading failures by tracing upstream through dependency graph
- Reduces alert noise: groups related alerts into single correlated incident
- Provides blast radius visualization — shows exactly which services are affected and why
- Supports "what-if" analysis: given service X fails, what would the expected blast radius be?
- Enables proactive dependency health monitoring

**Cons:**
- Requires accurate, up-to-date service dependency graph (manual maintenance or service mesh integration)
- Higher computational cost — O(V + E) graph traversal per incident
- Dependency graph can become stale if services are added/removed without updating the graph
- More complex to implement and debug
- Temporal correlation can be misleading if clocks are not synchronized (requires NTP discipline)

### Alternative 3: Causal-Lag RCA (Statistical)

**Description:** Use Granger causality or transfer entropy on time-series metrics to automatically discover causal relationships between services without a predefined dependency graph.

**Pros:**
- No manual dependency graph required — discovers relationships from data
- Can detect unexpected/undocumented dependencies
- Adapts automatically as architecture changes
- Works across any metric type (latency, error rate, throughput)

**Cons:**
- Requires significant historical data (weeks of metrics) to build reliable causal models
- High computational cost — O(n² × T) where T = time series length
- Prone to false positives from correlated but non-causal metrics (e.g., two services both degrade during high traffic without causal link)
- Slow to adapt to architecture changes — needs retraining period
- Difficult to explain results to on-call engineers ("why does the model think service A caused service B's failure?")
- Not suitable for rare failure modes with insufficient training data

---

## Consequences

### Positive Consequences

1. **Improved cascading failure detection:** In the reproduced outage scenario, topology-aware RCA would have grouped all 7 alerts into 1 incident and traced the dependency chain (inventory-svc → checkout-svc → api-gateway), reducing MTTR by eliminating the time spent correlating alerts manually.

2. **Reduced alert fatigue:** On-call engineers would receive 1 correlated incident page instead of 7 individual service alerts, directly addressing GAP-2 identified in the postmortem.

### Trade-off Consequences

1. **Operational overhead of maintaining dependency graph:** The team must keep the service dependency graph up-to-date as the architecture evolves. If a new service is added without updating the graph, the RCA engine will not trace failures through it. Mitigation: integrate with service mesh (e.g., Istio) to auto-discover dependencies from actual traffic patterns, and validate the graph weekly.

2. **Increased system complexity:** The topology-aware RCA module adds ~500 lines of graph traversal and temporal correlation code, increasing the attack surface for bugs. The dependency graph itself becomes a critical component — if it contains incorrect edges, the RCA will produce wrong results. Mitigation: implement graph validation checks and fallback to count-based RCA when the dependency graph is unavailable.

---

## References

- Postmortem: `postmortem.md` — GAP-2 (no cascading failure correlation)
- AWS S3 2017-02-28 Post-Incident Summary: cascading failure from index subsystem removal
- W3-D2 Chaos Report: Experiment #5 (DNS cascading failure) — RCA missed dns-resolver as root cause
- Nygard, Michael T. "Architecture Decision Records" — ADR template format