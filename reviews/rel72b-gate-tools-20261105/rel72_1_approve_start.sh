#!/usr/bin/env bash
# M3-REL72 (card 221 V1.1, core pipeline (full gate set), ONE NEW report) - start of the governed run under the user's chat approval (the card SHA was reported in chat first).
# Creates/approves the SW-2026-008 CHG, the 1-path Decision, the isolated worktree, the Work and the Run, and writes close.env and the approval receipt. Resumable.
# `--check-only` stops after the preconditions without writing anything. It REFUSES to start unless: the card bytes equal the SHA-256 below; the card section 4 lists exactly the owned paths
# and section 5.1 equals the reference manifest; the reference and tool bytes equal the manifest; the baseline (and, for a stacked card, the previous card's tip) is as frozen.
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
ROOT=/c/Users/fubai/Documents/My_Workspace
cd "$ROOT"
PY="$ROOT/.venv/Scripts/python.exe"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
CARD="$P/02_规划/221_M3-REL72_发版7.2候选门禁实施卡_V1.1_PM.md"
CARD_SHA=49a1d50cb6c079a0befe3beacdd7dae05fbcd302e2ae8019f8a498608f87d8f8
BASE=dd8b192f2e0a8ffdc370fd7e2dc4f7a999bb7642
BASE_BRANCH=m3-rel72-base
TODAY="$(date +%Y%m%d)"
DEC="DEC-$TODAY-M3R72B01"
WORK=WORK-SW008-M3-REL72-003
RUN=RUN-SW008-M3-REL72-003
OWNER=claude:m3rel72b
WT=.auto-pm/worktrees/m3-rel72b
BRANCH=claude/m3-rel72b
EV="$ROOT/.auto-pm/reports/m3-rel72b"
STATE="$EV/rel72_chg.txt"
FULL=("01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/05_收尾/017_M3_发版7.2候选构建与全量门禁_REP.md")
NEW_PATHS=("01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/05_收尾/017_M3_发版7.2候选构建与全量门禁_REP.md")
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
# approval_refs.env is PARSED line by line (never sourced, never eval'd); the refs and the SHA are checked by regular expressions, the text fields reject quotes, backticks, $ and backslashes
load_refs() {
  local f="$1" line key val
  GO_SHA=""; GO_REF=""; GO_TEXT=""; GO_AT=""; NIGHT_REF=""; NIGHT_TEXT=""
  [[ -f "$f" ]] || die "approval_refs.env is missing: it records the user's own go-ahead for THIS card SHA and is written only after the user said it"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == *=* ]] || die "approval_refs.env: a line without '='"
    key="${line%%=*}"; val="${line#*=}"
    case "$key" in
      GO_SHA)  [[ "$val" =~ ^[0-9a-f]{64}$ ]] || die "approval_refs.env: GO_SHA format"; GO_SHA="$val" ;;
      GO_REF)  [[ "$val" =~ ^user-confirmation:cmsg_[A-Za-z0-9]{20,80}$ ]] || die "approval_refs.env: GO_REF format"; GO_REF="$val" ;;
      NIGHT_REF) [[ "$val" =~ ^user-confirmation:cmsg_[A-Za-z0-9]{20,80}$ ]] || die "approval_refs.env: NIGHT_REF format"; NIGHT_REF="$val" ;;
      GO_AT) [[ "$val" =~ ^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z$ ]] || die "approval_refs.env: GO_AT format"; GO_AT="$val" ;;
      GO_TEXT|NIGHT_TEXT)
        [[ ${#val} -ge 1 && ${#val} -le 200 && "$val" != *\"* && "$val" != *\'* && "$val" != *\`* && "$val" != *'$'* && "$val" != *\\* ]] || die "approval_refs.env: $key has a rejected character or length"
        printf -v "$key" '%s' "$val" ;;
      *) die "approval_refs.env: unknown key" ;;
    esac
  done < "$f"
  [[ -n "$GO_SHA" && -n "$GO_REF" && -n "$GO_TEXT" && -n "$GO_AT" ]] || die "approval_refs.env is incomplete"
}

load_refs "$EV/approval_refs.env"
[[ "$GO_SHA" == "$CARD_SHA" ]] || die "approval_refs.env: GO_SHA is not this card SHA"
DELEG="委托执行：用户 2026-10-18 预授权自行收口推送；用户 ${GO_AT} 在本线程亲口回复“${GO_TEXT}”（${GO_REF}），门禁卡 SHA ${CARD_SHA}；extend-hold 一次的授权只取自 HOLD_REF.txt（没有则不延长）；只构建与门禁，不切换有效发布版本（切换另走切换卡，须门禁与独立审计全部通过，且用户亲口说“切换”）；批准条件：卡字节等于 SHA、机器预检通过、范围不超出卡列路径、任一门禁失败即停下保留现场；由 Claude 代为运行脚本；变更单收口按用户在 GO_TEXT 里的委托办理"
BACKGROUND="M3-REL72（发版 7.2 候选）：用 main 上的合并提交 dd8b192f 里已有的 scripts/pmf_build.py 构建两次并比对、两份都通过 verify、载荷可导入且命令行可用；再跑全量门禁：十组回归整组重跑（基线为发版 7 的受治理输出 RUN-SW008-M3-REL7-001；差值取自开跑前从 d671611 到冻结提交的逐组收集数和变化测试文件在两棵树上的跑数，只证明没有分组丢收集用例）、静态检查、全库审计如实记录、文档检查、真实钩子、全部注册项目对账、控制根定位无冲突。自发版 7（1.3.3-d671611）以来合入 43 个合并提交，产品子树 49 个文件不同。只提交合同报告，门禁全过才提交。不切换发布版本。"
mkdir -p "$EV"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
cli() { "$PY" -B main.py "$@"; }
q() { "$PY" -B -c 'import sqlite3,sys;c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True);r=c.execute(sys.argv[1],tuple(sys.argv[2:])).fetchone();print(r[0] if r else "NONE")' "$@"; }
chg_status() { awk -F'|' '/^\|[[:space:]]*变更状态[[:space:]]*\|/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3); print $3; exit}' "$1"; }

echo "== 0. Preconditions"
[[ "$CARD_SHA" != __CARD_SHA__ ]] || die "card SHA not filled in"
[[ "$(sha256sum < "$CARD" | cut -d' ' -f1)" == "$CARD_SHA" ]] || die "card 221 bytes differ from the reviewed final V1.1"
grep -qE '^> 安全回路: (是|否)$' "$CARD" || die "card 221 has no line '> 安全回路: 是' or '> 安全回路: 否' in its header (TD-SW008-211; pr open needs it)"
[[ "$(git rev-parse "$BASE^{commit}")" == "$BASE" ]] || die "baseline missing"
[[ "$(git rev-parse "$BASE_BRANCH")" == "$BASE" ]] || die "the baseline branch is no longer at the baseline"
[[ "$(q "select state from run_items where run_id=?" RUN-SW008-M3-REL7-002)" == SUCCEEDED && "$(q "select state from work_items where work_id=?" WORK-SW008-M3-REL7-002)" == CLOSED ]] || die "WORK-SW008-M3-REL7-002 is not SUCCEEDED/CLOSED"
PREV_FILE="$P/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-472.md"
[[ "$(chg_status "$PREV_FILE")" == completed ]] || die "the previous change request (CHG-SCPT-2026-472) is not completed"
[[ ! -d "$WT" ]] || die "the candidate worktree already exists"
for p in "${FULL[@]}"; do
  if [[ " ${NEW_PATHS[*]} " == *" $p "* ]]; then ! git cat-file -e "$BASE:$p" 2>/dev/null || die "planned-new path already exists at baseline: $p"; else git cat-file -e "$BASE:$p" || die "path missing at baseline: $p"; fi
done
"$PY" -B - "$CARD" "$EV/reference_manifest.json" "${FULL[@]}" <<'EOF'
import json, re, sys
card_path, manifest_path, *paths = sys.argv[1:]
card = open(card_path, encoding="utf-8").read()
manifest = json.load(open(manifest_path, encoding="utf-8"))
sec4 = card.split("## 4. ", 1)[1].split("\n## 5. ", 1)[0]
listed = re.findall(r"^\| \d+ \| `([^`]+)` \|", sec4, re.M)
assert len(listed) == len(paths) and sorted(listed) == sorted(paths), ("section 4 paths differ", sorted(set(listed) ^ set(paths)))
sec51 = card.split("### 5.1 ", 1)[1].split("### 5.2 ", 1)[0]
shas = dict(re.findall(r"^\| \d+ \| `([^`]+)` \| [^|]+ \| `([0-9a-f]{64})` \|", sec51, re.M))
reference = {k: v for k, v in manifest.items() if not k.startswith("tools/")}
assert shas == reference and len(shas) == len(paths), "card section 5.1 SHA table differs from the reference manifest"
print("card section 4 lists the", len(paths), "owned paths; section 5.1 SHA table equals the reference manifest")
EOF
"$PY" -B - "$EV/reference_manifest.json" <<'EOF'
import hashlib, sys, json
m = json.load(open(sys.argv[1], encoding="utf-8"))
for rel, sha in m.items():
    if rel.startswith("tools/m2-tools/"):
        path = f".auto-pm/reports/{rel[len('tools/'):]}"
    elif rel.startswith("tools/m2_"):
        path = f".auto-pm/reports/{rel[len('tools/'):]}"
    elif rel.startswith("tools/"):
        path = f".auto-pm/reports/m3-rel72b/{rel[len('tools/'):]}"
    else:
        path = f".auto-pm/reports/m3-rel72b/proto/{rel}"
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == sha, rel
print("reference and tool bytes match the manifest:", len(m))
EOF
bash "$EV/rel72_0_move_unregistered.sh" check || die "step M check failed (the 16 unregistered release folders)"
cli implementation-card precheck --card-file "$(pwd -W)/$CARD" > "$EV/precheck_V1.1.json" 2>/dev/null || die "card precheck failed"
cli ledger reconcile SW-2026-008 | grep 摘要
[[ "${1:-}" != "--check-only" ]] || { echo "CHECK_ONLY_OK: the preconditions hold; nothing was written"; exit 0; }

echo "== 1. CHG"
chg=""; [[ -f "$STATE" ]] && IFS= read -r chg < "$STATE"
if [[ -z "$chg" ]]; then
  out="$(cli change create --pid SW-2026-008 --domain SCPT --nature OPT --scope MODULE --applicant fubai \
    --background "$BACKGROUND" \
    --necessity "11-03 合进 main 的长任务守卫、内存预检与相关修复只有经过全量门禁的候选才能切换为有效版本" \
    --references "CARD-SW008-M3-REL72 V1.1；CARD_SHA256=$CARD_SHA；BASE=$BASE；$DELEG" --urgency normal)"
  printf '%s\n' "$out" | grep -E "CHG-|状态" || true
  chg="$(printf '%s\n' "$out" | grep -oE 'CHG-SCPT-2026-[0-9]+' | tail -n 1)"
  [[ -n "$chg" ]] || die "cannot parse CHG id"
  printf '%s\n' "$chg" > "$STATE"
fi
CHG_FILE="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/$chg.md"
while true; do
  case "$(chg_status "$CHG_FILE")" in
    draft)        cli change transition "$chg" --pid SW-2026-008 --to submitted    --approver fubai --comment "[$DELEG] 提交卡 221 V1.1" >/dev/null ;;
    submitted)    cli change transition "$chg" --pid SW-2026-008 --to under_review --approver fubai --comment "[$DELEG] 基线与 1 路径已核验，卡 §4 路径表与 §5.1 指纹表等于冻结的参考字节，前置卡已达技术终态，卡机器预检通过" >/dev/null ;;
    under_review) cli change transition "$chg" --pid SW-2026-008 --to approved     --approver fubai --approval-evidence-ref "$GO_REF" --comment "[$DELEG] 批准卡 221 V1.1：只允许卡 §4 列出的 1 个路径、字节等于 §5.1；禁止其他任何文件、手改冻结字节、产品文件、既有 CHG 原文、台账（除非本卡 §4 列出）、规则、Hook、release、直接 SQL、推送、合并进 main、打 tag、部署" >/dev/null ;;
    approved)     cli change transition "$chg" --pid SW-2026-008 --to implementing --approver fubai --comment "[$DELEG] 开始实施（隔离候选）" >/dev/null ;;
    implementing) break ;;
    *) die "CHG state not resumable: $(chg_status "$CHG_FILE")" ;;
  esac
