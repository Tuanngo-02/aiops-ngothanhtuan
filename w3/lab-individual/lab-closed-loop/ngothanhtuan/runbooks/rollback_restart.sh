#!/bin/bash
set -e

SERVICE=""
DRY_RUN=0

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --service) SERVICE="$2"; shift ;;
        --dry-run) DRY_RUN=1 ;;
    esac
    shift
done

if [ -z "$SERVICE" ]; then
    echo "Missing --service"
    exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[DRY-RUN] would execute: rollback_restart on $SERVICE"
    exit 0
fi

CONTAINER_NAME="ronki-${SERVICE#ronki-}"

echo "Executing rollback_restart on $CONTAINER_NAME..."
# For mock purposes, rollback of a restart might just be another restart or a no-op that simulates fixing state
docker restart "$CONTAINER_NAME"
echo "Rollback completed."
exit 0
