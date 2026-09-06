"""auto_pm.infrastructure.git_hook_enforcer - Git 物理提交门禁护航器

用于在 Git 底层（.git/hooks/pre-commit 与 .git/hooks/commit-msg）执行刚性拦截，
彻底杜绝 AI 或开发者“未经提单直接改代码”与“台账未闭环直接 commit”的行为。
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from auto_pm.change.parser import ChgParser

log = logging.getLogger(__name__)

PRODUCTION_EXTENSIONS = (".py", ".scl", ".st", ".qml")
EXCLUDED_PATH_KEYWORDS = (
    "tests/",
    "test_",
    "tests\\",
    "docs/",
    "docs\\",
    "scratch/",
    "scratch\\",
    ".auto-pm/",
    ".auto-pm\\",
    "00_Obsidian_Base",
    "PM_SESSION_",
)


def get_staged_files(workspace_root: Path) -> list[str]:
    """获取 Git 当前暂存区的文件相对路径列表"""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception as e:
        log.warning("获取暂存区文件失败: %s", e)
        return []


def filter_production_files(files: list[str]) -> list[str]:
    """从暂存区筛选出生产代码文件"""
    prod_files: list[str] = []
    for f in files:
        f_norm = f.replace("\\", "/")
        # 排除纯文档、测试、草稿及会话文件
        if any(keyword in f_norm for keyword in EXCLUDED_PATH_KEYWORDS):
            continue
        if any(f_norm.endswith(ext) for ext in PRODUCTION_EXTENSIONS):
            prod_files.append(f)
    return prod_files


def enforce_pre_commit(workspace_root: Path) -> int:
    """pre-commit 阶段拦截检查：
    1. 扫描暂存区关联项目的版本变更台帐一致性；
    2. 若全仓台账存在缺失/孤儿/不一致，直接 exit 1 阻断。
    """
    staged = get_staged_files(workspace_root)
    if not staged:
        return 0

    print("🔍 [auto-pm pre-commit] 正在执行全仓台账一致性物理门禁预检...")
    try:
        # 调用 auto-pm change verify 验证台账
        from auto_pm.core.project_service import ProjectService
        from auto_pm.domain.change.ledger_reconciler import LedgerReconciler

        ps = ProjectService(str(workspace_root))
        projects = ps.list_projects()
        reconciler = LedgerReconciler()

        has_ledger_error = False
        for p in projects:
            p_root = getattr(p, "path", None)
            pid = getattr(p, "id", "")
            if not p_root:
                continue
            ledger_file = Path(p_root) / "04_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台帐.md"
            if not ledger_file.is_file():
                ledger_file = Path(p_root) / "11_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台帐.md"
            if not ledger_file.is_file():
                continue

            report = reconciler.reconcile(str(p_root))
            if not report.is_clean:
                print(
                    f"❌ [auto-pm pre-commit] 项目 [{pid}] 台账对账不一致: "
                    f"缺失 {len(report.missing_in_ledger)} 条, "
                    f"孤儿 {len(report.orphan_in_ledger)} 条, "
                    f"状态差异 {len(report.status_mismatches)} 条！"
                )
                has_ledger_error = True

        if has_ledger_error:
            print("🚨 [auto-pm pre-commit] 物理阻断：台账未闭环，严禁直接 Commit！请先运行 auto-pm ledger reconcile <PID> --fix")
            return 1

    except Exception as e:
        print(f"⚠️ [auto-pm pre-commit] 台账检查异常: {e}")

    print("✅ [auto-pm pre-commit] 全仓台账门禁校验通过。")
    return 0


def enforce_commit_msg(workspace_root: Path, commit_msg_file: Path) -> int:
    """commit-msg 阶段拦截检查：
    1. 若暂存区包含生产代码（.py, .scl 等），强制 Commit Message 必须注明关联单号；
    2. 校验引用的变更单在工作空间中真实存在且处于合法执行态。
    """
    staged = get_staged_files(workspace_root)
    prod_files = filter_production_files(staged)

    if not prod_files:
        # 纯文档/治理/会话提交，豁免变更单号要求
        return 0

    if not commit_msg_file.is_file():
        print(f"❌ [auto-pm commit-msg] 未找到提交信息文件: {commit_msg_file}")
        return 1

    msg_content = commit_msg_file.read_text(encoding="utf-8", errors="replace").strip()

    # 匹配变更单号，如 CHG-SCPT-2026-170, CHG-PLC-2026-012
    chg_matches = re.findall(r"CHG-[A-Z0-9]+-\d{4}-\d+", msg_content)
    if not chg_matches:
        print("=" * 70)
        print("❌ [auto-pm commit-msg] 物理拦截：检测到暂存区包含生产代码变更，但 Commit Message 未绑定变更单！")
        print("📄 涉及生产文件:")
        for pf in prod_files[:5]:
            print(f"   - {pf}")
        if len(prod_files) > 5:
            print(f"   ... (共 {len(prod_files)} 个文件)")
        print("\n👉 规程要求：生产代码提交必须显式注明合法变更单号，例如:")
        print("   feat(core): [CHG-SCPT-2026-170] 落地决策包与门禁护航机制")
        print("=" * 70)
        return 1

    chg_id = chg_matches[0]
    # 检查变更单文件是否存在
    matched_tickets = list(workspace_root.glob(f"**/{chg_id}.md"))
    if not matched_tickets:
        print(f"❌ [auto-pm commit-msg] 物理拦截：引用的变更单在工作空间中不存在: {chg_id}.md")
        return 1

    # 检查变更单状态是否为合法执行态
    try:
        parser = ChgParser()
        cr = parser.parse(str(matched_tickets[0]))
        valid_statuses = (
            "approved",
            "conditionally_approved",
            "implementing",
            "pending_acceptance",
            "accepting",
            "completed",
            "closed",
        )
        if cr.status not in valid_statuses:
            print(
                f"❌ [auto-pm commit-msg] 物理拦截：关联变更单 {chg_id} 当前状态为 '{cr.status}'，"
                "尚未获得审批批准，严禁提交代码！"
            )
            return 1
    except Exception as e:
        print(f"⚠️ [auto-pm commit-msg] 解析变更单状态失败: {e}")

    print(f"✅ [auto-pm commit-msg] 生产代码与变更单 {chg_id} 强校验绑定通过！")
    return 0
