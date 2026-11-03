#!/usr/bin/env bash
# Keep a Run lease alive during a long gate run. Usage: m2_renew_loop.sh <close.env> [interval_seconds=1200]; stop with: touch <EV>/STOP_RENEW
# Renews (same owner/token, +3600 s) every interval until STOP_RENEW appears or a renewal fails.
set -u
CONFIG="$1"; INTERVAL="${2:-1200}"
# shellcheck disable=SC1090
source "$CONFIG"
while [[ ! -f "$EV/STOP_RENEW" ]]; do
  sleep "$INTERVAL"
  [[ -f "$EV/STOP_RENEW" ]] && break
  bash /c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m2_lease_renew.sh "$CONFIG" >> "$EV/renew_loop.log" 2>&1 || { echo "renewal failed $(date -u +%FT%TZ)" >> "$EV/renew_loop.log"; exit 1; }
done
