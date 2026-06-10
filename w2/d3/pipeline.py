# pipeline.py — glue layer
from correlate import correlate, build_graph_from_json
from rca import run_rca
import json
from pathlib import Path

# Load once at module level (cached)
GRAPH = build_graph_from_json('dataset/services.json')
HISTORY = json.loads(Path('dataset/incidents_history.json').read_text(encoding='utf-8'))['incidents']


def process_batch(alerts: list[dict]) -> dict:
    """Full pipeline. Trả về dict matching IncidentResponse schema."""
    # L1: Correlate
    clusters = correlate(alerts, GRAPH, gap_sec=120, max_hop=2)
    if not clusters:
        return {'clusters': [], 'root_cause': {'service': 'unknown', 'confidence': 0,
                'reasoning': 'No clusters'}, 'recommended_actions': [], 'similar_incidents': []}

    # Primary incident = cluster lớn nhất
    primary = max(clusters, key=lambda c: c['alert_count'])

    # L2 + L3: RCA + LLM enrichment
    rca_result = run_rca(primary, alerts, GRAPH, HISTORY)

    return {
        'clusters': [
            {'cluster_id': c['cluster_id'], 'alert_count': c['alert_count'],
             'services': c['services'], 'time_range': c['time_range']}
            for c in clusters
        ],
        'root_cause': {
            'service': rca_result['root_cause'],
            'confidence': rca_result['confidence'],
            'reasoning': rca_result.get('reasoning', ''),
        },
        'recommended_actions': rca_result.get('actions', []),
        'similar_incidents': [
            {'id': inc_id, 'similarity': 0.7, 'summary': '...'}
            for inc_id in rca_result.get('similar_incidents', [])[:3]
        ],
    }
