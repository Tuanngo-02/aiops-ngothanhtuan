import json
from typing import Dict, Any, List

import requests

def query_alerts(base_url: str, since: int) -> List[Dict[str, Any]]:
    """Queries the AIOps pipeline for alerts since a given timestamp."""
    try:
        response = requests.get(f"{base_url}/alerts?since={since}")
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json().get("alerts", [])
    except requests.exceptions.RequestException as e:
        print(f"Error querying alerts: {e}")
        return []

def query_correlate(base_url: str, window: Dict[str, Any]) -> Dict[str, Any]:
    """Queries the AIOps pipeline for event correlation."""
    try:
        response = requests.post(f"{base_url}/correlate", json=window)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error querying correlate: {e}")
        return {"error": str(e)}

def query_rca(base_url: str, cluster: Dict[str, Any]) -> Dict[str, Any]:
    """Queries the AIOps pipeline for root cause analysis."""
    try:
        response = requests.post(f"{base_url}/rca", json=cluster)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error querying rca: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Example usage:
    AIOPS_PIPELINE_URL = "http://localhost:8000"  # Assuming AIOps pipeline runs on port 8000

    # Example: Get alerts since a specific timestamp (e.g., 1 hour ago)
    one_hour_ago = int(time.time()) - 3600
    print(f"Fetching alerts since {one_hour_ago}...")
    alerts = query_alerts(AIOPS_PIPELINE_URL, since=one_hour_ago)
    print("--- Alerts ---")
    for alert in alerts:
        print(alert)

    # Example: Correlate events within a time window
    correlation_window = {"start_time": one_hour_ago, "end_time": int(time.time())}
    print("\nCorrelating events...")
    correlation_result = query_correlate(AIOPS_PIPELINE_URL, window=correlation_window)
    print("--- Correlation Result ---")
    print(correlation_result)

    # Example: Perform RCA on a cluster
    if "cluster_id" in correlation_result:
        print("\nPerforming RCA...")
        rca_result = query_rca(AIOPS_PIPELINE_URL, cluster=correlation_result)
        print("--- RCA Result ---")
        print(rca_result)
    else:
        print("\nSkipping RCA: No cluster ID found from correlation.")