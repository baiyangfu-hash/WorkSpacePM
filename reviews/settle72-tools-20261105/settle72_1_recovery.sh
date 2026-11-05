#!/usr/bin/env bash
# M3-SETTLE72 (card SETTLE72_recovery_card.md V1.0) - settle the Runs that trigger LIVE_RUN_UNDER_FINISHED_WORK under the release 7.2 runtime (6 in SW-2026-008, 2 in SYS-2026-001)
# and the two leftover Runs of the failed 7.2 attempts, through the same recovery chain as the M2/M3 precedents (settle10).  The canonical .auto-pm/continuity.db lives in the control root
# only (git-ignored), so the chain runs in the control root.
#   0. preconditions (approval receipt with the card SHA, empty index, every target non-terminal or already CANCELLED, original Decision files present, no process using the target worktrees);
#   1. one recovery CHG per project (SW-2026-008 SCPT, SYS-2026-001 DOCU), walked to implementing (closed later by settle72_2_chg_close.sh on acceptance);
#   2. one recovery Decision per project (settle_expired_run / CANCELLED / the project's target Runs);
#   3. ONE commit that binds exactly the Decision files (original ones not yet in Git + the two recovery Decisions) to the control-root HEAD (required by settle_expired_run);
#   4. per target: recovery Work/Run in the control root, settle-expired -> CANCELLED, the old lease token must be dead (when a token file exists), the target Work -> CANCELLED if it is still IN_PROGRESS or BLOCKED, the recovery chain closed.
# No SQL, no compensation scripts. Resumable: each step checks the current state first. NOTHING else is disposed of.  `--check-only` stops after the preconditions without writing anything.
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
REAL=/c/Users/fubai/Documents/My_Workspace
ROOT="$REAL"
cd "$ROOT"
PY="$REAL/.venv/Scripts/python.exe"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
DB=.auto-pm/continuity.db
EV="$ROOT/.auto-pm/reports/m3-settle72"
CARD="$EV/SETTLE72_recovery_card.md"
CARD_SHA=ec4bc4a5116a1e7088ce4b16246b8244ad37268334ff60e9ebba400eebc849ad
OWNER=claude:settle72

# groups: 0 = SW-2026-008, 1 = SYS-2026-001
G_PID=("SW-2026-008" "SYS-2026-001")
G_DOM=("SCPT" "DOCU")
G_DIR=("01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT" "SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU")
G_STATEF=("$EV/settle_chg_sw.txt" "$EV/settle_chg_sys.txt")
G_RDEC=("DEC-20261105-SETL72SW" "DEC-20261105-SETL72SY")
G_CHG=("" "")
# targets (index = card table row)
TAG=("a20101" "a20103" "a20104" "c03rec2" "e01" "g10" "wbs24" "wbs25" "rel72x2" "d07p1")
GRP=(0 0 0 0 0 0 1 1 0 0)
T_RUN=("RUN-SW008-A2-201-01" "RUN-SW008-A2-201-03" "RUN-SW008-A2-201-04" "RUN-SW008-PMF-C03REC-002" "RUN-SW008-PMF-E01-001" "RUN-SW008-PMF-G10-001" "RUN-SYS001-PMF-WBS24-001" "RUN-SYS001-PMF-WBS25-001" "RUN-SW008-M3-REL72-002" "RUN-SW008-M3-D07P-001")
T_WORK=("WORK-SW008-A2-201" "WORK-SW008-A2-201-R2" "WORK-SW008-A2-201-R2" "WORK-SW008-PMF-C03REC-001" "WORK-SW008-PMF-E01-001" "WORK-SW008-PMF-G10-002" "WORK-SYS001-PMF-WBS24-001" "WORK-SYS001-PMF-WBS25-001" "WORK-SW008-M3-REL72-002" "WORK-SW008-M3-D07P-001")
T_DEC=("DEC-20260910-C518CA55" "DEC-20260910-7285DE70" "DEC-20260910-7285DE70" "DEC-20260919-C03R0260" "DEC-20260914-26950AE2" "DEC-20260913-1A2BE7E8" "DEC-20260914-95F03E6A" "DEC-20260915-A5D0A37E" "DEC-20261104-M3R72A01" "DEC-20261105-M3D07P01")
T_OWNER=("Codex / Terra High" "Codex" "Codex" "codex-terra-high" "codex" "codex-gpt-5.6-sol" "codex" "codex" "claude:m3rel72" "claude:m3d07p")
T_TOKEN=("" "" "" "" "" "" "" "" "$REAL/.auto-pm/reports/m3-rel72/lease_token.txt" "$REAL/.auto-pm/reports/m3-d07p/lease_token.txt")
T_WHAT=("A2-201 第一次运行（BLOCKED），其 Work 已 CANCELLED" "A2-201-R2 第三次运行（RUNNING），其 Work 已 ACCEPTED" "A2-201-R2 第四次运行（VERIFYING），其 Work 已 ACCEPTED" "C03REC 第二次运行（VERIFYING），其 Work 已 CANCELLED" "PMF-E01 运行（BLOCKED），其 Work 已 ACCEPTED" "PMF-G10 运行（BLOCKED），其 Work 已 ACCEPTED" "WBS24 运行（VERIFYING），其 Work 已 CANCELLED（项目 SYS-2026-001）" "WBS25 运行（VERIFYING），其 Work 已 ACCEPTED（项目 SYS-2026-001）" "卡 221 V1.0 的失败 Run（RUNNING，租约已过期），其 Work 在 IN_PROGRESS" "切换卡 D07p V1.0 的回退 Run（RUNNING，租约 07:26 MST 到期），其 Work 在 IN_PROGRESS")
N=10

