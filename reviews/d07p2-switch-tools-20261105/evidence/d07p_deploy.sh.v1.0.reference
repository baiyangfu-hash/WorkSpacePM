#!/usr/bin/env bash
# M3-D07P (card D07p_card.md V1.0): switch the real active release to the build of main at dd8b192f (release 7.2, card 221 V1.1 gated, all nine gates PASS), same steps as D07p; changes: strict PASS verdict (no exception), the user's standing authorization of 2026-11-05T04:04:33Z plus the independent-audit reference, a worktree-count guard.
#   0  bindings and read-only preflight (`--check-only` stops here and writes nothing);
#   0b the user's one-line confirmation, recorded in user_switch_confirmation.txt from the user's own message in the thread (nothing switches without it);
#   1-3 deploy CHG / Decision (4 exact paths) / Work / Run on the control root;
#   4  install 1.3.3-dd8b192 from the frozen commit dd8b192f with the D06-drilled ops script (pmf_release_ops.sh, same bytes);
#   5  switch (previous := 1.3.3-d563293); 6 post-switch checks - ANY failure rolls the pointers back with the same script and stops;
#   7  Checkpoint, Run/Work terminal, CHG completed, receipt with the rollback command.
# The database is never rolled back or overwritten (a SQLite backup is taken before the switch for evidence only). Resumable: each step checks the state first.
# D07_ROOT may name a throw-away rehearsal root (marker .d07-rehearsal-root); everything else is read from the real workspace.
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
REAL=/c/Users/fubai/Documents/My_Workspace
ROOT="${D07_ROOT:-$REAL}"
if [[ "$ROOT" != "$REAL" ]]; then [[ -f "$ROOT/.d07-rehearsal-root" ]] || { echo "D07_ROOT is not a rehearsal root"; exit 1; }; fi
cd "$ROOT"
PY="$REAL/.venv/Scripts/python.exe"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
EV="$ROOT/.auto-pm/reports/m3-d07p"
CARD="$EV/D07p_card.md"
CARD_SHA=987d40264e047cc35e1fa90f99bc90a984c52233c8dcb6dc7bfb80e657842a1f
OPS="$REAL/.auto-pm/reports/m3-d06/pmf_release_ops.sh"
OPS_SHA=fe331979d463d4de32209bfb32c7eca8db1e17ee60a39622a92cd8c7be53e8de
DRILLPY="$REAL/.auto-pm/reports/m3-d06/drill.py"
D176_VERDICT="$REAL/.auto-pm/reports/m3-rel72b/gates/gate_verdict.json"
CARD176=dd8b192f2e0a8ffdc370fd7e2dc4f7a999bb7642
FROZEN=dd8b192f2e0a8ffdc370fd7e2dc4f7a999bb7642
RID=1.3.3-dd8b192
OLD=1.3.3-d563293
OLDER=1.3.3-d671611
OLD_ACTIVE_SHA=bade7381d9e081573907f3c21a9817c28e9fff1ce149f7e3a2709c782cdbb095
OLD_PREV_SHA=85b4cde8d71e4d6b89dae7040ad636fcde54886dfe08dd2b0f7733a4fff11a3d
OLD_MANIFEST_SHA=c71e1b5b9f4b06b183fd653787da7fa33c925ea3c39f763009b0fe08710bf2fd
TODAY="$(date +%Y%m%d)"
DEC="DEC-$TODAY-M3D07P01"
WORK=WORK-SW008-M3-D07P-001
RUN=RUN-SW008-M3-D07P-001
OWNER=claude:m3d07p
CKPT=CKPT-SW008-M3-D07P-001
STATE="$EV/d07p_chg.txt"
C=00_Infrastructure/auto_pm
PATHS=("$C/deployment_manifest.json" "$C/active_release.json" "$C/previous_release.json" "$C/releases/$RID")
PROJECTS=(SW-2026-008 SYS-2026-001 SW-2026-009 DJ-2026-005)
GO_REF="$( { grep '^CONFIRMED_BY_USER_IN_THREAD=' "$EV/user_switch_confirmation.txt" 2>/dev/null || true; } | head -n 1 | cut -d= -f2- | cut -d' ' -f1)"
DELEG="委托执行：用户 2026-10-18 预授权 Claude 自行收口推送；切换有效版本这一步由用户在本线程里授权（2026-11-05T04:04:33Z “不过不切换，过了自己切换。门禁已经授权了。”，消息编号与原话记在 .auto-pm/reports/m3-d07p/user_switch_confirmation.txt，这是常设授权，不点名本卡 SHA）；条件：卡 221 V1.1 的 G1～G9 全部 PASS（没有例外）、独立审计放行卡 221 V1.1 与本卡（引用记在 switch_audit_ref.txt）、候选产品子树等于卡 221 V1.1 门禁时测过的冻结提交、任一切换后核验失败即自动回退指针、不回滚数据库"
mkdir -p "$EV"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
cli() { "$PY" -B main.py "$@"; }
q() { "$PY" -B -c 'import sqlite3,sys;c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True);r=c.execute(sys.argv[1],tuple(sys.argv[2:])).fetchone();print(r[0] if r else "NONE")' "$@"; }
rid_of() { "$PY" -B -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["release_id"])' "$1"; }
entry_sha() { "$PY" -B -c '
import hashlib,json,sys
m=json.load(open(sys.argv[1],encoding="utf-8")); e=m["releases"].get(sys.argv[2])
print(hashlib.sha256(json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest() if e else "NONE")' "$C/deployment_manifest.json" "$RID"; }
ledger_ok() { local out; out="$(cli ledger reconcile "$1" 2>/dev/null || true)"; [[ "$out" == *'台账缺失: 0 条, 台账多余(孤儿): 0 条, 状态不一致: 0 条'* ]]; }

echo "== 0. Bindings and read-only preflight"
[[ "$CARD_SHA" != __CARD_SHA__ ]] || die "card SHA not filled in"
[[ "$(sha256sum < "$CARD" | cut -d' ' -f1)" == "$CARD_SHA" ]] || die "the D07 card bytes differ from the SHA reported in the thread"
[[ "$(sha256sum < "$OPS" | cut -d' ' -f1)" == "$OPS_SHA" ]] || die "pmf_release_ops.sh differs from the bytes D06 drilled"
:  # D07p: no exception record; the verdict must be nine PASS
"$PY" -B -c 'import json,sys;d=json.load(open(sys.argv[1],encoding="utf-8"));v=d["gates"];sys.exit(0 if d.get("card")=="CARD-SW008-M3-REL72 V1.1" and d.get("base")==sys.argv[2] and d.get("run_id")=="RUN-SW008-M3-REL72-003" and len(v)==9 and all(g["verdict"]=="PASS" for g in v.values()) else 1)' "$(cygpath -w "$D176_VERDICT")" "$FROZEN" || die "card 221 V1.1: gate_verdict.json is not nine PASS for the frozen commit"
:
:
for sub in auto_pm templates scripts; do [[ "$(git -C "$REAL" rev-parse "$FROZEN:$P/$sub")" == "$(git -C "$REAL" rev-parse "$CARD176:$P/$sub")" ]] || die "$sub of $FROZEN differs from the gated card 220 commit"; done
[[ "$(git -C "$REAL" rev-parse "$FROZEN^{commit}")" == "$FROZEN" ]] || die "the frozen commit is missing"
ACTIVE="$(rid_of "$C/active_release.json")"
if [[ "$ACTIVE" == "$OLD" ]]; then
  [[ "$(sha256sum < "$C/active_release.json" | cut -d' ' -f1)" == "$OLD_ACTIVE_SHA" ]] || die "active pointer drifted"
  [[ "$(sha256sum < "$C/previous_release.json" | cut -d' ' -f1)" == "$OLD_PREV_SHA" ]] || die "previous pointer drifted"
  [[ "$(rid_of "$C/previous_release.json")" == "$OLDER" ]] || die "previous is not $OLDER"
  if [[ "$(entry_sha)" == NONE ]]; then
    [[ "$(sha256sum < "$C/deployment_manifest.json" | cut -d' ' -f1)" == "$OLD_MANIFEST_SHA" ]] || die "manifest drifted"
    [[ ! -e "$C/releases/$RID" ]] || die "release slot exists without a manifest entry"
  fi
elif [[ "$ACTIVE" != "$RID" ]]; then die "active is neither $OLD nor $RID"; fi
for r in "$OLD" "$OLDER"; do bash "$OPS" verify "$ROOT" "$r" > /dev/null || die "exact-tree $r fails before the switch"; done
echo "pointers, manifest and the two installed releases as frozen; active=$ACTIVE"
echo "precondition: card 221 V1.1 gate_verdict is nine PASS for the frozen commit (no exception)"
[[ "$(q "select state from run_items where run_id=?" RUN-SW008-M3-REL72-003)" == SUCCEEDED ]] || die "RUN-SW008-M3-REL72-003 is not SUCCEEDED (the gate closure is not finished)"
[[ -s "$EV/switch_audit_ref.txt" ]] || die "no independent-audit reference (switch_audit_ref.txt): the audit PASS for card 221 V1.1 and this card is required"
nwt="$(ls -1 "$REAL/.auto-pm/worktrees" | wc -l)"; [[ -d "$REAL/.auto-pm/worktrees/m3-d07p" || "$nwt" -le 6 ]] || die "$nwt workstation folders: the station for this Run would be the 8th, over the doctor cap of 7"
cli implementation-card precheck --card-file "$(cygpath -w "$CARD")" > "$EV/precheck_before.json" 2>&1 || die "the D07 card fails the implementation-card precheck"
ledger_ok SW-2026-008 || die "SW-2026-008 ledger not 0/0/0"
nproc="$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process | Where-Object { \$_.Name -match '^pythonw?\\.exe$' -and \$_.CommandLine -match 'pytest|boss_main|main\\.py gui' }).Count" 2>/dev/null | tr -d '\r')"
[[ "$nproc" == 0 ]] || die "a test or cockpit process is running ($nproc)"
[[ ! -f "$REAL/.auto-pm/reports/HEAVY_GATES_RUNNING" ]] || die "HEAVY_GATES_RUNNING exists"
bash "$OPS" identity "$ROOT" > "$EV/identity_before.json" 2>/dev/null || die "cannot read the identity before the switch"
echo "identity before: $(cat "$EV/identity_before.json")"
[[ "${1:-}" != "--check-only" ]] || { echo "CHECK_ONLY_OK: the preconditions hold; nothing was written"; exit 0; }

echo "== 0b. The user's confirmation"
grep -q '^CONFIRMED_BY_USER_IN_THREAD=cmsg_' "$EV/user_switch_confirmation.txt" 2>/dev/null || die "no record of the user's standing switch authorization (user_switch_confirmation.txt)"
grep -q "^USER_TEXT=" "$EV/user_switch_confirmation.txt" || die "the confirmation file has no USER_TEXT line (the user's own words)"
if [[ ! -f "$EV/continuity.db.before_switch" ]]; then
  "$PY" -B -c "import sqlite3,sys;s=sqlite3.connect('file:.auto-pm/continuity.db?mode=ro',uri=True);d=sqlite3.connect(sys.argv[1]);s.backup(d);d.close();s.close()" "$(cygpath -m "$EV/continuity.db.before_switch")"
  echo "db evidence copy sha256=$(sha256sum "$EV/continuity.db.before_switch" | cut -d' ' -f1) (never restored)" | tee "$EV/db_backup.txt"
fi

echo "== 1. Deploy CHG"
chg=""; [[ -f "$STATE" ]] && IFS= read -r chg < "$STATE"
if [[ -z "$chg" ]]; then
  out="$(cli change create --pid SW-2026-008 --domain SCPT --nature CFG --scope SYSTEM --applicant fubai \
    --background "M3-D07P：把 PR 550 的合并提交 ${FROZEN:0:8}（发版 7.2 的发版点，卡 221 V1.1 门禁）用它自己的 pmf_build.py 安装为 $RID 并切换为有效版本（active=$RID，previous=$OLD），用 D06/D07 同一份操作脚本；切换后核验（含冒烟）任一失败即自动回退指针" \
    --necessity "1.3.3-d563293 之后合进 main 的合并提交（总闸、账本备份、分诊台与长回归等）只有切换为有效版本后才生效" \
    --references "CARD-SW008-M3-D07P V1.0；CARD_SHA256=$CARD_SHA；FROZEN=$FROZEN；RELEASE=$RID；OPS_SHA256=$OPS_SHA；CARD221=CARD-SW008-M3-REL72 V1.1；$DELEG" --urgency normal)"
  printf '%s\n' "$out" | grep -E "CHG-|状态" || true
  chg="$(printf '%s\n' "$out" | grep -oE 'CHG-SCPT-2026-[0-9]+' | tail -n 1)"
  [[ -n "$chg" ]] || die "cannot parse CHG id"
  printf '%s\n' "$chg" > "$STATE"
fi
CHG_FILE="$P/04_监控/01_变更管理/01_变更单/CHG-SCPT/$chg.md"
st() { awk -F'|' '/^\|[[:space:]]*变更状态[[:space:]]*\|/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3); print $3; exit}' "$CHG_FILE"; }
while true; do
  case "$(st)" in
    draft)        cli change transition "$chg" --pid SW-2026-008 --to submitted    --approver fubai --comment "[$DELEG] 提交 D07P" >/dev/null ;;
    submitted)    cli change transition "$chg" --pid SW-2026-008 --to under_review --approver fubai --comment "[$DELEG] 卡 221 V1.1 门禁九项全部 PASS，且候选产品子树与之相同；指针与清单字节等于冻结值；操作脚本字节等于 D06/D07 所用；独立审计引用已记录" >/dev/null ;;
    under_review) cli change transition "$chg" --pid SW-2026-008 --to approved     --approver fubai --approval-evidence-ref "user-confirmation:$GO_REF" --comment "[$DELEG] 批准：仅写入 releases/$RID、deployment_manifest.json、active_release.json、previous_release.json；切换后任一核验失败即回退指针；不回滚数据库、不合并 main" >/dev/null ;;
    approved)     cli change transition "$chg" --pid SW-2026-008 --to implementing --approver fubai --comment "[$DELEG] 开始部署" >/dev/null ;;
    implementing|completed) break ;;
    *) die "CHG state not resumable" ;;
  esac
