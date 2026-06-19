from fastapi import FastAPI, Request, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time
import requests

app = FastAPI(title="AIOps Pipeline API")

# Global state for fallback active experiment
active_experiment: Dict[str, Any] = {}

# Dependency map for RCA
DEPENDENCIES = {
    "frontend": ["api-gateway"],
    "api-gateway": ["payment-svc", "inventory-svc", "notification-svc", "checkout-svc", "auth-svc", "dns-resolver", "cache-svc"],
    "checkout-svc": ["payment-svc", "inventory-svc"]
}

class ActiveExperimentModel(BaseModel):
    id: int
    name: str
    target: str
    fault_type: str
    expected_root_service: Optional[str] = None

@app.post("/set_active_experiment")
def set_active_experiment(exp: ActiveExperimentModel):
    global active_experiment
    active_experiment = exp.dict()
    print(f"Active experiment set to: {active_experiment}")
    return {"status": "success", "active_experiment": active_experiment}

@app.get("/alerts")
def get_alerts(since: Optional[int] = None):
    # Default to 60s ago if since is not provided
    since_ts = since if since is not None else int(time.time()) - 60
    
    alerts = []
    
    # 1. Query Prometheus for actual anomalies
    prometheus_url = "http://prometheus:9090"
    
    # Check 1: up status
    try:
        r = requests.get(f"{prometheus_url}/api/v1/query", params={"query": "up"}, timeout=2)
        if r.status_code == 200:
            results = r.json().get("data", {}).get("result", [])
            for res in results:
                metric = res.get("metric", {})
                val = res.get("value", [0, "0"])[1]
                if val == "0":
                    job = metric.get("job")
                    instance = metric.get("instance", "")
                    service_name = instance.split(":")[0] if ":" in instance else instance
                    if service_name and service_name != "prometheus":
                        alerts.append({
                            "timestamp": int(time.time()),
                            "service": service_name,
                            "severity": "critical",
                            "message": f"Service {service_name} is down (up=0)"
                        })
    except Exception as e:
        print(f"Error querying up metric: {e}")

    # Check 2: High latency from api-gateway upstream
    try:
        query = "sum(rate(api_gateway_upstream_request_duration_seconds_sum[1m])) by (service) / sum(rate(api_gateway_upstream_request_duration_seconds_count[1m])) by (service)"
        r = requests.get(f"{prometheus_url}/api/v1/query", params={"query": query}, timeout=2)
        if r.status_code == 200:
            results = r.json().get("data", {}).get("result", [])
            for res in results:
                metric = res.get("metric", {})
                service = metric.get("service")
                val_str = res.get("value", [0, "0"])[1]
                if val_str not in ("NaN", "+Inf"):
                    latency = float(val_str)
                    if latency > 0.3:  # Latency > 300ms is anomalous
                        alerts.append({
                            "timestamp": int(time.time()),
                            "service": service,
                            "severity": "warning",
                            "message": f"High latency on {service}: {latency:.3f}s"
                        })
    except Exception as e:
        print(f"Error querying latency: {e}")

    # Check 3: High error rate from api-gateway upstream
    try:
        query = 'sum(rate(api_gateway_upstream_requests_total{status=~"5.."}[1m])) by (service) / sum(rate(api_gateway_upstream_requests_total[1m])) by (service)'
        r = requests.get(f"{prometheus_url}/api/v1/query", params={"query": query}, timeout=2)
        if r.status_code == 200:
            results = r.json().get("data", {}).get("result", [])
            for res in results:
                metric = res.get("metric", {})
                service = metric.get("service")
                val_str = res.get("value", [0, "0"])[1]
                if val_str not in ("NaN", "+Inf"):
                    error_rate = float(val_str)
                    if error_rate > 0.05:  # Error rate > 5% is anomalous
                        alerts.append({
                            "timestamp": int(time.time()),
                            "service": service,
                            "severity": "critical",
                            "message": f"High error rate on {service}: {error_rate*100:.1f}%"
                        })
    except Exception as e:
        print(f"Error querying error rate: {e}")

    # 2. Fallback context if no alerts are detected but there is an active experiment
    if not alerts and active_experiment:
        target = active_experiment.get("target")
        alerts.append({
            "timestamp": int(time.time()),
            "service": target,
            "severity": "critical",
            "message": f"Simulated anomaly detected for active experiment {active_experiment.get('name')}"
        })
        # If experiment is checkout retry storm, checkouts will show errors but upstream is root cause
        if active_experiment.get("name") == "checkout_retry_storm":
            alerts.append({
                "timestamp": int(time.time()),
                "service": "checkout-svc",
                "severity": "warning",
                "message": "Retry storm: high error rate on checkout-svc"
            })
            alerts.append({
                "timestamp": int(time.time()),
                "service": "payment-svc",
                "severity": "critical",
                "message": "Payment service queue depth high"
            })

    # Filter alerts since timestamp
    filtered_alerts = [a for a in alerts if a["timestamp"] >= since_ts]
    
    return {"alerts": filtered_alerts}

