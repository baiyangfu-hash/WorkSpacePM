#!/usr/bin/env bash
# Card 219 V1.0 launcher (DETACHED): start the governed Run, renew once (must succeed), then start the renewal loop, a keep-awake process, the memory guard (40 GB) and the gates
# through detach_run.py (own process group, no console, output to log files) so that nothing depends on the session that started them. Status: gates/status/*.json and status.log.
set -euo pipefail
ROOT=/c/Users/fubai/Documents/My_Workspace; EV="$ROOT/.auto-pm/reports/m3-rel7"; G="$EV/gates"
PY="$ROOT/.venv/Scripts/python.exe"; BASHW='C:\Program Files\Git\usr\bin\bash.exe'
cd "$ROOT"
bash "$EV/rel7_1_approve_start.sh" > "$EV/start2.out" 2>&1 || { echo "START FAILED"; tail -5 "$EV/start2.out"; exit 1; }
bash "$ROOT/.auto-pm/reports/m2_lease_renew.sh" "$EV/close.env" > "$EV/renew_first.log" 2>&1 || { echo "FIRST RENEW FAILED"; cat "$EV/renew_first.log"; exit 1; }
echo "first renewal ok"
rm -f "$EV/STOP_RENEW"
mkdir -p "$G/status"
det() { "$PY" -B "$EV/detach_run.py" "$@"; }
det "$EV/renew_loop.stdout" "$BASHW" "$ROOT/.auto-pm/reports/m2_renew_loop.sh" "$EV/close.env" 1200
det "$EV/keepawake.log" "$PY" -B "$EV/keepawake.py" "$EV/gates_all.exit"
cat > "$EV/rel7_gates_wrap.sh" <<'WRAP'
#!/usr/bin/env bash
EV=/c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel7
bash "$EV/rel7_gates_all.sh" > "$EV/gates_all.log" 2>&1
echo $? > "$EV/gates_all.exit"
WRAP
det "$EV/gates_all.launch.log" "$BASHW" "$EV/rel7_gates_wrap.sh"
det "$EV/mem_guard.log" "$PY" -B "$EV/mem_guard.py" "$G/status" "$G/status/current_pid" 40 36
echo "LAUNCHED DETACHED $(date +%H:%M)"
