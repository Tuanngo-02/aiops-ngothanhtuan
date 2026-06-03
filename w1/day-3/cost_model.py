from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


DAYS_PER_MONTH = 30
SECONDS_PER_DAY = 86_400
SECONDS_PER_MONTH = DAYS_PER_MONTH * SECONDS_PER_DAY
TB_TO_GB = 1_024

# Build cost assumptions, USD.
STORAGE_PER_GB_MONTH = 0.023  # object storage / hot retention baseline
COMPUTE_PER_VCPU_MONTH = 35.0  # managed VM / Kubernetes node blended price
NETWORK_PER_GB = 0.05  # inter-zone + egress blended network processing cost

# Capacity assumptions for self-build observability stack.
LOG_RETENTION_DAYS = 30
LOG_REPLICATION_FACTOR = 2
LOG_COMPRESSION_RATIO = 0.5
LOG_INDEX_OVERHEAD_RATIO = 0.3
LOG_COMPUTE_GB_PER_VCPU_DAY = 250
METRIC_EVENTS_PER_VCPU_SEC = 50_000
SERVICE_OVERHEAD_VCPU = 0.05
NETWORK_REPLICATION_FACTOR = 1.5

# Datadog-like SaaS assumptions, USD.
DATADOG_INFRA_HOST_PER_MONTH = 15.0
DATADOG_LOG_INGEST_PER_GB = 0.10
DATADOG_LOG_INDEXED_PER_GB = 1.70
DATADOG_LOG_INDEXED_RATIO = 0.2
DATADOG_CUSTOM_METRIC_PER_100_PER_MONTH = 5.0
DATADOG_CUSTOM_METRICS_PER_SERVICE = 100
HOSTS_PER_SERVICE = 1


@dataclass(frozen=True)
class ScaleTier:
    name: str
    services: int
    log_gb_per_day: float
    metric_events_per_sec: int


@dataclass(frozen=True)
class CostBreakdown:
    storage: float
    compute: float
    network: float

    @property
    def total(self) -> float:
        return self.storage + self.compute + self.network


TIERS: List[ScaleTier] = [
    ScaleTier("Small", services=10, log_gb_per_day=50, metric_events_per_sec=100_000),
    ScaleTier("Medium", services=100, log_gb_per_day=500, metric_events_per_sec=1_000_000),
    ScaleTier("Large", services=1_000, log_gb_per_day=5 * TB_TO_GB, metric_events_per_sec=10_000_000),
]


def estimate_build_cost(tier: ScaleTier) -> CostBreakdown:
    """Estimate monthly cost for a self-built log + metric observability stack."""
    raw_log_gb_month = tier.log_gb_per_day * DAYS_PER_MONTH

    stored_gb_month = (
        raw_log_gb_month
        * LOG_COMPRESSION_RATIO
        * (1 + LOG_INDEX_OVERHEAD_RATIO)
        * LOG_REPLICATION_FACTOR
    )
    storage_cost = stored_gb_month * STORAGE_PER_GB_MONTH

    log_vcpu = tier.log_gb_per_day / LOG_COMPUTE_GB_PER_VCPU_DAY
    metric_vcpu = tier.metric_events_per_sec / METRIC_EVENTS_PER_VCPU_SEC
    service_vcpu = tier.services * SERVICE_OVERHEAD_VCPU
    total_vcpu = log_vcpu + metric_vcpu + service_vcpu
    compute_cost = total_vcpu * COMPUTE_PER_VCPU_MONTH

    network_gb_month = raw_log_gb_month * NETWORK_REPLICATION_FACTOR
    network_cost = network_gb_month * NETWORK_PER_GB

    return CostBreakdown(
        storage=storage_cost,
        compute=compute_cost,
        network=network_cost,
    )


