#!/usr/bin/env bash
# M3-D07P V1.1, step M2.  V1.0 installed releases/1.3.3-dd8b192 (untracked) and added its manifest entry (uncommitted) in the control root, then rolled the pointers back.  The runtime refuses to start a Run
# whose owned range has such control-root drift, so BEFORE the Run starts this script puts both back to the main state with a reversible move: the folder is renamed to
# .auto-pm/archive/releases_installed_20261105/ (no byte changes, nothing deleted) and deployment_manifest.json is restored to the bytes of the control-root HEAD (its current bytes are backed up first).
# The release is then installed again after the Run has started (step 4 of the deploy script), exactly as in V1.0.
# usage: d07p2_0_move_back_installed.sh check   read-only: either the clean state already holds, or the leftovers are EXACTLY the V1.0 ones
#        d07p2_0_move_back_installed.sh move    check, then back up, move, restore, verify; undo = stepM2/UNDO_M2.sh
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
ROOT=/c/Users/fubai/Documents/My_Workspace; EV="$ROOT/.auto-pm/reports/m3-d07p2"; PY="$ROOT/.venv/Scripts/python.exe"
C=00_Infrastructure/auto_pm; RID=1.3.3-dd8b192; OLD_MANIFEST_SHA=c71e1b5b9f4b06b183fd653787da7fa33c925ea3c39f763009b0fe08710bf2fd
REL="$ROOT/$C/releases/$RID"; MAN="$ROOT/$C/deployment_manifest.json"; DEST="$ROOT/.auto-pm/archive/releases_installed_20261105"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
MODE="${1:-check}"; [[ "$MODE" == check || "$MODE" == move ]] || die "usage: check | move"
cd "$ROOT"
msha="$(sha256sum < "$MAN" | cut -d' ' -f1)"
if [[ ! -e "$REL" && "$msha" == "$OLD_MANIFEST_SHA" ]]; then echo "STEP_M2: clean start already holds (no installed $RID, the manifest equals the frozen bytes)"; exit 0; fi
[[ -d "$REL" && ! -L "$REL" ]] || die "the installed folder is missing or not a plain directory while the manifest differs from the frozen bytes"
[[ ! -e "$DEST" ]] || die "the target already exists: $DEST"
git ls-files --error-unmatch -- "$C/releases/$RID" > /dev/null 2>&1 && die "$RID is tracked by Git: not a V1.0 leftover"
"$PY" -B -I - "$MAN" "$REL" <<'EOF' || die "the leftovers are not exactly the V1.0 ones"
import json, os, stat, subprocess, sys
man, rel = sys.argv[1:3]
rid = os.path.basename(rel)
head = json.loads(subprocess.run(["git", "show", "HEAD:00_Infrastructure/auto_pm/deployment_manifest.json"], capture_output=True, check=True).stdout.decode("utf-8"))
work = json.load(open(man, encoding="utf-8"))
assert sorted(set(work["releases"]) - set(head["releases"])) == [rid] and not (set(head["releases"]) - set(work["releases"])), "manifest differs from HEAD by more than the one entry"
assert {k: v for k, v in work.items() if k != "releases"} == {k: v for k, v in head.items() if k != "releases"}, "manifest top level differs"
assert {k: v for k, v in work["releases"].items() if k != rid} == head["releases"], "other manifest entries differ"
for dp, dn, fn in os.walk(rel):
    for x in dn + fn:
        s2 = os.lstat(os.path.join(dp, x))
        assert not stat.S_ISLNK(s2.st_mode) and not (getattr(s2, "st_file_attributes", 0) & 0x400), ("link or junction inside", x)
print("leftovers are exactly the V1.0 ones: the folder", rid, "and its one manifest entry; no links or junctions")
EOF
HEADSHA="$(git show "HEAD:$C/deployment_manifest.json" | sha256sum | cut -d' ' -f1)"
[[ "$HEADSHA" == "$OLD_MANIFEST_SHA" ]] || die "the HEAD manifest bytes differ from the frozen value"
[[ "$MODE" == move ]] || { echo "STEP_M2_CHECK_OK: nothing was written"; exit 0; }
OUT="$EV/stepM2"; mkdir -p "$OUT"
cp "$MAN" "$OUT/deployment_manifest.json.before"
find "$REL" -type f | wc -l > "$OUT/file_count_before.txt"
{ echo '#!/usr/bin/env bash'; echo '# undo of step M2: puts the installed folder and the V1.0 manifest bytes back'; echo 'set -euo pipefail'; printf 'mv -- "%s" "%s"\n' "$DEST/$RID" "$REL"; printf 'cp -- "%s" "%s"\n' "$OUT/deployment_manifest.json.before" "$MAN"; } > "$OUT/UNDO_M2.sh"
mkdir -p "$DEST"
mv -- "$REL" "$DEST/$RID"
[[ "$(find "$DEST/$RID" -type f | wc -l)" == "$(cat "$OUT/file_count_before.txt")" ]] || die "file count differs after the move (UNDO_M2.sh puts everything back)"
git show "HEAD:$C/deployment_manifest.json" > "$MAN"
[[ "$(sha256sum < "$MAN" | cut -d' ' -f1)" == "$OLD_MANIFEST_SHA" ]] || die "the restored manifest does not equal the frozen bytes (UNDO_M2.sh puts everything back)"
[[ -z "$(git status --porcelain -- "$C/deployment_manifest.json" "$C/releases")" ]] || die "the release files are still dirty after step M2: $(git status --porcelain -- "$C/deployment_manifest.json" "$C/releases" | head -3)"
echo "STEP_M2_OK: the installed $RID folder moved to $DEST, the manifest restored to the HEAD bytes, release files clean"
