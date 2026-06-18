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
    echo "[DRY-RUN] would execute: rollback_clear_cache on $SERVICE"
    exit 0
fi

echo "Executing rollback_clear_cache on $SERVICE..."
sleep 1
echo "Rollback completed."
exit 0
