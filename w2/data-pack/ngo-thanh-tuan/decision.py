"""Cost-aware action selection."""
# Layer 3: Select the best action candidate, 
# applying heuristics to balance similarity, 
# historical support, and operational risk, 
# and escalating to on-call when uncertainty is high.

from __future__ import annotations

from typing import Any


DEFAULT_BLAST_RADIUS_LIMIT = 2
OOD_SIM_THRESHOLD = 0.20 #OOD (out-of-distribution)
AUTO_ACTION_THRESHOLD = 0.48
AMBIGUITY_MARGIN = 0.08


def _find_action_meta(actions_catalog: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for a in actions_catalog:
        if a.get("name") == name:
            return a
    return {"name": name, "params": [], "cost_min": 0, "downtime_min": 0, "blast_radius_services": 0, "rollback_window_sec": 0}


def _normalize_params(name: str, params: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
    out = dict(params or {})
    trigger_service = query.get("trigger_service")
    affected_services = set(query.get("affected_services", []) or [])

    def _prefer_local_service(current: Any) -> Any:
        if current and current in affected_services:
            return current
        if trigger_service:
            return trigger_service
        if affected_services:
            return sorted(affected_services)[0]
        return current

    if name == "page_oncall":
        out.setdefault("team", "platform-team")
    elif name == "rollback_service":
        out["service"] = _prefer_local_service(out.get("service"))
        out.setdefault("target_version", "previous")
    elif name == "increase_pool_size":
        out["service"] = _prefer_local_service(out.get("service"))
        out.setdefault("from_value", "50")
        out.setdefault("to_value", "100")
    elif name == "restart_pod":
        out["service"] = _prefer_local_service(out.get("service"))
        out.setdefault("pod_selector", "default")
    elif name == "dns_config_rollback":
        out.setdefault("configmap_name", "resolv-conf")
        out.setdefault("target_revision", "42")
    elif name == "network_policy_revert":
        out.setdefault("policy_name", "default")
    return {k: v for k, v in out.items() if v is not None}


def _dominant_trace_service(query: dict[str, Any]) -> Any:
    edges = query.get("trace_edges", []) or []
    scores: dict[str, float] = {}
    for edge in edges:
        src = edge.get("from")
        dst = edge.get("to")
        count = float(edge.get("count", 0) or 0)
        err = float(edge.get("error_count", 0) or 0)
        p50 = float(edge.get("p50_ms", 0) or 0)
        p99 = float(edge.get("p99_ms", 0) or 0)
        ratio = p99 / max(p50, 1.0) if (p50 or p99) else 0.0
        signal = (err * 3.0) + min(ratio, 6.0) + (count / 100.0)
        if src:
            scores[str(src)] = scores.get(str(src), 0.0) + signal * 0.6
        if dst:
            scores[str(dst)] = scores.get(str(dst), 0.0) + signal
    if not scores:
        return None
    return max(scores.items(), key=lambda item: item[1])[0]


def _utility(candidate_score: float, action_meta: dict[str, Any], query: dict[str, Any]) -> float:
    cost = float(action_meta.get("cost_min", 0) or 0)
    downtime = float(action_meta.get("downtime_min", 0) or 0)
    blast = float(action_meta.get("blast_radius_services", 0) or 0)

    # Keep actions cost-aware, but do not over-penalize low-blast operational fixes.
    risk_penalty = 0.025 * cost + 0.04 * downtime + 0.10 * blast
    return candidate_score * 2.0 - risk_penalty


def select_action(candidates: dict, actions_catalog: list[dict[str, Any]]) -> dict:
    ranked = candidates.get("ranked_actions", []) or []
    top_neighbors = candidates.get("top_neighbors", []) or []
    best_similarity = float(candidates.get("best_similarity", 0.0) or 0.0)
    second_similarity = float(candidates.get("second_similarity", 0.0) or 0.0)

    # OOD handling: novel inputs should escalate.
    # incident hiện tại không đủ giống dữ liệu lịch sử
    if best_similarity < OOD_SIM_THRESHOLD:
        meta = _find_action_meta(actions_catalog, "page_oncall")
        params = _normalize_params("page_oncall", {}, candidates)
        return {
            "incident_id": None,
            "selected_action": "page_oncall",
            "params": params,
            "confidence": round(max(0.12, best_similarity), 4),
            "evidence": {
                "mode": "ood_escalation",
                "best_similarity": round(best_similarity, 4),
                "reason": "No historical incident is close enough to trust an auto-action.",
                "top_neighbors": top_neighbors[:3],
                "ranked_actions": ranked[:5],
                "selected_action_meta": meta,
                "blast_radius_check": {"passed": True, "limit": DEFAULT_BLAST_RADIUS_LIMIT},
            },
        }
    # retrieval không đưa ra được action nào
    if not ranked:
        meta = _find_action_meta(actions_catalog, "page_oncall")
        return {
            "incident_id": None,
            "selected_action": "page_oncall",
            "params": _normalize_params("page_oncall", {}, candidates),
            "confidence": 0.25,
            "evidence": {
                "mode": "no_candidates",
                "top_neighbors": top_neighbors[:3],
                "selected_action_meta": meta,
            },
        }

    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None

    # Evaluate top candidate utility.
    action_name = best["name"]
    action_meta = _find_action_meta(actions_catalog, action_name)
    params = _normalize_params(action_name, best.get("params", {}), candidates)
    
    # memory leak thường gắn chặt với service đang báo động
    if action_name in {"rollback_service", "restart_pod"} and candidates.get("trigger_rule") == "memory-leak" and candidates.get("trigger_service"):
        params["service"] = candidates.get("trigger_service")

    util = _utility(float(best["score"]), action_meta, candidates)

    # Strong historical support should beat a naive escalation preference.
    strong_support = (
        action_name != "page_oncall"
        and len(best.get("history_ids", []) or []) >= 2
        and float(best.get("score", 0.0) or 0.0) >= 0.55
        and best_similarity >= 0.25
    )
    if strong_support:
        util += 0.35

    # If the top two are close and point to different actions, prefer escalation.
    if second and abs(float(best["score"]) - float(second["score"])) < AMBIGUITY_MARGIN and second["name"] != best["name"]:
        meta = _find_action_meta(actions_catalog, "page_oncall")
        return {
            "incident_id": None,
            "selected_action": "page_oncall",
            "params": _normalize_params("page_oncall", {}, candidates),
            "confidence": round(max(0.35, float(best["score"]) * 0.8), 4),
            "evidence": {
                "mode": "ambiguity_escalation",
                "best_similarity": round(best_similarity, 4),
                "second_similarity": round(second_similarity, 4),
                "top_neighbors": top_neighbors[:3],
                "ranked_actions": ranked[:5],
                "selected_action_meta": meta,
                "blast_radius_check": {"passed": True, "limit": DEFAULT_BLAST_RADIUS_LIMIT},
            },
        }

    blast_radius = float(action_meta.get("blast_radius_services", 0) or 0)
    confidence = max(0.05, min(0.99, float(best["score"]) / max(1.0, float(best["score"]) + 0.7)))

    # A downstream service may legitimately be the root cause in a latency cascade.
    # Only escalate on service mismatch when the rollback evidence itself is weak.
    rollback_support_count = len(best.get("history_ids", []) or [])
    if (
        candidates.get("trigger_rule") == "latency-p99-high"
        and action_name == "rollback_service"
        and candidates.get("trigger_service")
        and params.get("service") != candidates.get("trigger_service")
        and (
            best_similarity < 0.30
            or float(best.get("score", 0.0) or 0.0) < 0.45
            or rollback_support_count < 2
        )
    ):
        meta = _find_action_meta(actions_catalog, "page_oncall")
        return {
            "incident_id": None,
            "selected_action": "page_oncall",
            "params": _normalize_params("page_oncall", {}, candidates),
            "confidence": round(max(confidence, 0.33), 4),
            "evidence": {
                "mode": "service_mismatch_escalation",
                "best_similarity": round(best_similarity, 4),
                "top_neighbors": top_neighbors[:3],
                "ranked_actions": ranked[:5],
                "utility": round(util, 4),
                "selected_action_meta": meta,
                "blast_radius_check": {"passed": True, "limit": DEFAULT_BLAST_RADIUS_LIMIT},
            },
        }

    # Large blast radius actions need stronger evidence.
    if blast_radius > DEFAULT_BLAST_RADIUS_LIMIT and confidence < 0.68:
        meta = _find_action_meta(actions_catalog, "page_oncall")
        return {
            "incident_id": None,
            "selected_action": "page_oncall",
            "params": _normalize_params("page_oncall", {}, candidates),
            "confidence": round(confidence, 4),
            "evidence": {
                "mode": "blast_radius_escalation",
                "best_similarity": round(best_similarity, 4),
                "top_neighbors": top_neighbors[:3],
                "ranked_actions": ranked[:5],
                "selected_action_meta": meta,
                "blast_radius_check": {"passed": False, "limit": DEFAULT_BLAST_RADIUS_LIMIT, "blast_radius": blast_radius},
            },
        }

    # If the utility is weak and page_oncall is nearly as good, escalate.
    page_meta = _find_action_meta(actions_catalog, "page_oncall")
    page_utility = _utility(0.12, page_meta, candidates)
    if util < 0.10 and page_utility >= util - 0.03:
        return {
            "incident_id": None,
            "selected_action": "page_oncall",
            "params": _normalize_params("page_oncall", {}, candidates),
            "confidence": round(max(confidence, 0.33), 4),
            "evidence": {
                "mode": "utility_escalation",
                "best_similarity": round(best_similarity, 4),
                "top_neighbors": top_neighbors[:3],
                "ranked_actions": ranked[:5],
                "utility": round(util, 4),
                "page_utility": round(page_utility, 4),
                "selected_action_meta": page_meta,
                "blast_radius_check": {"passed": True, "limit": DEFAULT_BLAST_RADIUS_LIMIT},
            },
        }

    return {
        "incident_id": None,
        "selected_action": action_name,
        "params": params,
        "confidence": round(confidence, 4),
        "evidence": {
            "mode": "auto_action",
            "best_similarity": round(best_similarity, 4),
            "second_similarity": round(second_similarity, 4),
            "top_neighbors": top_neighbors[:3],
            "ranked_actions": ranked[:5],
            "utility": round(util, 4),
            "selected_action_meta": action_meta,
            "blast_radius_check": {"passed": blast_radius <= DEFAULT_BLAST_RADIUS_LIMIT, "limit": DEFAULT_BLAST_RADIUS_LIMIT, "blast_radius": blast_radius},
        },
    }
