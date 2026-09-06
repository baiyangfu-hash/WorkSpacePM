"""PLC-HMI 概念映射：HMI 变量表（System 域）

像 HMI 触摸屏的变量表，定义了 QML 画面能访问的所有系统设置相关变量和方法：
- @Slot 方法 = HMI 按钮触发的脚本（PM_SESSION 管理/模板管理/全局设置）
- Signal = HMI 变量变化事件（数据变了自动刷新画面）

--- 原始注释 ---
System Bridge (QML)

M4 第 2 批重构：3 个 Slot 改用 dataclasses.asdict() 转换 DTO 为 dict 给 QML。
listTemplates 返回 list[str]、getTemplatePath 返回 str，保持基础类型。
新增 1 个 Slot：applyTemplate（QML 端尚未接入，TODO M5）。
M5 CHG-117 新增 1 个 Slot：archivePmSession（PM_SESSION 归档对话框接入）。
"""
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Slot

from auto_pm.application.system_facade import SystemFacade

logger = logging.getLogger(__name__)


class SystemBridge(QObject):

    def __init__(self, facade: SystemFacade | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._facade = facade

    def set_facade(self, facade: SystemFacade | None) -> None:
        self._facade = facade

    @Property(bool, constant=True)
    def hasService(self) -> bool:
        return self._facade is not None

    @Slot(result=list)
    def listTemplates(self) -> list[str]:
        if self._facade:
            res = self._facade.list_templates()
            if res.success and res.payload is not None:
                return res.payload
        return []

    @Slot(str, result=str)
    def getTemplatePath(self, template_name: str) -> str:
        if self._facade:
            res = self._facade.get_template_path(template_name)
            if res.success and res.payload is not None:
                return res.payload
        return ""

    @Slot(str, result="QVariant")
    def getTemplateDetail(self, template_name: str) -> dict[str, Any]:
        if self._facade:
            res = self._facade.get_template_detail(template_name)
            if res.success and res.payload:
                return asdict(res.payload)
        return {}

    @Slot(result="QVariant")
    def getPmSessionView(self) -> dict[str, Any]:
        if self._facade:
            res = self._facade.get_pm_session_view()
            if res.success and res.payload:
                return asdict(res.payload)
        return {}

    @Slot(result="QVariant")
    def runPmSessionCheck(self) -> dict[str, Any]:
        if self._facade:
            res = self._facade.run_pm_session_check()
            if res.success and res.payload:
                return asdict(res.payload)
            return {"success": False, "message": res.message}
        return {"success": False, "message": "未初始化"}

    @Slot(str, str, result="QVariant")
    def applyTemplate(self, project_id: str, template_name: str) -> dict[str, Any]:
        # TODO M5 (TD-M5-02): QML 端接入模板应用对话框（TemplateApplyDialog），
        # 让用户选择模板并应用到指定项目。当前 Slot 仅暴露接口。
        # 已登记技术债：006_技术债评估报告.md §TD-M5-02
        if self._facade:
            res = self._facade.apply_template(project_id, template_name)
            if res.success and res.payload:
                return asdict(res.payload)
            return {"success": res.success, "message": res.message}
        return {"success": False, "message": "未初始化"}

    @Slot(str, int, bool, result="QVariant")
    def archivePmSession(self, section: str, keepRecent: int, dryRun: bool) -> dict[str, Any]:
        # M5 CHG-117: QML 端接入 PM_SESSION 归档对话框
        if self._facade:
            res = self._facade.archive_pm_session(section, keepRecent, dryRun)
            if res.success and res.payload:
                return asdict(res.payload)
            return {"success": res.success, "message": res.message}
        return {"success": False, "message": "未初始化"}

    @Slot(result="QVariant")
    def runDoctorCheck(self) -> dict[str, Any]:
        """执行 GUI 一键环境健康自检"""
        from auto_pm.cli.doctor import run_doctor_check
        try:
            return dict(run_doctor_check())
        except Exception as e:
            logger.warning("runDoctorCheck failed: %s", e, exc_info=True)
            return {"all_passed": False, "message": str(e)}

    @Slot(result="QVariant")
    def syncDocs(self) -> dict[str, Any]:
        """执行 Doc-as-Code 文档自省自动同步"""
        try:
            from auto_pm.domain.doc.services import DocSyncService
            ws = Path(os.getcwd())
            svc = DocSyncService(ws)
            logs = svc.sync_all()
            return {"success": True, "logs": logs, "message": f"成功同步 {len(logs)} 个文档锚点"}
        except Exception as e:
            logger.warning("syncDocs failed: %s", e, exc_info=True)
            return {"success": False, "logs": [], "message": str(e)}

    @Slot(result="QVariant")
    def checkDocs(self) -> dict[str, Any]:
        """执行 Doc-as-Code 文档一致性门禁检查"""
        try:
            from auto_pm.domain.doc.services import DocCheckService
            ws = Path(os.getcwd())
            svc = DocCheckService(ws)
            results = svc.check_all()
            all_passed = all(r.passed for r in results)
            return {
                "success": all_passed,
                "items": [{"check_id": r.check_id, "name": r.name, "passed": r.passed, "message": r.message} for r in results],
                "message": "所有文档门禁通过" if all_passed else "存在文档未同步滞后项"
            }
        except Exception as e:
            logger.warning("checkDocs failed: %s", e, exc_info=True)
            return {"success": False, "items": [], "message": str(e)}
