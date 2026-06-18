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
    echo "[DRY-RUN] would execute: clear_cache on $SERVICE"
    exit 0
fi

echo "Executing clear_cache on $SERVICE..."
# Simulate clearing cache
sleep 1
echo "Cache cleared."
exit 0
