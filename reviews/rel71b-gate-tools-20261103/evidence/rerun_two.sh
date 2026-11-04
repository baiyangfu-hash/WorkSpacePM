#!/usr/bin/env bash
# Exception evidence for release 7.1 G2 (user words cmsg_01AfNxhPWkgwWYuL1EVfYC7t7ArBXS4AXC393MHjk5J7Cu, 2026-11-04T03:35:09Z): rerun ONLY the two core cases, same candidate worktree/bytes/command/env as the V1.0 gate.
set -uo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
ROOT=/c/Users/fubai/Documents/My_Workspace; X="$ROOT/.auto-pm/reports/m3-rel71b/exception"; G10="$ROOT/.auto-pm/reports/m3-rel71/gates"
WT="$ROOT/.auto-pm/worktrees/m3-rel71"; P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
PY="$ROOT/.venv/Scripts/python.exe"
pin() { { echo "HEAD=$(git -C "$WT" rev-parse HEAD)"; echo "ORIGIN_MAIN=$(git -C "$ROOT" rev-parse origin/main)"; echo "date_utc=$(date -u +%FT%TZ)"; } > "$X/$1"; ( cd "$WT" && find . -path ./.git -prune -o -type f -newer "$G10/bytes_at_gates.txt" -print | head -0 ); }
power() { { echo "== powercfg /a"; powercfg /a; echo "== powercfg /requests"; powercfg /requests; echo "== lid close action"; powercfg /query SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936; } > "$X/$1" 2>&1; }
pin pin_before.txt; power power_before.txt
git -C "$WT" status --short > "$X/status_before.txt"
rm -f "$X/DONE"
"$PY" -B "$ROOT/.auto-pm/reports/m3-rel71b/heartbeat.py" "$X/heartbeat.log" "$X/DONE" &
HB=$!
cd "$WT/$P" || exit 9
"$PY" -B -m pytest -o addopts= --no-cov -p no:cacheprovider --color=no -v --durations=5 \
  "tests/core/test_agent_worktree_service.py::test_a_keep_list_agent_can_still_close_its_own_finished_station_and_open_the_next_card" \
  "tests/core/test_mission_switch_service.py::test_a_dispatch_run_is_held_to_one_lease_per_project_inside_the_transaction" > "$X/rerun.txt" 2>&1
echo $? > "$X/rerun.exit"
cd "$ROOT"
echo done > "$X/DONE"; sleep 32; kill $HB 2>/dev/null
pin pin_after.txt; power power_after.txt
git -C "$WT" status --short > "$X/status_after.txt"
echo finished > "$X/FINISHED"
