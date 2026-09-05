"""PLC-HMI 概念映射：HMI 变量表（Spec 域）

像 HMI 触摸屏的变量表，定义了 QML 画面能访问的所有规范检查相关变量和方法：
- @Slot 方法 = HMI 按钮触发的脚本（规范检查/索引/Frontmatter/报告）
- Signal = HMI 变量变化事件（检查结果变了自动刷新画面）

--- 原始注释 ---
Spec Bridge (QML)

M4 第 1 批重构：3 个 Slot 改用 dataclasses.asdict() 转换 DTO 为 dict 给 QML。
"""

import logging
from dataclasses import asdict
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from auto_pm.application.spec_facade import SpecFacade

logger = logging.getLogger(__name__)


class SpecBridge(QObject):
    specCheckCompleted = Signal(int, int, int)  # error_count, warning_count, info_count

    def __init__(self, facade: SpecFacade | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._facade = facade

    def set_facade(self, facade: SpecFacade | None) -> None:
        self._facade = facade

    @Property(bool, constant=True)
    def hasService(self) -> bool:
        return self._facade is not None

    @Slot(str, result="QVariant")
    @Slot(result="QVariant")
    def runSpecCheck(self, project_id: str = "") -> dict[str, Any]:
        if self._facade:
            res = self._facade.run_spec_check(project_id)
            if res.success and res.payload:
                payload = asdict(res.payload)
                self.specCheckCompleted.emit(
                    payload.get("error_count", 0),
                    payload.get("warning_count", 0),
                    payload.get("info_count", 0),
                )
                return payload
            return {"error_count": -1, "message": res.message}
        return {"error_count": -1, "message": "未初始化"}

    @Slot(str, result="QVariant")
    def repairSpec(self, project_id: str) -> dict[str, Any]:
        if self._facade:
            res = self._facade.run_spec_repair(project_id)
            if res.success and res.payload is not None:
                return {"success": True, "message": res.message, "payload": res.payload}
            return {"success": False, "message": res.message}
        return {"success": False, "message": "未初始化"}

    @Slot(result="QVariant")
    def getSpecOverview(self) -> dict[str, Any]:
        if self._facade:
            res = self._facade.get_spec_center_overview()
            if res.success and res.payload:
                return asdict(res.payload)
        return {}

    @Slot(str, result=list)
    def listSpecEntries(self, filter_domain: str = "") -> list[Any]:
        if self._facade:
            domain = filter_domain if filter_domain else None
            res = self._facade.list_spec_center_entries(domain)
            if res.success and res.payload:
                return [asdict(e) for e in res.payload]
        return []

    @Slot(str, result="QVariant")
    def generateSpecIndex(self, domain: str = "all") -> dict[str, Any]:
        """生成规范索引（M5 CHG-119 新增）

        Args:
            domain: "all" 生成全部（pm/plc/python），或 "pm"/"plc"/"python" 指定单域

        Returns:
            索引生成结果 dict（含 domain/generated_files/errors）或
            {"success": False, "message": ...}
        """
        if self._facade:
            res = self._facade.generate_spec_index(domain)
            if res.success and res.payload is not None:
                return asdict(res.payload)
            return {"success": res.success, "message": res.message}
        return {"success": False, "message": "未初始化"}

    @Slot(str, result="QVariant")
    def generateSpecReport(self, fmt: str = "markdown") -> dict[str, Any]:
        """生成规范报告（M5 CHG-120 新增）

        Args:
            fmt: 报告格式，"markdown" 或 "json"

        Returns:
            报告生成结果 dict（含 fmt/output_path/content/file_size）或
            {"success": False, "message": ...}
        """
        if self._facade:
            res = self._facade.generate_spec_report(fmt)
            if res.success and res.payload is not None:
                return asdict(res.payload)
            return {"success": res.success, "message": res.message}
        return {"success": False, "message": "未初始化"}

    @Slot(bool, result="QVariant")
    def checkSpecFrontmatter(self, autoFix: bool = False) -> dict[str, Any]:
        """检查/修复规范 Frontmatter（M5 CHG-121 新增）

        Args:
            autoFix: True 时自动添加缺失的 frontmatter

        Returns:
            检查结果 dict（含 items/total_count/pending_count/skipped_count/
            error_count/modified_count/auto_fixed）或
            {"success": False, "message": ...}
        """
        if self._facade:
            res = self._facade.check_spec_frontmatter(auto_fix=autoFix)
            if res.success and res.payload is not None:
                return asdict(res.payload)
            return {"success": res.success, "message": res.message}
        return {"success": False, "message": "未初始化"}

    @Slot(str, str, result="QVariant")
    def generateSclFromMatrix(self, md_text: str, output_path: str) -> dict[str, Any]:
        """根据 Markdown 工艺矩阵离线生成 Siemens SCL 状态机源码"""
        try:
            from auto_pm.plc.generator import ProcessMatrixParser, SclGenerator

            matrix = ProcessMatrixParser.parse_markdown(md_text)
            gen = SclGenerator()
            out_file = gen.generate_to_file(matrix, output_path)
            return {
                "success": True,
                "output_path": str(out_file),
                "steps_count": len(matrix.steps),
                "message": f"离线生成合规 SCL 成功: {out_file.name}",
            }
        except Exception as exc:
            logger.warning("generateSclFromMatrix failed: %s", exc, exc_info=True)
            return {"success": False, "message": f"生成 SCL 失败: {exc}"}

    @Slot(str, result="QVariant")
    def checkSclCodeCompliance(self, file_path: str) -> dict[str, Any]:
        """对单个 .scl 文件按 LSP-905 运行代码规范排查"""
        try:
            from auto_pm.plc.scl_linter import SclLinter

            report = SclLinter.lint_file(file_path)
            violations_data = [
                {
                    "line": v.line_number,
                    "rule": v.rule_id,
                    "severity": v.severity,
                    "message": v.message,
                    "snippet": v.code_snippet,
                }
                for v in report.violations
            ]
            return {
                "success": True,
                "is_clean": report.is_clean,
                "file_path": report.file_path,
                "total_violations": report.total_violations,
                "errors_count": report.errors_count,
                "warnings_count": report.warnings_count,
                "violations": violations_data,
            }
        except Exception as exc:
            logger.warning("checkSclCodeCompliance failed: %s", exc, exc_info=True)
            return {"success": False, "message": f"SCL 规范排查失败: {exc}"}

    @Slot(result="QVariant")
    def syncObsidian(self) -> dict[str, Any]:
        """一键全量同步与重构 Obsidian 全局规范仓库 (DEV-030 V2.2.0)"""
        if self._facade:
            res = self._facade.sync_obsidian_repository()
            return {"success": res.success, "message": res.message, "payload": res.payload}
        return {"success": False, "message": "SpecFacade 未初始化"}