done

echo "== 2. Decision $DEC (4 paths)"
if [[ ! -f ".auto-pm/decisions/$DEC.json" ]]; then
  A=(); for p in "${PATHS[@]}"; do A+=(--file "$p"); done
  cli decision create --change-id "$chg" --pid SW-2026-008 --approver fubai --approval-evidence-ref "user-confirmation:$GO_REF" --decision-id "$DEC" "${A[@]}" \
    --condition "仅写入 releases/$RID、deployment_manifest.json、active_release.json、previous_release.json；release 由合并提交 $FROZEN 以其自身 pmf_build.py 经 pmf_release_ops.sh（SHA-256 $OPS_SHA）构建" \
    --condition "切换后核验任一失败即回退指针；不回滚数据库、不改历史 release/事件/Checkpoint、不合并 main、不推送" \
    --json-output 2>&1 | grep -E '"decision_id"|"change_id"|rror|错误' || true
  [[ -f ".auto-pm/decisions/$DEC.json" ]] || die "Decision $DEC was not created"
fi

echo "== 3. Work and Run on the control root"
S=(); O=(); for p in "${PATHS[@]}"; do S+=(--scope "$p"); O+=(--owned "$p" --declared-dirty "$p"); done
[[ "$(q "select state from work_items where work_id=?" "$WORK")" != NONE ]] || cli continuity work create --work-id "$WORK" --pid SW-2026-008 --kind WBS \
  --title "M3-D07P 有效版本切换到 $RID" --owner "$OWNER" "${S[@]}" --card-file "$(pwd -W)/.auto-pm/reports/m3-d07p/D07p_card.md" --idempotency-key d07p-work-create-1 | grep '"state"'
