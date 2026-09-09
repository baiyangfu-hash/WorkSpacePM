"""auto_pm.ui 包

V0.9.0 起 QML 为唯一 UI 入口，旧 QWidget 模块已全部移除。

架构分层：
- contracts/: DTO/Command/Event 接口契约（UI 与 Application 层的稳定接口面）
- qml/: QML 视图 + 组件 + 主题 + 对话框 + qml_bridge.py 数据桥
- qml_main_window.py: QML GUI 入口
- global_pages/: 全局页面适配器（SpecCenterAdapter 等）
- models/: Qt 模型适配器（ProjectModel 等）
- registry.py: Facade 装配器（手工 DI，将 Service 组装为 Application Facade）

UI 层通过 Application Facade（application/）访问能力，不直接访问 Service/文件系统/DB。
"""

__all__: list[str] = []
