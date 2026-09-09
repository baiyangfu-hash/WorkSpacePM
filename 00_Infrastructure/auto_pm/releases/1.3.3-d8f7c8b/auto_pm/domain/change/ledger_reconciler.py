"""PLC-HMI 概念映射：SFB 库函数（台账对账器（比对文件系统与数据库中的变更单））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

台账对账器（CHG-108 缺陷 1 修复）

扫描 01_变更单/ 所有 CHG-*.md 文件 vs 版本变更台账记录，输出 diff 报告
+ 自动补建缺失行 + 修复状态不一致。

三类差异：
  - missing_in_ledger: CHG 文件存在但台账无记录（需补建）
  - orphan_in_ledger:  台账有记录但 CHG 文件不存在（孤儿记录，人工审核）
  - status_mismatches: CHG 状态 vs 台账状态不一致（需修正）

设计要点：
  - 只读 reconcile() 不修改任何文件，仅返回 ReconcileDiff
  - auto_fix() 执行补建 + 状态修正（孤儿记录不自动删除，保留人工审核）
  - 复用 ChgParser 解析 CHG 元信息（applicant/apply_date/status/background）
  - 复用 LedgerUpdater.update()/update_status() 写入台账
  - 复用 LEDGER_STATUS_MAP 保持状态文案一致性
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from auto_pm.change.constants import LEDGER_STATUS_MAP, ChangeRequest
from auto_pm.change.ledger_updater import LedgerUpdater
from auto_pm.change.parser import ChgParser
from auto_pm.change.path_resolver import (
    find_ledger_file,
    get_or_create_ledger_file,
    scan_change_files,
)
from auto_pm.utils.file_utils import read_file

log = logging.getLogger(__name__)


@dataclass
class ReconcileDiff:
    """对账差异报告"""

    # CHG 文件存在但台账无记录的变更编号列表
    missing_in_ledger: list[str] = field(default_factory=list)
    # 台账有记录但 CHG 文件不存在的变更编号列表（孤儿记录）
    orphan_in_ledger: list[str] = field(default_factory=list)
    # 状态不一致：(change_number, chg_期望状态文案, ledger_实际状态文案)
    status_mismatches: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """对账无差异"""
        return (
            not self.missing_in_ledger
            and not self.orphan_in_ledger
            and not self.status_mismatches
        )

    def summary(self) -> str:
        """生成对账摘要文本"""
        return (
            f"台账缺失: {len(self.missing_in_ledger)} 条, "
            f"台账多余(孤儿): {len(self.orphan_in_ledger)} 条, "
            f"状态不一致: {len(self.status_mismatches)} 条"
        )


# 变更编号正则（与 path_resolver._CHANGE_NUMBER_PATTERN 对齐）
_CHANGE_NUMBER_RE = re.compile(r"CHG-[A-Z]+-\d{4}-\d{3}")


class LedgerReconciler:
    """台账对账器（CHG-108 缺陷 1 修复）

    用法：
        reconciler = LedgerReconciler()
        diff = reconciler.reconcile(project_path)   # 只读扫描
        if not diff.is_clean:
            reconciler.auto_fix(project_path, diff)  # 自动修复
    """

    def __init__(
        self,
        parser: ChgParser | None = None,
        updater: LedgerUpdater | None = None,
    ) -> None:
        self._parser = parser or ChgParser()
        self._updater = updater or LedgerUpdater()

    def reconcile(self, project_path: str) -> ReconcileDiff:
        """扫描对账，返回差异报告（不修改任何文件）

        Args:
            project_path: 项目根目录

        Returns:
            ReconcileDiff 差异报告；未找到台账时返回空 diff
        """
        # 扫描 CHG 文件并解析元信息
        chg_files = scan_change_files(project_path)

        ledger_path = find_ledger_file(project_path)
        if not ledger_path:
            if not chg_files:
                # 既没有台账，也没有变更单文件，说明未启用变更管理，是正常干净的状态
                return ReconcileDiff()

            # 有变更单文件但没有台账文件，说明变更已启用但台账丢失，生成“所有变更均缺失于台账”的差异
            log.warning("对账失败: 未找到台账文件 (project=%s)", project_path)
            chg_meta: dict[str, ChangeRequest] = {}
            for fp in chg_files:
                cr = self._parser.parse(fp)
                if cr.change_number:
                    chg_meta[cr.change_number] = cr
            diff = ReconcileDiff()
            diff.missing_in_ledger = sorted(chg_meta.keys())
            return diff

        chg_meta = {}
        for fp in chg_files:
            cr = self._parser.parse(fp)
            if cr.change_number:
                chg_meta[cr.change_number] = cr

        chg_numbers = set(chg_meta.keys())
        ledger_numbers = self._parse_ledger_numbers(ledger_path)
        ledger_status_map = self._parse_ledger_status_map(ledger_path)

        diff = ReconcileDiff()
        diff.missing_in_ledger = sorted(chg_numbers - ledger_numbers)
        diff.orphan_in_ledger = sorted(ledger_numbers - chg_numbers)

        # 状态一致性比对（仅对双方都存在的变更编号）
        for cn in sorted(chg_numbers & ledger_numbers):
            cr = chg_meta[cn]
            expected = LEDGER_STATUS_MAP.get(cr.status, "")
            actual = ledger_status_map.get(cn, "")
            if expected and actual and expected != actual:
                diff.status_mismatches.append((cn, expected, actual))

        log.info(
            "对账完成: %s — %s",
            project_path,
            diff.summary(),
        )
        return diff

    def auto_fix(self, project_path: str, diff: ReconcileDiff | None = None) -> ReconcileDiff:
        """自动修复差异

        - 缺失行：调用 LedgerUpdater.update 补建，并按 CHG 实际状态修正（非默认"待处理"）
        - 状态不一致：调用 LedgerUpdater.update_status 修正
        - 孤儿记录：不自动删除（保留人工审核），仅报告

        Args:
            project_path: 项目根目录
            diff: 预计算的差异报告；None 时自动调用 reconcile()

        Returns:
            修复前的差异报告（用于日志/展示）
        """
        if diff is None:
            diff = self.reconcile(project_path)

        if diff.is_clean:
            log.info("对账无差异，无需修复")
            return diff

        ledger_path = get_or_create_ledger_file(project_path)
        if not ledger_path:
            log.warning("自动修复失败: 无法创建或未找到台账文件 (project=%s)", project_path)
            return diff

        # 重新解析 CHG 元信息（auto_fix 可能被独立调用，diff 来自外部）
        chg_meta: dict[str, ChangeRequest] = {}
        if diff.missing_in_ledger or diff.status_mismatches:
            for fp in scan_change_files(project_path):
                parsed_cr = self._parser.parse(fp)
                if parsed_cr.change_number:
                    chg_meta[parsed_cr.change_number] = parsed_cr

        # 1. 补建缺失行
        for cn in diff.missing_in_ledger:
            chg_cr = chg_meta.get(cn)
            if not chg_cr:
                log.warning("补建跳过: 未找到 CHG 文件元信息 %s", cn)
                continue
            desc = (
                chg_cr.background[:50] + "..." if len(chg_cr.background) > 50 else chg_cr.background
            ) or cn
            self._updater.update(
                ledger_path,
                cn,
                desc,
                applicant=chg_cr.applicant,
                apply_date=chg_cr.apply_date,
            )
            # 补建后默认状态为"🔄待处理"，若 CHG 实际状态非 draft，需修正
            expected_status = LEDGER_STATUS_MAP.get(chg_cr.status, "🔄待处理")
            if expected_status != "🔄待处理":
                complete_date = ""
                if chg_cr.status in ("completed", "closed", "archived"):
                    complete_date = date.today().isoformat()
                self._updater.update_status(
                    ledger_path,
                    cn,
                    expected_status,
                    complete_date=complete_date,
                    applicant=chg_cr.applicant,
                    apply_date=chg_cr.apply_date,
                )
            log.info("已补建台账缺失行: %s (状态=%s)", cn, expected_status)

        # 2. 修复状态不一致
        for cn, expected, _actual in diff.status_mismatches:
            chg_cr = chg_meta.get(cn)
            complete_date = ""
            if chg_cr and chg_cr.status in ("completed", "closed", "archived"):
                complete_date = date.today().isoformat()
            self._updater.update_status(
                ledger_path,
                cn,
                expected,
                complete_date=complete_date,
                applicant=chg_cr.applicant if chg_cr else "",
                apply_date=chg_cr.apply_date if chg_cr else "",
            )
            log.info("已修正状态不一致: %s → %s", cn, expected)

        log.info(
            "自动修复完成: 补建 %d 条, 状态修正 %d 条（孤儿记录 %d 条保留人工审核）",
            len(diff.missing_in_ledger),
            len(diff.status_mismatches),
            len(diff.orphan_in_ledger),
        )
        return diff

    def _parse_ledger_numbers(self, ledger_path: str) -> set[str]:
        """从台账解析所有变更编号集合"""
        content = read_file(ledger_path)
        if not content:
            return set()
        return set(_CHANGE_NUMBER_RE.findall(content))

    def _parse_ledger_status_map(self, ledger_path: str) -> dict[str, str]:
        """从台账解析 {变更编号: 状态文案}

        状态列是表格行的最后一个内容列。
        """
        content = read_file(ledger_path)
        if not content:
            return {}
        result: dict[str, str] = {}
        in_index = False
        for line in content.split("\n"):
            stripped = line.strip()
            if "变更单索引" in stripped:
                in_index = True
                continue
            if not in_index:
                continue
            if not stripped.startswith("|"):
                if stripped:
                    in_index = False
                continue
            # 跳过表头和分隔行
            if stripped.startswith("| 序号") or re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            m = _CHANGE_NUMBER_RE.search(stripped)
            if not m:
                continue
            cn = m.group(0)
            parts = [p.strip() for p in stripped.split("|") if p.strip()]
            if parts:
                result[cn] = parts[-1]
        return result
