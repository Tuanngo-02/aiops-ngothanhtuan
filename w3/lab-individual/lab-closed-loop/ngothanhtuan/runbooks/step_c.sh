#!/bin/bash
set -e
DRY_RUN=0
SERVICE=""
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --service) SERVICE="$2"; shift ;;
        --dry-run) DRY_RUN=1 ;;
    esac
    shift
done
if [ "$DRY_RUN" -eq 1 ]; then echo "[DRY-RUN] step_c on $SERVICE"; exit 0; fi
echo "Running step_c on $SERVICE"
# Simulate failure for scenario 4 if checkout-svc or api-gateway is killed?
# We will just assume it succeeds normally, and the failure can be injected externally if needed.
# Wait, the instruction says "force step C to fail by stopping container".
# If we just do docker inspect or similar, but let's just make it always succeed unless we inject failure.
# Let's check if the container is running.
CONTAINER_NAME="ronki-${SERVICE#ronki-}"
if [ "$(docker inspect -f '{{.State.Running}}' $CONTAINER_NAME 2>/dev/null)" != "true" ]; then
    echo "Container is not running. Failing step C."
    exit 1
fi
exit 0
