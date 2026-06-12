"""Feature extraction for the evidence-driven remediation engine.

This module converts raw incident JSON into a normalized representation that
can be compared against historical incidents.
"""
# Layer 1: Extract and normalize raw features from the incident.
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
from typing import Any


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-:/.]*")
_NUM_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
_HEX_RE = re.compile(r"\b[0-9a-f]{6,}\b", re.I)


def _normalize_text(text: str) -> str:
    text = _TS_RE.sub("<ts>", text)
    text = _NUM_RE.sub("<num>", text)
    return text.lower().strip()


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(_normalize_text(text))


def _drain_normalize_message(msg: str) -> str:
    """Normalize highly variable values before Drain-style token clustering."""
    msg = _normalize_text(msg)
    msg = _IP_RE.sub("<ip>", msg)
    msg = _UUID_RE.sub("<uuid>", msg)
    msg = _HEX_RE.sub("<hex>", msg)
    msg = re.sub(r"\btrue\b|\bfalse\b", "<bool>", msg)
    return msg


def _drain_tokenize(msg: str) -> list[str]:
    return _drain_normalize_message(msg).split()


def _is_variable_token(token: str) -> bool:
    if not token:
        return True
    if token.startswith("<") and token.endswith(">"):
        return True
    if any(ch.isdigit() for ch in token):
        return True
    if "/" in token or "." in token or ":" in token or "=" in token:
        return True
    return False


class _DrainCluster:
    """One lightweight Drain-style cluster for similar log messages."""

    def __init__(self, tokens: list[str]) -> None:
        self.template_tokens = list(tokens)
        self.size = 1

    def similarity(self, tokens: list[str]) -> float:
        if len(tokens) != len(self.template_tokens):
            return 0.0
        if not tokens:
            return 1.0
        matches = 0
        non_param_slots = 0
        for templ, tok in zip(self.template_tokens, tokens):
            if templ != "<*>":
                non_param_slots += 1
            if templ == tok or templ == "<*>":
                matches += 1
        base = matches / len(tokens)
        if non_param_slots == 0:
            return base * 0.8
        exact = sum(1 for templ, tok in zip(self.template_tokens, tokens) if templ == tok)
        return 0.65 * base + 0.35 * (exact / non_param_slots)

    def update(self, tokens: list[str]) -> str:
        merged: list[str] = []
        for templ, tok in zip(self.template_tokens, tokens):
            if templ == tok:
                merged.append(templ)
            else:
                merged.append("<*>")
        self.template_tokens = merged
        self.size += 1
        return self.template()

    def template(self) -> str:
        return " ".join(self.template_tokens)


class _DrainParser:
    """A compact Drain-inspired parser.

    Messages are first bucketed by token count and a coarse prefix signature,
    then matched against existing clusters by token similarity. When no cluster
    is similar enough, a new cluster is created.
    """

    def __init__(self, similarity_threshold: float = 0.6, max_prefix_tokens: int = 3) -> None:
        self.similarity_threshold = similarity_threshold
        self.max_prefix_tokens = max_prefix_tokens
        self._clusters: dict[tuple[int, tuple[str, ...]], list[_DrainCluster]] = defaultdict(list)

    def _bucket_key(self, tokens: list[str]) -> tuple[int, tuple[str, ...]]:
        prefix: list[str] = []
        for tok in tokens[: self.max_prefix_tokens]:
            prefix.append("<*>" if _is_variable_token(tok) else tok)
        return len(tokens), tuple(prefix)

    def add(self, msg: str) -> str:
        tokens = _drain_tokenize(msg)
        if not tokens:
            return ""

        bucket = self._clusters[self._bucket_key(tokens)]
        best_cluster: _DrainCluster | None = None
        best_score = -1.0

        for cluster in bucket:
            score = cluster.similarity(tokens)
            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is not None and best_score >= self.similarity_threshold:
            return best_cluster.update(tokens)

        cluster = _DrainCluster(tokens)
        bucket.append(cluster)
        return cluster.template()


def _log_template(msg: str) -> str:
    """Fallback single-line templating for callers outside extract_features.

    The main incident path uses the Drain-style parser across all log lines so
    similar messages within the same incident collapse into shared templates.
    """
    return _DrainParser().add(msg)


def _service_metric_name(metric_key: str) -> tuple[str, str] | tuple[None, None]:
    if "." not in metric_key:
        return None, None
    svc, metric = metric_key.split(".", 1)
    return svc, metric


def _series_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "last": 0.0, "first": 0.0, "slope": 0.0}
    first = float(values[0])
    last = float(values[-1])
    mean = float(sum(values) / len(values))
    mn = float(min(values))
    mx = float(max(values))
    slope = last - first
    return {"mean": mean, "min": mn, "max": mx, "last": last, "first": first, "slope": slope}