mkdir -p "$EV"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
cli() { "$PY" -B main.py "$@"; }
sq() { "$PY" -B - "$@" <<'EOF'
import sqlite3,sys
c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True)
r=c.execute(sys.argv[1],tuple(sys.argv[2:])).fetchone(); print(r[0] if r else "NONE")
EOF
}
run_state()  { sq "select state from run_items where run_id=?" "$1"; }
work_state() { sq "select state from work_items where work_id=?" "$1"; }
lease_ver()  { sq "select version from execution_leases where run_id=?" "$1"; }
lease_exp()  { sq "select expires_at from execution_leases where run_id=?" "$1"; }
chg_status() { awk -F'|' '/^\|[[:space:]]*变更状态[[:space:]]*\|/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3); print $3; exit}' "${G_DIR[$1]}/${G_CHG[$1]}.md"; }
orphans() { "$PY" -B - "$1" <<'EOF'
import sqlite3,sys
c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True)
rows=c.execute("SELECT r.run_id FROM run_items r JOIN work_items w ON w.work_id=r.work_id WHERE w.subject_project_id=? AND r.state NOT IN ('SUCCEEDED','FAILED','CANCELLED') AND w.state IN ('ACCEPTED','CLOSED','CANCELLED') ORDER BY r.run_id",(sys.argv[1],)).fetchall()
print(len(rows), " ".join(r[0] for r in rows))
EOF
}

echo "== 0. Preconditions"
[[ "$CARD_SHA" != __CARD_SHA__ ]] || die "card SHA not filled in"
[[ "$(sha256sum < "$CARD" | cut -d' ' -f1)" == "$CARD_SHA" ]] || die "the recovery card bytes differ from the SHA reported to the user"
grep -q "^CARD_SHA256=$CARD_SHA$" "$EV/approval_receipt.txt" 2>/dev/null || die "no approval receipt for this card SHA (the user's approval must be recorded in $EV/approval_receipt.txt)"
for ((i=0;i<N;i++)); do
  s="$(run_state "${T_RUN[$i]}")"
  case "$s" in RUNNING|VERIFYING|BLOCKED|READY|CANCELLED) ;; *) die "unexpected state of ${T_RUN[$i]}: $s" ;; esac
  [[ -f ".auto-pm/decisions/${T_DEC[$i]}.json" ]] || die "original Decision file of ${T_RUN[$i]} is missing"
  [[ "$(work_state "${T_WORK[$i]}")" != NONE ]] || die "target Work ${T_WORK[$i]} is missing"
