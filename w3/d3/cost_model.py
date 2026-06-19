"""
AIOps Platform Cost Model — Ngo Thanh Tuan
W3-D3: ROI calculator for AIOps investment decision.

Calculates whether deploying an AIOps platform is financially justified
based on incident frequency, downtime costs, and expected MTTR reduction.
"""


def is_worth_it(
    num_services: int,
    incidents_per_month: int,
    avg_incident_duration_hours: float,
    downtime_cost_per_hour: float,
    expected_mttr_reduction_pct: float = 0.4,
    aiops_monthly_cost: float = 15_000,
) -> dict:
    """
    Calculate ROI of deploying an AIOps platform.

    Args:
        num_services: Number of microservices being monitored.
        incidents_per_month: Average number of incidents per month.
        avg_incident_duration_hours: Average duration of each incident in hours.
        downtime_cost_per_hour: Cost of downtime per hour in dollars.
        expected_mttr_reduction_pct: Expected reduction in MTTR from AIOps (0.0-1.0).
        aiops_monthly_cost: Monthly cost of running the AIOps platform.

    Returns:
        dict with keys:
          - monthly_value: float — estimated monthly savings from reduced downtime
          - monthly_cost: float — monthly cost of AIOps platform
          - roi: float — return on investment ratio (value / cost)
          - payback_months: float — months to break even (or float('inf'))
          - verdict: "worth_it" | "marginal" | "not_worth_it"

    Verdict rule:
        roi > 1.5 → worth_it
        1.0 < roi ≤ 1.5 → marginal
        roi ≤ 1.0 → not_worth_it
    """
    # Total monthly downtime cost without AIOps
    total_downtime_hours = incidents_per_month * avg_incident_duration_hours
    total_downtime_cost = total_downtime_hours * downtime_cost_per_hour

    # Monthly value = savings from reduced MTTR
    # AIOps reduces incident duration by expected_mttr_reduction_pct
    monthly_value = total_downtime_cost * expected_mttr_reduction_pct

    # Monthly cost of AIOps platform
    monthly_cost = aiops_monthly_cost

    # ROI = value / cost
    if monthly_cost == 0:
        roi = float('inf') if monthly_value > 0 else 0.0
    else:
        roi = monthly_value / monthly_cost

    # Payback period: how many months until cumulative savings cover initial setup
    # Assume setup cost = 3x monthly cost (typical for platform deployment)
    setup_cost = monthly_cost * 3
    net_monthly_savings = monthly_value - monthly_cost

    if net_monthly_savings <= 0:
        payback_months = float('inf')
    else:
        payback_months = round(setup_cost / net_monthly_savings, 1)

    # Verdict
    if roi > 1.5:
        verdict = "worth_it"
    elif roi > 1.0:
        verdict = "marginal"
    else:
        verdict = "not_worth_it"

    return {
        "monthly_value": round(monthly_value, 2),
        "monthly_cost": round(monthly_cost, 2),
        "roi": round(roi, 2),
        "payback_months": payback_months,
        "verdict": verdict,
    }


if __name__ == "__main__":
    # ─── Scenario 1: Small startup, low incident rate ───────────────
    print("=== Scenario 1: Small Startup (20 services) ===")
    result1 = is_worth_it(
        num_services=20,
        incidents_per_month=2,
        avg_incident_duration_hours=1,
        downtime_cost_per_hour=10_000,
        aiops_monthly_cost=15_000,
    )
    print(result1)
    print()

    # ─── Scenario 2: Mid-size company, moderate incidents ──────────
    print("=== Scenario 2: Mid-Size Company (100 services) ===")
    result2 = is_worth_it(
        num_services=100,
        incidents_per_month=5,
        avg_incident_duration_hours=2,
        downtime_cost_per_hour=20_000,
        aiops_monthly_cost=25_000,
    )
    print(result2)
    print()

    # ─── Scenario 3: E-Commerce Platform (our stack) ───────────────
    # Industry: E-Commerce (online retail)
    # Downtime cost justification:
    #   - Average e-commerce revenue: $50,000/hour for mid-tier platform
    #   - During peak hours (flash sales, holidays): up to $200,000/hour
    #   - Using conservative estimate of $50,000/hour which includes:
    #     * Direct revenue loss from failed transactions
    #     * Cart abandonment (customers leave and don't return)
    #     * Brand reputation damage (social media complaints)
    #     * SLA penalties to B2B partners
    #   - Source: Gartner estimates average IT downtime cost at $5,600/min ($336,000/hr)
    #     for large enterprises. $50,000/hr is conservative for mid-tier e-commerce.
    print("=== Scenario 3: E-Commerce Platform (10 services, our stack) ===")
    result3 = is_worth_it(
        num_services=10,
        incidents_per_month=3,
        avg_incident_duration_hours=1.5,
        downtime_cost_per_hour=50_000,
        expected_mttr_reduction_pct=0.4,
        aiops_monthly_cost=15_000,
    )
    print(result3)
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for i, (name, r) in enumerate([
        ("Small Startup", result1),
        ("Mid-Size Company", result2),
        ("E-Commerce (our stack)", result3),
    ], 1):
        print(f"  {i}. {name}: ROI={r['roi']}, Payback={r['payback_months']}mo, Verdict={r['verdict']}")