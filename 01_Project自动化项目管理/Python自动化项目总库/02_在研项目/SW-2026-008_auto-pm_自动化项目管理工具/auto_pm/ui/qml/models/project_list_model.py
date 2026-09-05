"""PLC-HMI 概念映射：HMI 数据模型（项目列表模型（QML 项目列表的数据源））

像 HMI 触摸屏的配方数据表/报警列表，为 QML 的 ListView/TableView 提供数据源。

--- 原始注释 ---

项目列表 QAbstractListModel（V0.6.0 重构）

ProjectListModel 包装 ProjectService.list_projects() 为 QAbstractListModel，
供 QML ListView 直接使用。QML 端通过 roleNames 访问字段。

设计参考：02_设计/GUI原型设计.md §15.4 QML 架构设计

角色映射（QML 端通过 model.project_id / model.name 等访问）：
- ProjectIdRole: project_id（如 SW-2026-008）
- NameRole: name（项目名称）
- StackRole: stack（plc/python/unknown）
- PhaseRole: phase（developing/commissioning/production/archived）
- VersionRole: version（版本号）
- PathRole: path（项目绝对路径）
- BusinessLineRole: business_line（SW/DJ/ZD/XT/WX）
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from auto_pm.models import ProjectInfo


class ProjectListModel(QAbstractListModel):
    """项目列表 QAbstractListModel

    包装 ProjectService.list_projects() 结果，供 QML ListView 使用。
    """

    countChanged = Signal()

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._projects)

    # 角色枚举（UserRole 起步避免与 Qt 内置角色冲突）
    ProjectIdRole = Qt.ItemDataRole.UserRole + 1
    NameRole = Qt.ItemDataRole.UserRole + 2
    StackRole = Qt.ItemDataRole.UserRole + 3
    PhaseRole = Qt.ItemDataRole.UserRole + 4
    VersionRole = Qt.ItemDataRole.UserRole + 5
    PathRole = Qt.ItemDataRole.UserRole + 6
    BusinessLineRole = Qt.ItemDataRole.UserRole + 7

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._projects: list[Any] = []

    # ── QAbstractListModel 必须实现 ───────────────────────

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        """返回项目数"""
        if parent.isValid():
            return 0
        return len(self._projects)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """返回指定 index + role 的数据"""
        if not index.isValid() or not (0 <= index.row() < len(self._projects)):
            return None

        project = self._projects[index.row()]
        role_name = self._role_to_field(role)
        if role_name is None:
            return None

        if isinstance(project, dict):
            value = project.get(role_name, "")
        else:
            value = getattr(project, role_name, "")

        # 枚举类型转字符串（Stack/ProjectPhase/BusinessLine）
        if hasattr(value, "value"):
            return str(value.value)
        return str(value) if not isinstance(value, str) else value

    def roleNames(self) -> dict[int, bytes]:  # type: ignore[override]
        """返回 role → roleName 映射（QML 端通过 model.roleName 访问）

        Note: PySide6 类型桩声明返回 dict[int, QByteArray]，但运行时接受 bytes。
        PySide6 binding 会自动转换 bytes → QByteArray，故保留 bytes 字面量简洁实现。
        """
        return {
            self.ProjectIdRole: b"project_id",
            self.NameRole: b"name",
            self.StackRole: b"stack",
            self.PhaseRole: b"phase",
            self.VersionRole: b"version",
            self.PathRole: b"path",
            self.BusinessLineRole: b"business_line",
        }

    # ── 数据更新接口 ──────────────────────────────────────

    @Slot(list)
    def setProjects(self, projects: list[Any]) -> None:
        """批量替换项目列表（重置模型）

        @Slot(list) 装饰器使 QML 端可调用 projectModel.setProjects(projects)。
        QML 端传入的 JS 数组会被 PySide6 自动转换为 Python list。
        """
        self.beginResetModel()
        self._projects = list(projects)
        self.endResetModel()
        self.countChanged.emit()

    @Slot()
    def clear(self) -> None:
        """清空项目列表"""
        self.beginResetModel()
        self._projects = []
        self.endResetModel()
        self.countChanged.emit()

    @Slot(int, result="QVariant")
    def getProjectAt(self, row: int) -> ProjectInfo | None:
        """返回指定行的 ProjectInfo（Python 端测试用）"""
        if 0 <= row < len(self._projects):
            from typing import cast

            return cast(ProjectInfo, self._projects[row])
        return None

    @Slot(result=int)
    def projectCount(self) -> int:
        """返回项目数（Python 端测试用）"""
        return len(self._projects)

    # ── 内部辅助 ──────────────────────────────────────────

    def _role_to_field(self, role: int) -> str | None:
        """角色枚举 → ProjectInfo 字段名映射"""
        mapping = {
            self.ProjectIdRole: "project_id",
            self.NameRole: "name",
            self.StackRole: "stack",
            self.PhaseRole: "phase",
            self.VersionRole: "version",
            self.PathRole: "path",
            self.BusinessLineRole: "business_line",
        }
        return mapping.get(role)