done
echo "CHG $chg implementing"

echo "== 2. Decision $DEC (1 paths)"
if [[ ! -f ".auto-pm/decisions/$DEC.json" ]]; then
  A=(); for p in "${FULL[@]}"; do A+=(--file "$p"); done
  cli decision create --change-id "$chg" --pid SW-2026-008 --approver fubai --approval-evidence-ref "$GO_REF" --decision-id "$DEC" "${A[@]}" \
    --condition "严格限定卡 221 V1.1 的 1 个 owned path；文件字节必须等于卡 §5.1 的 SHA-256" \
    --condition "不得改 §4 之外的任何文件（产品文件、其他测试、既有 CHG 原文、台账、规则、AGENTS.md、.trae、.cursor、.agent、Hook 脚本、release）；不得直接 SQL 改真实库 .auto-pm/continuity.db；不合并进 main、不推送、不打 tag、不部署、不切换 release、不处置任何债务或历史失败记录" \
    --json-output | grep -E '"decision_id"|"change_id"'
fi

echo "== 3. Isolated worktree"
git worktree add -q -b "$BRANCH" "$WT" $BASE
[[ "$(git -C "$WT" rev-parse HEAD)" == "$(git rev-parse $BASE)" ]] || die "worktree HEAD is not the expected start commit"
[[ -z "$(git -C "$WT" status --porcelain)" ]] || die "worktree not clean"

