"""Unit tests for ModbusBridge (PySide6 QML Bridge) (CHG-SCPT-2026-163)."""

from collections.abc import Callable
from time import monotonic

import pytest
from PySide6.QtCore import QCoreApplication

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _wait_until(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    """连接/读/写都在线程池里跑，结果经主线程定时器回传，测试需等事件循环。"""
    deadline = monotonic() + timeout_s
    while not condition():
        assert monotonic() < deadline, "等待后台 Modbus 操作超时"
        QCoreApplication.processEvents()


def _connect_sim(bridge: ModbusBridge) -> None:
    bridge.connectDevice("127.0.0.1", 502, slave_id=1, sim_mode=True, source_ip="")
    _wait_until(bridge.isConnected)


def test_modbus_bridge_network_interfaces(qapp):
    bridge = ModbusBridge()
    interfaces = bridge.getNetworkInterfaces()
    assert isinstance(interfaces, list)
    assert len(interfaces) >= 1
    assert "name" in interfaces[0]
    assert "ip" in interfaces[0]


def test_modbus_bridge_connect_and_disconnect(qapp):
    bridge = ModbusBridge()
    states = []
    bridge.connectionStateChanged.connect(lambda state: states.append(state))

    assert bridge.isConnected() is False
    bridge.connectDevice("127.0.0.1", 502, slave_id=1, sim_mode=True, source_ip="")
    _wait_until(lambda: bool(states))
    assert bridge.isConnected() is True
    assert states == [True]

    bridge.disconnectDevice()
    assert bridge.isConnected() is False
    assert states == [True, False]


def test_modbus_bridge_read_and_write(qapp):
    bridge = ModbusBridge()
    _connect_sim(bridge)

    received_data = []
    logs = []
    bridge.registerDataReceived.connect(lambda data: received_data.append(data))
    bridge.consoleLogAppended.connect(lambda log_type, hex_str: logs.append((log_type, hex_str)))

    bridge.readRegisters(fc="03", start=0, count=4, endian="CDAB", preset="siemens_fan")
    _wait_until(lambda: bool(received_data))
    assert len(received_data) == 1
    assert len(received_data[0]) == 4
    assert any(log_entry[0] == "TX" for log_entry in logs)
    assert any(log_entry[0] == "RX" for log_entry in logs)

    bridge.writeRegister(write_fc="06", addr=0, value_str="1500")
    _wait_until(lambda: not bridge._io_jobs)
    assert any("40001" in log_entry[1] or "06" in log_entry[1] for log_entry in logs)

    bridge.disconnectDevice()


def test_modbus_bridge_export_import_config(qapp, tmp_path):
    bridge = ModbusBridge()
    _connect_sim(bridge)

    cfg_file = tmp_path / "bridge_cfg.json"
    ok = bridge.exportConfig(str(cfg_file))
    assert ok is True
    assert cfg_file.exists()

    imported = bridge.importConfig(str(cfg_file))
    assert isinstance(imported, dict)
    assert imported.get("ip") == "127.0.0.1"
    assert imported.get("port") == 502
    assert imported.get("slave_id") == 1

    bridge.disconnectDevice()
