"""QML UI 模块（V0.6.0 重构）

提供 PySide6 + QML 重构所需的 Python 桥接层：
- QmlBridge: 暴露后端 Service 为 QML 可调用属性
- ProjectListModel: QAbstractListModel 包装项目列表

Week 1 PoC 范围：仅实现 QmlBridge + ProjectListModel + 项目列表 QML ListView。
后端 Service 层零改动，UI 层重构不得影响 CLI/Service 接口。
"""

from auto_pm.ui.qml.models.project_list_model import ProjectListModel

__all__ = ["ProjectListModel"]
