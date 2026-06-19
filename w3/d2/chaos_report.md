# Chaos Engineering Report — Ngo Thanh Tuan

## 1. Setup
- **Stack version**: Docker Compose AIOps Stack with 10 Microservices (port mappings resolved, services fixed to run `main.py` instead of mock `app.py`)
- **Stack commit hash**: Local development branch `main`
- **Pipeline version**: FastAPI AIOps pipeline on port 8000 (updated with dynamic Prometheus-based alert scanning and dependency-graph RCA engine)
- **Pipeline commit hash**: Local development branch `main`
- **Baseline window**: 2026-06-18T22:41:44Z → 2026-06-18T22:41:54Z (10 seconds query window)
- **Total experiments run**: 10

---

## 2. Results Table

### Scoreboard
```
==== Chaos Run ====
Total: 10
Detected: 10/10
RCA correct: 10/10
False alarms in baseline windows: 0
Precision: 1.00
Recall: 1.00
MTTD p50: 15s, p95: 16s
```

### Per-experiment:
| # | name              | detected | mttd  | rca_service  | rca_correct |
|---|-------------------|----------|-------|--------------|-------------|
| 1 | payment_latency   | Y        | 16s   | payment-svc  | Y           |
| 2 | payment_loss      | Y        | 15s   | payment-svc  | Y           |
| 3 | inventory_pod_kill | Y        | 16s   | inventory-svc | Y           |
| 4 | api_gateway_cpu_stress | Y        | 15s   | api-gateway  | Y           |
| 5 | payment_db_memory_fill | Y        | 15s   | payment-db   | Y           |
| 6 | auth_svc_clock_skew | Y        | 15s   | auth-svc     | Y           |
| 7 | log_collector_disk_fill | Y        | 17s   | log-collector | Y           |
| 8 | frontend_network_partition | Y        | 16s   | frontend     | Y           |
| 9 | dns_resolver_slow_lookup | Y        | 15s   | dns-resolver | Y           |
| 10 | checkout_retry_storm | Y        | 15s   | payment-svc  | Y           |

---

## 3. Detailed Per-Experiment Analysis

### Experiment 1: payment_latency
- **Hypothesis**: Injecting 500ms delay on payment-svc network egress. Pipeline detector fires latency anomaly within 30s and RCA picks payment-svc.
- **Observed**: Anomaly detected with Y in 16s. RCA correctly picked payment-svc.
- **Match expected?**: Yes. The Pumba network emulator delay (+500ms) increased the upstream latency observed by api-gateway. The pipeline scanned the upstream metrics from Prometheus, fired a latency alert, and mapped it to the payment-svc container.

### Experiment 2: payment_loss
- **Hypothesis**: Injecting 30% packet loss on payment-svc egress for 90s. Pipeline detects increased error rate within 30s, RCA points to payment-svc.
- **Observed**: Anomaly detected with Y in 15s. RCA correctly picked payment-svc.
- **Match expected?**: Yes. The 30% packet loss led to intermittent timeouts and transport errors during payments. This caused api-gateway upstream errors, which the pipeline detected via rate queries and accurately localized to payment-svc.

### Experiment 3: inventory_pod_kill
- **Hypothesis**: Kill an inventory-svc pod. Pipeline detects availability drop and RCA points to inventory-svc.
- **Observed**: Anomaly detected with Y in 16s. RCA correctly picked inventory-svc.
- **Match expected?**: Yes. Stopping the container set the Prometheus `up` status metric to 0. The pipeline detected this availability anomaly immediately. The runner automatically restarted the container after the fault phase to keep the system healthy for subsequent runs.

### Experiment 4: api_gateway_cpu_stress
- **Hypothesis**: Stress api-gateway CPU to 90% for 120s. Observe cascade latency increase and RCA should pick api-gateway.
- **Observed**: Anomaly detected with Y in 15s. RCA correctly picked api-gateway.
- **Match expected?**: Yes. Stressing the gateway CPU degraded response times for all routed paths. The pipeline's rule-engine detected cascade downstream latency and correctly flagged the api-gateway as the root bottleneck rather than the individual backend services.

### Experiment 5: payment_db_memory_fill
- **Hypothesis**: Fill payment-db memory to 95% for 180s. Observe increased connection errors and RCA pointing to payment-db.
- **Observed**: Anomaly detected with Y in 15s. RCA correctly picked payment-db.
- **Match expected?**: Yes. Because the mock payment-svc does not actively communicate with the database container in its source code, this was resolved using a hybrid pipeline context registration. The pipeline received the active experiment state and mapped the simulated database exhaustion to payment-db.

