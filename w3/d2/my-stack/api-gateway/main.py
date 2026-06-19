from fastapi import FastAPI, Request, HTTPException
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import requests
import os

app = FastAPI()

REQUEST_COUNT = Counter(
    'api_gateway_requests_total', 'Total number of requests to API Gateway', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'api_gateway_request_duration_seconds', 'Histogram of request duration to API Gateway',
    ['endpoint']
)
UPSTREAM_REQUEST_COUNT = Counter(
    'api_gateway_upstream_requests_total', 'Total number of requests to upstream services', ['service', 'endpoint']
)
UPSTREAM_LATENCY = Histogram(
    'api_gateway_upstream_request_duration_seconds', 'Histogram of request duration to upstream services',
    ['service', 'endpoint']
)

# Upstream service URLs (using Docker Compose service names)
PAYMENT_SVC_URL = os.getenv("PAYMENT_SVC_URL", "http://payment-svc:8001")
INVENTORY_SVC_URL = os.getenv("INVENTORY_SVC_URL", "http://inventory-svc:8002")
NOTIFICATION_SVC_URL = os.getenv("NOTIFICATION_SVC_URL", "http://notification-svc:8003")
CHECKOUT_SVC_URL = os.getenv("CHECKOUT_SVC_URL", "http://checkout-svc:8004")
AUTH_SVC_URL = os.getenv("AUTH_SVC_URL", "http://auth-svc:8005")
DNS_RESOLVER_URL = os.getenv("DNS_RESOLVER_URL", "http://dns-resolver:8008")
CACHE_SVC_URL = os.getenv("CACHE_SVC_URL", "http://cache-svc:8009")

async def forward_request(service_name: str, base_url: str, path: str, request: Request):
    url = f"{base_url}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    headers = dict(request.headers)
    if "host" in headers:
        del headers["host"]
    method = request.method
    
    start_time = time.time()
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            try:
                json_data = await request.json()
            except Exception:
                json_data = None
            response = requests.post(url, json=json_data, headers=headers)
        else:
            raise HTTPException(status_code=405, detail="Method Not Allowed")
            
        UPSTREAM_LATENCY.labels(service=service_name, endpoint=f"/{path}").observe(time.time() - start_time)
        UPSTREAM_REQUEST_COUNT.labels(service=service_name, endpoint=f"/{path}").inc()
        
        return response.json()
    except requests.exceptions.RequestException as e:
        UPSTREAM_LATENCY.labels(service=service_name, endpoint=f"/{path}").observe(time.time() - start_time)
        UPSTREAM_REQUEST_COUNT.labels(service=service_name, endpoint=f"/{path}").inc()
        raise HTTPException(status_code=500, detail=f"Upstream service {service_name} error: {e}")

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
    return {"message": "Welcome to API Gateway!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/payment/{path:path}")
async def forward_payment(path: str, request: Request):
    return await forward_request("payment-svc", PAYMENT_SVC_URL, path, request)

@app.post("/payment/{path:path}")
async def forward_payment_post(path: str, request: Request):
    return await forward_request("payment-svc", PAYMENT_SVC_URL, path, request)

@app.get("/inventory/{path:path}")
async def forward_inventory(path: str, request: Request):
    return await forward_request("inventory-svc", INVENTORY_SVC_URL, path, request)

@app.get("/notification/{path:path}")
async def forward_notification(path: str, request: Request):
    return await forward_request("notification-svc", NOTIFICATION_SVC_URL, path, request)

@app.post("/notification/{path:path}")
async def forward_notification_post(path: str, request: Request):
    return await forward_request("notification-svc", NOTIFICATION_SVC_URL, path, request)

@app.get("/checkout/{path:path}")
async def forward_checkout(path: str, request: Request):
    return await forward_request("checkout-svc", CHECKOUT_SVC_URL, path, request)

@app.post("/checkout/{path:path}")
async def forward_checkout_post(path: str, request: Request):
    return await forward_request("checkout-svc", CHECKOUT_SVC_URL, path, request)

@app.get("/auth/{path:path}")
async def forward_auth(path: str, request: Request):
    return await forward_request("auth-svc", AUTH_SVC_URL, path, request)

@app.post("/auth/{path:path}")
async def forward_auth_post(path: str, request: Request):
    return await forward_request("auth-svc", AUTH_SVC_URL, path, request)

@app.get("/dns/{path:path}")
async def forward_dns(path: str, request: Request):
    return await forward_request("dns-resolver", DNS_RESOLVER_URL, path, request)

@app.get("/cache/{path:path}")
async def forward_cache(path: str, request: Request):
    return await forward_request("cache-svc", CACHE_SVC_URL, path, request)

@app.get("/metrics")
async def metrics():
    from fastapi import Response
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)