def estimate_datadog_cost(tier: ScaleTier) -> CostBreakdown:
    """Estimate comparable monthly Datadog SaaS cost.

    Storage maps to indexed log retention, compute maps to infra hosts and
    custom metrics, and network maps to log ingest volume.
    """
    raw_log_gb_month = tier.log_gb_per_day * DAYS_PER_MONTH
    indexed_log_gb_month = raw_log_gb_month * DATADOG_LOG_INDEXED_RATIO

    storage_cost = indexed_log_gb_month * DATADOG_LOG_INDEXED_PER_GB

    host_count = tier.services * HOSTS_PER_SERVICE
    custom_metric_count = tier.services * DATADOG_CUSTOM_METRICS_PER_SERVICE
    compute_cost = (
        host_count * DATADOG_INFRA_HOST_PER_MONTH
        + (custom_metric_count / 100) * DATADOG_CUSTOM_METRIC_PER_100_PER_MONTH
    )

    network_cost = raw_log_gb_month * DATADOG_LOG_INGEST_PER_GB

    return CostBreakdown(
        storage=storage_cost,
        compute=compute_cost,
        network=network_cost,
    )


def money(value: float) -> str:
    return f"${value:,.0f}"


def ratio(build_total: float, buy_total: float) -> str:
    if build_total == 0:
        return "n/a"
    return f"{buy_total / build_total:,.1f}x"


def render_table(headers: List[str], rows: List[List[str]]) -> str:
    widths = [
        max(len(str(row[column])) for row in [headers, *rows])
        for column in range(len(headers))
    ]

    def render_row(row: List[str]) -> str:
        return " | ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(row))

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join([render_row(headers), separator, *(render_row(row) for row in rows)])


def build_rows() -> List[List[str]]:
    rows: List[List[str]] = []

    for tier in TIERS:
        build = estimate_build_cost(tier)
        buy = estimate_datadog_cost(tier)

        rows.append(
            [
                tier.name,
                str(tier.services),
                f"{tier.log_gb_per_day:,.0f}",
                f"{tier.metric_events_per_sec:,.0f}",
                money(build.storage),
                money(build.compute),
                money(build.network),
                money(build.total),
                money(buy.storage),
                money(buy.compute),
                money(buy.network),
                money(buy.total),
                ratio(build.total, buy.total),
            ]
        )

    return rows


def build_component_summary() -> Dict[str, Dict[str, CostBreakdown]]:
    return {
        tier.name: {
            "build": estimate_build_cost(tier),
            "datadog_saas": estimate_datadog_cost(tier),
        }
        for tier in TIERS
    }


def main() -> None:
    headers = [
        "Tier",
        "Services",
        "Log GB/day",
        "Metric events/sec",
        "Build storage",
        "Build compute",
        "Build network",
        "Build total",
        "Datadog storage",
        "Datadog compute",
        "Datadog network",
        "Datadog total",
        "Buy/Build",
    ]

    print("Monthly observability cost estimate (USD)")
    print(render_table(headers, build_rows()))
    print()
    print("Assumptions:")
    print(f"- Month length: {DAYS_PER_MONTH} days")
    print(
        "- Build storage: "
        f"{LOG_RETENTION_DAYS}d retention, {LOG_COMPRESSION_RATIO:g}x compression, "
        f"{LOG_REPLICATION_FACTOR}x replication, {LOG_INDEX_OVERHEAD_RATIO:g} index overhead"
    )
    print(
        "- Build compute: "
        f"{LOG_COMPUTE_GB_PER_VCPU_DAY:,} log GB/vCPU/day, "
        f"{METRIC_EVENTS_PER_VCPU_SEC:,} metric events/vCPU/sec, "
        f"{SERVICE_OVERHEAD_VCPU:g} service overhead vCPU/service"
    )
    print(
        "- Datadog SaaS: "
        f"${DATADOG_LOG_INGEST_PER_GB:g}/GB log ingest, "
        f"${DATADOG_LOG_INDEXED_PER_GB:g}/GB indexed logs, "
        f"{DATADOG_LOG_INDEXED_RATIO:g} indexed ratio, "
        f"${DATADOG_INFRA_HOST_PER_MONTH:g}/host-month"
    )


if __name__ == "__main__":
    main()