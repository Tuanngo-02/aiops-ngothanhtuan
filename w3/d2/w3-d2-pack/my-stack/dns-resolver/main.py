from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import random

app = FastAPI()

REQUEST_COUNT = Counter(
    'dns_resolver_requests_total', 'Total number of requests to DNS resolver', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'dns_resolver_request_duration_seconds', 'Histogram of request duration to DNS resolver',
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
    return {"message": "Welcome to DNS Resolver Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/resolve")
async def resolve_dns(hostname: str):
    # Simulate DNS resolution
    time.sleep(random.uniform(0.01, 0.1))
    return {"hostname": hostname, "ip": f"192.168.1.{random.randint(1, 254)}"}

@app.get("/metrics")
async def metrics():
    return generate_latest()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8008)