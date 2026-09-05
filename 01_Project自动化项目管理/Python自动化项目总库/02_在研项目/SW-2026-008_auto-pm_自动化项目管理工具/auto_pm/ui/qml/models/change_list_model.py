"""PLC-HMI 概念映射：HMI 数据模型（变更列表模型（QML 变更单列表的数据源））

像 HMI 触摸屏的配方数据表/报警列表，为 QML 的 ListView/TableView 提供数据源。

--- 原始注释 ---

变更列表 QAbstractListModel（V0.6.0 W2-S3）

ChangeListModel 包装 ChangeSummary 字典列表为 QAbstractListModel，
供 QML ListView 直接使用。QML 端通过 roleNames 访问字段。

设计参考：02_设计/GUI原型设计.md §15.4 QML 架构设计

角色映射（QML 端通过 model.change_number / model.title 等访问）：
- ChangeNumberRole: change_number（如 CHG-SCPT-2026-086）
- ProjectIdRole: project_id
- ProjectNameRole: project_name
- DomainRole: domain（ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE）
- BusinessNatureRole: business_nature（REQ/DEF/OPT/CFG/EMRG）
- StatusRole: status（draft/submitted/.../closed）
- ApplicantRole: applicant
- ApplyDateRole: apply_date
- TitleRole: title（background 摘要）
- UrgencyRole: urgency（normal/urgent/critical）
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt, Slot


class ChangeListModel(QAbstractListModel):
    """变更列表 QAbstractListModel

    包装 ChangeSummary dict 列表，供 QML ListView 使用。
    数据源：QmlBridge.listAllChanges() / listChanges(project_id) 返回的 dict 列表。
    """

    # 角色枚举
    ChangeNumberRole = Qt.ItemDataRole.UserRole + 1
    ProjectIdRole = Qt.ItemDataRole.UserRole + 2
    ProjectNameRole = Qt.ItemDataRole.UserRole + 3
    DomainRole = Qt.ItemDataRole.UserRole + 4
    BusinessNatureRole = Qt.ItemDataRole.UserRole + 5
    StatusRole = Qt.ItemDataRole.UserRole + 6
    ApplicantRole = Qt.ItemDataRole.UserRole + 7
    ApplyDateRole = Qt.ItemDataRole.UserRole + 8
    TitleRole = Qt.ItemDataRole.UserRole + 9
    UrgencyRole = Qt.ItemDataRole.UserRole + 10

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._changes: list[dict[str, Any]] = []

    # ── QAbstractListModel 必须实现 ───────────────────────

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._changes)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._changes)):
            return None

        change = self._changes[index.row()]
        role_name = self._role_to_field(role)
        if role_name is None:
            return None

        value = change.get(role_name, "")

        # impact_scope 是 list，转字符串
        if isinstance(value, list):
            return ",".join(str(v) for v in value)
        return value

    def roleNames(self) -> dict[int, bytes]:  # type: ignore[override]
        return {
            self.ChangeNumberRole: b"change_number",
            self.ProjectIdRole: b"project_id",
            self.ProjectNameRole: b"project_name",
            self.DomainRole: b"domain",
            self.BusinessNatureRole: b"business_nature",
            self.StatusRole: b"status",
            self.ApplicantRole: b"applicant",
            self.ApplyDateRole: b"apply_date",
            self.TitleRole: b"title",
            self.UrgencyRole: b"urgency",
        }

    # ── 数据更新接口 ──────────────────────────────────────

    @Slot(list)
    def setChanges(self, changes: list[Any]) -> None:
        """批量替换变更列表（重置模型）

        @Slot(list) 装饰器使 QML 端可调用 changeModel.setChanges(changes)。
        """
        self.beginResetModel()
        self._changes = list(changes)
        self.endResetModel()

    @Slot()
    def clear(self) -> None:
        """清空变更列表"""
        self.beginResetModel()
        self._changes = []
        self.endResetModel()

    @Slot(int, result="QVariant")
    def getChangeAt(self, row: int) -> dict[str, Any] | None:
        """返回指定行的变更 dict（Python 端测试用）"""
        if 0 <= row < len(self._changes):
            return self._changes[row]
        return None

    @Slot(result=int)
    def changeCount(self) -> int:
        """返回变更数（Python 端测试用）"""
        return len(self._changes)

    # ── 内部辅助 ──────────────────────────────────────────

    def _role_to_field(self, role: int) -> str | None:
        mapping = {
            self.ChangeNumberRole: "change_number",
            self.ProjectIdRole: "project_id",
            self.ProjectNameRole: "project_name",
            self.DomainRole: "domain",
            self.BusinessNatureRole: "business_nature",
            self.StatusRole: "status",
            self.ApplicantRole: "applicant",
            self.ApplyDateRole: "apply_date",
            self.TitleRole: "title",
            self.UrgencyRole: "urgency",
        }
        return mapping.get(role)
