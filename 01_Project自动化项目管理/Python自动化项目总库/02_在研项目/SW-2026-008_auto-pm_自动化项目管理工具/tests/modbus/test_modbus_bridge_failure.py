"""Modbus 扫描/Ping 后台出错时界面不卡死（扫描卡死小卡）。

后台线程抛错、未连接就点扫描、扫描中再点一次：bridge 都必须回传失败原因，
QML 据此恢复“重新探测”按钮；不得只写一条日志就静默返回。
"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic

import pytest
from PySide6.QtCore import QCoreApplication

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge
from auto_pm.domain.modbus.modbus_service import PingResult, ScanCell


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _wait_until(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = monotonic() + timeout_s
    while not condition():
        assert monotonic() < deadline, "等待超时：界面会一直停在“扫描中”"
        QCoreApplication.processEvents()


class _Recorder:
    def __init__(self, bridge: ModbusBridge) -> None:
        self.cells: list[tuple[int, bool]] = []
        self.finished = 0
        self.failed: list[str] = []
        self.pings: list[tuple[bool, str]] = []
        self.logs: list[tuple[str, str]] = []
        bridge.scanCellUpdated.connect(lambda o, a: self.cells.append((o, a)))
        bridge.scanFinished.connect(self._on_finished)
        bridge.scanFailed.connect(self.failed.append)
        bridge.pingResultReceived.connect(lambda ok, msg: self.pings.append((ok, msg)))
        bridge.consoleLogAppended.connect(lambda t, m: self.logs.append((t, m)))

    def _on_finished(self) -> None:
        self.finished += 1

    @property
    def settled(self) -> bool:
        return self.finished > 0 or bool(self.failed)


def _connected_bridge(monkeypatch: pytest.MonkeyPatch) -> ModbusBridge:
    bridge = ModbusBridge()
    bridge._scan_timer.setInterval(1)
    bridge._ping_timer.setInterval(1)
    monkeypatch.setattr(type(bridge._service), "is_connected", property(lambda self: True))
    return bridge


def test_scan_worker_exception_reports_failure_and_releases_button(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)

    def boom(start: int, end: int) -> list[ScanCell]:
        raise ConnectionResetError("连接被对端复位")

    monkeypatch.setattr(bridge._service, "scan_registers", boom)
    bridge.scanRegisters(0, 9)
    _wait_until(lambda: rec.settled)

    assert rec.finished == 0
    assert len(rec.failed) == 1 and rec.failed[0]
    assert any(t == "ERR" and "扫描失败" in m for t, m in rec.logs)
    assert bridge._scan_worker is None, "失败后必须允许重新扫描"


def test_scan_success_still_pushes_every_cell_then_finishes(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    cells = [ScanCell(offset=i, is_active=i % 2 == 0) for i in range(5)]
    monkeypatch.setattr(bridge._service, "scan_registers", lambda s, e: cells)

    bridge.scanRegisters(0, 4)
    _wait_until(lambda: rec.settled)

    assert rec.failed == []
    assert rec.finished == 1
    assert rec.cells == [(c.offset, c.is_active) for c in cells]


def test_scan_when_not_connected_releases_button(qapp):
    bridge = ModbusBridge()
    rec = _Recorder(bridge)

    bridge.scanRegisters(0, 99)

    assert rec.failed == ["请先连接 Modbus TCP 设备再执行扫描！"]
    assert rec.finished == 0


def test_second_scan_while_running_is_refused_with_reason(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    monkeypatch.setattr(bridge._service, "scan_registers", lambda s, e: [ScanCell(offset=0, is_active=True)])

    bridge.scanRegisters(0, 0)
    bridge.scanRegisters(0, 0)
    assert rec.failed == ["上一次扫描尚未结束，请稍候再试。"]
    _wait_until(lambda: rec.finished > 0)
    assert rec.cells == [(0, True)]

    bridge.scanRegisters(0, 0)
    _wait_until(lambda: rec.finished > 1)


def test_ping_worker_exception_reports_reason(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)

    def boom(ip: str, source_ip: str | None = None) -> PingResult:
        raise OSError("ping 命令不存在")

    monkeypatch.setattr(bridge._service, "ping_host", boom)
    bridge.pingHost("192.168.0.1", "")
    _wait_until(lambda: bool(rec.pings))

    ok, msg = rec.pings[0]
    assert ok is False
    assert msg.startswith("Ping 后台异常")
    assert not bridge._ping_workers


def test_ping_success_still_reported(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    monkeypatch.setattr(
        bridge._service, "ping_host", lambda ip, src=None: PingResult(success=True, message="回复 TTL=64", latency_ms=1.0)
    )
    bridge.pingHost("192.168.0.1", "")
    _wait_until(lambda: bool(rec.pings))
    assert rec.pings == [(True, "回复 TTL=64")]
