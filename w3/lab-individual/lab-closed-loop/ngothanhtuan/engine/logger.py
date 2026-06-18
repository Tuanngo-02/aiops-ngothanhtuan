import json
import time
import sys
import os

AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "audit_log.jsonl")

def log_event(event_type, service, action="none", result="none", **kwargs):
    event = {
        "ts": time.time(),
        "event_type": event_type,
        "service": service,
        "action": action,
        "result": result
    }
    event.update(kwargs)
    
    log_line = json.dumps(event)
    
    # Print to stdout
    print(log_line)
    sys.stdout.flush()
    
    # Write to audit log file if path exists or we can create it
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    except:
        pass
    try:
        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Failed to write to audit log: {e}", file=sys.stderr)
