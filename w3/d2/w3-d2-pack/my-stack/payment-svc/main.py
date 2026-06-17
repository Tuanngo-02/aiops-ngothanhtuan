from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Summary
import uvicorn
import time
import random

app = FastAPI()

REQUEST_COUNT = Counter(
    'payment_svc_requests_total', 'Total number of requests to payment service', ['endpoint']
)
# Using Summary instead of Histogram for simplicity in mock
REQUEST_LATENCY = Summary(
    'payment_svc_request_duration_seconds', 'Summary of request duration to payment service',
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
    return {"message": "Welcome to Payment Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/process-payment")
async def process_payment():
    # Simulate payment processing time
    time.sleep(random.uniform(0.1, 0.5)) 
    return {"status": "payment processed successfully", "transaction_id": f"txn_{int(time.time())}"}

@app.get("/metrics")
async def metrics():
    return generate_latest()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)