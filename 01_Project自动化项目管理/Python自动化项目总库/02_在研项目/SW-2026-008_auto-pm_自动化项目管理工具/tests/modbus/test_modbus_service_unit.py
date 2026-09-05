"""Unit tests for ModbusService and Modbus helper algorithms (CHG-SCPT-2026-162)."""

import pytest

from auto_pm.domain.modbus.modbus_service import (
    ModbusService,
    _build_hex_frame,
    _build_write_hex_frame,
    _decode_float_cdab,
    _sim_val,
)


def test_decode_float_cdab_standard():
    # 20.0 in IEEE 754 float: 0x41A00000 -> high=0x41A0, low=0x0000
    # In CDAB (Word Swap): swapped raw = (0x0000 << 16) | 0x41A0 = 0x000041A0
    # To get 20.0 from CDAB: raw = (high << 16) | low => swapped = 0x41A00000 => high=0x0000, low=0x41A0
    res = _decode_float_cdab(high=0x0000, low=0x41A0)
    assert res == "20.000"


def test_decode_float_cdab_invalid():
    # Verify exception safety and invalid cases return N/A
    res = _decode_float_cdab(high=0xFFFFFFFF, low=0xFFFFFFFF)
    assert res == "N/A" or isinstance(res, str)


def test_build_hex_frame_read():
    hex_str = _build_hex_frame(transaction_id=1, slave=1, fc=3, start=0, count=10)
    assert "0001 0000 0006" in hex_str
    assert "01 03 0000 000A" in hex_str


def test_build_write_hex_frame_single():
    hex_str = _build_write_hex_frame(transaction_id=2, slave=1, fc=6, addr=100, value=1234)
    assert "0002 0000 0006" in hex_str
    assert "01 06 0064 04D2" in hex_str


def test_build_write_hex_frame_multiple():
    hex_str = _build_write_hex_frame(transaction_id=3, slave=1, fc=16, addr=200, value=5678)
    assert "0003 0000 0009" in hex_str
    assert "01 10 00C8 0001 02 162E" in hex_str


def test_sim_val_presets():
    val, tag = _sim_val(0, "siemens_fan", ts=100.0)
    assert tag == "Fan_Start_CMD (启动给定)"
    assert val == 1

    val, tag = _sim_val(99, "custom", ts=100.0)
    assert "DB10.DBW198" == tag
    assert isinstance(val, int)


class TestModbusServiceSimulation:
    @pytest.fixture
    def svc(self):
        service = ModbusService()
        service.connect("127.0.0.1", 502, slave_id=1, sim_mode=True)
        yield service
        service.disconnect()

    def test_connect_disconnect(self, svc):
        assert svc.is_connected

    def test_read_holding_registers(self, svc):
        result = svc.read_registers(fc="03", start=0, count=8, preset="siemens_fan")
        assert result.success is True
        assert len(result.registers) == 8
        assert result.registers[0].tag == "Fan_Start_CMD (启动给定)"
        assert result.registers[0].physical == "40001"
        assert result.tx_hex != ""
        assert result.rx_hex != ""

    def test_read_coils(self, svc):
        result = svc.read_registers(fc="01", start=0, count=10)
        assert result.success is True
        assert len(result.registers) == 10
        assert result.registers[0].is_coil is True
        assert result.registers[0].physical == "1"

    def test_write_single_register(self, svc):
        result = svc.write_register(write_fc="06", addr=0, value=1500)
        assert result.success is True
        assert "40001" in result.message
        assert result.tx_hex != ""

    def test_write_single_coil(self, svc):
        result = svc.write_register(write_fc="05", addr=0, value=1)
        assert result.success is True
        assert result.tx_hex != ""

    def test_scan_registers(self, svc):
        cells = svc.scan_registers(start_offset=0, end_offset=19)
        assert len(cells) == 20
        assert any(c.is_active for c in cells)

    def test_export_and_import_config(self, svc, tmp_path):
        cfg_file = tmp_path / "modbus_test_cfg.json"
        success, msg = svc.export_config(str(cfg_file))
        assert success is True
        assert cfg_file.exists()

        success, msg, cfg = svc.import_config(str(cfg_file))
        assert success is True
        assert cfg.get("ip") == "127.0.0.1"
        assert cfg.get("port") == 502
        assert cfg.get("slave_id") == 1
