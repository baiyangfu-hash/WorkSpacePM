"""全局功能页模块（V0.9.0 Phase 2 / CHG-094 起仅保留 SpecCenterAdapter）

V0.9.0 Phase 2 已将 main_window.py + 7 个旧 QWidget 模块目录全部删除。
旧 QWidget 全局页（ReportPage/SettingsPage/SpecCenterView/TemplatePage/
GlobalView）已由 QML 页面完整替代。

保留：
- ``spec_center_dto.py``：SpecCenterAdapter + DTOs，由 QML SpecCenterView 通过
  QmlBridge 使用
"""

__all__: list[str] = []
