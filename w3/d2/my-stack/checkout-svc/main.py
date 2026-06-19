from fastapi import FastAPI, Request
from prometheus_client import generate_latest, Counter, Histogram
import uvicorn
import time
import random
import requests

app = FastAPI()

REQUEST_COUNT = Counter(
    'checkout_svc_requests_total', 'Total number of requests to checkout service', ['endpoint']
)
REQUEST_LATENCY = Histogram(
    'checkout_svc_request_duration_seconds', 'Histogram of request duration to checkout service',
    ['endpoint']
)

# Assuming these are the service URLs available in the docker network
PAYMENT_SVC_URL = "http://payment-svc:8001"
INVENTORY_SVC_URL = "http://inventory-svc:8002"
NOTIFICATION_SVC_URL = "http://notification-svc:8003" # Assuming notification svc is used by checkout

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
    return {"message": "Welcome to Checkout Service!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/checkout")
async def checkout(order_details: dict):
    print(f"Received order: {order_details}")
    try:
        # Call payment service
        payment_response = requests.post(f"{PAYMENT_SVC_URL}/process-payment", json={"order": order_details})
        payment_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        payment_result = payment_response.json()

        # Call inventory service
        inventory_response = requests.get(f"{INVENTORY_SVC_URL}/items") # Simplified, assuming this updates inventory
        inventory_response.raise_for_status()
        inventory_result = inventory_response.json()

        # Call notification service
        notification_response = requests.post(f"{NOTIFICATION_SVC_URL}/notify", json={"message": "Order processed", "order_id": payment_result.get("transaction_id")})
        notification_response.raise_for_status()
        notification_result = notification_response.json()

        return {"status": "checkout successful", "payment": payment_result, "inventory": inventory_result, "notification": notification_result}

    except requests.exceptions.RequestException as e:
        print(f"Error during checkout: {e}")
        return {"status": "checkout failed", "error": str(e)}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {"status": "checkout failed", "error": "An unexpected error occurred"}

@app.get("/metrics")
async def metrics():
    from fastapi import Response
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)