done
[[ -z "$(git diff --cached --name-only)" ]] || die "the control-root index already has staged changes; refusing to commit"
[[ "$(git branch --show-current)" == main ]] || die "the control root is not on the expected branch"
cli ledger reconcile SW-2026-008 | grep 摘要
cli ledger reconcile SYS-2026-001 | grep 摘要
echo "-- before: Runs under finished Work: SW-2026-008 = $(orphans SW-2026-008); SYS-2026-001 = $(orphans SYS-2026-001)"
echo "-- no process may use the target worktrees or Runs"
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.ProcessId -ne \$PID -and (\$_.CommandLine -like '*REL72-002*' -or \$_.CommandLine -like '*D07P-001*' -or \$_.CommandLine -like '*worktrees/m3-rel72*' -or \$_.CommandLine -like '*worktrees/m3-d07p*') } | Select-Object ProcessId,Name,CommandLine | Format-List" > "$EV/process_check.txt" 2>&1 || true
if grep -q "ProcessId" "$EV/process_check.txt"; then cat "$EV/process_check.txt"; die "a process still references a target worktree or Run"; fi
echo "no matching process"
[[ "${1:-}" != "--check-only" ]] || { echo "CHECK_ONLY_OK: the preconditions hold; nothing was written"; exit 0; }

DELEG="用户在线程里亲口批准本卡（回执 .auto-pm/reports/m3-settle72/approval_receipt.txt，含本卡 SHA-256 $CARD_SHA 的前 12 位）；用户 2026-10-18 预授权 Claude 自行收口推送；由 Claude 代为运行脚本"

echo "== 1. Recovery CHGs (one per project)"
for g in 0 1; do
  [[ ! -f "${G_STATEF[$g]}" ]] || IFS= read -r "G_CHG[$g]" < "${G_STATEF[$g]}"
  if [[ -z "${G_CHG[$g]}" ]]; then
    out="$(cli change create --pid "${G_PID[$g]}" --domain "${G_DOM[$g]}" --nature CFG --scope MODULE --applicant fubai \
      --background "发版 7.2 的运行时新增互锁 LIVE_RUN_UNDER_FINISHED_WORK；项目 ${G_PID[$g]} 里有挂在已结束 Work 下的旧 Run（以及 7.2 两次失败尝试的遗留 Run），切换卡 D07p 的切换后核验因此不过并自动回退；这些 Run 的租约都已过期或到期，前向结算为 CANCELLED，Work 仍在 IN_PROGRESS/BLOCKED 的转 CANCELLED，已 ACCEPTED/CANCELLED 的原样不动" \
      --necessity "现有服务不允许 RUNNING/VERIFYING/BLOCKED 直接取消，过期 lease 不能续期；只有独立恢复授权下的 settle-expired 能合法收口，且恢复 CHG 必须与目标 Run 同项目。不处置会让 7.2 切换后 pm orient 永远报冲突并拦住后续操作" \
      --references "CARD-SW008-M3-SETTLE72 V1.0；CARD_SHA256=$CARD_SHA；$DELEG；先例 M3-SETTLE10、M2-SETTLE、BL02、U07A 恢复链" --urgency normal)"
    printf '%s\n' "$out" | grep -E "CHG-|状态" || true
    G_CHG[$g]="$(printf '%s\n' "$out" | grep -oE "CHG-${G_DOM[$g]}-2026-[0-9]+" | tail -n 1)"
    [[ -n "${G_CHG[$g]}" ]] || die "cannot parse a new recovery CHG id for group $g"
    printf '%s\n' "${G_CHG[$g]}" > "${G_STATEF[$g]}"
  fi
  while true; do
    case "$(chg_status "$g")" in
      draft)        cli change transition "${G_CHG[$g]}" --pid "${G_PID[$g]}" --to submitted    --approver fubai --comment "[$DELEG] 提交恢复变更" >/dev/null ;;
      submitted)    cli change transition "${G_CHG[$g]}" --pid "${G_PID[$g]}" --to under_review --approver fubai --comment "[$DELEG] 进入评审" >/dev/null ;;
      under_review) cli change transition "${G_CHG[$g]}" --pid "${G_PID[$g]}" --to approved     --approver fubai --comment "[$DELEG] 批准恢复变更：仅结算卡 SETTLE72 表里属于 ${G_PID[$g]} 的目标 Run 并取消仍在 IN_PROGRESS/BLOCKED 的目标 Work，不处置任何其他记录" >/dev/null ;;
      approved)     cli change transition "${G_CHG[$g]}" --pid "${G_PID[$g]}" --to implementing --approver fubai --comment "[$DELEG] 开始实施" >/dev/null ;;
      implementing) break ;;
      *) die "recovery CHG ${G_CHG[$g]} state not resumable: $(chg_status "$g")" ;;
    esac
  done
