import os
from prometheus_client import start_http_server, Counter, Gauge

# Define Prometheus metrics
ACTION_TOTAL = Counter("closed_loop_actions_total", "Total closed-loop actions executed", ["service", "runbook", "outcome"])
CIRCUIT_BREAKER_STATE = Gauge("closed_loop_circuit_breaker_state", "Circuit-breaker state per service (0=closed 1=open)", ["service"])
BLAST_RADIUS_REMAINING = Gauge("closed_loop_blast_radius_remaining", "Remaining actions allowed in the current blast-radius window", ["service"])
MUTEX_STATE = Gauge("closed_loop_mutex_locked", "Per-service mutex state (0=free 1=locked)", ["service"])

def start_metrics_server(port=9100):
    start_http_server(port)
    print(f"Metrics server started on port {port}")
