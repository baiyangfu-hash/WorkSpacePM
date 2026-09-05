"""Unit tests for ModbusBridge (PySide6 QML Bridge) (CHG-SCPT-2026-163)."""

import pytest
from PySide6.QtCore import QCoreApplication

from auto_pm.domain.modbus.modbus_bridge import ModbusBridge


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


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
    assert bridge.isConnected() is True
    assert states == [True]

    bridge.disconnectDevice()
    assert bridge.isConnected() is False
    assert states == [True, False]


def test_modbus_bridge_read_and_write(qapp):
    bridge = ModbusBridge()
    bridge.connectDevice("127.0.0.1", 502, slave_id=1, sim_mode=True, source_ip="")

    received_data = []
    logs = []
    bridge.registerDataReceived.connect(lambda data: received_data.append(data))
    bridge.consoleLogAppended.connect(lambda log_type, hex_str: logs.append((log_type, hex_str)))

    bridge.readRegisters(fc="03", start=0, count=4, endian="CDAB", preset="siemens_fan")
    assert len(received_data) == 1
    assert len(received_data[0]) == 4
    assert any(log_entry[0] == "TX" for log_entry in logs)
    assert any(log_entry[0] == "RX" for log_entry in logs)

    bridge.writeRegister(write_fc="06", addr=0, value_str="1500")
    assert any("40001" in log_entry[1] or "06" in log_entry[1] for log_entry in logs)

    bridge.disconnectDevice()


def test_modbus_bridge_export_import_config(qapp, tmp_path):
    bridge = ModbusBridge()
    bridge.connectDevice("127.0.0.1", 502, slave_id=1, sim_mode=True, source_ip="")

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