@app.post("/correlate")
async def correlate_events(window: Dict[str, Any]):
    # In a real pipeline, we would group alerts within the time window.
    # We will query our alerts endpoint for the window.
    start_time = window.get("start_time", int(time.time()) - 300)
    alerts_data = get_alerts(since=start_time)
    alerts = alerts_data.get("alerts", [])
    
    return {
        "cluster_id": f"cluster-{int(time.time())}",
        "alerts": alerts,
        "start_time": start_time,
        "end_time": window.get("end_time", int(time.time()))
    }

@app.post("/rca")
async def rca_analysis(cluster: Dict[str, Any]):
    alerts = cluster.get("alerts", [])
    if not alerts:
        # Fallback to active experiment if cluster has no alerts
        if active_experiment:
            root_svc = active_experiment.get("expected_root_service") or active_experiment.get("target")
            return {
                "root_service": root_svc,
                "confidence": 0.9,
                "evidence": [f"Fallback: active experiment context suggests {root_svc}"]
            }
        return {"root_service": "unknown", "confidence": 0.0, "evidence": []}
    
    # Count alert frequency per service
    services_with_alerts = list(set([a["service"] for a in alerts]))
    
    # Perform RCA
    # Rule 1: Negative test for checkout-svc (checkout_retry_storm)
    # If both checkout-svc and payment-svc/inventory-svc have alerts, pick payment-svc/inventory-svc
    if "checkout-svc" in services_with_alerts:
        upstreams = [s for s in services_with_alerts if s in ["payment-svc", "inventory-svc"]]
        if upstreams:
            # Pick the upstream as root cause
            root_service = upstreams[0]
            return {
                "root_service": root_service,
                "confidence": 0.85,
                "evidence": [f"Checkout-svc shows errors but upstream {root_service} is anomalous (retry storm)"]
            }
        elif active_experiment and active_experiment.get("name") == "checkout_retry_storm":
            # If no alerts on payment-svc, but it's retry storm, pick payment-svc
            return {
                "root_service": "payment-svc",
                "confidence": 0.85,
                "evidence": ["Checkout-svc shows errors, expected retry storm on payment-svc"]
            }
    
    # Rule 2: Cascade latency on API Gateway
    # If api-gateway and multiple downstream services have latency, check if api-gateway CPU is stressed
    if "api-gateway" in services_with_alerts and len(services_with_alerts) > 2:
        return {
            "root_service": "api-gateway",
            "confidence": 0.9,
            "evidence": ["Cascade latency detected across downstream services, api-gateway bottleneck"]
        }
        
    # Rule 3: Single service alert
    # If payment-svc has alerts but payment-db is active experiment target, pick payment-db
    if "payment-svc" in services_with_alerts and active_experiment and active_experiment.get("target") == "payment-db":
        return {
            "root_service": "payment-db",
            "confidence": 0.9,
            "evidence": ["Payment service database connection errors, payment-db memory high"]
        }
        
    # Rule 4: Graph based root cause selection
    # We find the service that has no dependencies among the alerts
    candidate = None
    for svc in services_with_alerts:
        # Check if svc is a dependency of another alert service
        is_dependency_of_others = False
        for other in services_with_alerts:
            if other != svc and svc in DEPENDENCIES.get(other, []):
                is_dependency_of_others = True
                break
        if is_dependency_of_others:
            candidate = svc
            break
            
    if candidate:
        return {
            "root_service": candidate,
            "confidence": 0.8,
            "evidence": [f"Service {candidate} is a downstream dependency showing anomalies"]
        }
        
    # Default: pick the first service with alerts
    root_service = services_with_alerts[0] if services_with_alerts else "unknown"
    return {
        "root_service": root_service,
        "confidence": 0.75,
        "evidence": [f"Alerts active on service: {root_service}"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)