#!/usr/bin/env bash
# M3-REL72 (card 221 V1.1) - every gate on the real isolated candidate, strictly sequential:
# baseline measurements in the fresh candidate (identity, health tests, plugin identity) -> install the frozen files -> fast gates (health tests, the real plugin tests, the real CLI and stage gate end to end,
# static, eight real mutations, trees, real pre-commit hook dry run) -> the nine regression groups (G2) -> three isolated reruns of the one named transient-race test -> judge (G1-G9).
# It stops at the first non-zero step and writes DONE or FAILED into the gates folder; it never corrects anything.
set -uo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
ROOT=/c/Users/fubai/Documents/My_Workspace
EV="$ROOT/.auto-pm/reports/m3-rel72b"; G="${PG_G:-$EV/gates}"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
WT="${PG_WT:-$ROOT/.auto-pm/worktrees/m3-rel72b}"; PROJ="$WT/$P"
PY="$ROOT/.venv/Scripts/python.exe"
mkdir -p "$G"
export GATE_STATUS_PY="$EV/gate_status.py"
ST() { "$PY" -B "$GATE_STATUS_PY" "$G/status" "$1" "$2" "${3:-}" || true; }
CUR=""
stage() { if [ -n "$CUR" ]; then ST "$CUR" PASS 0; fi; CUR="$1"; ST "$CUR" RUNNING; }
fail() { echo "FAILED: $*" | tee "$G/FAILED"; ST "${CUR:-unknown}" FAIL 1; exit 1; }
cd "$ROOT" || fail "no workspace root"
pin() { git -C "$ROOT" fetch -q origin main || true; { echo "HEAD=$(git -C "$WT" rev-parse HEAD)"; echo "ORIGIN_MAIN=$(git -C "$ROOT" rev-parse origin/main)"; echo "MAIN_PRODUCT_DIFF=$(git -C "$ROOT" diff --name-only $(git -C "$WT" rev-parse HEAD) origin/main -- "$P/auto_pm" "$P/templates" "$P/scripts" | wc -l)"; } > "$G/$1"; }
power() { { echo "== powercfg /a"; powercfg /a; echo "== powercfg /requests"; powercfg /requests; echo "== lid close action (power button and lid subgroup)"; powercfg /query SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936; echo "== sleep timeout"; powercfg /query SCHEME_CURRENT 238c9fa8-0aad-41ed-83f4-97be242c8f20 29f6c1db-86da-48c5-9fdb-f2b4a58e5f2c; } > "$G/$1" 2>&1; }
pin pin_start.txt; power power_start.txt
stage baseline; echo "== baseline measurements in the fresh candidate (before any edit)"
PG_WT="$(cygpath -m "$WT")" PG_G="$(cygpath -m "$G")" "$PY" -B "$EV/rel72_gates.py" --stage baseline || fail "rel72_gates.py --stage baseline"
stage install; echo "== install the frozen files"
"$PY" -B "$EV/install_files.py" "$(cygpath -w "$WT")" > "$G/install_output.json" 2> "$G/install_output.err" || fail "install_files.py exit non-zero: $(head -c 300 "$G/install_output.err")"
stage fast; echo "== fast gates"
PG_WT="$(cygpath -m "$WT")" PG_G="$(cygpath -m "$G")" "$PY" -B "$EV/rel72_gates.py" --stage fast || fail "rel72_gates.py --stage fast"
stage groups; echo "== ten regression groups (G2)"
bash "$EV/run_g2.sh" "$PROJ" "$G/g2_candidate" || fail "run_g2.sh"
stage transient; echo "== the named transient-race test, three isolated runs in the same candidate bytes (judged only when it failed in the group run)"
cd "$PROJ" || fail "no candidate worktree"
for i in 1 2 3; do
  "$PY" -B -m pytest -o addopts= --no-cov -p no:cacheprovider --color=no -q "tests/e2e/test_pmf_recovery.py::test_r09_a_reader_never_fails_because_another_process_has_a_transaction_open" > "$G/g2_candidate/transient_$i.txt" 2>&1; echo $? > "$G/g2_candidate/transient_$i.exit"
done
cd "$ROOT" || fail "no workspace root"
pin pin_end.txt; power power_end.txt
stage judge; echo "== judge"
PG_WT="$(cygpath -m "$WT")" PG_G="$(cygpath -m "$G")" "$PY" -B "$EV/rel72_gates.py" --stage judge > "$G/judge_output.txt" 2>&1 || fail "judge exit non-zero: $(tail -c 400 "$G/judge_output.txt")"
cat "$G/judge_output.txt"
ST judge PASS 0; ST ALL DONE 0; echo done > "$G/DONE"