[[ "$(q "select state from work_items where work_id=?" "$WORK")" != PLANNED ]] || cli continuity work authorize --work-id "$WORK" --decision-id "$DEC" --idempotency-key d07p-work-auth-1 | grep '"state"'
WTD="$ROOT/.auto-pm/worktrees/m3-d07p"
if [[ ! -d "$WTD" ]]; then
  git fetch -q origin main || die "cannot fetch origin/main"
  git worktree add --detach "$WTD" origin/main > "$EV/worktree_add.txt" 2>&1 || die "cannot create the managed station for the Run"
fi
# the control root's scope files must equal the station start: after step M of card 221 V1.1 they normally equal main, so nothing is staged; if a pointer or the manifest differs, its bytes are recorded through the normal hook, once
RS="$(q "select state from run_items where run_id=?" "$RUN")"; WS="$(q "select state from work_items where work_id=?" "$WORK")"
if ! { [[ "$RS" == READY || "$RS" == RUNNING ]] && [[ "$WS" == READY || "$WS" == AUTHORIZED || "$WS" == IN_PROGRESS ]]; }; then  # no further station commit while the Run is live (its git_head is fixed)
for f in deployment_manifest.json active_release.json previous_release.json; do
  if ! diff -q <(tr -d '\r' < "$ROOT/$C/$f") <(git -C "$WTD" show "HEAD:$C/$f" | tr -d '\r') > /dev/null; then
    cp "$ROOT/$C/$f" "$WTD/$C/$f"; git -C "$WTD" add -- "$C/$f"; echo "station: control-root bytes of $f staged" >> "$EV/worktree_add.txt"
  fi
