#!/usr/bin/env bash
# M3-REL72 V1.0 rehearsal (NOT governed, no CHG/Run): scratch worktree from the byte baseline -> baseline measurements -> install -> fast gates (including the real pre-commit hook dry run) -> a SYNTHETIC set of
# group outputs (a copy of the governed outputs of the previous card, which is exactly what an unchanged product must reproduce) -> judge; then judge negative variants of the group outputs.
# The nine real groups are NOT run here; their judge logic is exercised on the synthetic set only. Writes into gates_rehearsal/.
set -uo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
ROOT=/c/Users/fubai/Documents/My_Workspace
cd "$ROOT" || exit 9
EV="$ROOT/.auto-pm/reports/m3-rel72"
G="$EV/gates_rehearsal"
WT_REL=.auto-pm/worktrees/m3-rel72-rehearse
WT="$ROOT/$WT_REL"
PY="$ROOT/.venv/Scripts/python.exe"
BASE=$(sed -n 's/.*"base": "\([0-9a-f]*\)".*/\1/p' "$EV/rel72_config.json" | head -1)
BG2="$ROOT/.auto-pm/reports/m3-rel72/baseline_g2"
fail() { echo "FAILED: $*" | tee "$G/FAILED"; exit 1; }
rm -rf "$G"; mkdir -p "$G"
git worktree add -q --detach "$WT_REL" "$BASE" || fail "worktree add"
export PG_WT="$(cygpath -m "$WT")" PG_G="$(cygpath -m "$G")" PG_REHEARSAL=1
"$PY" -B "$EV/rel72_gates.py" --stage baseline || fail "baseline stage"
"$PY" -B "$EV/install_files.py" "$(cygpath -w "$WT")" > "$G/install_output.json" 2> "$G/install_output.err" || fail "install: $(head -c 300 "$G/install_output.err")"
"$PY" -B "$EV/rel72_gates.py" --stage fast || fail "fast stage"
S="$G/g2_candidate"; mkdir -p "$S"
for n in rest application plc change contracts infrastructure qml_debounce_alone cli qml core; do cp "$BG2/$n.txt" "$S/$n.txt"; cp "$BG2/$n.exit" "$S/$n.exit"; done
"$PY" -B "$EV/adjust_counts.py" "$S" "$EV/rel72_config.json" > "$G/adjust_counts.txt" || fail "adjust counts"
for i in 1 2 3; do printf '%s\n' '============================== 1 passed in 2.00s ==============================' > "$S/transient_$i.txt"; echo 0 > "$S/transient_$i.exit"; done
"$PY" -B "$EV/rel72_gates.py" --stage judge > "$G/judge_output.txt" 2>&1; echo $? > "$G/judge_positive.exit"
tail -3 "$G/judge_output.txt"
variant() { name="$1"; shift; "$@"; "$PY" -B "$EV/rel72_gates.py" --stage judge > "$G/judge_$name.txt" 2>&1; echo "$name judge exit=$?" | tee -a "$G/judge_variants.txt"; }
cp "$S/core.txt" "$G/core.keep"; cp "$S/rest.txt" "$G/rest.keep"; cp "$S/rest.exit" "$G/rest.exit.keep"
variant core_count_changed bash -c "n=\$(grep -o '[0-9]* passed' '$S/core.txt' | tail -1 | cut -d' ' -f1); sed -i \"s/\$n passed/\$((n-1)) passed/\" '$S/core.txt'"
cp "$G/core.keep" "$S/core.txt"
variant rest_one_failure bash -c "printf '%s\n' 'FAILED tests/e2e/test_x.py::test_other - boom' '=========== 1 failed, 1 passed in 1.00s ===========' > '$S/rest.txt'; echo 1 > '$S/rest.exit'"
cp "$G/rest.keep" "$S/rest.txt"; cp "$G/rest.exit.keep" "$S/rest.exit"
NP=$(grep -o '[0-9]* passed' "$G/rest.keep" | tail -1 | cut -d' ' -f1); NS=$(grep -o '[0-9]* skipped' "$G/rest.keep" | tail -1 | cut -d' ' -f1)
R09=tests/e2e/test_pmf_recovery.py::test_r09_a_reader_never_fails_because_another_process_has_a_transaction_open
printf '%s\n' "FAILED $R09 - x" "=========== 1 failed, $((NP-1)) passed, $NS skipped in 1400.00s ===========" > "$G/rest_transient.txt"
variant rest_transient_ok bash -c "cp '$G/rest_transient.txt' '$S/rest.txt'; echo 1 > '$S/rest.exit'"
variant rest_transient_rerun_failed bash -c "echo 1 > '$S/transient_2.exit'; echo '1 failed in 2.00s' > '$S/transient_2.txt'"
echo 0 > "$S/transient_2.exit"; echo '============================== 1 passed in 2.00s ==============================' > "$S/transient_2.txt"
cp "$G/rest.keep" "$S/rest.txt"; cp "$G/rest.exit.keep" "$S/rest.exit"
git -C "$ROOT" worktree list | grep -c m3-rel72-rehearse > "$G/worktree_listed.txt"
echo REHEARSAL_DONE > "$G/DONE"
