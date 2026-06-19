import json
import os
import time
from typing import Dict, Any, List

import requests

from scripts.query_pipeline import query_alerts, query_correlate, query_rca


# --- TODO: Fill in your stack's specific details below ---

# Assuming your stack is managed by docker-compose in the parent directory
# and services are accessible by their names within the docker network.
# We'll use 'localhost' and map ports if necessary.

# Base URL for the AIOps pipeline
AIOPS_PIPELINE_URL = "http://localhost:8000"  # Changed from 8001 to 8000 based on docker-compose

# Mapping of service names to their ports as defined in docker-compose.yml
# If a service doesn't expose an HTTP port for health checks or similar, it can be omitted.
SERVICE_PORTS = {
    "frontend": 80,
    "api-gateway": 8080,
    "payment-svc": 8000,
    "inventory-svc": 8000,
    "notification-svc": 8000,
    "checkout-svc": 8000,
    "auth-svc": 8000,
    "log-collector": 8000,
    "dns-resolver": 8000,
    "cache-svc": 8000,
    "aiops-pipeline": 8000, # AIOps pipeline itself
}

# --- Helper Functions ---

def get_service_url(service_name: str) -> str:
    """Constructs the URL for a given service."""
    port = SERVICE_PORTS.get(service_name)
    if not port:
        raise ValueError(f"Port for service '{service_name}' not defined in SERVICE_PORTS.")
    # Use localhost for external access, assuming docker-compose maps ports correctly
    return f"http://localhost:{port}"

def run_probe(endpoint: str, log_file: str, interval: int = 5, threshold_ms: int = 500):
    """Runs the synthetic probe script."""
    # NOTE: This assumes synthetic_probe.sh is executable and in the PATH or specified with its path.
    # For simplicity here, we'll call it directly assuming it's in the same directory or accessible.
    # In a real scenario, you might want to make the path more robust.
    probe_script_path = os.path.join(os.path.dirname(__file__), "..", "synthetic_probe.sh")
    command = f"bash {probe_script_path} {endpoint} {log_file} {interval} {threshold_ms}"
    print(f"Running probe: {command}")
    # Using os.system for simplicity, but subprocess.Popen would be more robust for real-time monitoring
    os.system(command + " &") # Run in background
    return command # Return command for potential killing later

def stop_probe(command_str):
    """Attempts to stop the probe script run in the background."""
    # This is a simplistic way to stop the background process.
    # A more robust solution would involve managing PIDs.
    print(f"Stopping probe with command: {command_str}")
    # Find the process ID and kill it. This is OS-dependent and fragile.
    # On Linux/macOS, you might use `pkill -f "synthetic_probe.sh"`.
    # On Windows, you might use taskkill.
    # For this example, we'll assume a way to kill it.
    # os.system("pkill -f 'synthetic_probe.sh'") # Example for Linux/macOS
    pass # Placeholder for actual process termination logic


# --- Chaos Runner Implementation ---

