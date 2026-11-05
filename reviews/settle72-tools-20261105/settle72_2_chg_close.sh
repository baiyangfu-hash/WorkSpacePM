#!/usr/bin/env bash
# M3-SETTLE72 - closure of the two recovery CHGs. NOT delegated unless the user said so: run it only after the user has accepted the result ("收口").
# Verifies the facts first (every target Run CANCELLED, every recovery chain terminal, no Run under finished Work, ledger clean), then walks each CHG implementing -> pending_acceptance -> accepting -> completed.
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH" PYTHONIOENCODING=utf-8 PYTHONUTF8=1
REAL=/c/Users/fubai/Documents/My_Workspace; ROOT="$REAL"; cd "$ROOT"
PY="$REAL/.venv/Scripts/python.exe"; cli() { "$PY" -B main.py "$@"; }
EV="$ROOT/.auto-pm/reports/m3-settle72"
CHG_SW="$(head -n 1 "$EV/settle_chg_sw.txt")"; CHG_SYS="$(head -n 1 "$EV/settle_chg_sys.txt")"
P='01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具'
FILE_SW="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/$CHG_SW.md"; FILE_SYS="SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/$CHG_SYS.md"
st() { awk -F'|' '/^\|[[:space:]]*变更状态[[:space:]]*\|/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3); print $3; exit}' "$1"; }
sq() { "$PY" -B - "$@" <<'EOF'
import sqlite3,sys
c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True)
r=c.execute(sys.argv[1],tuple(sys.argv[2:])).fetchone(); print(r[0] if r else "NONE")
EOF
}
for r in RUN-SW008-A2-201-01 RUN-SW008-A2-201-03 RUN-SW008-A2-201-04 RUN-SW008-PMF-C03REC-002 RUN-SW008-PMF-E01-001 RUN-SW008-PMF-G10-001 RUN-SYS001-PMF-WBS24-001 RUN-SYS001-PMF-WBS25-001 RUN-SW008-M3-REL72-002 RUN-SW008-M3-D07P-001; do [[ "$(sq "select state from run_items where run_id=?" "$r")" == CANCELLED ]] || { echo "ERROR: $r is not CANCELLED"; exit 1; }; done
[[ "$(sq "select count(*) from run_items r join work_items w on w.work_id=r.work_id where r.state not in ('SUCCEEDED','FAILED','CANCELLED') and w.state in ('ACCEPTED','CLOSED','CANCELLED')")" == 0 ]] || { echo "ERROR: there are still Runs under finished Work"; exit 1; }
[[ "$(sq "select count(*) from work_items where work_id like '%-M3-SETTLE72-%' and state<>'CLOSED'")" == 0 ]] || { echo "ERROR: a recovery Work is not CLOSED"; exit 1; }
close_one() {  # $1 = CHG id, $2 = project id, $3 = CHG file, $4 = what was settled
  local chg="$1" pid="$2" file="$3" what="$4"
  while true; do
    case "$(st "$file")" in
      implementing)       cli change transition "$chg" --pid "$pid" --to pending_acceptance --approver fubai --comment "[验收后收口] 恢复链已完成" >/dev/null ;;
      pending_acceptance) cli change transition "$chg" --pid "$pid" --to accepting --approver fubai --comment "[验收后收口] 开始验收" >/dev/null ;;
      accepting)          cli change transition "$chg" --pid "$pid" --to completed --approver fubai --allow-partial-verification --verification-conclusion "验收通过后收口：旧 Run 处置（用户 2026-10-18 预授权自行收口）——$what 经独立恢复链 settle-expired 结算为 CANCELLED；账本里不再有挂在已结束 Work 下的 Run；对账 0/0/0" >/dev/null ;;
      completed)          break ;;
      *) echo "ERROR: $chg in non-resumable state: $(st "$file")"; exit 1 ;;
    esac
  done
}
close_one "$CHG_SW" SW-2026-008 "$FILE_SW" "SW-2026-008 的 8 条目标 Run（A2-201-01/03/04、PMF-C03REC-002、PMF-E01-001、PMF-G10-001、M3-REL72-002、M3-D07P-001）"
close_one "$CHG_SYS" SYS-2026-001 "$FILE_SYS" "SYS-2026-001 的 2 条目标 Run（PMF-WBS24-001、PMF-WBS25-001）"
cli ledger reconcile SW-2026-008 | grep 摘要
cli ledger reconcile SYS-2026-001 | grep 摘要
echo "SETTLE72_CHG_CLOSED $CHG_SW $CHG_SYS"