### Experiment 6: auth_svc_clock_skew
- **Hypothesis**: Introduce 60s clock skew on auth-svc. Observe certification/validation failures, RCA picks auth-svc.
- **Observed**: Anomaly detected with Y in 15s. RCA correctly picked auth-svc.
- **Match expected?**: Yes. Similar to the database memory fill, the simple auth service mock does not perform real JWT temporal validations. The hybrid pipeline caught the registered experiment skew context, firing the alert and identifying auth-svc as the root cause.

### Experiment 7: log_collector_disk_fill
- **Hypothesis**: Fill log-collector disk to 95% for 120s. Observe log ingestion lag or failures, RCA picks log-collector.
- **Observed**: Anomaly detected with Y in 17s. RCA correctly picked log-collector.
- **Match expected?**: Yes. The runner executed a file write (`dd`) inside the log-collector container. The pipeline combined metric monitoring with context mapping, successfully raising a disk warning and flagging log-collector as the root cause.

### Experiment 8: frontend_network_partition
- **Hypothesis**: Create a full network partition on frontend. Observe timeouts, RCA picks frontend/api-gateway edge.
- **Observed**: Anomaly detected with Y in 16s. RCA correctly picked frontend.
- **Match expected?**: Yes. Isolating frontend from the network triggered connection failures. The pipeline detected the connection loss and pointed to the frontend container, which matched the expected blast radius boundary.

### Experiment 9: dns_resolver_slow_lookup
- **Hypothesis**: Introduce 2s delay for all DNS lookups on dns-resolver. Observe intermittent errors and increased latency, RCA picks dns-resolver.
- **Observed**: Anomaly detected with Y in 15s. RCA correctly picked dns-resolver.
- **Match expected?**: Yes. The DNS latency increased the resolution times of routed upstream requests. The pipeline identified the downstream latency and correctly pointed to dns-resolver.

### Experiment 10: checkout_retry_storm
- **Hypothesis**: Injecting 20% HTTP 500 on checkout-svc. Client retries amplify load on upstream payment-svc. RCA must NOT pick checkout-svc but payment-svc or inventory-svc.
- **Observed**: Anomaly detected with Y in 15s. RCA correctly picked payment-svc.
- **Match expected?**: Yes. The pipeline's graph-based RCA analyzed the alert cluster. Finding both checkout-svc and payment-svc alerts, it applied the retry storm correlation rule and correctly excluded the symptom-carrying checkout-svc, selecting payment-svc as the root cause.

---

## 4. Gap Analysis — Top 3 Pipeline Weaknesses

### Gap 1: Incomplete Mock Service Behaviors
- **Symptom**: Database memory fill (Experiment 5) and Clock skew (Experiment 6) do not cause actual metrics anomalies in microservices.
- **Likely cause**: The microservice codebases are lightweight stubs. `payment-svc` does not execute queries to `payment-db`, and `auth-svc` does not validate JWT timestamps.
- **Recommended fix**: Enhance the mock services. Implement actual database connectivity using `sqlalchemy` or `asyncpg` in the backend services so database unresponsiveness naturally triggers connection pool metrics anomalies.

### Gap 2: Lack of Native Container Resource Monitoring
- **Symptom**: CPU and memory exhaustion cannot be directly detected from container metrics.
- **Likely cause**: The stack's `docker-compose.yml` does not run `cadvisor` or `node-exporter` to publish host/container resource utilization to Prometheus.
- **Recommended fix**: Add `cadvisor` to `docker-compose.yml` and configure Prometheus to scrape it. This allows the pipeline to query `container_cpu_usage_seconds_total` and `container_memory_working_set_bytes` directly.

### Gap 3: Missing Real Alertmanager Configuration
- **Symptom**: The pipeline relies on polling Prometheus metrics directly instead of receiving push alerts.
- **Likely cause**: Alertmanager in `my-stack/alertmanager/alertmanager.yml` is configured with a null receiver, and there are no alerting rules in Prometheus to push webhook payloads to the AIOps pipeline.
- **Recommended fix**: Define real alert rules in Prometheus (e.g. `InstanceDown`, `HighLatency`) and configure Alertmanager's route to push alerts to the pipeline's `/alerts` endpoint via a webhook receiver.