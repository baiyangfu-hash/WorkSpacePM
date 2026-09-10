"""Safe default QML entry: a read-only PM cockpit with no legacy startup side effects."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge


def run_boss_cockpit(workspace_root: str, debug: bool = False) -> int:
    """Run the user-friendly default screen without constructing legacy services."""
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    QQuickStyle.setStyle("Basic")

    qml_path = Path(__file__).parent / "qml" / "boss_main.qml"
    if not qml_path.is_file():
        if debug:
            sys.stderr.write(f"[ERROR] boss_main.qml 不存在: {qml_path}\n")
        return 1

    engine = QQmlApplicationEngine()
    bridge = PmCockpitBridge(workspace_root)
    engine.rootContext().setContextProperty("pmCockpitBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        if debug:
            sys.stderr.write("[ERROR] 老板驾驶舱 QML 加载失败\n")
        return 1
    return app.exec()
