#!/usr/bin/env bash
# Card 219 V1.0 launcher (DETACHED): start the governed Run, renew once (must succeed), then start the renewal loop, a keep-awake process, the memory guard (40 GB) and the gates
# through detach_run.py (own process group, no console, output to log files) so that nothing depends on the session that started them. Status: gates/status/*.json and status.log.
set -euo pipefail
ROOT=/c/Users/fubai/Documents/My_Workspace; EV="$ROOT/.auto-pm/reports/m3-rel7"; G="$EV/gates"
PY="$ROOT/.venv/Scripts/python.exe"; BASHW='C:\Program Files\Git\usr\bin\bash.exe'
cd "$ROOT"
unset PG_G PG_WT GATE_GROUPS  # leftovers of a rehearsal or a test must not steer the real run
if [ -f "$G/FAILED" ]; then mv "$G/FAILED" "$G/FAILED.previous.$(date +%s)"; fi  # a previous failure is kept as evidence, never deleted
rm -f "$EV/gates_all.exit" "$G/DONE" "$G/status/RESUME" "$G/status/PAUSED" "$G/status/current_pid"
if [ "${1:-}" = "--dry-run" ]; then
  D="$EV/dryrun"; mkdir -p "$D/gates/status"; rm -f "$D/gates_all.exit" "$D/gates/DONE" "$D/gates/FAILED"
  det() { "$PY" -B "$EV/detach_run.py" "$@"; }
  cat > "$D/dummy_gates.sh" <<'DUMMY'
#!/usr/bin/env bash
EV=/c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel7
D="$EV/dryrun"; PY=/c/Users/fubai/Documents/My_Workspace/.venv/Scripts/python.exe
"$PY" -B "$EV/gate_status.py" "$D/gates/status" dry_stage RUNNING
sleep 45
"$PY" -B "$EV/gate_status.py" "$D/gates/status" dry_stage PASS 0
echo done > "$D/gates/DONE"; echo 0 > "$D/gates_all.exit"
DUMMY
  det "$D/keepawake.log" "$PY" -B "$EV/keepawake.py" "$D/gates_all.exit"
  det "$D/gates.log" "$BASHW" "$D/dummy_gates.sh"
  det "$D/mem_guard.log" "$PY" -B "$EV/mem_guard.py" "$D/gates/status" "$D/gates/status/current_pid" 40 36
  echo "DRYRUN LAUNCHED DETACHED (no Run, no real gates)"; exit 0
fi
bash "$EV/rel7_1_approve_start.sh" > "$EV/start2.out" 2>&1 || { echo "START FAILED"; tail -5 "$EV/start2.out"; exit 1; }
bash "$ROOT/.auto-pm/reports/m2_lease_renew.sh" "$EV/close.env" > "$EV/renew_first.log" 2>&1 || { echo "FIRST RENEW FAILED"; cat "$EV/renew_first.log"; exit 1; }
echo "first renewal ok"
# the user's own words (typed in the main-executor thread, message cmsg_01AfNxhPWkgwWYuL1EVfYC7tJPaJZwt3hvXGtUMyCqBguG; first typed 2026-11-02 16:32 MST in another thread as cmsg_01AfNxhPWkgwWYuL1EVfYC7tDZkqRnAohX7d2d2DtjbBJB: "同意发版 7 门禁租约延长 1 小时") authorize one extension of this Run's 3 h hold cap by 3600 s
"$PY" -B main.py continuity lease extend-hold --run-id RUN-SW008-M3-REL7-001 --extra-seconds 3600 --approval-evidence-ref user-confirmation:cmsg_01AfNxhPWkgwWYuL1EVfYC7tJPaJZwt3hvXGtUMyCqBguG --idempotency-key RUN-SW008-M3-REL7-001-hold-1 > "$EV/extend_hold.out" 2>&1 || { echo "EXTEND-HOLD FAILED"; tail -5 "$EV/extend_hold.out"; exit 1; }
echo "hold cap extended by 3600 s"
rm -f "$EV/STOP_RENEW"
mkdir -p "$G/status"
det() { "$PY" -B "$EV/detach_run.py" "$@"; }
det "$EV/renew_loop.stdout" "$BASHW" "$ROOT/.auto-pm/reports/m2_renew_loop.sh" "$EV/close.env" 1200
det "$EV/keepawake.log" "$PY" -B "$EV/keepawake.py" "$EV/gates_all.exit"
cat > "$EV/rel7_gates_wrap.sh" <<'WRAP'
#!/usr/bin/env bash
EV=/c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel7
bash "$EV/rel7_gates_all.sh" > "$EV/gates_all.log" 2>&1
rc=$?
echo $rc > "$EV/gates_all.exit"
if [ "$rc" -ne 0 ]; then touch "$EV/STOP_RENEW"; fi  # failed gates: no reason to keep the lease alive (the close script stops it on success)
WRAP
det "$EV/gates_all.launch.log" "$BASHW" "$EV/rel7_gates_wrap.sh"
det "$EV/mem_guard.log" "$PY" -B "$EV/mem_guard.py" "$G/status" "$G/status/current_pid" 40 36
echo "LAUNCHED DETACHED $(date +%H:%M)"
