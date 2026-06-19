import time
import requests
import yaml
import argparse
import subprocess
import threading
from collections import defaultdict

from engine.metrics import (
    start_metrics_server, 
    ACTION_TOTAL, 
    CIRCUIT_BREAKER_STATE, 
    BLAST_RADIUS_REMAINING, 
    MUTEX_STATE
)
from engine.logger import log_event

# Configuration
CONFIG_PATH = "config.yaml"
ALERTMANAGER_URL = "http://localhost:9093/api/v2/alerts"

# State management
service_locks = defaultdict(threading.Lock)
failure_count = defaultdict(int)
circuit_breaker_open = defaultdict(bool)
action_timestamps = []
restart_timestamps = defaultdict(list)
in_progress_alerts = set() # To avoid duplicate processing

# Load config
def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def clean_old_timestamps(ts_list, window_seconds):
    now = time.time()
    return [t for t in ts_list if now - t <= window_seconds]

def check_blast_radius(config, service):
    global action_timestamps, restart_timestamps
    
    # Clean old timestamps
    action_timestamps = clean_old_timestamps(action_timestamps, 60)
    restart_timestamps[service] = clean_old_timestamps(restart_timestamps[service], 3600)
    
    max_actions_min = config.get("blast_radius", {}).get("max_actions_per_minute", 5)
    max_restarts_hr = config.get("blast_radius", {}).get("max_restarts_per_service_per_hour", 3)
    
    BLAST_RADIUS_REMAINING.labels(service=service).set(max_actions_min - len(action_timestamps))
    
    if len(action_timestamps) >= max_actions_min:
        return False, "Max actions per minute exceeded"
    if len(restart_timestamps[service]) >= max_restarts_hr:
        return False, f"Max restarts per hour exceeded for {service}"
    
    return True, ""

def record_action(service, is_restart=False):
    global action_timestamps, restart_timestamps
    now = time.time()
    action_timestamps.append(now)
    if is_restart:
        restart_timestamps[service].append(now)

def execute_runbook(runbook, service, dry_run=False):
    cmd = ["bash", runbook, "--service", service]
    if dry_run:
        cmd.append("--dry-run")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Timeout"
    except Exception as e:
        return False, "", str(e)

def verify_system(config, alertname, service):
    verify_cfg = config.get("verify_thresholds", {})
    prom_url = verify_cfg.get("prometheus_url", "http://localhost:9090")
    timeout = verify_cfg.get("timeout_seconds", 60)
    poll_interval = verify_cfg.get("poll_interval_seconds", 5)
    required_successes = verify_cfg.get("required_successes", 3)
    
    query_cfg = verify_cfg.get("queries", {}).get(alertname)
    if not query_cfg:
        # If no verify query defined, assume success
        return True
    
    query = query_cfg["query"].replace("service", f'service=~".*{service}.*"')
    # wait, the query in config uses 'service', we should inject the filter.
    # Actually, simpler: replace "(service)" with "(service)" - wait, the query in config is like:
    # histogram_quantile(..., sum(rate(...)) by (le, service))
    # We'll just pass the query directly and check if any returned value for the service meets the threshold.
    # Let's format the query to filter for the specific service.
    # For simplicity, we just append `{service="frontend"}` to the metric, but it's hard to parse arbitrary promql.
    # We will just evaluate the raw query and look at the result for the matching service label.
    
    success_count = 0
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(f"{prom_url}/api/v1/query", params={"query": query_cfg["query"]}, timeout=5)
            data = resp.json()
            
            if data["status"] == "success":
                results = data["data"]["result"]
                # Find our service
                val = None
                for res in results:
                    # check if service name is in labels
                    if service in str(res.get("metric", {}).values()):
                        val = float(res["value"][1])
                        break
                
                if val is not None:
                    import math
                    if math.isnan(val):
                        val = 0.0
                        
                    op = query_cfg["operator"]
                    thresh = float(query_cfg["threshold"])
                    passed = False
                    if op == "<" and val < thresh: passed = True
                    elif op == ">" and val > thresh: passed = True
                    elif op == "==" and val == thresh: passed = True
                    
                    if passed:
                        success_count += 1
                        if success_count >= required_successes:
                            return True
                    else:
                        # Reset success count if it fluctuates
                        success_count = 0
        except Exception as e:
            pass
        
        time.sleep(poll_interval)
        
    return False

