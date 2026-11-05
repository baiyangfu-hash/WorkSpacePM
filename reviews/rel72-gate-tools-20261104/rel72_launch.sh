#!/usr/bin/env bash
# Card 221 V1.0 launcher (DETACHED): start the governed Run, renew once (must succeed), then start the renewal loop, a keep-awake process, the memory guard (40 GB) and the gates
# through detach_run.py (own process group, no console, output to log files) so that nothing depends on the session that started them. Status: gates/status/*.json and status.log.
set -euo pipefail
ROOT=/c/Users/fubai/Documents/My_Workspace; EV="$ROOT/.auto-pm/reports/m3-rel72"; G="$EV/gates"
PY="$ROOT/.venv/Scripts/python.exe"; BASHW='C:\Program Files\Git\usr\bin\bash.exe'
cd "$ROOT"
unset PG_G PG_WT GATE_GROUPS PG_REHEARSAL  # leftovers of a rehearsal or a test must not steer the real run
if [ -f "$G/FAILED" ]; then mv "$G/FAILED" "$G/FAILED.previous.$(date +%s)"; fi  # a previous failure is kept as evidence, never deleted
rm -f "$EV/gates_all.exit" "$G/DONE" "$G/status/RESUME" "$G/status/PAUSED" "$G/status/current_pid"
if [ "${1:-}" = "--dry-run" ]; then
  D="$EV/dryrun"; mkdir -p "$D/gates/status"; rm -f "$D/gates_all.exit" "$D/gates/DONE" "$D/gates/FAILED"
  det() { "$PY" -B "$EV/detach_run.py" "$@"; }
  cat > "$D/dummy_gates.sh" <<'DUMMY'
#!/usr/bin/env bash
EV=/c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel72
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
# out-of-band anchor: approve_start in this folder must equal the copy on the reviewed branch (its hash is also reported in the thread); the comparison goes to launch_anchor.log
git fetch -q origin claude/rel72-gate-tools-20261104 || { echo "ANCHOR: cannot fetch the reviewed branch"; exit 1; }
BRANCH_SHA="$(git show origin/claude/rel72-gate-tools-20261104:reviews/rel72-gate-tools-20261104/rel72_1_approve_start.sh | sha256sum | cut -d' ' -f1)"
LOCAL_SHA="$(sha256sum < "$EV/rel72_1_approve_start.sh" | cut -d' ' -f1)"
echo "$(date -u +%FT%TZ) approve_start anchor: branch=$BRANCH_SHA local=$LOCAL_SHA" | tee -a "$EV/launch_anchor.log"
[ "$BRANCH_SHA" = "$LOCAL_SHA" ] || { echo "ANCHOR MISMATCH: refusing to start"; exit 1; }
bash "$EV/rel72_1_approve_start.sh" > "$EV/start2.out" 2>&1 || { echo "START FAILED"; tail -5 "$EV/start2.out"; exit 1; }
bash "$ROOT/.auto-pm/reports/m2_lease_renew.sh" "$EV/close.env" > "$EV/renew_first.log" 2>&1 || { echo "FIRST RENEW FAILED"; cat "$EV/renew_first.log"; exit 1; }
echo "first renewal ok"
# The 3 h hold cap is shorter than the ten groups.  The extension needs the user's OWN authorization for THIS card, written to HOLD_REF.txt (the bare message id) before or during the run.
# So the extension is NOT done at the start: a detached hold watcher waits 150 minutes (the 3 h hold cap is then 30 minutes away) and, only if the gates are still running, extends ONCE by 7200 s.
cat > "$EV/rel72_hold_watch.sh" <<'HOLD'
#!/usr/bin/env bash
EV=/c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel72; ROOT=/c/Users/fubai/Documents/My_Workspace; PY="$ROOT/.venv/Scripts/python.exe"
cd "$ROOT"
sleep 9000
if [ -f "$EV/gates_all.exit" ] || [ -f "$EV/gates/DONE" ] || [ -f "$EV/EXTENDED_ONCE" ]; then echo "$(date -u +%FT%TZ) no extension needed or already done" >> "$EV/extend_hold.out"; exit 0; fi
HREF="$(tr -d '\r\n' < "$EV/HOLD_REF.txt" 2>/dev/null)"
if [ -z "$HREF" ]; then echo "$(date -u +%FT%TZ) no extension authorization (HOLD_REF.txt absent): no extension" >> "$EV/extend_hold.out"; exit 0; fi
"$PY" -B main.py continuity lease extend-hold --run-id RUN-SW008-M3-REL72-002 --extra-seconds 7200 --approval-evidence-ref user-confirmation:$HREF --idempotency-key RUN-SW008-M3-REL72-002-hold-1 >> "$EV/extend_hold.out" 2>&1 && touch "$EV/EXTENDED_ONCE"
HOLD
rm -f "$EV/STOP_RENEW"
mkdir -p "$G/status"
det() { "$PY" -B "$EV/detach_run.py" "$@"; }
det "$EV/renew_loop.stdout" "$BASHW" "$ROOT/.auto-pm/reports/m2_renew_loop.sh" "$EV/close.env" 1200
det "$EV/keepawake.log" "$PY" -B "$EV/keepawake.py" "$EV/gates_all.exit"
mkdir -p "$G"
det "$EV/heartbeat.stdout" "$PY" -B "$EV/heartbeat.py" "$G/heartbeat.log" "$EV/gates_all.exit"
cat > "$EV/rel72_gates_wrap.sh" <<'WRAP'
#!/usr/bin/env bash
EV=/c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel72
bash "$EV/rel72_gates_all.sh" > "$EV/gates_all.log" 2>&1
rc=$?
echo $rc > "$EV/gates_all.exit"
if [ "$rc" -ne 0 ]; then touch "$EV/STOP_RENEW"; fi  # failed gates: no reason to keep the lease alive (the close script stops it on success)
WRAP
det "$EV/gates_all.launch.log" "$BASHW" "$EV/rel72_gates_wrap.sh"
det "$EV/mem_guard.log" "$PY" -B "$EV/mem_guard.py" "$G/status" "$G/status/current_pid" 40 36
det "$EV/hold_watch.log" "$BASHW" "$EV/rel72_hold_watch.sh"
echo "LAUNCHED DETACHED $(date +%H:%M)"
