"""Modbus 联调工坊不卡界面（扫描卡死小卡 + 预审 88 返工）。

- 后台出错、未连接就扫描：bridge 回传失败原因，QML 据此恢复按钮
- 设备在线但不回话：扫描连续无应答/超总时限即判失败，可中途停止，逐格出进度
- 连接、读、写、轮询、扫描、Ping 都不在界面线程碰网络
- 扫描与读写共用的 pymodbus 客户端不并发收发
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from time import monotonic, sleep
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication

from auto_pm.domain.modbus import modbus_bridge as bridge_module
from auto_pm.domain.modbus.modbus_bridge import ModbusBridge
from auto_pm.domain.modbus.modbus_service import ModbusService, PingResult


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _wait_until(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = monotonic() + timeout_s
    while not condition():
        assert monotonic() < deadline, "等待超时：界面会一直停在“忙”状态"
        QCoreApplication.processEvents()


class _Recorder:
    def __init__(self, bridge: ModbusBridge) -> None:
        self.cells: list[tuple[int, bool]] = []
        self.finished = 0
        self.failed: list[str] = []
        self.pings: list[tuple[bool, str]] = []
        self.logs: list[tuple[str, str]] = []
        self.states: list[bool] = []
        self.data: list[list[Any]] = []
        bridge.scanCellUpdated.connect(lambda o, a: self.cells.append((o, a)))
        bridge.scanFinished.connect(self._on_finished)
        bridge.scanFailed.connect(self.failed.append)
        bridge.pingResultReceived.connect(lambda ok, msg: self.pings.append((ok, msg)))
        bridge.consoleLogAppended.connect(lambda t, m: self.logs.append((t, m)))
        bridge.connectionStateChanged.connect(self.states.append)
        bridge.registerDataReceived.connect(self.data.append)

    def _on_finished(self) -> None:
        self.finished += 1

    @property
    def settled(self) -> bool:
        return self.finished > 0 or bool(self.failed)


def _connected_bridge(monkeypatch: pytest.MonkeyPatch) -> ModbusBridge:
    bridge = ModbusBridge()
    bridge._scan_timer.setInterval(1)
    bridge._io_timer.setInterval(1)
    monkeypatch.setattr(type(bridge._service), "is_connected", property(lambda self: True))
    return bridge


# ── 后台出错 / 未连接 ─────────────────────────────────────


def test_scan_worker_exception_reports_failure_and_releases_button(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)

    def boom(offset: int) -> bool | None:
        raise RuntimeError("意外错误")

    monkeypatch.setattr(bridge._service, "probe_register", boom)
    bridge.scanRegisters(0, 9)
    _wait_until(lambda: rec.settled)

    assert rec.finished == 0
    assert len(rec.failed) == 1 and rec.failed[0]
    assert any(t == "ERR" and "扫描失败" in m for t, m in rec.logs)
    assert bridge._scan_worker is None, "失败后必须允许重新扫描"


def test_scan_success_still_pushes_every_cell_then_finishes(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    monkeypatch.setattr(bridge._service, "probe_register", lambda offset: offset % 2 == 0)

    bridge.scanRegisters(0, 4)
    _wait_until(lambda: rec.settled)

    assert rec.failed == []
    assert rec.finished == 1
    assert rec.cells == [(i, i % 2 == 0) for i in range(5)]
    assert bridge._scan_worker is None


def test_scan_when_not_connected_releases_button(qapp):
    bridge = ModbusBridge()
    rec = _Recorder(bridge)

    bridge.scanRegisters(0, 99)

    assert rec.failed == ["请先连接 Modbus TCP 设备再执行扫描！"]
    assert rec.finished == 0


def test_second_scan_while_running_is_refused_without_releasing_the_button(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    gate = threading.Event()

    def slow_probe(offset: int) -> bool:
        gate.wait(5)
        return True

    monkeypatch.setattr(bridge._service, "probe_register", slow_probe)
    bridge.scanRegisters(0, 0)
    bridge.scanRegisters(0, 0)
    assert rec.failed == [], "第一次扫描还在跑，不能发 scanFailed 让界面放开按钮"
    assert any(t == "ERR" and "上一次扫描尚未结束" in m for t, m in rec.logs)

    gate.set()
    _wait_until(lambda: rec.finished > 0)
    assert rec.cells == [(0, True)]
    bridge.scanRegisters(0, 0)
    _wait_until(lambda: rec.finished > 1)


# ── 设备在线但不回话 ───────────────────────────────────────


def test_scan_shows_each_cell_while_the_scan_is_still_running(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    gate = threading.Event()

    def probe(offset: int) -> bool:
        if offset == 1:
            gate.wait(5)
        return True

    monkeypatch.setattr(bridge._service, "probe_register", probe)
    bridge.scanRegisters(0, 1)
    try:
        _wait_until(lambda: bool(rec.cells))
        assert rec.cells == [(0, True)], "慢设备上要边扫边显示，不能等全部扫完"
        assert not rec.settled
    finally:
        gate.set()
    _wait_until(lambda: rec.settled)
    assert rec.cells == [(0, True), (1, True)]


def test_silent_device_aborts_scan_after_consecutive_no_answers(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    calls: list[int] = []

    def silent(offset: int) -> bool | None:
        calls.append(offset)
        return None

    monkeypatch.setattr(bridge._service, "probe_register", silent)
    bridge.scanRegisters(0, 99)
    _wait_until(lambda: rec.settled)

    assert rec.finished == 0
    assert "无应答" in rec.failed[0]
    assert len(calls) == bridge_module.SCAN_SILENT_CELL_LIMIT, "必须在连续无应答达到上限时立刻停，不能扫满 100 格"
    assert rec.cells == [(o, False) for o in calls], "已探测的格子要逐格显示（红）"


def test_one_answer_resets_the_silent_counter(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    answers = {0: None, 1: True, 2: None, 3: False, 4: None}
    monkeypatch.setattr(bridge._service, "probe_register", lambda offset: answers[offset])

    bridge.scanRegisters(0, 4)
    _wait_until(lambda: rec.settled)

    assert rec.failed == []
    assert rec.cells == [(0, False), (1, True), (2, False), (3, False), (4, False)]


def test_scan_time_limit_aborts_slow_scan(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    monkeypatch.setattr(bridge_module, "SCAN_TIME_LIMIT_S", 0.2)

    def slow(offset: int) -> bool:
        sleep(0.05)
        return True

    monkeypatch.setattr(bridge._service, "probe_register", slow)
    bridge.scanRegisters(0, 99)
    _wait_until(lambda: rec.settled)

    assert rec.finished == 0
    assert "未完成" in rec.failed[0]
    assert 0 < len(rec.cells) < 100


def test_stop_scan_reports_stopped_and_keeps_cells(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    first = threading.Event()

    def probe(offset: int) -> bool:
        first.set()
        sleep(0.02)
        return True

    monkeypatch.setattr(bridge._service, "probe_register", probe)
    bridge.scanRegisters(0, 99)
    assert first.wait(5)
    bridge.stopScan()
    _wait_until(lambda: rec.settled)

    assert rec.finished == 0
    assert "已停止" in rec.failed[0]
    assert 0 < len(rec.cells) < 100
    assert bridge._scan_worker is None


def test_disconnect_stops_a_running_scan(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    first = threading.Event()

    def probe(offset: int) -> bool:
        first.set()
        sleep(0.02)
        return True

    monkeypatch.setattr(bridge._service, "probe_register", probe)
    bridge.scanRegisters(0, 99)
    assert first.wait(5)
    bridge.disconnectDevice()
    _wait_until(lambda: rec.settled)
    assert "已停止" in rec.failed[0]


# ── 网络操作不在界面线程 ───────────────────────────────────


def test_network_calls_never_run_on_the_gui_thread(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    gui = threading.get_ident()
    seen: dict[str, int] = {}
    real = ModbusService()
    real.connect("127.0.0.1", 502, 1, True, "")

    def record(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            seen[name] = threading.get_ident()
            return fn(*args, **kwargs)
        return wrapper

    svc = bridge._service
    monkeypatch.setattr(svc, "connect", record("connect", real.connect))
    monkeypatch.setattr(svc, "read_registers", record("read", real.read_registers))
    monkeypatch.setattr(svc, "write_register", record("write", real.write_register))
    monkeypatch.setattr(svc, "probe_register", record("probe", lambda offset: True))
    monkeypatch.setattr(
        svc, "ping_host", record("ping", lambda ip, src=None: PingResult(success=True, message="ok", latency_ms=1.0))
    )

    bridge.connectDevice("127.0.0.1", 502, 1, True, "")
    bridge.readRegisters("03", 0, 2, "ABCD", "")
    bridge.writeRegister("06", 0, "5")
    bridge.pingHost("127.0.0.1", "")
    bridge.scanRegisters(0, 1)
    _wait_until(lambda: rec.settled and not bridge._io_jobs)

    assert set(seen) == {"connect", "read", "write", "probe", "ping"}
    on_gui = sorted(name for name, ident in seen.items() if ident == gui)
    assert on_gui == [], f"这些操作在界面线程等设备：{on_gui}"
    assert rec.states == [True]
    assert len(rec.data) == 1


def test_slow_read_does_not_block_the_gui_thread_and_poll_does_not_pile_up(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    gate = threading.Event()
    calls: list[int] = []

    def slow_read(*args: Any) -> Any:
        calls.append(1)
        gate.wait(5)
        raise TimeoutError("timed out")

    monkeypatch.setattr(bridge._service, "read_registers", slow_read)
    rec = _Recorder(bridge)
    t0 = monotonic()
    bridge.readRegisters("03", 0, 1, "ABCD", "")
    bridge._start_read("03", 0, 1, "ABCD", "", from_poll=True)
    bridge._start_read("03", 0, 1, "ABCD", "", from_poll=True)
    assert monotonic() - t0 < 1.0, "读取不能在界面线程等设备"
    gate.set()
    _wait_until(lambda: not bridge._io_jobs)
    assert len(calls) == 1, "上一次读取没返回时，轮询必须跳过而不是堆请求"
    assert any(t == "ERR" for t, _ in rec.logs)
    assert bridge._read_in_flight is False


def test_scan_and_reads_never_use_the_client_at_the_same_time(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    active = 0
    peak = 0
    guard = threading.Lock()

    def busy(result: Any) -> Callable[..., Any]:
        def fn(*args: Any) -> Any:
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            sleep(0.01)
            with guard:
                active -= 1
            return result
        return fn

    real = ModbusService()
    real.connect("127.0.0.1", 502, 1, True, "")
    read_result = real.read_registers("03", 0, 1, "ABCD", "")
    monkeypatch.setattr(bridge._service, "probe_register", busy(True))
    monkeypatch.setattr(bridge._service, "read_registers", busy(read_result))
    monkeypatch.setattr(bridge._service, "write_register", busy(read_result))

    bridge.scanRegisters(0, 19)
    for _ in range(10):
        bridge.readRegisters("03", 0, 1, "ABCD", "")
        bridge.writeRegister("06", 0, "1")
        _wait_until(lambda: not bridge._read_in_flight)
    _wait_until(lambda: rec.settled and not bridge._io_jobs)

    assert rec.finished == 1
    assert peak == 1, "扫描和读写同时在用同一个 Modbus 客户端（会串包）"


# ── Ping ──────────────────────────────────────────────────


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
    assert not bridge._io_jobs


def test_ping_success_still_reported(qapp, monkeypatch):
    bridge = _connected_bridge(monkeypatch)
    rec = _Recorder(bridge)
    monkeypatch.setattr(
        bridge._service, "ping_host", lambda ip, src=None: PingResult(success=True, message="回复 TTL=64", latency_ms=1.0)
    )
    bridge.pingHost("192.168.0.1", "")
    _wait_until(lambda: bool(rec.pings))
    assert rec.pings == [(True, "回复 TTL=64")]


# ── 连接失败 / 后台异常 ─────────────────────────────────────


def test_connect_exception_reports_disconnected(qapp, monkeypatch):
    bridge = ModbusBridge()
    bridge._io_timer.setInterval(1)
    rec = _Recorder(bridge)

    def boom(*args: Any) -> tuple[bool, str]:
        raise OSError("网卡不存在")

    monkeypatch.setattr(bridge._service, "connect", boom)
    bridge.connectDevice("10.0.0.1", 502, 1, False, "")
    _wait_until(lambda: bool(rec.states))
    assert rec.states == [False]
    assert bridge._connect_in_flight is False


# ── 服务层单格探测 ─────────────────────────────────────────


class _Resp:
    def __init__(self, error: bool) -> None:
        self._error = error

    def isError(self) -> bool:  # noqa: N802 - pymodbus API
        return self._error


class _Client:
    def __init__(self, behaviour: Any) -> None:
        self._behaviour = behaviour

    def read_holding_registers(self, address: int, count: int, device_id: int) -> _Resp:
        if isinstance(self._behaviour, Exception):
            raise self._behaviour
        return _Resp(self._behaviour)


@pytest.mark.parametrize(
    ("behaviour", "expected"),
    [(False, True), (True, False), (TimeoutError("no response"), None)],
)
def test_probe_register_tells_no_answer_apart_from_exception_reply(behaviour, expected):
    svc = ModbusService()
    svc._connected = True
    svc._client = _Client(behaviour)
    assert svc.probe_register(0) is expected


def test_probe_register_when_disconnected_is_no_answer():
    assert ModbusService().probe_register(0) is None
