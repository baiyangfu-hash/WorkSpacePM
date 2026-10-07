"""Safe default QML entry: a read-only PM cockpit with no legacy startup side effects."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from auto_pm.config.app_config import AutoPmConfig
from auto_pm.core.pm_cockpit_service import PmCockpitService
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge


def build_cockpit_bridge(
    workspace_root: str, config: AutoPmConfig | None = None, *, control_root: str | None = None
) -> PmCockpitBridge:
    """Create the cockpit bridge with the configured approver (empty when unset or unreadable).

    ``control_root`` is the governed main root; ``workspace_root`` stays the root the GUI was started in.
    """

    try:
        approver = (config or AutoPmConfig()).cockpit_approver
    except ValueError:
        approver = ""
    return PmCockpitBridge(
        workspace_root,
        service=PmCockpitService(workspace_root, approver=approver, control_root=control_root),
        control_root=control_root,
    )


def run_boss_cockpit(workspace_root: str, debug: bool = False, *, control_root: str | None = None) -> int:
    """Run the user-friendly default screen without constructing legacy services."""
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    QQuickStyle.setStyle("Basic")

    qml_path = Path(__file__).parent / "qml" / "boss_main.qml"
    if not qml_path.is_file():
        if debug:
            sys.stderr.write(f"[ERROR] boss_main.qml 不存在: {qml_path}\n")
        return 1

    engine = QQmlApplicationEngine()
    bridge = build_cockpit_bridge(workspace_root, control_root=control_root)
    engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        if debug:
            sys.stderr.write("[ERROR] 老板驾驶舱 QML 加载失败\n")
        return 1
    return app.exec()
