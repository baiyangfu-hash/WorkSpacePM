#!/usr/bin/env bash
# M3-REL7 (card 219 V1.1) - every gate on the real isolated candidate, strictly sequential:
# baseline measurements in the fresh candidate (identity, health tests, plugin identity) -> install the frozen files -> fast gates (health tests, the real plugin tests, the real CLI and stage gate end to end,
# static, eight real mutations, trees, real pre-commit hook dry run) -> the nine regression groups (G2) -> three isolated reruns of the one named transient-race test -> judge (G1-G9).
# It stops at the first non-zero step and writes DONE or FAILED into the gates folder; it never corrects anything.
set -uo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
ROOT=/c/Users/fubai/Documents/My_Workspace
EV="$ROOT/.auto-pm/reports/m3-rel7b"; G="${PG_G:-$EV/gates}"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
WT="${PG_WT:-$ROOT/.auto-pm/worktrees/m3-rel7b}"; PROJ="$WT/$P"
PY="$ROOT/.venv/Scripts/python.exe"
mkdir -p "$G"
export GATE_STATUS_PY="$EV/gate_status.py"
ST() { "$PY" -B "$GATE_STATUS_PY" "$G/status" "$1" "$2" "${3:-}" || true; }
CUR=""
stage() { if [ -n "$CUR" ]; then ST "$CUR" PASS 0; fi; CUR="$1"; ST "$CUR" RUNNING; }
fail() { echo "FAILED: $*" | tee "$G/FAILED"; ST "${CUR:-unknown}" FAIL 1; exit 1; }
cd "$ROOT" || fail "no workspace root"
stage baseline; echo "== baseline measurements in the fresh candidate (before any edit)"
PG_WT="$(cygpath -m "$WT")" PG_G="$(cygpath -m "$G")" "$PY" -B "$EV/rel7_gates.py" --stage baseline || fail "rel7_gates.py --stage baseline"
stage install; echo "== install the frozen files"
"$PY" -B "$EV/install_files.py" "$(cygpath -w "$WT")" > "$G/install_output.json" 2> "$G/install_output.err" || fail "install_files.py exit non-zero: $(head -c 300 "$G/install_output.err")"
stage fast; echo "== fast gates"
PG_WT="$(cygpath -m "$WT")" PG_G="$(cygpath -m "$G")" "$PY" -B "$EV/rel7_gates.py" --stage fast || fail "rel7_gates.py --stage fast"
stage reuse; echo "== V1.1: reuse the ten group outputs and the three r09 reruns of RUN-SW008-M3-REL7-001 (same frozen commit and contract; the declared deltas are the measured ones)"
SRC_G2="$ROOT/.auto-pm/reports/m3-rel7/gates/g2_candidate"
[[ -f "$SRC_G2/ALL_DONE" && "$(cat "$SRC_G2/transient_3.exit")" == "0" ]] || fail "the reused group outputs are incomplete"
for n in rest application plc change contracts infrastructure qml_debounce_alone cli qml core; do [[ "$(cat "$SRC_G2/$n.exit")" == "0" ]] || fail "reused group $n did not exit 0"; done
mkdir -p "$G/g2_candidate"
( cd "$SRC_G2" && sha256sum -- *.txt *.exit ) > "$G/reuse_manifest.sha256"
cp -p "$SRC_G2"/*.txt "$SRC_G2"/*.exit "$G/g2_candidate/"
( cd "$G/g2_candidate" && sha256sum -c --quiet "$G/reuse_manifest.sha256" ) || fail "the copied group outputs differ from the source"
echo "reused $(wc -l < "$G/reuse_manifest.sha256") files from RUN-SW008-M3-REL7-001"
printf 'done\n' > "$G/g2_candidate/ALL_DONE"
cd "$ROOT" || fail "no workspace root"
stage judge; echo "== judge"
PG_WT="$(cygpath -m "$WT")" PG_G="$(cygpath -m "$G")" "$PY" -B "$EV/rel7_gates.py" --stage judge > "$G/judge_output.txt" 2>&1 || fail "judge exit non-zero: $(tail -c 400 "$G/judge_output.txt")"
cat "$G/judge_output.txt"
ST judge PASS 0; ST ALL DONE 0; echo done > "$G/DONE"
