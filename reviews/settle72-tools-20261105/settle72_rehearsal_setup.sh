#!/usr/bin/env bash
# Build a throw-away control root for the SETTLE72 rehearsal (reads the real workspace, writes only under $T; never touches the real .auto-pm or 00_Infrastructure).
# usage: bash settle72_rehearsal_setup.sh <T>      then:  SETTLE_ROOT=<T> bash <T>/.auto-pm/reports/m3-settle72/settle72_1_recovery.sh
# Adapted from m3-settle2/settle2_rehearsal_setup.sh.  The rehearsal runs with the ACTIVE release (1.3.3-d563293), the runtime that the real chain will use.
# Run it when no governed Run is writing the database (the DB is copied only when its WAL is empty).
set -euo pipefail
R=/c/Users/fubai/Documents/My_Workspace
T="$1"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
EVR="$R/.auto-pm/reports/m3-settle72"
REL=1.3.3-d563293
[[ "$("$R/.venv/Scripts/python.exe" -c 'import json,sys;print(json.load(open(sys.argv[1]))["release_id"])' "$R/00_Infrastructure/auto_pm/active_release.json")" == "$REL" ]] || { echo "active release is not $REL"; exit 1; }
rm -rf "$T"; mkdir -p "$T"
git init -q "$T"
git -C "$T" config user.name "rehearsal"
git -C "$T" config user.email "rehearsal@localhost"
git -C "$T" config core.longpaths true
# read-only access to the real object store, so that the card's isolation baseline and the frozen tier-rule commit resolve as they do in the real root (the rehearsal's own writes stay in $T)
mkdir -p "$T/.git/objects/info"; echo "$(cygpath -m "$R")/.git/objects" > "$T/.git/objects/info/alternates"
touch "$T/.settle-rehearsal-root"
cp "$R/main.py" "$R/.gitignore" "$T/"
mkdir -p "$T/00_Infrastructure/auto_pm/releases" "$T/SYS-2026-001_WorkspaceGovernance" "$T/$P" "$T/.auto-pm/reports/m3-settle72"
cp -r "$R/00_Infrastructure/auto_pm/launcher" "$T/00_Infrastructure/auto_pm/"
find "$T/00_Infrastructure/auto_pm/launcher" -name __pycache__ -prune -exec rm -rf {} +
cp "$R/00_Infrastructure/auto_pm/"{active_release.json,previous_release.json,deployment_manifest.json} "$T/00_Infrastructure/auto_pm/"
cp -r "$R/00_Infrastructure/auto_pm/releases/$REL" "$T/00_Infrastructure/auto_pm/releases/"
cp -r "$R/SYS-2026-001_WorkspaceGovernance/04_监控" "$T/SYS-2026-001_WorkspaceGovernance/"
cp "$R/SYS-2026-001_WorkspaceGovernance/"{workspace_registry.json,PM_SESSION_SYS-2026-001.md} "$T/SYS-2026-001_WorkspaceGovernance/"
cp "$R/$P/"{.copier-answers.yml,.auto-pm-workspace,PM_SESSION_SW-2026-008.md} "$T/$P/"
cp -r "$R/$P/04_监控" "$T/$P/"
cp -r "$R/.auto-pm/decisions" "$T/.auto-pm/"
[ ! -s "$R/.auto-pm/continuity.db-wal" ] || { echo "WAL not empty; abort (a governed Run is writing the database)"; exit 1; }
cp "$R/.auto-pm/continuity.db" "$T/.auto-pm/continuity.db"
sha256sum "$R/.auto-pm/continuity.db" "$T/.auto-pm/continuity.db"
# the card, the script (card SHA filled in for the rehearsal) and a REHEARSAL approval receipt (a dummy message id of the right shape; it is not a user message and exists only in this throw-away root)
cp "$EVR/SETTLE72_recovery_card.md" "$T/.auto-pm/reports/m3-settle72/"
SHA="$(sha256sum < "$EVR/SETTLE72_recovery_card.md" | cut -d' ' -f1)"
sed "s/^CARD_SHA=.*/CARD_SHA=$SHA/" "$EVR/settle72_1_recovery.sh" > "$T/.auto-pm/reports/m3-settle72/settle72_1_recovery.sh"
printf 'REHEARSAL ONLY - not the user approval\nCARD_SHA256=%s\nGO_REF=user-confirmation:cmsg_REHEARSALONLYNOTAUSERMESSAGE000000\n' "$SHA" > "$T/.auto-pm/reports/m3-settle72/approval_receipt.txt"
# baseline commit mirrors the real control root: Decision files tracked except the two originals that are untracked in reality (the failed 7.2 attempts)
git -C "$T" add -A -- .auto-pm/decisions
git -C "$T" reset -q -- .auto-pm/decisions/DEC-20261104-M3R72A01.json .auto-pm/decisions/DEC-20261105-M3D07P01.json
git -C "$T" add -- main.py .gitignore SYS-2026-001_WorkspaceGovernance "$P/.copier-answers.yml" "$P/.auto-pm-workspace"
git -C "$T" commit -q -m "rehearsal baseline"
git -C "$T" branch -M main
git -C "$T" rev-parse HEAD
echo SETUP_OK