done

echo "== 2. Recovery Decisions (one per project, every target Run of the project named)"
for g in 0 1; do
  if [[ ! -f ".auto-pm/decisions/${G_RDEC[$g]}.json" ]]; then
    TARGS=(); for ((i=0;i<N;i++)); do if [[ "${GRP[$i]}" == "$g" ]]; then TARGS+=(--target-run-id "${T_RUN[$i]}"); fi; done
    cli decision create --change-id "${G_CHG[$g]}" --pid "${G_PID[$g]}" --approver fubai --decision-id "${G_RDEC[$g]}" --file "$DB" \
      --allow-runtime-action settle_expired_run --allow-outcome CANCELLED "${TARGS[@]}" --json-output | grep -E '"decision_id"|"change_id"'
  fi
done

echo "== 3. Git-bind the Decision files (exact paths only; ONE commit, before any recovery Run starts)"
FILES=(); for ((i=0;i<N;i++)); do FILES+=(".auto-pm/decisions/${T_DEC[$i]}.json"); done; for g in 0 1; do FILES+=(".auto-pm/decisions/${G_RDEC[$g]}.json"); done
mapfile -t FILES < <(printf '%s\n' "${FILES[@]}" | sort -u)
if [[ -n "$(git status --porcelain -- "${FILES[@]}")" ]]; then
  git add -- "${FILES[@]}"
  for f in $(git diff --cached --name-only); do [[ " ${FILES[*]} " == *" $f "* ]] || die "staged file outside the Decision set: $f"; done
  for g in 0 1; do git diff --cached --name-only | grep -qx ".auto-pm/decisions/${G_RDEC[$g]}.json" || die "recovery Decision ${G_RDEC[$g]} is not staged"; done
  git commit -m "chore(governance): [${G_CHG[0]}, ${G_CHG[1]}] bind the settlement decisions of the 7.2 live-run cleanup" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
fi
git ls-files --error-unmatch -- "${FILES[@]}" >/dev/null
[[ -z "$(git status --porcelain -- "${FILES[@]}")" ]] || die "Decision files differ from HEAD"
HEAD_SHA="$(git rev-parse HEAD)"
echo "control-root HEAD for recovery: $HEAD_SHA" | tee "$EV/recovery_head.txt"