echo "== 4. Work and Run"
S=(); O=(); for p in "${FULL[@]}"; do S+=(--scope "$p"); O+=(--owned "$p" --declared-dirty "$p"); done
[[ "$(q "select state from work_items where work_id=?" "$WORK")" != NONE ]] || cli continuity work create --work-id "$WORK" --pid SW-2026-008 --kind WBS \
  --title "M3-REL72 发版 7.2 候选构建与全量门禁（核心流程，一个报告）" --owner "$OWNER" "${S[@]}" --card-file "$(pwd -W)/$CARD" --idempotency-key work-sw008-m3-rel72b-002-work-create-1 | grep '"state"'
[[ "$(q "select state from work_items where work_id=?" "$WORK")" != PLANNED ]] || cli continuity work authorize --work-id "$WORK" --decision-id "$DEC" --idempotency-key work-sw008-m3-rel72b-002-work-auth-1 | grep '"state"'
TOKEN_FILE="$EV/lease_token.txt"; [[ -f "$TOKEN_FILE" ]] || openssl rand -hex 16 > "$TOKEN_FILE"; TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != NONE ]] || cli continuity run start --run-id "$RUN" --work-id "$WORK" --executor "$OWNER" --adapter claude-code "${O[@]}" \
  --worktree "$(cygpath -w "$ROOT/$WT")" --lease-token "$TOKEN" --lease-seconds 3600 --idempotency-key work-sw008-m3-rel72b-002-run-start-1 | grep -E '"state"|"git_head"'