def handle_alert(config, alert):
    labels = alert.get("labels", {})
    alertname = labels.get("alertname")
    service = labels.get("service", labels.get("job", "unknown"))
    
    # Strip prefix if it exists in service name
    service_short = service.replace("ronki-", "")
    
    # 1. Check Circuit Breaker
    if circuit_breaker_open[service]:
        log_event("CIRCUIT_BREAKER_HALT", service, alertname, "halted", msg="Circuit breaker is OPEN")
        return

    # 2. Mutex Lock
    lock = service_locks[service]
    if not lock.acquire(blocking=False):
        log_event("SERVICE_LOCK_BUSY", service, alertname, "ignore", msg="Service is currently being remediated")
        return
        
    MUTEX_STATE.labels(service=service).set(1)

    try:
        log_event("ALERT_DETECTED", service, alertname, "detect")
        
        # 3. Decide & Validate
        runbook = config.get("runbook_map", {}).get(alertname)
        if not runbook:
            log_event("NO_RUNBOOK_FOUND", service, alertname, "ignore")
            return
            
        is_multi_step = runbook == "MULTI_STEP_DEPLOY"
        scripts_to_check = config.get("multi_step_map", {}).get(runbook, []) if is_multi_step else [runbook]
        
        registry = config.get("registry", [])
        for script in scripts_to_check:
            if script not in registry:
                log_event("DECISION_VALIDATION_FAILED", service, alertname, "escalate_no_auto_action", bad_runbook=script, raw_decision=runbook)
                return
                
        # 4. Blast Radius Check
        ok, msg = check_blast_radius(config, service)
        if not ok:
            log_event("BLAST_RADIUS_EXCEEDED", service, alertname, "escalate", msg=msg)
            return
            
        # 5. Dry-Run
        if is_multi_step:
            for script in scripts_to_check:
                ok, out, err = execute_runbook(script, service, dry_run=True)
                if not ok:
                    log_event("DRY_RUN_FAIL", service, alertname, script, error=err)
                    return
        else:
            ok, out, err = execute_runbook(runbook, service, dry_run=True)
            if not ok:
                log_event("DRY_RUN_FAIL", service, alertname, runbook, error=err)
                return
        
        log_event("DRY_RUN_PASS", service, alertname, "dry_run")
        
        # 6. Act
        if is_multi_step:
            completed_steps = []
            failed_step = None
            for script in scripts_to_check:
                log_event("RUNBOOK_EXEC", service, alertname, script)
                ok, out, err = execute_runbook(script, service, dry_run=False)
                record_action(service)
                if ok:
                    completed_steps.append(script)
                else:
                    failed_step = script
                    break
                    
            if failed_step:
                log_event("TRANSACTIONAL_STEP_FAIL", service, alertname, failed_step, completed_before_failure=completed_steps)
                ACTION_TOTAL.labels(outcome='fail', runbook=runbook, service=service).inc()
                
                # Rollback
                rolled_back = []
                for step in reversed(completed_steps):
                    rb_script = config.get("multi_step_rollback_map", {}).get(step)
                    if rb_script:
                        log_event("TRANSACTIONAL_ROLLBACK_STEP", service, alertname, rb_script)
                        execute_runbook(rb_script, service, dry_run=False)
                        rolled_back.append(rb_script)
                
                log_event("TRANSACTIONAL_ROLLBACK_COMPLETE", service, alertname, "rollback", rolled_back=rolled_back)
                
                failure_count[service] += 1
                if failure_count[service] >= 3:
                    circuit_breaker_open[service] = True
                    CIRCUIT_BREAKER_STATE.labels(service=service).set(1)
                    log_event("CIRCUIT_OPEN", service, alertname, "halt")
                return
                
        else:
            log_event("RUNBOOK_EXEC", service, alertname, runbook)
            ok, out, err = execute_runbook(runbook, service, dry_run=False)
            record_action(service, is_restart=("restart" in runbook))
            if not ok:
                log_event("ACTION_FAIL", service, alertname, runbook, error=err)
                ACTION_TOTAL.labels(outcome='fail', runbook=runbook, service=service).inc()
                failure_count[service] += 1
                if failure_count[service] >= 3:
                    circuit_breaker_open[service] = True
                    CIRCUIT_BREAKER_STATE.labels(service=service).set(1)
                    log_event("CIRCUIT_OPEN", service, alertname, "halt")
                return
                
        # 7. Verify
        log_event("VERIFY_START", service, alertname, "verify")
        verify_ok = verify_system(config, alertname, service)
        
        if verify_ok:
            log_event("ACTION_SUCCESS", service, alertname, runbook)
            ACTION_TOTAL.labels(outcome='success', runbook=runbook, service=service).inc()
            failure_count[service] = 0 # reset on success
            CIRCUIT_BREAKER_STATE.labels(service=service).set(0)
        else:
            log_event("VERIFY_FAIL", service, alertname, runbook)
            log_event("ROLLBACK_TRIGGERED", service, alertname, runbook)
            
            # Exec Rollback
            rb_script = config.get("rollback_map", {}).get(runbook)
            if rb_script:
                execute_runbook(rb_script, service, dry_run=False)
                log_event("ROLLBACK_EXECUTED", service, alertname, rb_script)
                ACTION_TOTAL.labels(outcome='rollback', runbook=rb_script, service=service).inc()
            
            failure_count[service] += 1
            if failure_count[service] >= 3:
                circuit_breaker_open[service] = True
                CIRCUIT_BREAKER_STATE.labels(service=service).set(1)
                log_event("CIRCUIT_OPEN", service, alertname, "halt")

    except Exception as e:
        log_event("ORCHESTRATOR_ERROR", service, alertname, "error", error=str(e))
    finally:
        # Release Mutex
        lock.release()
        MUTEX_STATE.labels(service=service).set(0)
        in_progress_alerts.discard(alert.get("fingerprint"))

def poll_alertmanager(config):
    while True:
        try:
            resp = requests.get(ALERTMANAGER_URL, timeout=5)
            if resp.status_code == 200:
                alerts = resp.json()
                for alert in alerts:
                    # Only process active alerts
                    if alert.get("status", {}).get("state") == "active":
                        fp = alert.get("fingerprint")
                        if fp not in in_progress_alerts:
                            in_progress_alerts.add(fp)
                            t = threading.Thread(target=handle_alert, args=(config, alert))
                            t.daemon = True
                            t.start()
        except Exception as e:
            log_event("POLL_ERROR", "system", "poll", "error", error=str(e))
            
        time.sleep(15)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=CONFIG_PATH, help="Path to config file")
    args = parser.parse_args()
    
    config = load_config(args.config)
    start_metrics_server(9100)
    
    print(f"Starting closed-loop orchestrator with config {args.config}")
    poll_alertmanager(config)
