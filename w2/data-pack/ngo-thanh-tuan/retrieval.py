"""Similarity search and outcome-weighted voting."""


# Layer 2: Compare the query features to historical signatures, 
# ranking historical incidents by similarity and voting for candidate actions based on the top matches.
# and compute similarity scores.
from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any

from optional_helpers import parse_history_action, parse_metric_delta  # type: ignore

from features import historical_signatures


OUTCOME_WEIGHT = {
    "success": 1.0,
    "partial": 0.6,
    "failed": 0.2,
}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _token_set(s: str) -> set[str]:
    return set(s.lower().replace(":", " ").replace("->", " ").split())


def _metric_delta_score(query_metric: dict[str, Any], hist_metric: dict[str, Any]) -> float:
    qv = query_metric.get("last", 0.0) - query_metric.get("first", 0.0)
    hv0, hv1 = parse_metric_delta(hist_metric.get("delta", "0 -> 0"))
    hdiff = hv1 - hv0
    # Compare both sign and scale.
    denom = max(abs(qv), abs(hdiff), 1.0)
    scale_score = 1.0 - min(abs(abs(qv) - abs(hdiff)) / denom, 1.0)
    sign_score = 1.0 if qv == 0 or hdiff == 0 or (qv > 0) == (hdiff > 0) else 0.2
    return 0.7 * scale_score + 0.3 * sign_score


def _trace_score(query_traces: list[dict[str, Any]], hist_traces: list[dict[str, Any]]) -> float:
    if not hist_traces:
        return 0.15 if not query_traces else 0.25
    total = 0.0
    for h in hist_traces:
        best = 0.0
        for q in query_traces:
            if q.get("from") != h.get("from") or q.get("to") != h.get("to"):
                continue
            q_err = float(q.get("error_count", 0) or 0) / max(float(q.get("count", 1) or 1), 1.0)
            q_ratio = float(q.get("p99_over_p50", 0) or 0)
            h_ratio = float(h.get("p99_deviation_ratio", 0) or 0)
            h_err = float(h.get("error_rate", 0) or 0)
            err_score = 1.0 - min(abs(q_err - h_err) / max(h_err, 0.05), 1.0)
            ratio_score = 1.0 - min(abs(q_ratio - h_ratio) / max(h_ratio, 1.0), 1.0)
            best = max(best, 0.6 * err_score + 0.4 * ratio_score)
        total += best
    return total / max(len(hist_traces), 1)


def _log_score(query_templates: list[str], hist_templates: list[str]) -> float:
    if not hist_templates:
        return 0.1
    q_tokens = set()
    for t in query_templates:
        q_tokens |= _token_set(t)
    best_scores = []
    for h in hist_templates:
        htok = _token_set(h)
        best_scores.append(_jaccard(q_tokens, htok))
    return sum(best_scores) / len(best_scores)


def _service_overlap_score(query_services: set[str], hist_services: set[str]) -> float:
    return _jaccard(query_services, hist_services)


def similarity(a: dict, b: dict) -> float:
    """Similarity between query features and a historical incident."""
    hist = historical_signatures(b)

    log_score = _log_score(a.get("log_templates", []), hist["log_signatures"])
    trace_score = _trace_score(a.get("trace_edges", []), hist["trace_signatures"])
    metric_score = 0.0
    for hm in hist["metric_signatures"]:
        svc = hm.get("service")
        metric = hm.get("metric")
        key = f"{svc}.{metric}"
        q_metric = a.get("metric_series", {}).get(key)
        if q_metric:
            metric_score = max(metric_score, _metric_delta_score(q_metric, hm))

    service_score = _service_overlap_score(set(a.get("affected_services", [])), set(hist["affected_services"]))
    topology_score = 0.0
    if hist["affected_services"]:
        topology_score = service_score * 0.5 + min(len(set(a.get("topology_edges", []))) / 20.0, 0.5)

    # Logs and traces are the main signal; metrics refine the match.
    sim = (
        0.34 * log_score
        + 0.34 * trace_score
        + 0.16 * metric_score
        + 0.10 * service_score
        + 0.06 * topology_score
    )
    return max(0.0, min(1.0, sim))


def _parse_action(action_str: str) -> dict[str, Any]:
    parsed = parse_history_action(action_str)
    name = parsed["name"]
    params = parsed["params"]
    if name == "page_oncall":
        return {"name": name, "params": {"team": params[0] if params else "platform-team"}}
    if name == "rollback_service":
        return {"name": name, "params": {"service": params[0] if params else None, "target_version": params[1] if len(params) > 1 else "previous"}}
    if name == "increase_pool_size":
        return {"name": name, "params": {"service": params[0] if params else None, "from_value": params[1] if len(params) > 1 else None, "to_value": params[2] if len(params) > 2 else None}}
    if name == "restart_pod":
        return {"name": name, "params": {"service": params[0] if params else None, "pod_selector": params[1] if len(params) > 1 else "default"}}
    if name == "dns_config_rollback":
        return {"name": name, "params": {"configmap_name": params[0] if params else None, "target_revision": params[1] if len(params) > 1 else None}}
    if name == "network_policy_revert":
        return {"name": name, "params": {"policy_name": params[0] if params else None}}
    return {"name": name, "params": {f"arg{i}": p for i, p in enumerate(params)}}


def retrieve_and_vote(query: dict, history: list[dict], top_k: int = 4) -> dict:
    """Rank historical incidents and vote for candidate actions."""
    scored = []
    for entry in history:
        s = similarity(query, entry)
        scored.append((s, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    votes: dict[tuple[str, tuple[tuple[str, Any], ...]], dict[str, Any]] = {}
    action_evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for sim, entry in top:
        hist = historical_signatures(entry)
        outcome_w = OUTCOME_WEIGHT.get(hist["outcome"], 0.4)
        vote_weight = sim * outcome_w
        for raw_action in hist["actions_taken"]:
            parsed = _parse_action(raw_action)
            # Canonicalize by action name + params for aggregation.
            key = (parsed["name"], tuple(sorted((k, str(v)) for k, v in parsed["params"].items() if v is not None)))
            bucket = votes.setdefault(
                key,
                {
                    "name": parsed["name"],
                    "params": dict(parsed["params"]),
                    "score": 0.0,
                    "support": 0.0,
                    "history_ids": [],
                    "histories": [],
                },
            )
            bucket["score"] += vote_weight
            bucket["support"] += sim
            bucket["history_ids"].append(hist["id"])
            bucket["histories"].append(
                {
                    "id": hist["id"],
                    "similarity": round(sim, 4),
                    "outcome": hist["outcome"],
                    "outcome_weight": outcome_w,
                    "vote_weight": round(vote_weight, 4),
                }
            )
            action_evidence[parsed["name"]].append(
                {
                    "incident_id": hist["id"],
                    "similarity": round(sim, 4),
                    "outcome": hist["outcome"],
                    "vote_weight": round(vote_weight, 4),
                    "params": parsed["params"],
                }
            )

    ranked = sorted(votes.values(), key=lambda x: (x["score"], x["support"]), reverse=True)
    return {
        "top_neighbors": [
            {
                "incident_id": entry.get("id"),
                "similarity": round(sim, 4),
                "outcome": entry.get("outcome"),
                "actions_taken": entry.get("actions_taken", []),
                "root_cause_class": entry.get("root_cause_class"),
            }
            for sim, entry in top
        ],
        "ranked_actions": ranked,
        "action_evidence": dict(action_evidence),
        "best_similarity": top[0][0] if top else 0.0,
        "second_similarity": top[1][0] if len(top) > 1 else 0.0,
    }