#!/usr/bin/env bash
# M3-REL72 V1.1, step M.  The control root's releases/ folder holds 16 deployed release folders that deployment_manifest.json does not register (V1.0 failed on exactly these:
# `doctor --pre-release` -> "发布记录互相核对" FAIL).  This script MOVES them (a rename on the same volume: no byte is changed, nothing is deleted) to
# .auto-pm/archive/releases_unregistered_20261104/ and then requires `main.py doctor --pre-release` to exit 0.  Undo = the same mv back (UNDO_MOVE.sh, written before the first move).
# usage: rel72_0_move_unregistered.sh check   read-only: the on-disk-but-unregistered set must equal the 16 names below, the target must not exist, no link or junction
#        rel72_0_move_unregistered.sh move    check, then record file counts, move, write UNDO_MOVE.sh, verify counts, run the doctor (exit 0 required)
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
ROOT=/c/Users/fubai/Documents/My_Workspace; EV="$ROOT/.auto-pm/reports/m3-rel72b"; PY="$ROOT/.venv/Scripts/python.exe"
REL="$ROOT/00_Infrastructure/auto_pm/releases"; DEST="$ROOT/.auto-pm/archive/releases_unregistered_20261104"
NAMES=(1.3.3-0b72499 1.3.3-10165f9 1.3.3-28ac772 1.3.3-4090f81 1.3.3-4845857 1.3.3-4b5c630 1.3.3-7735ec5 1.3.3-8b02de5 1.3.3-8f08c1a 1.3.3-a4506c3 1.3.3-a53d9f2 1.3.3-a808fa8 1.3.3-ba184ca 1.3.3-e648e0b 1.3.3-f462694 1.3.3-f474b52)
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
MODE="${1:-check}"; [[ "$MODE" == check || "$MODE" == move ]] || die "usage: check | move"
cd "$ROOT"
"$PY" -B -I - "$ROOT/00_Infrastructure/auto_pm" "${NAMES[@]}" <<'EOF' || die "the unregistered release folders differ from the card (section 1 item 17)"
import json, os, stat, sys
base, *names = sys.argv[1:]
man = set(json.load(open(os.path.join(base, "deployment_manifest.json"), encoding="utf-8"))["releases"])
folder = os.path.join(base, "releases")
on_disk = {n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))}
extra = sorted(on_disk - man)
assert extra == sorted(names), ("on-disk-but-unregistered set differs from the 16 names of the card", extra)
assert not (man - on_disk), ("the manifest registers a folder that is not on disk", sorted(man - on_disk))
for n in names:
    p = os.path.join(folder, n)
    st = os.lstat(p)
    assert stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and not (getattr(st, "st_file_attributes", 0) & 0x400), ("not a plain directory (link or junction)", n)
    for dp, dn, fn in os.walk(p):
        for x in dn + fn:
            s2 = os.lstat(os.path.join(dp, x))
            assert not stat.S_ISLNK(s2.st_mode) and not (getattr(s2, "st_file_attributes", 0) & 0x400), ("link or junction inside", n, x)
print("unregistered set equals the 16 names of the card; no links or junctions; the manifest registers", len(man), "folders, all on disk")
EOF
[[ ! -e "$DEST" ]] || die "the target already exists: $DEST"
[[ "$MODE" == move ]] || { echo "STEP_M_CHECK_OK: nothing was written"; exit 0; }
OUT="$EV/stepM"; mkdir -p "$OUT"
for n in "${NAMES[@]}"; do printf '%s\t%s\n' "$n" "$(find "$REL/$n" -type f | wc -l)"; done > "$OUT/moved_manifest_before.tsv"
"$PY" -B main.py doctor --pre-release > "$OUT/doctor_before_move.txt" 2>&1 && die "the doctor already exits 0 before the move; this card's premise is wrong, stop and report" || echo "doctor before the move: non-zero (expected)"
mkdir -p "$DEST"
{ echo '#!/usr/bin/env bash'; echo '# undo of step M: moves the 16 folders back into releases/ (same volume rename)'; echo 'set -euo pipefail'; } > "$OUT/UNDO_MOVE.sh"
for n in "${NAMES[@]}"; do printf 'mv -- "%s/%s" "%s/%s"\n' "$DEST" "$n" "$REL" "$n" >> "$OUT/UNDO_MOVE.sh"; done
for n in "${NAMES[@]}"; do mv -- "$REL/$n" "$DEST/$n"; done
for n in "${NAMES[@]}"; do printf '%s\t%s\n' "$n" "$(find "$DEST/$n" -type f | wc -l)"; done > "$OUT/moved_manifest_after.tsv"
cmp "$OUT/moved_manifest_before.tsv" "$OUT/moved_manifest_after.tsv" || die "file counts differ after the move (UNDO_MOVE.sh puts everything back)"
ls "$REL" | wc -l > "$OUT/releases_count_after.txt"
"$PY" -B main.py doctor --pre-release > "$OUT/doctor_after_move.txt" 2>&1 || die "doctor --pre-release is still non-zero after the move: see $OUT/doctor_after_move.txt (the gates are NOT started; UNDO_MOVE.sh puts the folders back)"
echo "STEP_M_OK: 16 folders moved, file counts equal, doctor --pre-release exit 0"
