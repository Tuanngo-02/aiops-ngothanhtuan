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
    echo "[DRY-RUN] would execute: restart_service on $SERVICE"
    exit 0
fi

# Clean up service name if it includes 'ronki-'
CONTAINER_NAME="ronki-${SERVICE#ronki-}"

echo "Executing restart_service on $CONTAINER_NAME..."
docker restart "$CONTAINER_NAME"
echo "Restart completed."
exit 0
