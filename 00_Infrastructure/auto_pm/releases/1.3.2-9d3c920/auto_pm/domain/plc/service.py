"""PLC-HMI 概念映射：SFB 库函数（PLC 项目服务（初始化/检查/修复 PLC 项目））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

PLC Service - 封装 PlcChecker/PlcRepairer/SubstanceChecker（M3-Iter4）

提供统一的 PLC 项目检查/修复/标准化入口，实现 PlcServiceProtocol。
UI/CLI 层通过 PlcService 操作 PLC 项目，不直接访问 PlcChecker/PlcRepairer。

职责：
- check: 综合检查（结构 + 文档实质化）
- repair: 修复结构问题
- standardize: 标准化文档命名
- check_substance: 文档实质化检查（V2.0.1-B）
"""

from __future__ import annotations

import logging
import os

from auto_pm.plc.checker import PlcChecker
from auto_pm.plc.models import CheckResult, RepairResult, StandardizeResult
from auto_pm.plc.repairer import PlcRepairer
from auto_pm.plc.substance_checker import SubstanceChecker

log = logging.getLogger(__name__)


class PlcService:
    """PLC 项目服务 - 封装 PlcChecker/PlcRepairer/SubstanceChecker

    实现 PlcServiceProtocol（无需显式继承）。
    UI/CLI 层通过本服务操作 PLC 项目，遵循分层架构。
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self._checker = PlcChecker(self.workspace_root)
        self._repairer = PlcRepairer(self.workspace_root)
        self._substance_checker = SubstanceChecker(self.workspace_root)

    def check(self, project_path: str, fix: bool = False) -> CheckResult:
        """检查 PLC 项目规范性

        Args:
            project_path: 项目根目录绝对路径
            fix: True 时检查后自动修复（非破坏性）

        Returns:
            CheckResult: 检查结果
        """
        log.info("检查 PLC 项目: %s (fix=%s)", project_path, fix)
        result = self._checker.check_project(project_path)

        if fix and result.fail_count > 0:
            log.info("检查发现问题，自动修复中: %s", project_path)
            self._repairer.repair_project(project_path, dry_run=False)
            # 修复后重新检查
            result = self._checker.check_project(project_path)

        return result

    def repair(
        self,
        project_path: str,
        dry_run: bool = False,
        rename_confirm: bool = False,
    ) -> RepairResult:
        """修复 PLC 项目规范问题

        Args:
            project_path: 项目根目录绝对路径
            dry_run: 仅预览不执行
            rename_confirm: 是否确认文件重命名（破坏性操作）

        Returns:
            RepairResult: 修复结果
        """
        log.info(
            "修复 PLC 项目: %s (dry_run=%s, rename_confirm=%s)",
            project_path, dry_run, rename_confirm,
        )
        return self._repairer.repair_project(
            project_path,
            dry_run=dry_run,
            rename_confirm=rename_confirm,
        )

    def standardize(
        self,
        project_path: str,
        dry_run: bool = False,
    ) -> StandardizeResult:
        """标准化 PLC 项目文档命名

        Args:
            project_path: 项目根目录绝对路径
            dry_run: True 仅预览，False 执行重命名

        Returns:
            StandardizeResult: 标准化结果
        """
        log.info("标准化 PLC 项目文档: %s (dry_run=%s)", project_path, dry_run)
        return self._repairer.standardize_docs(
            project_path, apply=not dry_run
        )

    def check_substance(self, project_path: str) -> CheckResult:
        """文档实质化检查（V2.0.1-B）

        检查 PRD/DSN/INT/TEC 文档字数、章节数、占位符，
        识别"占位文档"（仅有标题无实质内容）。

        Args:
            project_path: 项目根目录绝对路径

        Returns:
            CheckResult: 实质化检查结果
        """
        log.info("文档实质化检查: %s", project_path)
        return self._substance_checker.check_project(project_path)

    def check_workspace(self) -> list[CheckResult]:
        """检查工作空间内所有 PLC 项目

        Returns:
            所有 PLC 项目的检查结果列表
        """
        log.info("检查工作空间所有 PLC 项目: %s", self.workspace_root)
        return self._checker.check_workspace()