[[ "$(q "select state from run_items where run_id=?" "$RUN")" != READY ]] || cli continuity run transition --run-id "$RUN" --to RUNNING --owner "$OWNER" --lease-token "$TOKEN" --idempotency-key work-sw008-m3-rel72b-002-run-running-1 | grep '"state"'
[[ "$(q "select state from work_items where work_id=?" "$WORK")" != READY ]] || cli continuity work transition --work-id "$WORK" --to IN_PROGRESS --idempotency-key work-sw008-m3-rel72b-002-work-inprogress-1 | grep '"state"'

sed "s/__CHG__/$chg/" "$EV/commit_msg.template.txt" > "$EV/commit_msg.txt"
{
  echo 'LABEL="CARD-SW008-M3-REL72 V1.1"'; echo "CHG=$chg"; echo "WORK=$WORK"; echo "RUN=$RUN"; echo "OWNER=$OWNER"; echo "BASE=$BASE"
  
  echo "BYTE_BASE=$BASE"
  echo "WT=$ROOT/$WT"; echo "TOKEN_FILE=$EV/lease_token.txt"; echo "VERDICT=$EV/gates/gate_verdict.json"; echo "CKPT=CKPT-SW008-M3-REL72-003"
  echo "COMMIT_MSG_FILE=$EV/commit_msg.txt"; echo "EV=$EV"; echo "STOP_AFTER_COMMIT=0"; echo 'EXPECT_GATES="G1 G2 G3 G4 G5 G6 G7 G8 G9"'
  echo "MERGE_PARENTS="
  printf 'OWNED=('; for p in "${FULL[@]}"; do printf '"%s" ' "$p"; done; printf ')\n'
} > "$EV/close.env"
{
  echo "APPROVAL_EVIDENCE_ID=APPROVAL-$TODAY-M3-REL72"
  echo "CARD=CARD-SW008-M3-REL72 V1.1"; echo "CARD_SHA256=$CARD_SHA"; echo "BASELINE=$BASE"; true
  echo "CHG_ID=$chg"; echo "DECISION_ID=$DEC"; echo "WORK_ID=$WORK"; echo "RUN_ID=$RUN"; echo "WORKTREE=$WT"; echo "BRANCH=$BRANCH"
  echo "OWNED_PATHS=1 (card section 4)"; echo "EXECUTOR=claude"
  echo "GO_REF=$GO_REF"; echo "NIGHT_REF=${NIGHT_REF:-}"; echo "APPROVAL_ORDER=user chat approval given after the card SHA-256 was reported in chat (GO_REF, GO_AT and GO_TEXT in approval_refs.env); the card bytes equal that SHA-256 (checked by this script at start); the approval evidence is the user's own go-ahead for this card SHA (GO_REF)"
  echo "FORBIDDEN=any path outside the card; hand edit of frozen bytes; existing CHG text; product files; direct SQL on the real DB; history rewrite; merge into main; push; tag; deploy; disposing of any debt or failure record"
  echo "APPROVED_BY=fubai (same user as baiyang)"; echo "SIGNATURE_MODE=DELEGATED; $DELEG"; echo "APPROVED_AT=$(date -u +%FT%TZ)"
  echo "NOT_DELEGATED=merge into main, push, tag, deploy, release switch; the content acceptance and the closure of the change request are the user's (not delegated)"
} > "$EV/approval_receipt.txt"
echo "$RUN $(date -u +%FT%TZ)" > "$ROOT/.auto-pm/reports/HEAVY_GATES_RUNNING"  # TD-SW008-205: names its Run; removed by the close script of the same Run
cli ledger reconcile SW-2026-008 | grep 摘要
echo "REL72_STARTED chg=$chg run=$RUN"