done
if [[ -n "$(git -C "$WTD" diff --cached --name-only)" ]]; then
  git -C "$WTD" commit -q -m "chore(release): [$chg] record the control root's release files in the D07p station so the Run starts from them" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>" >> "$EV/worktree_add.txt" 2>&1 || die "station commit refused by the hook"
fi
fi
TOKEN_FILE="$EV/lease_token.txt"; [[ -f "$TOKEN_FILE" ]] || openssl rand -hex 16 > "$TOKEN_FILE"; TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != NONE ]] || cli continuity run start --run-id "$RUN" --work-id "$WORK" --executor "$OWNER" --adapter claude-code "${O[@]}" \
  --worktree "$(cygpath -w "$WTD")" --lease-token "$TOKEN" --lease-seconds 3600 --idempotency-key d07p-run-start-1 | grep -E '"state"|"git_head"'
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != READY ]] || cli continuity run transition --run-id "$RUN" --to RUNNING --owner "$OWNER" --lease-token "$TOKEN" --idempotency-key d07p-run-running-1 | grep '"state"'
[[ "$(q "select state from work_items where work_id=?" "$WORK")" != READY ]] || cli continuity work transition --work-id "$WORK" --to IN_PROGRESS --idempotency-key d07p-work-inprogress-1 | grep '"state"'

