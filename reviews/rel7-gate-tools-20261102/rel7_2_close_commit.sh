#!/usr/bin/env bash
# M3-REL7 (card 219) commit + Run/Work closure; same flow as the V04 script (the CHG is NEVER closed here: only after the user confirms).
# Usage: bash .auto-pm/reports/m2_card_close.sh <config.env>
# Order (lesson from BL02): machine verdict -> Checkpoint on the uncommitted candidate bytes (Run git_head = base)
# -> commit through the normal Hook (exact owned paths only) -> committed blobs must equal the Checkpoint hashes
# -> Run VERIFYING/SUCCEEDED -> Work VERIFYING/ACCEPTED/CLOSED -> CHG pending_acceptance/accepting/completed.
# Refuses on any mismatch; resumable (each step checks the current state first).
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
ROOT=/c/Users/fubai/Documents/My_Workspace
cd "$ROOT"
touch /c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m3-rel7/STOP_RENEW  # the gates are done: stop the renewal loop (the lease keeps >= 40 min, the closure takes about 10)
CONFIG="$1"; [[ -f "$CONFIG" ]] || { echo "config missing: $CONFIG"; exit 1; }
# shellcheck disable=SC1090
source "$CONFIG"   # LABEL CHG WORK RUN OWNER BASE WT TOKEN_FILE VERDICT CKPT COMMIT_MSG_FILE OWNED(array) EV
# Optional: MERGE_PARENTS="<sha> <sha>" (the commit is a --no-ff merge of BASE with these, in this order);
# STOP_AFTER_COMMIT=1 (stop after step 4; a later run with the final VERDICT finishes steps 5-6);
# CKPT_VERDICT=<file> (the verdict bound by the Checkpoint when the final VERDICT is a later, larger one).
CONCLUSION_EXTRA="${CONCLUSION_EXTRA:-}"; MERGE_PARENTS="${MERGE_PARENTS:-}"; STOP_AFTER_COMMIT="${STOP_AFTER_COMMIT:-0}"; CKPT_VERDICT="${CKPT_VERDICT:-$VERDICT}"
PY="$ROOT/.venv/Scripts/python.exe"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
CHG_FILE="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/$CHG.md"
DELEG="委托执行：用户 2026-10-18 预授权自行收口推送；用户 2026-11-02 12:04（当地时间）说“今天电脑给你用，允许白天跑门禁下午5点之前尽量结束”（协调者转述原话，用户消息 cmsg_01AfNxhPWkgwWYuL1EVfYC7tDgoX2UY8rPK5n7nMxruFa2）；只构建与门禁，不切换有效发布版本（切换要用户另回“切换”）；批准条件：卡字节等于 SHA、机器预检通过、范围不超出卡列路径、任一门禁失败即停下保留现场；由 Claude 代为运行脚本；变更单收口在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
cli() { "$PY" -B main.py "$@"; }
q() { "$PY" -B -c 'import sqlite3,sys;c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True);r=c.execute(sys.argv[1],tuple(sys.argv[2:])).fetchone();print(r[0] if r else "NONE")' "$@"; }
TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
mkdir -p "$EV"

echo "== 0. Machine verdict ($LABEL)"
[[ -f "$VERDICT" ]] || die "verdict file missing: $VERDICT"
[[ -f "$CKPT_VERDICT" ]] || die "checkpoint verdict file missing: $CKPT_VERDICT"
VSHA="$(sha256sum "$VERDICT" | cut -d' ' -f1)"
CVSHA="$(sha256sum "$CKPT_VERDICT" | cut -d' ' -f1)"
for vf in "$CKPT_VERDICT" "$VERDICT"; do
  "$PY" -B "$ROOT/.auto-pm/reports/m2-tools/verdict_check.py" "$vf" "$ROOT" "$LABEL" "$BASE" "$RUN" ${EXPECT_GATES:-} || die "verdict check refused: $vf"
done

echo "== 1. Candidate facts"
HEAD_NOW="$(git -C "$WT" rev-parse HEAD)"
changed="$(git -C "$WT" -c core.quotepath=false status --porcelain --untracked-files=all | sed 's/^...//' | sort)"
owned_sorted="$(printf '%s\n' "${OWNED[@]}" | sort)"
if [[ "$HEAD_NOW" == "$BASE" ]]; then
  [[ "$changed" == "$owned_sorted" ]] || die "uncommitted change set is not exactly the owned paths"
  if [[ -n "$MERGE_PARENTS" ]]; then
    [[ "$(tr '\n' ' ' < "$(git -C "$WT" rev-parse --git-dir)/MERGE_HEAD" | sed 's/ $//')" == "$MERGE_PARENTS" ]] || die "MERGE_HEAD is not $MERGE_PARENTS"
  fi
else
  [[ "$(git -C "$WT" rev-parse HEAD^)" == "$BASE" ]] || die "candidate HEAD is neither base nor one commit above base"
  [[ -z "$changed" ]] || die "committed candidate has further dirty files"
fi

