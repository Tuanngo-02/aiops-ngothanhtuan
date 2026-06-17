from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import random

app = FastAPI()

REQUEST_COUNT = Counter(
    'cache_svc_requests_total', 'Total number of requests to cache service', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'cache_svc_request_duration_seconds', 'Histogram of request duration to cache service',
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
    return {"message": "Welcome to Cache Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/get")
async def get_cache(key: str):
    # Simulate cache hit/miss
    time.sleep(random.uniform(0.001, 0.01))
    if random.random() > 0.1:
        return {"key": key, "value": f"cached_value_for_{key}", "hit": True}
    else:
        return {"key": key, "value": None, "hit": False}

@app.get("/metrics")
async def metrics():
    return generate_latest()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8009)