echo "== 4. Install $RID"
if [[ "$(entry_sha)" == NONE ]]; then bash "$OPS" build "$ROOT" "$FROZEN" | tee "$EV/install.txt"; fi
ENTRY_SHA="$(entry_sha)"; [[ "$ENTRY_SHA" != NONE ]] || die "no manifest entry for $RID after the install"
bash "$OPS" verify "$ROOT" "$RID"
# the installed payload must equal, byte for byte, the payload the gates built and tested at the frozen commit
GATE_PAYLOAD="$REAL/.auto-pm/reports/m3-rel72b/gates/d04/build_a"
diff -rq -x release_meta.json "$GATE_PAYLOAD" "$ROOT/00_Infrastructure/auto_pm/releases/$RID" > "$EV/payload_vs_gate.txt" 2>&1 || { cat "$EV/payload_vs_gate.txt" | head -5; die "the installed payload differs from the payload tested at the gates"; }
echo "payload bytes equal the gate-time payload"

echo "== 5. Switch"
if [[ "$(rid_of "$C/active_release.json")" == "$OLD" ]]; then
  BK="$EV/pointer_backup_$(date -u +%Y%m%dT%H%M%SZ)"
  bash "$OPS" switch "$ROOT" "$RID" "$OLD" "$BK" | tee "$EV/switch.txt"
else BK="$(ls -d "$EV"/pointer_backup_* 2>/dev/null | sort | tail -n 1)"; [[ -n "$BK" && -f "$BK/SHA256SUMS" ]] || die "switched earlier but no pointer backup found"; fi
echo "pointer backup: $BK"
[[ "$(rid_of "$C/active_release.json")" == "$RID" && "$(rid_of "$C/previous_release.json")" == "$OLD" ]] || die "pointers are not active=$RID previous=$OLD"

