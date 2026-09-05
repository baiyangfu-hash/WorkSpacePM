"""PLC-HMI 概念映射：HMI 数据模型（项目模型（旧版项目数据模型，向后兼容））

像 HMI 触摸屏的配方数据表/报警列表，为 QML 的 ListView/TableView 提供数据源。

--- 原始注释 ---

项目列表模型（QAbstractListModel 适配器）

将 ProjectInfo 列表适配为 Qt 模型，供视图组件绑定。
遵循 MVC 模式：模型负责数据持有与通知，视图负责渲染。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt

from auto_pm.models import ProjectInfo


class ProjectModel(QAbstractListModel):
    """项目列表模型

    持有 ProjectInfo 列表，通过标准 Qt 模型接口暴露给视图。
    支持批量重置、追加、删除项目。
    """

    # 自定义数据角色
    ProjectRole = Qt.ItemDataRole.UserRole + 1  # 完整 ProjectInfo 对象
    IdRole = Qt.ItemDataRole.UserRole + 2
    NameRole = Qt.ItemDataRole.UserRole + 3
    StackRole = Qt.ItemDataRole.UserRole + 4
    PhaseRole = Qt.ItemDataRole.UserRole + 5
    VersionRole = Qt.ItemDataRole.UserRole + 6
    PathRole = Qt.ItemDataRole.UserRole + 7

    def __init__(self, projects: list[ProjectInfo] | None = None) -> None:
        super().__init__()
        self._projects: list[ProjectInfo] = list(projects) if projects else []

    # ── Qt 模型接口 ────────────────────────────────────────

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._projects)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._projects)):
            return None
        proj = self._projects[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return proj.name
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{proj.project_id} | {proj.stack} | {proj.path}"
        if role == self.ProjectRole:
            return proj
        if role == self.IdRole:
            return proj.project_id
        if role == self.NameRole:
            return proj.name
        if role == self.StackRole:
            return proj.stack
        if role == self.PhaseRole:
            return proj.phase
        if role == self.VersionRole:
            return proj.version
        if role == self.PathRole:
            return proj.path
        return None

    # ── 数据操作 ──────────────────────────────────────────

    def set_projects(self, projects: list[ProjectInfo]) -> None:
        """批量重置项目列表"""
        self.beginResetModel()
        self._projects = list(projects)
        self.endResetModel()

    def append_project(self, project: ProjectInfo) -> None:
        """追加单个项目"""
        row = len(self._projects)
        self.beginInsertRows(QModelIndex(), row, row)
        self._projects.append(project)
        self.endInsertRows()

    def remove_project(self, project_id: str) -> None:
        """按 project_id 删除项目"""
        for row, proj in enumerate(self._projects):
            if proj.project_id == project_id:
                self.beginRemoveRows(QModelIndex(), row, row)
                self._projects.pop(row)
                self.endRemoveRows()
                return

    def get_project(self, project_id: str) -> ProjectInfo | None:
        """按 project_id 查询项目"""
        for proj in self._projects:
            if proj.project_id == project_id:
                return proj
        return None

    def all_projects(self) -> list[ProjectInfo]:
        """返回全部项目（只读副本）"""
        return list(self._projects)
