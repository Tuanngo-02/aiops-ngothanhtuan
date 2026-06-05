from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Deque, Dict, List, Optional

import json

from fastapi import FastAPI, Request
import uvicorn

APP_DIR = Path(__file__).resolve().parent
ALERTS_FILE = APP_DIR / "alerts.jsonl"

app = FastAPI(title="Streaming Anomaly Pipeline")


class StreamingAnomalyDetector:
    def __init__(self) -> None:
        self.history: Deque[Dict] = deque(maxlen=120)
        self.last_alert_type: Optional[str] = None
        self.last_alert_tick: int = -999
        self.tick_count = 0

    def process(self, timestamp: str, metrics: Dict, logs: List[Dict]) -> Optional[Dict]:
        self.tick_count += 1

        snapshot = {
            "timestamp": timestamp,
            "memory_utilization": metrics["memory_usage_bytes"] / max(metrics["memory_limit_bytes"], 1),
            "cpu_usage_percent": float(metrics["cpu_usage_percent"]),
            "http_requests_per_sec": float(metrics["http_requests_per_sec"]),
            "http_p99_latency_ms": float(metrics["http_p99_latency_ms"]),
            "http_5xx_rate": float(metrics["http_5xx_rate"]),
            "jvm_gc_pause_ms_avg": float(metrics["jvm_gc_pause_ms_avg"]),
            "queue_depth": float(metrics["queue_depth"]),
            "upstream_timeout_rate": float(metrics["upstream_timeout_rate"]),
            "logs": logs,
        }
        self.history.append(snapshot)

        if len(self.history) < 12:
            return None

        baseline_window = list(self.history)[:-5]
        recent_window = list(self.history)[-5:]

        if len(baseline_window) < 6:
            return None

        baseline = self._window_stats(baseline_window)
        recent = self._window_stats(recent_window)
        current = recent_window[-1]

        memory_alert = self._detect_memory_leak(current, recent, baseline, recent_window)
        traffic_alert = self._detect_traffic_spike(current, recent, baseline, recent_window)
        dependency_alert = self._detect_dependency_timeout(current, recent, baseline, recent_window)

        candidates = [a for a in [dependency_alert, traffic_alert, memory_alert] if a is not None]
        if not candidates:
            return None

        alert = max(candidates, key=lambda item: item["score"])

        if self.last_alert_type == alert["type"] and (self.tick_count - self.last_alert_tick) < 10:
            return None

        self.last_alert_type = alert["type"]
        self.last_alert_tick = self.tick_count

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "type": alert["type"],
            "severity": alert["severity"],
            "message": alert["message"],
        }

    def _window_stats(self, window: List[Dict]) -> Dict[str, float]:
        keys = [
            "memory_utilization",
            "cpu_usage_percent",
            "http_requests_per_sec",
            "http_p99_latency_ms",
            "http_5xx_rate",
            "jvm_gc_pause_ms_avg",
            "queue_depth",
            "upstream_timeout_rate",
        ]
        stats = {}
        for key in keys:
            values = [item[key] for item in window]
            stats[key] = median(values)
            stats[f"{key}_max"] = max(values)
        stats["error_logs"] = sum(1 for item in window for log in item["logs"] if log.get("level") in {"ERROR", "FATAL"})
        stats["warn_logs"] = sum(1 for item in window for log in item["logs"] if log.get("level") == "WARN")
        return stats

    def _detect_memory_leak(
        self,
        current: Dict[str, float],
        recent: Dict[str, float],
        baseline: Dict[str, float],
        recent_window: List[Dict],
    ) -> Optional[Dict]:
        recent_memory_values = [item["memory_utilization"] for item in recent_window]
        memory_growth = recent_memory_values[-1] - recent_memory_values[0]
        gc_growth = recent["jvm_gc_pause_ms_avg"] - baseline["jvm_gc_pause_ms_avg"]

        strong_signal = (
            recent["memory_utilization"] >= 0.82
            and recent["jvm_gc_pause_ms_avg"] >= 45
            and gc_growth >= 20
        )
        medium_signal = (
            recent["memory_utilization"] >= 0.72
            and memory_growth >= 0.08
            and recent["cpu_usage_percent"] >= baseline["cpu_usage_percent"] + 12
            and recent["jvm_gc_pause_ms_avg"] >= baseline["jvm_gc_pause_ms_avg"] + 25
        )

        oom_hint = any("OutOfMemoryWarning" in log.get("message", "") for item in recent_window for log in item["logs"])
        gc_hint = any("GC pause exceeded threshold" in log.get("message", "") for item in recent_window for log in item["logs"])

        if not (strong_signal or medium_signal or oom_hint):
            return None

        severity = "critical" if strong_signal or oom_hint else "warning"
        score = 90 if severity == "critical" else 70
        if gc_hint:
            score += 5

        return {
            "type": "memory_leak",
            "severity": severity,
            "score": score,
            "message": (
                f"Memory utilization at {current['memory_utilization'] * 100:.1f}%, "
                f"GC pause {current['jvm_gc_pause_ms_avg']:.1f}ms, "
                f"CPU {current['cpu_usage_percent']:.1f}%"
            ),
        }

    def _detect_traffic_spike(
        self,
        current: Dict[str, float],
        recent: Dict[str, float],
        baseline: Dict[str, float],
        recent_window: List[Dict],
    ) -> Optional[Dict]:
        rps_ratio = recent["http_requests_per_sec"] / max(baseline["http_requests_per_sec"], 1.0)
        queue_jump = recent["queue_depth"] - baseline["queue_depth"]
        latency_jump = recent["http_p99_latency_ms"] - baseline["http_p99_latency_ms"]

        overload_hint = any("server overloaded" in log.get("message", "").lower() for item in recent_window for log in item["logs"])
        queue_hint = any("Queue depth high" in log.get("message", "") for item in recent_window for log in item["logs"])

        strong_signal = (
            rps_ratio >= 3.0
            and recent["queue_depth"] >= 40
            and latency_jump >= 300
        )
        medium_signal = (
            rps_ratio >= 2.0
            and queue_jump >= 25
            and recent["cpu_usage_percent"] >= baseline["cpu_usage_percent"] + 10
            and recent["upstream_timeout_rate"] < 10
        )

        if not (strong_signal or medium_signal or overload_hint):
            return None

        severity = "critical" if strong_signal or overload_hint or recent["http_5xx_rate"] >= 8 else "warning"
        score = 85 if severity == "critical" else 65
        if queue_hint:
            score += 5

        return {
            "type": "traffic_spike",
            "severity": severity,
            "score": score,
            "message": (
                f"Traffic surged to {current['http_requests_per_sec']:.1f} req/s "
                f"({rps_ratio:.1f}x baseline), queue depth {current['queue_depth']:.0f}, "
                f"p99 latency {current['http_p99_latency_ms']:.1f}ms"
            ),
        }

    def _detect_dependency_timeout(
        self,
        current: Dict[str, float],
        recent: Dict[str, float],
        baseline: Dict[str, float],
        recent_window: List[Dict],
    ) -> Optional[Dict]:
        timeout_jump = recent["upstream_timeout_rate"] - baseline["upstream_timeout_rate"]
        latency_jump = recent["http_p99_latency_ms"] - baseline["http_p99_latency_ms"]

        timeout_hint = any("upstream timeout" in log.get("message", "").lower() for item in recent_window for log in item["logs"])
        breaker_hint = any("circuit breaker open" in log.get("message", "").lower() for item in recent_window for log in item["logs"])

        strong_signal = (
            recent["upstream_timeout_rate"] >= 12
            and timeout_jump >= 8
            and recent["http_5xx_rate"] >= 5
            and latency_jump >= 400
        )
        medium_signal = (
            recent["upstream_timeout_rate"] >= 8
            and timeout_jump >= 5
            and recent["http_5xx_rate"] >= 3
        )
        log_backed_signal = (
            recent["upstream_timeout_rate_max"] >= 12
            and recent["http_5xx_rate_max"] >= 5
            and (timeout_hint or breaker_hint)
        )

        if not (strong_signal or medium_signal or log_backed_signal):
            return None

        severity = "critical" if strong_signal or breaker_hint or current["upstream_timeout_rate"] >= 25 else "warning"
        score = 95 if severity == "critical" else 75

        return {
            "type": "dependency_timeout",
            "severity": severity,
            "score": score,
            "message": (
                f"Upstream timeout rate at {current['upstream_timeout_rate']:.1f}%, "
                f"5xx rate {current['http_5xx_rate']:.1f}%, "
                f"p99 latency {current['http_p99_latency_ms']:.1f}ms"
            ),
        }


detector = StreamingAnomalyDetector()


def append_alert(alert: Dict) -> None:
    with ALERTS_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(alert, ensure_ascii=False) + "\n")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(request: Request) -> Dict[str, str]:
    payload = await request.json()
    metrics = payload["metrics"]
    logs = payload.get("logs", [])
    timestamp = payload["timestamp"]

    alert = detector.process(timestamp, metrics, logs)
    if alert:
        append_alert(alert)

    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("pipeline:app", host="0.0.0.0", port=8000, reload=False)