echo "== 6. Post-switch checks"
post_checks() {
  local fail=0 id rc c pid
  id="$(bash "$OPS" identity "$ROOT")"; echo "identity $id"
  "$PY" -B -c 'import json,sys;d=json.loads(sys.argv[1]);r=sys.argv[2];sys.exit(0 if d["configured_release_id"]==r==d["effective_release_id"] and not d["runtime_fallback_reason"] and d["conflicts"] == [] and r in (d["runtime_load_path"] or "") else 1)' "$id" "$RID" \
    && echo "identity OK: configured == effective == $RID, loaded from the release, no fallback, conflicts empty (no exception)" || { echo "FAIL identity"; fail=1; }
  for c in "pm handoff" "pm takeover" "pm orient" "continuity run reclaim" "continuity lease record-holder" "gui" "long-run" "pm state-backup" "pm triage"; do
    cli $c --help > /dev/null 2>&1; rc=$?; echo "$c --help exit=$rc"; [[ $rc == 0 ]] || fail=1
  done
  oc="$(cli pm orient SW-2026-008 --json 2>/dev/null | "$PY" -B -c 'import sys,json;t=sys.stdin.read();d=json.JSONDecoder().raw_decode(t[t.index("{"):])[0];print(json.dumps(d.get("conflicts")))' 2>/dev/null)"; echo "smoke: pm orient conflicts=$oc"; [[ "$oc" == "[]" ]] || { echo "FAIL smoke orient conflicts"; fail=1; }
  cli implementation-card precheck --card-file "$(pwd -W)/.auto-pm/reports/m3-d07p/D07p_card.md" > "$EV/precheck_after.json" 2>&1; rc=$?; echo "card precheck with the new runtime exit=$rc"; [[ $rc == 0 ]] || fail=1
  for pid in "${PROJECTS[@]}"; do if ledger_ok "$pid"; then echo "ledger $pid 0/0/0"; else echo "FAIL ledger $pid"; fail=1; fi; done
  if [[ -f .git/hooks/pre-commit ]]; then
    [[ -z "$(git diff --cached --name-only)" ]] || { echo "FAIL the control-root index is not empty"; fail=1; }
    sh .git/hooks/pre-commit > "$EV/hook_dry_run.txt" 2>&1; rc=$?; echo "real pre-commit hook (empty index) through the new runtime exit=$rc"; [[ $rc == 0 ]] || fail=1
  else echo "FAIL no pre-commit hook"; fail=1; fi
  local T; T="$(mktemp -d)"; mkdir -p "$T/.auto-pm"; cp -r .auto-pm/decisions "$T/.auto-pm/"
  "$PY" -B -c "import sqlite3,sys;s=sqlite3.connect('file:.auto-pm/continuity.db?mode=ro',uri=True);d=sqlite3.connect(sys.argv[1]);s.backup(d);d.close();s.close()" "$(cygpath -m "$T/.auto-pm/continuity.db")"
  "$PY" -B -I "$DRILLPY" "$(cygpath -m "$ROOT/$C/releases/$RID")" "$(cygpath -m "$T")" > "$EV/event_chain_drill.json" 2> "$EV/event_chain_drill.err"
  rm -rf "$T"
  "$PY" -B -c 'import json,sys;d=json.load(open(sys.argv[1],encoding="utf-8"));print("event chain: events",d["events_total"],"breaks",d["chain_breaks"],"run activity failures",len(d["run_activity_fail"]),"works",d.get("works_read"));sys.exit(0 if d["chain_breaks"]==0 and not d["run_activity_fail"] and "work_run_read_error" not in d else 1)' "$EV/event_chain_drill.json" || { echo "FAIL event chain"; fail=1; }
  for r in "$RID" "$OLD" "$OLDER"; do bash "$OPS" verify "$ROOT" "$r" || { echo "FAIL exact-tree $r"; fail=1; }; done
  echo "POST_CHECKS_RESULT=$([[ $fail == 0 ]] && echo OK || echo FAIL)"
}
post_checks 2>&1 | tee "$EV/post_checks.txt" || true
if ! grep -q '^POST_CHECKS_RESULT=OK' "$EV/post_checks.txt" || grep -q '^FAIL' "$EV/post_checks.txt" || ! grep -q '^identity OK' "$EV/post_checks.txt" || ! grep -q "exact-tree OK $OLDER" "$EV/post_checks.txt"; then
  echo "POST-SWITCH CHECK FAILED -> rollback"
  bash "$OPS" rollback "$ROOT" "$BK" | tee "$EV/rollback.txt"
  die "D07 rolled back to $OLD; see $EV/post_checks.txt"
fi
echo "all post-switch checks passed"

echo "== 7. Checkpoint and closure"
if [[ "$(q "select count(*) from checkpoints where checkpoint_id=?" "$CKPT")" == 0 ]]; then
  EVARGS=(--evidence "card=CARD-SW008-M3-D07P V1.0 sha256=$CARD_SHA" --evidence "release=$RID frozen=$FROZEN manifest_entry_sha256=$ENTRY_SHA"
          --evidence "post_checks sha256=$(sha256sum < "$EV/post_checks.txt" | cut -d' ' -f1)" --evidence "user confirmation $(grep '^CONFIRMED_BY_USER_IN_THREAD=' "$EV/user_switch_confirmation.txt" | cut -d= -f2-)")
  for f in active_release.json previous_release.json deployment_manifest.json; do EVARGS+=(--evidence "sha256:$C/$f:$(sha256sum < "$C/$f" | cut -d' ' -f1)"); done
  cli continuity checkpoint create --checkpoint-id "$CKPT" --run-id "$RUN" --owner "$OWNER" --lease-token "$TOKEN" \
    --summary "active release switched to $RID (previous $OLD); post-switch checks passed" "${EVARGS[@]}" --idempotency-key d07p-checkpoint-1 | grep -E '"checkpoint_id"|"git_head"'
fi
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != RUNNING ]] || cli continuity run transition --run-id "$RUN" --to VERIFYING --owner "$OWNER" --lease-token "$TOKEN" --idempotency-key d07p-run-verifying | grep '"state"'
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != VERIFYING ]] || cli continuity run transition --run-id "$RUN" --to SUCCEEDED --owner "$OWNER" --lease-token "$TOKEN" --idempotency-key d07p-run-succeeded | grep '"state"'
[[ "$(q "select state from run_items where run_id=?" "$RUN")" == SUCCEEDED ]] || die "Run not SUCCEEDED"
while true; do
  case "$(q "select state from work_items where work_id=?" "$WORK")" in
    IN_PROGRESS) cli continuity work transition --work-id "$WORK" --to VERIFYING --idempotency-key d07p-work-verifying | grep '"state"' ;;
    VERIFYING)   cli continuity work transition --work-id "$WORK" --to ACCEPTED  --idempotency-key d07p-work-accepted | grep '"state"' ;;
    ACCEPTED)    cli continuity work transition --work-id "$WORK" --to CLOSED    --idempotency-key d07p-work-closed | grep '"state"' ;;
    CLOSED)      break ;;
    *) die "Work in unexpected state" ;;
  esac
