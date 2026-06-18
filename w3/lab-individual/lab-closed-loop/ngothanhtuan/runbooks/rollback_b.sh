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
if [ "$DRY_RUN" -eq 1 ]; then echo "[DRY-RUN] rollback_b on $SERVICE"; exit 0; fi
echo "Running rollback_b on $SERVICE"
exit 0
