from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List, Optional
import time

app = FastAPI(title="AIOps Pipeline API")

class CorrelateRequest(BaseModel):
    window: int

class RcaRequest(BaseModel):
    cluster: str

@app.get("/alerts")
def get_alerts(since: Optional[int] = None):
    # Mock return list of alerts
    return {
        "status": "success",
        "data": [
            {
                "id": 1,
                "service": "payment-svc",
                "message": "High latency detected",
                "timestamp": int(time.time()) - 10
            }
        ]
    }

@app.post("/correlate")
def correlate_alerts(req: CorrelateRequest):
    # Mock cluster alerts based on window
    return {
        "status": "success",
        "data": {
            "cluster_id": "cluster-1",
            "alerts": [1]
        }
    }

@app.post("/rca")
def perform_rca(req: RcaRequest):
    # Mock root cause analysis
    return {
        "status": "success",
        "data": {
            "root_service": "payment-svc",
            "confidence": 0.85,
            "evidence": ["payment-svc latency spiked to 600ms", "downstream traffic normal"]
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)