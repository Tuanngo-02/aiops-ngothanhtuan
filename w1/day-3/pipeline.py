from __future__ import annotations

import csv
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Deque, List


WINDOW_SIZE = 5
INPUT_FILE = "resource/machine_temperature_system_failure.csv"
OUTPUT_FILE = "features.json"
SERVICE_NAME = "machine_temperature"
METRIC_NAME = "temperature"


@dataclass
class MetricEvent:
    timestamp: str
    service: str
    metric: str
    value: float


@dataclass
class FeatureRecord:
    timestamp: str
    service: str
    metric: str
    value: float
    rolling_mean: float
    rolling_std: float
    rate_of_change: float


def load_events_from_csv(csv_path: Path) -> List[MetricEvent]:
    events: List[MetricEvent] = []

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            events.append(
                MetricEvent(
                    timestamp=row["timestamp"],
                    service=SERVICE_NAME,
                    metric=METRIC_NAME,
                    value=float(row["value"]),
                )
            )

    return events


def produce_events(csv_path: Path, event_queue: Queue[MetricEvent | None]) -> int:
    events = load_events_from_csv(csv_path)

    for event in events:
        event_queue.put(event)

    event_queue.put(None)
    return len(events)


def compute_rolling_std(window: Deque[float]) -> float:
    if len(window) < 2:
        return 0.0

    mean = sum(window) / len(window)
    variance = sum((value - mean) ** 2 for value in window) / len(window)
    return math.sqrt(variance)


def consume_and_extract_features(
    event_queue: Queue[MetricEvent | None], window_size: int = WINDOW_SIZE
) -> List[FeatureRecord]:
    window: Deque[float] = deque(maxlen=window_size)
    previous_value: float | None = None
    features: List[FeatureRecord] = []

    while True:
        try:
            event = event_queue.get_nowait()
        except Empty:
            break

        if event is None:
            break

        window.append(event.value)

        rolling_mean = sum(window) / len(window)
        rolling_std = compute_rolling_std(window)
        rate_of_change = 0.0 if previous_value is None else event.value - previous_value

        features.append(
            FeatureRecord(
                timestamp=event.timestamp,
                service=event.service,
                metric=event.metric,
                value=event.value,
                rolling_mean=round(rolling_mean, 6),
                rolling_std=round(rolling_std, 6),
                rate_of_change=round(rate_of_change, 6),
            )
        )

        previous_value = event.value

    return features


def write_features(features: List[FeatureRecord], destination: Path) -> None:
    payload = [asdict(feature) for feature in features]
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    input_path = base_dir / INPUT_FILE
    output_path = base_dir / OUTPUT_FILE

    event_queue: Queue[MetricEvent | None] = Queue()
    produced_count = produce_events(input_path, event_queue)
    features = consume_and_extract_features(event_queue)

    write_features(features, output_path)

    print(f"Read source data from {input_path.name}")
    print(f"Produced {produced_count} events into mock queue")
    print(f"Consumed {len(features)} events and wrote features to {output_path.name}")


if __name__ == "__main__":
    main()