settle_one() {
  local i="$1" tag="${TAG[$1]}" TR="${T_RUN[$1]}" TW="${T_WORK[$1]}" TO="${T_OWNER[$1]}" g="${GRP[$1]}"
  local RD="${G_RDEC[$g]}" pid="${G_PID[$g]}"
  local RW="WORK-${pid//-/}-M3-SETTLE72-${tag^^}-001" RR="RUN-${pid//-/}-M3-SETTLE72-${tag^^}-001"
  RW="${RW/WORK-SW2026008/WORK-SW008}"; RR="${RR/RUN-SW2026008/RUN-SW008}"; RW="${RW/WORK-SYS2026001/WORK-SYS001}"; RR="${RR/RUN-SYS2026001/RUN-SYS001}"
  local tokfile="$EV/recovery_lease_token_$tag.txt" token
  if [[ "$(run_state "$TR")" != CANCELLED ]]; then
    "$PY" -B - "$(lease_exp "$TR")" <<'EOF' || die "the lease of the target Run $TR has not expired yet (see its expires_at); run the script again after that time, it resumes here"
import sys, datetime
exp = datetime.datetime.fromisoformat(sys.argv[1])
sys.exit(0 if exp <= datetime.datetime.now(datetime.timezone.utc) else 1)
EOF
  fi
  echo "== 4.$tag Recovery Work and Run (control root, owned $DB) for $TR"
  [[ -f "$tokfile" ]] || openssl rand -hex 16 > "$tokfile"
  token="$(tr -d '\r\n' < "$tokfile")"
  [[ "$(work_state "$RW")" != NONE ]] || cli continuity work create --work-id "$RW" --pid "$pid" --kind GOVERNANCE \
    --title "过期 Run $TR 结算恢复" --owner "$OWNER" --scope "$DB" --card-file "$(pwd -W)/.auto-pm/reports/m3-settle72/SETTLE72_recovery_card.md" --idempotency-key "settle72-$tag-work-create-1" | grep '"state"'
  [[ "$(work_state "$RW")" != PLANNED ]] || cli continuity work authorize --work-id "$RW" --decision-id "$RD" --idempotency-key "settle72-$tag-work-auth-1" | grep '"state"'
  if [[ "$(run_state "$RR")" == NONE ]]; then
    cli continuity run start --run-id "$RR" --work-id "$RW" --executor "$OWNER" --adapter claude-code \
      --owned "$DB" --declared-dirty "$DB" --worktree "$(cygpath -w "$ROOT")" --lease-token "$token" --lease-seconds 1800 --idempotency-key "settle72-$tag-run-start-1" | grep -E '"state"|"git_head"'
  fi
  [[ "$(run_state "$RR")" != READY ]] || cli continuity run transition --run-id "$RR" --to RUNNING --owner "$OWNER" --lease-token "$token" --idempotency-key "settle72-$tag-run-running-1" | grep '"state"'
  [[ "$(work_state "$RW")" != READY ]] || cli continuity work transition --work-id "$RW" --to IN_PROGRESS --idempotency-key "settle72-$tag-work-inprogress-1" | grep '"state"'

  echo "== 5.$tag Settle $TR -> CANCELLED"
  local ver; ver="$(lease_ver "$TR")"
  if [[ "$(run_state "$TR")" != CANCELLED ]]; then
    cli continuity run settle-expired --target-run-id "$TR" --recovery-run-id "$RR" --recovery-owner "$OWNER" \
      --recovery-lease-token "$token" --decision-id "$RD" --outcome CANCELLED \
      --reason "SETTLE72：${T_WHAT[$1]}；发版 7.2 运行时的互锁 LIVE_RUN_UNDER_FINISHED_WORK 要求结清；租约已过期，前向取消" \
      --idempotency-key "settle72-$tag-settle-1" | tee "$EV/settle_output_$tag.json" | grep -E '"state"|"run_id"'
  fi
  [[ "$(run_state "$TR")" == CANCELLED ]] || die "target Run $TR is not CANCELLED"

  echo "== 6.$tag The old lease token must be dead (only when a token file exists)"
  local old=""; if [[ -n "${T_TOKEN[$1]}" && -f "${T_TOKEN[$1]}" ]]; then old="$(tr -d '\r\n' < "${T_TOKEN[$1]}" 2>/dev/null || true)"; fi
  if [[ -n "$old" ]]; then
    if SETTLE_OLD_TOKEN="$old" cli continuity lease renew --run-id "$TR" --owner "$TO" --lease-token-env SETTLE_OLD_TOKEN \
         --expected-version "$ver" --lease-seconds 60 --idempotency-key "settle72-$tag-oldtoken-probe-1" > "$EV/old_token_renew_$tag.txt" 2>&1; then
      die "old lease token of $TR was still accepted"
    fi
    echo "old token renew rejected: $(grep -v "^launcher:" "$EV/old_token_renew_$tag.txt" | tail -1)" | tee -a "$EV/old_token_renew_$tag.txt"
  fi

  echo "== 7.$tag Target Work $TW"
  case "$(work_state "$TW")" in
    IN_PROGRESS|BLOCKED) cli continuity work transition --work-id "$TW" --to CANCELLED --idempotency-key "settle72-$tag-target-work-cancelled-1" | grep '"state"' ;;
    ACCEPTED|CLOSED|CANCELLED) echo "target Work $TW is already $(work_state "$TW"): left as it is" ;;
    *) die "unexpected state of target Work $TW: $(work_state "$TW")" ;;
  esac

  echo "== 8.$tag Close the recovery chain itself"
  [[ "$(run_state "$RR")" != RUNNING ]]   || cli continuity run transition --run-id "$RR" --to VERIFYING --owner "$OWNER" --lease-token "$token" --idempotency-key "settle72-$tag-run-verifying-1" | grep '"state"'
  [[ "$(run_state "$RR")" != VERIFYING ]] || cli continuity run transition --run-id "$RR" --to SUCCEEDED --owner "$OWNER" --lease-token "$token" --idempotency-key "settle72-$tag-run-succeeded-1" | grep '"state"'
  for s in VERIFYING ACCEPTED CLOSED; do
    [[ "$(work_state "$RW")" == CLOSED ]] && break
    cli continuity work transition --work-id "$RW" --to "$s" --idempotency-key "settle72-$tag-work-$s-1" | grep '"state"'
  done
  [[ "$(run_state "$RR")" == SUCCEEDED && "$(work_state "$RW")" == CLOSED ]] || die "recovery chain $tag did not reach its terminal states"
  if SETTLE_REC_TOKEN="$token" cli continuity lease renew --run-id "$RR" --owner "$OWNER" --lease-token-env SETTLE_REC_TOKEN \
       --expected-version "$(lease_ver "$RR")" --lease-seconds 60 --idempotency-key "settle72-$tag-rectoken-probe-1" > "$EV/recovery_token_renew_$tag.txt" 2>&1; then
    die "recovery lease token of $RR was still accepted after SUCCEEDED"
  fi
  echo "recovery token renew rejected: $(grep -v "^launcher:" "$EV/recovery_token_renew_$tag.txt" | tail -1)" | tee -a "$EV/recovery_token_renew_$tag.txt"
}
for ((i=0;i<N;i++)); do settle_one "$i"; done

echo "== 9. Evidence"
cli ledger reconcile SW-2026-008 | grep 摘要
cli ledger reconcile SYS-2026-001 | grep 摘要
echo "after: Runs under finished Work: SW-2026-008 = $(orphans SW-2026-008); SYS-2026-001 = $(orphans SYS-2026-001)" | tee "$EV/orphans_after.txt"
grep -q "^after: Runs under finished Work: SW-2026-008 = 0 ; SYS-2026-001 = 0 $" "$EV/orphans_after.txt" || die "there are still Runs under finished Work (see orphans_after.txt)"
for pid in SW-2026-008 SYS-2026-001; do cli pm orient "$pid" --json 2>/dev/null | "$PY" -B -c 'import sys,json;t=sys.stdin.read();d=json.JSONDecoder().raw_decode(t[t.index("{"):])[0];print(sys.argv[1],"orient conflicts:",json.dumps(d.get("conflicts")))' "$pid" | tee -a "$EV/orient_after.txt"; done
echo "SETTLE72_DONE chg_sw=${G_CHG[0]} chg_sys=${G_CHG[1]} head=$HEAD_SHA targets=$N" | tee "$EV/settle_result.txt"
