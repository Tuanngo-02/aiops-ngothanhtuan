# serve.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from pipeline import HISTORY, process_batch, GRAPH

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('aiops')

app = FastAPI(
    title='AIOps Incident Pipeline',
    version='1.0.0',
    description='Correlate alerts → RCA → suggest action',
)

# --- Input schema ---
class Alert(BaseModel):
    id: str
    ts: str
    service: str
    metric: str
    severity: str
    value: float
    threshold: float
    labels: Optional[dict] = Field(default_factory=dict)

class IncidentRequest(BaseModel):
    alerts: list[Alert]

# --- Output schema ---
class Cluster(BaseModel):
    cluster_id: str
    alert_count: int
    services: list[str]
    time_range: list[str]

class RootCause(BaseModel):
    service: str
    confidence: float
    reasoning: str

class SimilarIncident(BaseModel):
    id: str
    similarity: float
    summary: str

class IncidentResponse(BaseModel):
    clusters: list[Cluster]
    root_cause: RootCause
    recommended_actions: list[str]
    similar_incidents: list[SimilarIncident]


@app.get('/healthz')
def healthz() -> dict:
    return {'status': 'ok'}

@app.post('/incident', response_model=IncidentResponse)
def post_incident(req: IncidentRequest) -> IncidentResponse:
    alerts_dict = [a.model_dump() for a in req.alerts]
    try:
        result = process_batch(alerts_dict)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f'Pipeline error: {e}')
    return IncidentResponse(**result)
import time
from fastapi import Request

@app.middleware('http')
async def add_timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers['X-Response-Time-Ms'] = f'{duration_ms:.1f}'
    logger.info(f"{request.method} {request.url.path} {response.status_code} {duration_ms:.0f}ms")
    return response

@app.get('/readyz')
def readyz() -> dict:
    """Check downstream dependencies. Trả 503 nếu chưa ready."""
    checks = {
        'graph': GRAPH.number_of_nodes() > 0,
        'history': len(HISTORY) > 0,
    }
    # LLM check (optional — readiness không nên depend external service)
    try:
        from openai import OpenAI
        OpenAI(timeout=2.0).models.list()
        checks['llm'] = True
    except Exception:
        checks['llm'] = False

    if not all(checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {'status': 'ready', 'checks': checks}
APP_VERSION = '1.0.0'

@app.get('/version')
def version() -> dict:
    return {
        'app': APP_VERSION,
        'pipeline_config': {
            'correlate_gap_sec': 120,
            'correlate_max_hop': 2,
            'rca_method': 'graph+llm',
            'llm_model': 'gpt-4o-mini',
        },
    }