echo "== 2. Checkpoint on current bytes (before commit)"
if [[ "$(q "select count(*) from checkpoints where checkpoint_id=?" "$CKPT")" == 0 ]]; then
  [[ "$HEAD_NOW" == "$BASE" ]] || die "checkpoint must be taken before the commit"
  EVARGS=(--evidence "gate_verdict=${CKPT_VERDICT#$ROOT/} sha256=$CVSHA" --evidence "card=$LABEL base=$BASE chg=$CHG" --evidence "executor=claude under the user's chat approval of 2026-10-11")
  for p in "${OWNED[@]}"; do EVARGS+=(--evidence "sha256:$p:$(sha256sum "$WT/$p" | cut -d' ' -f1)"); done
  cli continuity checkpoint create --checkpoint-id "$CKPT" --run-id "$RUN" --owner "$OWNER" --lease-token "$TOKEN" \
    --summary "$LABEL candidate bytes at base $BASE; gates per verdict ${CVSHA:0:12}" "${EVARGS[@]}" \
    --idempotency-key "${CKPT,,}-create" | grep -E '"checkpoint_id"|"git_head"'
fi
CK_EVIDENCE="$(q "select evidence_json from checkpoints where checkpoint_id=?" "$CKPT")"
[[ "$CK_EVIDENCE" == *"$CVSHA"* ]] || die "checkpoint does not bind the verdict hash"

echo "== 3. Commit through the normal Hook (exact owned paths)"
if [[ "$(git -C "$WT" rev-parse HEAD)" == "$BASE" ]]; then
  ( cd "$WT" && for p in "${OWNED[@]}"; do git add -- "$p"; done
    staged="$(git -c core.quotepath=false diff --cached --name-only | sort)"
    [[ "$staged" == "$owned_sorted" ]] || { echo "staged set differs from owned paths"; exit 1; }
    git commit -F "$COMMIT_MSG_FILE" )
fi
COMMIT="$(git -C "$WT" rev-parse HEAD)"
[[ "$(git -C "$WT" rev-parse HEAD^)" == "$BASE" ]] || die "commit parent is not the base"
[[ "$(git -C "$WT" rev-list --parents -n 1 HEAD | cut -d' ' -f2-)" == "$(echo $BASE $MERGE_PARENTS)" ]] || die "commit parents are not: $BASE $MERGE_PARENTS"
[[ "$(git -C "$WT" -c core.quotepath=false diff --name-only "$BASE" HEAD | sort)" == "$owned_sorted" ]] || die "commit contains paths outside the owned set"

echo "== 4. Committed blobs must equal the Checkpoint hashes"
for p in "${OWNED[@]}"; do
  sha="$(git -C "$WT" -c core.quotePath=false show "HEAD:$p" | sha256sum | cut -d' ' -f1)"
  [[ "$CK_EVIDENCE" == *"sha256:$p:$sha"* ]] || die "committed bytes of $p differ from the checkpoint"
done
echo "all ${#OWNED[@]} committed blobs match the checkpoint; commit $COMMIT"
if [[ "$STOP_AFTER_COMMIT" == 1 ]]; then echo "STOP_AFTER_COMMIT: Run/Work/CHG left open; commit $COMMIT"; exit 0; fi

echo "== 5. Run / Work terminal states"
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != RUNNING ]] || cli continuity run transition --run-id "$RUN" --to VERIFYING --owner "$OWNER" --lease-token "$TOKEN" --idempotency-key "${RUN,,}-verifying" | grep '"state"'
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != VERIFYING ]] || cli continuity run transition --run-id "$RUN" --to SUCCEEDED --owner "$OWNER" --lease-token "$TOKEN" --idempotency-key "${RUN,,}-succeeded" | grep '"state"'
[[ "$(q "select state from run_items where run_id=?" "$RUN")" == SUCCEEDED ]] || die "Run not SUCCEEDED"
while true; do
  case "$(q "select state from work_items where work_id=?" "$WORK")" in
    IN_PROGRESS) cli continuity work transition --work-id "$WORK" --to VERIFYING --idempotency-key "${WORK,,}-verifying" | grep '"state"' ;;
    VERIFYING)   cli continuity work transition --work-id "$WORK" --to ACCEPTED  --idempotency-key "${WORK,,}-accepted" | grep '"state"' ;;
    ACCEPTED)    cli continuity work transition --work-id "$WORK" --to CLOSED    --idempotency-key "${WORK,,}-closed" | grep '"state"' ;;
    CLOSED)      break ;;
    *) die "Work in unexpected state" ;;
  esac
done

HM="$ROOT/.auto-pm/reports/HEAVY_GATES_RUNNING"
if [[ -f "$HM" ]]; then
  if [[ "$(cut -d' ' -f1 "$HM")" == "$RUN" ]]; then rm -f -- "$HM"; echo "HEAVY_GATES_RUNNING of $RUN removed"; else echo "HEAVY_GATES_RUNNING belongs to another Run: $(cat "$HM")"; fi
fi
cli ledger reconcile SW-2026-008 | grep 摘要
{
  echo "LABEL=$LABEL"; echo "COMMIT=$COMMIT"; echo "PARENT=$BASE"; [[ -z "$MERGE_PARENTS" ]] || echo "MERGED=$MERGE_PARENTS"
  echo "CHECKPOINT=$CKPT"; [[ "$CVSHA" == "$VSHA" ]] || echo "CHECKPOINT_VERDICT_SHA256=$CVSHA"; echo "VERDICT_SHA256=$VSHA"
  echo "RUN=$RUN SUCCEEDED"; echo "WORK=$WORK CLOSED"; echo "CHG=$CHG implementing (final closure by user only)"
  echo "SIGNATURE_MODE=DELEGATED; $DELEG"; echo "CLOSED_AT=$(date -u +%FT%TZ)"
  echo "NOT_AUTHORIZED=merge, push, tag, deploy, release switch, CHG closure"
} | tee "$EV/acceptance_receipt.txt"
echo "REL7_COMMITTED $LABEL $COMMIT"
