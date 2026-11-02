#!/usr/bin/env bash
EV=/c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel7
D="$EV/dryrun"; PY=/c/Users/fubai/Documents/My_Workspace/.venv/Scripts/python.exe
"$PY" -B "$EV/gate_status.py" "$D/gates/status" dry_stage RUNNING
sleep 45
"$PY" -B "$EV/gate_status.py" "$D/gates/status" dry_stage PASS 0
echo done > "$D/gates/DONE"; echo 0 > "$D/gates_all.exit"