# vector đặc trưng đã chuẩn hóa
def extract_features(incident: dict) -> dict[str, Any]:
    trigger = incident.get("trigger_alert", {}) or {}
    topology = incident.get("topology", {}) or {}
    nodes = topology.get("nodes", []) or []
    edges = topology.get("edges", []) or []
    logs = incident.get("logs", []) or []
    traces = incident.get("traces", []) or []
    metrics = (incident.get("metrics_window", {}) or {}).get("samples", {}) or {}

    log_templates: list[str] = []
    log_tokens: Counter[str] = Counter()
    log_svc_counter: Counter[str] = Counter()
    log_level_counter: Counter[str] = Counter()
    drain_parser = _DrainParser()

    for line in logs:
        msg = str(line.get("msg", ""))
        log_templates.append(drain_parser.add(msg))
        log_tokens.update(_tokenize(msg))
        if line.get("svc"):
            log_svc_counter[str(line["svc"])] += 1
        if line.get("level"):
            log_level_counter[str(line["level"])] += 1

    trace_edges: list[dict[str, Any]] = []
    trace_pair_counter: Counter[tuple[str, str]] = Counter()
    trace_src_counter: Counter[str] = Counter()
    trace_dst_counter: Counter[str] = Counter()
    trace_signal_score = 0.0

    for t in traces:
        src = str(t.get("from", ""))
        dst = str(t.get("to", ""))
        count = float(t.get("count", 0) or 0)
        err = float(t.get("error_count", 0) or 0)
        p50 = float(t.get("p50_ms", 0) or 0)
        p99 = float(t.get("p99_ms", 0) or 0)
        err_rate = err / count if count else 0.0
        dev_ratio = (p99 / max(p50, 1.0)) if p50 else (p99 / 100.0)
        trace_edges.append(
            {
                "from": src,
                "to": dst,
                "count": count,
                "error_count": err,
                "error_rate": err_rate,
                "p50_ms": p50,
                "p99_ms": p99,
                "p99_over_p50": dev_ratio,
            }
        )
        trace_pair_counter[(src, dst)] += 1
        if src:
            trace_src_counter[src] += 1
        if dst:
            trace_dst_counter[dst] += 1
        trace_signal_score += err_rate * min(dev_ratio / 2.0, 3.0)

    metric_series: dict[str, dict[str, float]] = {}
    metric_growth: dict[str, float] = {}
    metric_top_services: Counter[str] = Counter()
    metric_top_names: Counter[str] = Counter()

    for key, samples in metrics.items():
        vals = [float(v) for _, v in samples or []]
        stats = _series_stats(vals)
        metric_series[key] = stats
        if len(vals) >= 2:
            growth = vals[-1] - vals[0]
            metric_growth[key] = growth
        svc, metric = _service_metric_name(key)
        if svc:
            metric_top_services[svc] += 1
        if metric:
            metric_top_names[metric] += 1

    affected_services = set()
    if trigger.get("service"):
        affected_services.add(str(trigger["service"]))
    affected_services.update(log_svc_counter)
    affected_services.update(trace_src_counter)
    affected_services.update(trace_dst_counter)
    for key in metrics:
        svc, _ = _service_metric_name(key)
        if svc:
            affected_services.add(svc)

    anomaly_services = Counter()
    for key, stats in metric_series.items():
        svc, metric = _service_metric_name(key)
        if not svc:
            continue
        # Score likely anomalies by slope and magnitude.
        magnitude = abs(stats["slope"]) + abs(stats["max"] - stats["min"])
        if magnitude > 0:
            anomaly_services[svc] += int(min(10, magnitude / 50.0) + 1)

    baseline_metric_keys = sorted(metric_series.keys())[:5]

    feature_vec = {
        "incident_id": incident.get("incident_id"),
        "trigger_service": trigger.get("service"),
        "trigger_rule": trigger.get("rule_id"),
        "trigger_severity": trigger.get("severity"),
        "log_templates": log_templates,
        "log_tokens": dict(log_tokens),
        "log_svc_counter": dict(log_svc_counter),
        "log_level_counter": dict(log_level_counter),
        "trace_edges": trace_edges,
        "trace_pair_counter": {f"{a}->{b}": c for (a, b), c in trace_pair_counter.items()},
        "metric_series": metric_series,
        "metric_growth": metric_growth,
        "metric_top_services": dict(metric_top_services),
        "metric_top_names": dict(metric_top_names),
        "affected_services": sorted(affected_services),
        "topology_nodes": [n.get("id") for n in nodes if n.get("id")],
        "topology_edges": [f'{e.get("from")}->{e.get("to")}:{e.get("protocol")}' for e in edges if e.get("from") and e.get("to")],
        "trace_signal_score": trace_signal_score,
        "anomaly_services": dict(anomaly_services),
        "baseline_metric_keys": baseline_metric_keys,
    }
    return feature_vec


def historical_signatures(entry: dict) -> dict[str, Any]:
    """Normalize one historical incident into comparable signature shapes."""
    actions = entry.get("actions_taken", []) or []
    return {
        "id": entry.get("id"),
        "root_cause_class": entry.get("root_cause_class"),
        "affected_services": entry.get("affected_services", []) or [],
        "log_signatures": [_drain_normalize_message(s) for s in entry.get("log_signatures", []) or []],
        "log_signature_tokens": [set(_tokenize(s)) for s in entry.get("log_signatures", []) or []],
        "trace_signatures": entry.get("trace_signatures", []) or [],
        "metric_signatures": entry.get("metric_signatures", []) or [],
        "actions_taken": actions,
        "outcome": entry.get("outcome"),
        "mttr_minutes": entry.get("mttr_minutes"),
    }