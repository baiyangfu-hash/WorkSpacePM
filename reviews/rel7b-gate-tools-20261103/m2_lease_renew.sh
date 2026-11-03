#!/usr/bin/env bash
# Renew the lease of the Run named in an M2 card config (same owner, same token, current version, 3600 s).
# Usage: bash .auto-pm/reports/m2_lease_renew.sh <config.env>
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
ROOT=/c/Users/fubai/Documents/My_Workspace
# The config path is made absolute BEFORE the cd below: a relative path used to make every renewal fail silently (V05-C first attempt, 2026-10-09).
CONFIG="$(realpath -- "$1" 2>/dev/null)" || { echo "config missing: $1"; exit 1; }
cd "$ROOT"
[[ -f "$CONFIG" ]] || { echo "config missing: $CONFIG"; exit 1; }
# shellcheck disable=SC1090
source "$CONFIG"
PY="$ROOT/.venv/Scripts/python.exe"
q() { "$PY" -B -c 'import sqlite3,sys;c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True);r=c.execute(sys.argv[1],tuple(sys.argv[2:])).fetchone();print(r[0] if r else "NONE")' "$@"; }
VER="$(q "select version from execution_leases where run_id=?" "$RUN")"
[[ "$VER" != NONE ]] || { echo "no lease for Run $RUN"; exit 1; }
M2_LEASE_TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")" "$PY" -B main.py continuity lease renew --run-id "$RUN" --owner "$OWNER" \
  --lease-token-env M2_LEASE_TOKEN --expected-version "$VER" --lease-seconds 3600 \
  --idempotency-key "${RUN,,}-renew-v$VER" | grep -E '"state"|"version"|lease_expires'
