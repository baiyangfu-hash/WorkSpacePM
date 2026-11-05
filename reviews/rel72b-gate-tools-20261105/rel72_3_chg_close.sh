#!/usr/bin/env bash
# M3-REL72 (card 221 V1.1) - CHG closure. NOT DELEGATED: run it only after the user has read the result and said in the chat that it is accepted.
# The facts (all nine gates, commit == frozen file set, Run SUCCEEDED, Work CLOSED) are verified first; the acceptance itself is the user's.
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
ROOT=/c/Users/fubai/Documents/My_Workspace; cd "$ROOT"
PY="$ROOT/.venv/Scripts/python.exe"; cli() { "$PY" -B main.py "$@"; }
EV="$ROOT/.auto-pm/reports/m3-rel72b"
CHG="$(head -n 1 "$EV/rel72_chg.txt")"
COMMIT="$(git rev-parse claude/m3-rel72b)"; CARD_SHA="$(grep '^CARD_SHA256=' "$EV/approval_receipt.txt" | cut -d= -f2)"
PARENT="$(grep '^BASE=' "$EV/close.env" | cut -d= -f2)"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
FILE="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/$CHG.md"
st() { awk -F'|' '/^\|[[:space:]]*变更状态[[:space:]]*\|/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3); print $3; exit}' "$FILE"; }
[[ "$(git rev-parse "$COMMIT^")" == "$PARENT" ]] || { echo "ERROR: the commit parent is not the recorded start commit"; exit 1; }
VER=".auto-pm/reports/m3-rel72b/gates/gate_verdict.json"
"$PY" -B .auto-pm/reports/m2-tools/verdict_check.py "$VER" "$ROOT" "CARD-SW008-M3-REL72 V1.1" "$PARENT" RUN-SW008-M3-REL72-003 G1 G2 G3 G4 G5 G6 G7 G8 G9 || { echo "ERROR: verdict condition not met"; exit 1; }
DELEG="用户阅读结果并在对话中确认验收后收口（验收由用户做出，不是委托验收）；由 Claude 代为运行脚本；G1～G9 全部通过且提交与冻结文件一致已核验"
while true; do
  case "$(st)" in
    implementing)       cli change transition "$CHG" --pid SW-2026-008 --to pending_acceptance --approver fubai --comment "[$DELEG] 实施提交已形成" >/dev/null ;;
    pending_acceptance) cli change transition "$CHG" --pid SW-2026-008 --to accepting --approver fubai --comment "[$DELEG] 开始验收" >/dev/null ;;
    accepting)          cli change transition "$CHG" --pid SW-2026-008 --to completed --approver fubai --allow-partial-verification \
      --verification-conclusion "用户阅读结果后验收通过并收口（这不是委托验收）。卡 221 V1.1（SHA-256 $CARD_SHA；SHA 已先在聊天报出，其后卡字节未变）：提交 $COMMIT（父 ${PARENT:0:8}，本地分支 claude/m3-rel72b，1 个文件）；Checkpoint 绑定冻结字节，Run SUCCEEDED、Work CLOSED；G1～G9 全部通过且提交与冻结清单一致；不推送、不打 tag、不处置任何债务或历史失败记录" >/dev/null ;;
    completed)          break ;;
    *) echo "ERROR: CHG in non-resumable state: $(st)"; exit 1 ;;
  esac
done
cli ledger reconcile SW-2026-008 | grep 摘要
cli ledger reconcile SYS-2026-001 | grep 摘要
echo "REL72_CHG_CLOSED $CHG"
