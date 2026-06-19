from fastapi import FastAPI
app = FastAPI()
@app.get("/{path:path}")
async def read_root(path: str = "/"):
    return {"service": "auth-svc", "path": path}
