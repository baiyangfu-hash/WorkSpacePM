"""ModbusDebuggerView：扫描失败时按钮恢复、红框显示原因（扫描卡死小卡）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

_VIEW = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml" / "views" / "ModbusDebuggerView.qml"


class _FakeModbusBridge(QObject):
    """只实现视图扫描路径用到的接口；scanRegisters 立刻回报失败。"""

    registerDataReceived = Signal(list)
    consoleLogAppended = Signal(str, str)
    connectionStateChanged = Signal(bool)
    pingResultReceived = Signal(bool, str)
    scanCellUpdated = Signal(int, bool)
    scanFinished = Signal()
    scanFailed = Signal(str)
    trendDataUpdated = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.scan_calls = 0
        self.stop_calls = 0
        self.hold = False
        self.fail_reason = "【通信中断】连接被对端复位"

    @Slot(result="QVariant")
    def getNetworkInterfaces(self) -> list[dict[str, Any]]:
        return [{"name": "自动选择 (Auto Default)", "ip": ""}]

    @Slot(int, int)
    def scanRegisters(self, start: int, end: int) -> None:
        self.scan_calls += 1
        if self.hold:
            return
        if self.fail_reason:
            self.scanFailed.emit(self.fail_reason)
        else:
            self.scanFinished.emit()

    @Slot()
    def stopScan(self) -> None:
        self.stop_calls += 1

    @Slot(result=bool)
    def isConnected(self) -> bool:
        return True


def _create_view(engine: QQmlEngine, bridge: _FakeModbusBridge) -> QObject:
    engine.rootContext().setContextProperty("modbusBridge", bridge)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_VIEW)))
    assert not component.isError(), "\n".join(e.toString() for e in component.errors())
    view = component.create()
    assert view is not None
    view._component_ref = component  # type: ignore[attr-defined]
    view._bridge_ref = bridge  # type: ignore[attr-defined]
    return view


def test_scan_failure_releases_button_and_shows_reason(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    bridge = _FakeModbusBridge()
    view = _create_view(qml_engine, bridge)
    button = view.findChild(QObject, "startScanBtn")
    error_text = view.findChild(QObject, "scanErrorText")
    error_box = view.findChild(QObject, "scanErrorBox")
    assert button is not None and error_text is not None and error_box is not None

    button.clicked.emit()
    qapp.processEvents()

    assert bridge.scan_calls == 1
    assert button.property("enabled") is True
    assert button.property("text") != "扫描中..."
    assert error_text.property("text") == "扫描失败：【通信中断】连接被对端复位"

    # 下一次成功扫描清掉旧的失败原因
    bridge.fail_reason = ""
    button.clicked.emit()
    qapp.processEvents()
    assert bridge.scan_calls == 2
    assert error_text.property("text") == ""
    assert button.property("enabled") is True


def test_stop_button_follows_the_scan_and_calls_stop(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    bridge = _FakeModbusBridge()
    bridge.hold = True
    view = _create_view(qml_engine, bridge)
    start = view.findChild(QObject, "startScanBtn")
    stop = view.findChild(QObject, "stopScanBtn")
    assert start is not None and stop is not None
    assert view.property("_scanning") is False

    start.clicked.emit()
    qapp.processEvents()
    assert view.property("_scanning") is True
    assert start.property("enabled") is False

    stop.clicked.emit()
    qapp.processEvents()
    assert bridge.stop_calls == 1

    bridge.scanFailed.emit("扫描已停止（已探测 3 格）。")
    qapp.processEvents()
    assert view.property("_scanning") is False
    assert start.property("enabled") is True
    assert view.findChild(QObject, "scanErrorText").property("text") == "扫描失败：扫描已停止（已探测 3 格）。"
