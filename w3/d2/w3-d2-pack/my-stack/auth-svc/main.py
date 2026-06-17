from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import random

app = FastAPI()

REQUEST_COUNT = Counter(
    'auth_svc_requests_total', 'Total number of requests to auth service', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'auth_svc_request_duration_seconds', 'Histogram of request duration to auth service',
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
    return {"message": "Welcome to Auth Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/login")
async def login(credentials: dict):
    # Simulate authentication
    time.sleep(random.uniform(0.1, 0.3))
    username = credentials.get("username")
    if username == "testuser":
        return {"status": "login successful", "token": f"fake_jwt_token_for_{username}"}
    else:
        return {"status": "login failed", "error": "invalid credentials"}

@app.get("/metrics")
async def metrics():
    return generate_latest()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)