done
while true; do
  case "$(st)" in
    implementing)       cli change transition "$chg" --pid SW-2026-008 --to pending_acceptance --approver fubai --comment "[$DELEG] 已切换并通过切换后核验" >/dev/null ;;
    pending_acceptance) cli change transition "$chg" --pid SW-2026-008 --to accepting --approver fubai --comment "[$DELEG] 开始验收" >/dev/null ;;
    accepting)          cli change transition "$chg" --pid SW-2026-008 --to completed --approver fubai --approval-evidence-ref "user-confirmation:$GO_REF" --verification-conclusion "[$DELEG] 验收通过（委托验收，切换按用户 2026-11-05T04:04:33Z（11-04 21:04 MST）的授权）。有效版本 active=$RID（PR #550 合并提交 ${FROZEN:0:8}，清单条目 $ENTRY_SHA），previous=$OLD；无回落、无冲突；新命令可用；真实钩子经新运行时退出 0；全部注册项目对账 0/0/0；事件链无断点；三个发布逐文件校验通过；回退命令记在回执里；数据库未回滚" >/dev/null ;;
    completed)          break ;;
    *) die "CHG in non-resumable state" ;;
  esac
done
cli ledger reconcile SW-2026-008 | grep 摘要
{
  echo "LABEL=CARD-SW008-M3-D07P V1.0"; echo "RELEASE=$RID"; echo "FROZEN_COMMIT=$FROZEN"; echo "MANIFEST_ENTRY_SHA256=$ENTRY_SHA"
  echo "ACTIVE=$RID"; echo "PREVIOUS=$OLD"; echo "POINTER_BACKUP=$BK"; echo "CHECKPOINT=$CKPT"
  echo "RUN=$RUN SUCCEEDED"; echo "WORK=$WORK CLOSED"; echo "CHG=$chg completed"; echo "DECISION=$DEC"
  echo "POST_CHECKS_SHA256=$(sha256sum < "$EV/post_checks.txt" | cut -d' ' -f1)"
  echo "ROLLBACK_COMMAND=bash $OPS rollback $ROOT $BK"
  grep '^CONFIRMED_BY_USER_IN_THREAD=' "$EV/user_switch_confirmation.txt"
  echo "SIGNATURE_MODE=DELEGATED; $DELEG"; echo "CLOSED_AT=$(date -u +%FT%TZ)"
  echo "NOT_AUTHORIZED=merge to main, database rollback"
} | tee "$EV/acceptance_receipt.txt"
echo "D07P_DONE $RID"
