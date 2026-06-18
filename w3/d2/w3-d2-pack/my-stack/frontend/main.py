from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import requests

app = FastAPI()

REQUEST_COUNT = Counter(
    'frontend_requests_total', 'Total number of requests to frontend', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'frontend_request_duration_seconds', 'Histogram of request duration to frontend',
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
    return {"message": "Welcome to Frontend Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/metrics")
async def metrics():
    from fastapi import Response
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)