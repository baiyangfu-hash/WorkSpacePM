#!/usr/bin/env bash
# The nine regression groups (ten outputs) in a smart order: the group that failed last time and the quick ones first, the long `core` group last. Strictly sequential.
# Usage: run_g2.sh PROJECT_ROOT OUTDIR
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
PY=/c/Users/fubai/Documents/My_Workspace/.venv/Scripts/python.exe
OUT="$2"; cd "$1" || exit 9; mkdir -p "$OUT"
run() { n="$1"; shift
  if [ -n "${GATE_GROUPS:-}" ] && ! echo " $GATE_GROUPS " | grep -q " $n "; then return; fi
  ST_DIR="$(dirname "$OUT")/status"; mkdir -p "$ST_DIR"
  if [ -n "${GATE_STATUS_PY:-}" ]; then "$PY" -B "$GATE_STATUS_PY" "$ST_DIR" "group_$n" RUNNING || true; fi
  date +%FT%T > "$OUT/$n.started"
  "$PY" -B -m pytest -o addopts= --no-cov -p no:cacheprovider --color=no "$@" > "$OUT/$n.txt" 2>&1 &
  wp="$(cat /proc/$!/winpid 2>/dev/null)"; if [ -n "$wp" ]; then echo "$wp" > "$ST_DIR/current_pid"; fi
  wait $!; rc=$?
  echo $rc > "$OUT/$n.exit"; date +%FT%T > "$OUT/$n.finished"; rm -f "$ST_DIR/current_pid"
  if [ -n "${GATE_STATUS_PY:-}" ]; then
    if [ "$rc" -eq 0 ]; then "$PY" -B "$GATE_STATUS_PY" "$ST_DIR" "group_$n" PASS 0 || true; else "$PY" -B "$GATE_STATUS_PY" "$ST_DIR" "group_$n" FAIL "$rc" || true; fi
  fi; }
run rest tests/db tests/delivery tests/doc tests/domain tests/models tests/spec tests/utils tests/vartable tests/constraint tests/config tests/logging tests/e2e tests/ui tests/test_bug1_get_project_path.py tests/test_bug2_sync_changes.py tests/test_bug4_retrofit_src_path.py tests/test_bug5_scan_depth.py tests/test_fixture_health.py tests/test_import.py tests/test_pm_session_size.py tests/test_smoke.py tests/test_layer_import_direction.py --ignore=tests/e2e/test_closure_drill.py --ignore=tests/e2e/test_closure_drill_agent_misconduct.py --ignore=tests/e2e/test_release_pycache_drill.py --ignore=tests/e2e/test_trial_run_drill.py
run application tests/application
run plc tests/plc
run change tests/change
run contracts tests/contracts
run infrastructure tests/infrastructure
run qml_debounce_alone tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
run cli tests/cli
run qml tests/qml --deselect tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
run core tests/core
echo done > "$OUT/ALL_DONE"