def run_chaos_experiment(experiment: Dict[str, Any], baseline_file: str, chaos_results_file: str):
    """
    Executes a single chaos experiment.

    Args:
        experiment: A dictionary containing the experiment details (name, fault_type, target, etc.).
        baseline_file: Path to the baseline metrics file.
        chaos_results_file: Path to the file where results will be logged.
    """
    print(f"\n--- Running Experiment: {experiment['name']} ---")

    # Load baseline metrics
    try:
        with open(baseline_file, 'r') as f:
            baseline_metrics = json.load(f)
    except FileNotFoundError:
        print(f"Error: Baseline file not found at {baseline_file}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from baseline file at {baseline_file}")
        return

    target_service = experiment["target"]
    fault_type = experiment["fault_type"]
    duration = experiment.get("duration_seconds", 60) # Default duration if not specified

    probe_endpoint = None
    probe_log_file = f"chaos_run_{experiment['id']}.log"
    probe_process_command = None

    # 1. Inject Fault (using placeholder commands - replace with actual tooling like Pumba/Toxiproxy)
    print(f"Injecting fault: {fault_type} on {target_service} for {duration}s")
    if fault_type == "latency":
        # Example: Inject latency using tc (requires root/sudo or capabilities)
        # This is a placeholder and would need proper execution context.
        # We'll simulate the effect by adjusting the probe threshold if needed.
        delay_ms = experiment.get("delay_ms", 500)
        probe_threshold = experiment.get("probe_threshold_ms", 1000) # Higher threshold during latency injection
        print(f"Simulating {delay_ms}ms latency on {target_service}")
        # Real command would be something like:
        # sudo tc qdisc add dev eth0 root netem delay {delay_ms}ms
        # For now, we'll adjust the probe threshold.
        probe_endpoint = get_service_url(target_service)
        probe_process_command = run_probe(probe_endpoint, probe_log_file, threshold_ms=probe_threshold)

    elif fault_type == "pod_kill":
        # Example: Kill a pod (requires kubectl or equivalent)
        # This is highly dependent on your cluster orchestrator.
        print(f"Simulating pod kill for {target_service}")
        # Real command: kubectl delete pod <pod-name> -n <namespace>
        pass # No direct probe endpoint for pod kill simulation

    elif fault_type == "stress_cpu":
        # Example: Stress CPU (requires kubectl or specific tooling)
        print(f"Simulating CPU stress for {target_service}")
        # Real command: kubectl exec <pod-name> -n <namespace> -- stress --cpu 1 --timeout 60s
        pass # No direct probe endpoint for CPU stress simulation

    elif fault_type == "network_partition":
        print(f"Simulating network partition for {target_service}")
        # This is complex and depends on the network tooling (e.g., iptables, chaos mesh)
        pass # No direct probe endpoint for network partition simulation

    else:
        print(f"Unsupported fault type: {fault_type}")
        return

    # If a probe is associated with this fault, start it
    if probe_endpoint:
        probe_process_command = run_probe(probe_endpoint, probe_log_file, threshold_ms=experiment.get("probe_threshold_ms", 500))


    # Wait for fault to be active and for the specified duration
    print(f"Waiting for {duration} seconds...")
    time.sleep(duration)

    # 2. Stop Fault (cleanup)
    print("Stopping fault injection...")
    if fault_type == "latency":
        # Example: Remove latency rule
        # sudo tc qdisc del dev eth0 root netem delay {delay_ms}ms
        pass # Placeholder for cleanup command
    # Add cleanup for other fault types as needed

    # Stop the probe if it was running
    if probe_process_command:
        stop_probe(probe_process_command)
        # Allow some time for probe logs to be written after stopping
        time.sleep(5)

    # 3. Gather Metrics and Analyze
    print("Gathering metrics and analyzing results...")

    # Get current timestamp for metric queries
    current_ts = int(time.time())

    # Query AIOps pipeline for alerts, correlation, and RCA
    # Use the timestamp range that covers the experiment duration + some buffer
    query_start_ts = int(time.time()) - duration - 60 # Start 60s before fault injection
    query_end_ts = current_ts

    # --- TODO: Call AIOps pipeline endpoints ---
    alerts = query_alerts(AIOPS_PIPELINE_URL, since=query_start_ts)
    # Mocking correlate and rca calls for now, as their implementation is not provided
    # correlate_result = query_correlate(AIOPS_PIPELINE_URL, window={"start_time": query_start_ts, "end_time": query_end_ts})
    # rca_result = query_rca(AIOPS_PIPELINE_URL, cluster=correlate_result) # Assumes correlate returns a cluster object

    # Mock results for correlate and rca for now
    correlate_result = {"cluster_id": "mock-cluster-abc", "events_count": 10}
    rca_result = {"root_service": "unknown", "confidence": 0.0, "evidence": []}


    # --- Process Probe Results ---
    probe_results = {"pass_rate": 0.0, "avg_latency_ms": 0.0, "fail_count": 0}
    if os.path.exists(probe_log_file):
        try:
            with open(probe_log_file, 'r') as f:
                lines = f.readlines()
                total_probes = 0
                passed_probes = 0
                total_latency = 0
                failed_probes = 0
                for line in lines:
                    if line.startswith("#"): continue # Skip header
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        ts, status, latency_ms_str = parts[0], parts[1], parts[2]
                        latency_ms = int(latency_ms_str)
                        total_probes += 1
                        if status == "pass":
                            passed_probes += 1
                            total_latency += latency_ms
                        else:
                            failed_probes += 1
                if passed_probes > 0:
                    probe_results["pass_rate"] = (passed_probes / total_probes) * 100 if total_probes > 0 else 0
                    probe_results["avg_latency_ms"] = total_latency / passed_probes
                probe_results["fail_count"] = failed_probes
        except Exception as e:
            print(f"Error processing probe log {probe_log_file}: {e}")


    # --- Compare with Ground Truth and Hypothesis ---
    # This is where you'd compare the observed metrics against the expected outcomes.
    # For now, we'll just log the collected data.

    # Populate the result dictionary
    chaos_run_result = {
        "experiment_id": experiment["id"],
        "name": experiment["name"],
        "timestamp": current_ts,
        "hypothesis": experiment.get("hypothesis", "N/A"),
        "ground_truth": experiment.get("ground_truth", {}),
        "measured_metrics": {
            "probe_results": probe_results,
            "alerts": alerts,
            "correlation": correlate_result,
            "rca": rca_result,
            # Add other metrics here if captured (e.g., from Prometheus)
        },
        "pass": False # Default to False, set to True if all conditions met
    }

    # --- TODO: Implement your actual validation logic here ---
    # Compare chaos_run_result['measured_metrics'] with chaos_run_result['ground_truth']
    # and potentially the hypothesis.

    # Example validation (very basic):
    # Check if RCA picked the correct root service if specified in ground truth
    expected_root_service = experiment.get("ground_truth", {}).get("expected_root_service")
    if expected_root_service and rca_result.get("root_service") == expected_root_service:
        print(f"RCA correctly identified '{expected_root_service}' as root service.")
        # chaos_run_result["pass"] = True # Tentative pass, needs more checks
    elif expected_root_service and rca_result.get("root_service") != expected_root_service:
        print(f"RCA incorrectly identified '{rca_result.get('root_service')}' instead of '{expected_root_service}'.")
    elif expected_root_service == "NOT checkout-svc" and rca_result.get("root_service") != "checkout-svc":
        print(f"RCA correctly excluded 'checkout-svc' as root service.")
        # chaos_run_result["pass"] = True # Tentative pass, needs more checks

    # Check probe pass rate if specified
    expected_pass_rate = experiment.get("ground_truth", {}).get("expected_pass_rate")
    if expected_pass_rate is not None and probe_results["pass_rate"] >= expected_pass_rate:
        print(f"Probe pass rate ({probe_results['pass_rate']:.2f}%) meets expected threshold ({expected_pass_rate}%).")
        # chaos_run_result["pass"] = True # Tentative pass
    elif expected_pass_rate is not None:
        print(f"Probe pass rate ({probe_results['pass_rate']:.2f}%) did not meet expected threshold ({expected_pass_rate}%).")


    # Log the result
    try:
        # Append results to the chaos_results.json file
        if not os.path.exists(chaos_results_file):
            results_data = []
        else:
            with open(chaos_results_file, 'r') as f:
                try:
                    results_data = json.load(f)
                except json.JSONDecodeError:
                    results_data = [] # Start fresh if file is corrupted

        results_data.append(chaos_run_result)
        with open(chaos_results_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        print(f"Experiment result logged to {chaos_results_file}")

    except Exception as e:
        print(f"Error writing chaos results to {chaos_results_file}: {e}")

    # Clean up probe log file if it exists
    if os.path.exists(probe_log_file):
        try:
            os.remove(probe_log_file)
            print(f"Cleaned up probe log file: {probe_log_file}")
        except OSError as e:
            print(f"Error removing probe log file {probe_log_file}: {e}")


# --- Main Execution Logic ---

if __name__ == "__main__":
    # --- Configuration ---
    EXPERIMENTS_TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "..", "experiments_template.yaml")
    BASELINE_METRICS_FILE = "baseline.json" # Assumes this file is in the current directory
    CHAOS_RESULTS_FILE = "chaos_results.json" # Output file for all experiment results

    # --- Load Experiments ---
    try:
        import yaml
        with open(EXPERIMENTS_TEMPLATE_FILE, 'r') as f:
            experiments_data = yaml.safe_load(f)
            # Filter out the reference experiments (id 1 and 10) for actual runs
            experiments_to_run = [exp for exp in experiments_data.get("experiments", []) if exp.get("id") not in [1, 10]]
    except FileNotFoundError:
        print(f"Error: Experiments template file not found at {EXPERIMENTS_TEMPLATE_FILE}")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {EXPERIMENTS_TEMPLATE_FILE}: {e}")
        exit(1)

    if not experiments_to_run:
        print("No experiments found to run (excluding reference experiments 1 and 10).")
        exit(0)

    # --- Pre-run Setup ---
    print("Starting chaos engineering run...")

    # Ensure baseline file exists (or prompt user to capture it)
    if not os.path.exists(BASELINE_METRICS_FILE):
        print(f"Warning: Baseline metrics file '{BASELINE_METRICS_FILE}' not found.")
        print("Please run 'python scripts/capture_baseline.py --duration 300 --out baseline.json' first.")
        # Optionally, attempt to capture baseline here or exit.
        # For now, we'll proceed but experiments requiring baseline will likely fail.

    # --- Execute Experiments ---
    for experiment in experiments_to_run:
        run_chaos_experiment(experiment, BASELINE_METRICS_FILE, CHAOS_RESULTS_FILE)

    print("\n--- Chaos Engineering Run Complete ---")
    print(f"Results logged to: {CHAOS_RESULTS_FILE}")
    # You can add a command here to view the results, e.g., 'cat chaos_results.json' or 'python scripts/score_run.py'