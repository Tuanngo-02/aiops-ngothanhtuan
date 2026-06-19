from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import random

app = FastAPI()

REQUEST_COUNT = Counter(
    'inventory_svc_requests_total', 'Total number of requests to inventory service', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'inventory_svc_request_duration_seconds', 'Histogram of request duration to inventory service',
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
    return {"message": "Welcome to Inventory Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/items")
async def get_items():
    # Simulate inventory check
    time.sleep(random.uniform(0.05, 0.2))
    return {"items": [{"id": 1, "name": "Laptop", "quantity": 50}, {"id": 2, "name": "Keyboard", "quantity": 100}]}

@app.get("/metrics")
async def metrics():
    from fastapi import Response
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)