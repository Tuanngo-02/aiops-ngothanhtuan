from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import random

app = FastAPI()

REQUEST_COUNT = Counter(
    'log_collector_requests_total', 'Total number of requests to log collector', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'log_collector_request_duration_seconds', 'Histogram of request duration to log collector',
    ['endpoint']
)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(process_time)
    REQUEST_COUNT.labels(endpoint=request.url.path).inc()
    return response

@app.get("/")
async def read_root():
    return {"message": "Welcome to Log Collector Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/log")
async def receive_log(log_entry: dict):
    # Simulate receiving and processing logs
    print(f"Received log: {log_entry}")
    time.sleep(random.uniform(0.01, 0.05))
    return {"status": "log received", "log_id": f"log_{int(time.time())}"}

@app.get("/metrics")
async def metrics():
    return generate_latest()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8007)