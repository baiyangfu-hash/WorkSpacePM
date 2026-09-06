"""PLC-HMI 概念映射：HMI 变量表（Change 域）

像 HMI 触摸屏的变量表，定义了 QML 画面能访问的所有变更管理相关变量和方法：
- @Slot 方法 = HMI 按钮触发的脚本（创建/编辑/审批变更单）
- Signal = HMI 变量变化事件（变更单数据变了自动刷新画面）

--- 原始注释 ---
Change Bridge (QML)"""
import dataclasses
import logging
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from auto_pm.application.change_facade import ChangeFacade
from auto_pm.ui.contracts.commands.change_commands import (
    CreateChangeCommand,
    TransitionChangeCommand,
)

logger = logging.getLogger(__name__)


class ChangeBridge(QObject):
    changesChanged = Signal()

    def __init__(self, facade: ChangeFacade | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._changes_cache: list[Any] = []
        self._change_detail_cache: dict[str, Any] = {}

    def set_facade(self, facade: ChangeFacade | None) -> None:
        self._facade = facade
        self._changes_cache = []
        self._change_detail_cache = {}
        self.changesChanged.emit()

    @Property(bool, notify=changesChanged)
    def hasService(self) -> bool:
        return self._facade is not None

    @Property(int, notify=changesChanged)
    def changeCount(self) -> int:
        """变更单数量（只读属性，供 QML 绑定使用，避免绑定循环）"""
        return len(self._changes_cache)

    @Slot(result=list)
    def listAllChanges(self) -> list[Any]:
        if self._changes_cache:
            return self._changes_cache
        if self._facade:
            res = self._facade.list_change_requests()
            if res.success and res.payload is not None:
                self._changes_cache = [dataclasses.asdict(c) for c in res.payload]
                self.changesChanged.emit()
                return self._changes_cache
        return []

    @Slot(str, result=list)
    def listChanges(self, project_id: str) -> list[Any]:
        if self._facade:
            res = self._facade.list_change_requests(project_id)
            if res.success and res.payload is not None:
                return [dataclasses.asdict(c) for c in res.payload]
        return []

    @Slot(str, str, result="QVariant")
    @Slot(str, result="QVariant")
    def getChangeRequest(self, change_number: str, project_id: str = "") -> Any:
        cache_key = f"{project_id}:{change_number}" if project_id else change_number
        if cache_key in self._change_detail_cache:
            return self._change_detail_cache[cache_key]
        if self._facade:
            res = self._facade.get_change_detail(change_number, project_id=project_id or None)
            if res.success and res.payload is not None:
                detail = dataclasses.asdict(res.payload)
                self._change_detail_cache[cache_key] = detail
                return detail
        return {}

    @Slot()
    def refreshChanges(self) -> None:
        self._changes_cache = []
        self._change_detail_cache.clear()
        self.changesChanged.emit()

    # ── M3/M5 Slot ───────────────────────────────────────────
    # 说明：以下 Slot 接口已与 QML UI 完整对接：
    #   - 创建变更单对话框：auto_pm/ui/qml/dialogs/NewChangeDialog.qml
    #   - 状态流转操作：auto_pm/ui/qml/components/DashboardStateMachine.qml
    #   - 变更详情与验证：auto_pm/ui/qml/components/ChangeDetailPanel.qml
    # ─────────────────────────────────────────────────────────

    @Slot("QVariant", result="QVariant")
    def createChange(self, command_dict: dict[str, Any]) -> dict[str, Any]:
        """创建变更单（M3 新增）

        Args:
            command_dict: 包含 project_id/title/domain/nature/background/
                         necessity/applicant/impact_scope(可选) 的字典

        Returns:
            创建后的变更单详情 dict（成功）或 {"success": False, "message": ...}（失败）
        """
        if self._facade:
            try:
                cmd = CreateChangeCommand(
                    project_id=str(command_dict.get("project_id", "")),
                    title=str(command_dict.get("title", "")),
                    domain=str(command_dict.get("domain", "")),
                    nature=str(command_dict.get("nature", "")),
                    background=str(command_dict.get("background", "")),
                    necessity=str(command_dict.get("necessity", "")),
                    applicant=str(command_dict.get("applicant", "")),
                    impact_scope=list(command_dict.get("impact_scope", []) or []),
                )
                res = self._facade.create_change_request(cmd)
                if res.success and res.payload is not None:
                    self._changes_cache = []  # 失效列表缓存
                    self.changesChanged.emit()
                    return dataclasses.asdict(res.payload)
                return {"success": False, "message": res.message}
            except Exception as e:
                logger.warning("createChange failed: %s", e, exc_info=True)
                return {"success": False, "message": str(e)}
        return {"success": False, "message": "未初始化"}

    @Slot("QVariant", result="QVariant")
    def transitionChange(self, command_dict: dict[str, Any]) -> dict[str, Any]:
        """变更单状态流转（M3 新增）

        Args:
            command_dict: 包含 change_id/target_status/operator/note(可选)/
                         allow_partial_verification(可选,默认False) 的字典

        Returns:
            流转后的变更单详情 dict（成功）或 {"success": False, "message": ...}（失败）
        """
        if self._facade:
            try:
                cmd = TransitionChangeCommand(
                    change_id=str(command_dict.get("change_id", "")),
                    target_status=str(command_dict.get("target_status", "")),
                    operator=str(command_dict.get("operator", "")),
                    note=command_dict.get("note"),
                    allow_partial_verification=bool(
                        command_dict.get("allow_partial_verification", False)
                    ),
                    project_id=command_dict.get("project_id") or None,
                )
                res = self._facade.transition_change(cmd)
                if res.success and res.payload is not None:
                    # 失效详情缓存（状态已变）
                    project_id = command_dict.get("project_id", "")
                    cache_key = f"{project_id}:{cmd.change_id}" if project_id else cmd.change_id
                    self._change_detail_cache.pop(cache_key, None)
                    self._change_detail_cache.pop(cmd.change_id, None)
                    self._changes_cache = []
                    self.changesChanged.emit()
                    return dataclasses.asdict(res.payload)
                return {"success": False, "message": res.message}
            except Exception as e:
                logger.warning("transitionChange failed: %s", e, exc_info=True)
                return {"success": False, "message": str(e)}
        return {"success": False, "message": "未初始化"}

    @Slot(str, str, result=list)
    @Slot(str, result=list)
    def getChangeTimeline(self, change_number: str, project_id: str = "") -> list[Any]:
        """获取变更单审批时间线（M3 新增）

        Args:
            change_number: 变更单编号
            project_id: 项目编号（B4 新增）

        Returns:
            时间线条目列表 list[dict]，每条含 from_status/to_status/approver/
            comment/transition_date
        """
        if self._facade:
            res = self._facade.get_change_timeline(change_number, project_id=project_id or None)
            if res.success and res.payload is not None:
                return [dataclasses.asdict(item) for item in res.payload]
        return []

    @Slot(str, str, result="QVariant")
    @Slot(str, result="QVariant")
    def getChangeValidationSummary(self, change_number: str, project_id: str = "") -> dict[str, Any]:
        """获取变更验证摘要（M3 新增）

        Args:
            change_number: 变更单编号
            project_id: 项目编号（B4 新增）

        Returns:
            摘要 dict，含 current_status/risk_level/mitigation/propagation_chain/
            approval_count/last_approval_date/domain_impacts/related_changes
        """
        if self._facade:
            res = self._facade.get_change_validation_summary(change_number, project_id=project_id or None)
            if res.success and res.payload is not None:
                return dataclasses.asdict(res.payload)
        return {}

    @Slot(str, "QVariant", str, result="QVariant")
    def updateChange(self, change_id: str, command_dict: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
        """更新变更单（GUI 编辑支持）"""
        if self._facade:
            try:
                res = self._facade.update_change_request(change_id, command_dict, project_id)
                if res.success and res.payload is not None:
                    self._change_detail_cache.pop(change_id, None)
                    self._changes_cache = []
                    self.changesChanged.emit()
                    return dataclasses.asdict(res.payload)
                return {"success": False, "message": res.message}
            except Exception as e:
                logger.warning("updateChange failed: %s", e, exc_info=True)
                return {"success": False, "message": str(e)}
        return {"success": False, "message": "未初始化"}

    @Slot(str, bool, result="QVariant")
    def reconcileLedger(self, project_id: str, auto_fix: bool) -> dict[str, Any]:
        """台账对账（M5 CHG-118 新增）

        Args:
            project_id: 项目编号
            auto_fix: True 时自动补建缺失行 + 修复状态不一致

        Returns:
            对账结果 dict（含 is_clean/missing_in_ledger/orphan_in_ledger/
            status_mismatches/summary/auto_fixed）或 {"success": False, "message": ...}
        """
        # M5 CHG-118: QML 端接入台账对账对话框
        if self._facade:
            res = self._facade.reconcile_ledger(project_id, auto_fix)
            if res.success and res.payload is not None:
                return dataclasses.asdict(res.payload)
            return {"success": res.success, "message": res.message}
        return {"success": False, "message": "未初始化"}
