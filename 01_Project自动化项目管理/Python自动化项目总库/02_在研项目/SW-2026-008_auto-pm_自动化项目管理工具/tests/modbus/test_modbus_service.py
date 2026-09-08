"""ModbusService 单元测试（V1.1.0 仿真模式）

覆盖所有核心功能路径：
- Ping 诊断（仿真/无效IP）
- 连接管理
- 功能码读取（FC01/02/03/04/07/17/20/22/23/24/43）— 11 个全覆盖
- 功能码写入（FC05/06/15/16/21/22）— 6 个全覆盖
- CDAB 浮点解码
- JSON 配置导入导出
- 寄存器扫描探测

测试策略：纯单元测试，无 PySide6/QML 依赖，无外部网络。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.modbus.modbus_service import ModbusService

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture()
def svc() -> ModbusService:
    """已连接（仿真模式）的 ModbusService 实例。"""
    s = ModbusService()
    s.connect("192.168.1.10", 502, 1, sim_mode=True)
    return s


@pytest.fixture()
def svc_disconnected() -> ModbusService:
    """未连接的 ModbusService 实例。"""
    return ModbusService()


# ─────────────────────────────────────────────
# 1. Ping 诊断
# ─────────────────────────────────────────────

class TestPing:
    def test_ping_sim_returns_ok(self, svc: ModbusService) -> None:
        """仿真模式下 Ping 任何有效 IP 应返回成功。"""
        result = svc.ping_host("192.168.1.10")
        assert result.success is True
        assert result.latency_ms >= 0

    def test_ping_empty_ip_returns_fail(self, svc: ModbusService) -> None:
        """空字符串 IP 应返回失败。"""
        result = svc.ping_host("")
        assert result.success is False
        assert result.message  # 有错误说明

    def test_ping_zero_ip_returns_fail(self, svc: ModbusService) -> None:
        """无效 IP 0.0.0.0 应返回失败。"""
        result = svc.ping_host("0.0.0.0")
        assert result.success is False


# ─────────────────────────────────────────────
# 2. 连接管理
# ─────────────────────────────────────────────

class TestConnect:
    def test_connect_sim_mode_returns_ok(self) -> None:
        """仿真模式连接应返回 True 并更新连接状态。"""
        svc = ModbusService()
        ok, msg = svc.connect("10.0.0.1", 502, 2, sim_mode=True)
        assert ok is True
        assert svc.is_connected is True
        assert "仿真" in msg or "SIM" in msg.upper() or "握手成功" in msg

    def test_disconnect_clears_state(self, svc: ModbusService) -> None:
        """断开连接后 is_connected 应为 False。"""
        assert svc.is_connected is True
        svc.disconnect()
        assert svc.is_connected is False


# ─────────────────────────────────────────────
# 3. 寄存器读取
# ─────────────────────────────────────────────

class TestReadRegisters:
    def test_read_disconnected_returns_failure(self, svc_disconnected: ModbusService) -> None:
        """未连接时读取应失败。"""
        result = svc_disconnected.read_registers("03", 0, 5)
        assert result.success is False

    def test_read_holding_registers_fc03(self, svc: ModbusService) -> None:
        """FC03 读保持寄存器应返回指定数量的条目。"""
        result = svc.read_registers("03", 0, 8)
        assert result.success is True
        assert len(result.registers) == 8
        assert result.tx_hex  # TX 帧非空
        assert result.rx_hex  # RX 帧非空

    def test_read_coils_fc01(self, svc: ModbusService) -> None:
        """FC01 读线圈应返回 is_coil=True 的条目。"""
        result = svc.read_registers("01", 0, 4)
        assert result.success is True
        assert len(result.registers) == 4
        for entry in result.registers:
            assert entry.is_coil is True
            assert entry.dec in (0, 1)

    def test_read_input_registers_fc04(self, svc: ModbusService) -> None:
        """FC04 读输入寄存器应返回正确物理地址前缀 30001。"""
        result = svc.read_registers("04", 0, 3)
        assert result.success is True
        assert result.registers[0].physical.startswith("3")

    def test_read_report_slave_id_fc17(self, svc: ModbusService) -> None:
        """FC17 读取设备描述字应返回 1 条特殊条目。"""
        result = svc.read_registers("17", 0, 1)
        assert result.success is True
        assert len(result.registers) == 1
        assert "17" in result.registers[0].tag

    def test_read_preset_siemens_fan(self, svc: ModbusService) -> None:
        """西门子风机预设应填充有意义的标签名。"""
        result = svc.read_registers("03", 0, 4, preset="siemens_fan")
        assert result.success is True
        assert "Fan_" in result.registers[0].tag

    def test_read_holding_registers_physical_addr_prefix(self, svc: ModbusService) -> None:
        """FC03 保持寄存器第一条物理地址应为 40001+start。"""
        result = svc.read_registers("03", 5, 1)
        assert result.success is True
        assert result.registers[0].physical == "40006"  # 40001 + 5

    def test_read_returns_hex_strings(self, svc: ModbusService) -> None:
        """读取结果应包含格式正确的 Hex 字符串（0x 前缀）。"""
        result = svc.read_registers("03", 0, 2)
        assert result.success is True
        for entry in result.registers:
            assert entry.hex.startswith("0x")


# ─────────────────────────────────────────────
# 4. 寄存器写入
# ─────────────────────────────────────────────

class TestWriteRegister:
    def test_write_disconnected_returns_failure(self, svc_disconnected: ModbusService) -> None:
        """未连接时写入应失败。"""
        result = svc_disconnected.write_register("06", 0, 1234)
        assert result.success is False

    def test_write_single_register_fc06(self, svc: ModbusService) -> None:
        """FC06 写单个保持寄存器应成功并返回报文。"""
        result = svc.write_register("06", 10, 3600)
        assert result.success is True
        assert result.tx_hex
        assert "06" in result.tx_hex  # FC 字段存在

    def test_write_single_coil_fc05(self, svc: ModbusService) -> None:
        """FC05 写单个线圈应成功。"""
        result = svc.write_register("05", 0, 1)
        assert result.success is True

    def test_write_multiple_registers_fc16(self, svc: ModbusService) -> None:
        """FC16 写多个保持寄存器应成功。"""
        result = svc.write_register("16", 0, 2000)
        assert result.success is True

    def test_write_multiple_coils_fc15(self, svc: ModbusService) -> None:
        """FC15 写多个线圈应成功。"""
        result = svc.write_register("15", 0, 255)
        assert result.success is True


# ─────────────────────────────────────────────
# 5. 浮点解码
# ─────────────────────────────────────────────

class TestFloatDecode:
    def test_float_decode_cdab(self, svc: ModbusService) -> None:
        """FC03 读 2 个连续寄存器后第一条应有浮点解码值（非 '—'）。"""
        result = svc.read_registers("03", 0, 2, endian="CDAB")
        assert result.success is True
        # 第一条应包含浮点结果（非横线）
        assert result.registers[0].float_decoded != "—"


# ─────────────────────────────────────────────
# 6. 寄存器扫描
# ─────────────────────────────────────────────

class TestScanRegisters:
    def test_scan_disconnected_returns_empty(self, svc_disconnected: ModbusService) -> None:
        """未连接时扫描应返回空列表。"""
        cells = svc_disconnected.scan_registers(0, 9)
        assert cells == []

    def test_scan_returns_correct_count(self, svc: ModbusService) -> None:
        """扫描 0-9 应返回 10 个格子。"""
        cells = svc.scan_registers(0, 9)
        assert len(cells) == 10

    def test_scan_returns_active_map(self, svc: ModbusService) -> None:
        """已知活跃地址（0-7）应标记为 is_active=True。"""
        cells = svc.scan_registers(0, 15)
        active_offsets = {c.offset for c in cells if c.is_active}
        # 0-7 应全部在活跃集合中
        for expected in range(8):
            assert expected in active_offsets, f"offset {expected} should be active"


# ─────────────────────────────────────────────
# 7. JSON 配置导入导出
# ─────────────────────────────────────────────

class TestJsonConfig:
    def test_export_creates_file(self, svc: ModbusService, tmp_path: Path) -> None:
        """导出应创建 JSON 文件。"""
        out = tmp_path / "modbus_cfg.json"
        ok, msg = svc.export_config(str(out))
        assert ok is True
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["ip"] == "192.168.1.10"

    def test_import_updates_state(self, svc_disconnected: ModbusService, tmp_path: Path) -> None:
        """导入应正确更新服务内部配置。"""
        cfg = {"ip": "10.0.0.99", "port": 503, "slave_id": 5, "sim_mode": False, "version": "1.0"}
        cfg_file = tmp_path / "cfg.json"
        cfg_file.write_text(json.dumps(cfg))

        ok, msg, loaded = svc_disconnected.import_config(str(cfg_file))
        assert ok is True
        assert loaded["ip"] == "10.0.0.99"
        assert svc_disconnected._ip == "10.0.0.99"
        assert svc_disconnected._port == 503

    def test_import_bad_file_returns_failure(self, svc_disconnected: ModbusService) -> None:
        """导入不存在的文件应返回失败。"""
        ok, msg, loaded = svc_disconnected.import_config("/nonexistent/path/config.json")
        assert ok is False
        assert loaded == {}


# ─────────────────────────────────────────────
# 8. 新增读取功能码（CHG-133 补齐，CHG-136 测试覆盖）
#    FC02/07/20/22/23/24/43
# ─────────────────────────────────────────────

class TestReadNewFunctionCodes:
    """测试 CHG-133 新增的 7 个读取功能码。"""

    def test_read_discrete_inputs_fc02(self, svc: ModbusService) -> None:
        """FC02 读离散输入应返回 is_coil=True 且物理地址前缀为 1。"""
        result = svc.read_registers("02", 0, 4)
        assert result.success is True
        assert len(result.registers) == 4
        for entry in result.registers:
            assert entry.is_coil is True
            assert entry.physical.startswith("1")

    def test_read_discrete_inputs_fc02_physical_range(self, svc: ModbusService) -> None:
        """FC02 起始地址 5 时第一条物理地址应为 10006。"""
        result = svc.read_registers("02", 5, 1)
        assert result.success is True
        assert result.registers[0].physical == "10006"  # 10001 + 5

    def test_read_exception_status_fc07(self, svc: ModbusService) -> None:
        """FC07 读异常状态应返回 1 条特殊标记条目。"""
        result = svc.read_registers("07", 0, 1)
        assert result.success is True
        assert len(result.registers) == 1
        assert "FC07" in result.registers[0].tag

    def test_read_file_record_fc20(self, svc: ModbusService) -> None:
        """FC20 读文件记录应返回 4 条寄存器。"""
        result = svc.read_registers("20", 0, 4)
        assert result.success is True
        assert len(result.registers) == 4
        assert result.registers[0].physical == "40001"

    def test_read_mask_write_fc22(self, svc: ModbusService) -> None:
        """FC22 掩码写应返回当前值条目（读回）。"""
        result = svc.read_registers("22", 10, 1)
        assert result.success is True
        assert len(result.registers) == 1
        assert "Mask Write (FC22)" in result.registers[0].tag

    def test_read_write_multiple_fc23(self, svc: ModbusService) -> None:
        """FC23 读/写多寄存器应返回指定数量的寄存器。"""
        result = svc.read_registers("23", 0, 6)
        assert result.success is True
        assert len(result.registers) == 6
        assert result.registers[0].physical == "40001"

    def test_read_write_multiple_fc23_float_decode(self, svc: ModbusService) -> None:
        """FC23 读/写多寄存器 + CDAB 浮点解码应返回有效浮点值。"""
        result = svc.read_registers("23", 0, 2, endian="CDAB")
        assert result.success is True
        assert result.registers[0].float_decoded != "—"

    def test_read_fifo_queue_fc24(self, svc: ModbusService) -> None:
        """FC24 读 FIFO 队列应返回多个条目（含队列计数+数据）。"""
        result = svc.read_registers("24", 0, 4)
        assert result.success is True
        assert len(result.registers) == 4
        # FIFO 第一条为队列计数值（mock 返回 3）
        assert result.registers[0].dec == 3

    def test_read_device_identification_fc43(self, svc: ModbusService) -> None:
        """FC43 读设备标识应返回 1 条设备信息条目。"""
        result = svc.read_registers("43", 0, 1)
        assert result.success is True
        assert len(result.registers) == 1
        assert "FC43" in result.registers[0].tag


# ─────────────────────────────────────────────
# 9. 新增写入功能码（CHG-133 补齐，CHG-136 测试覆盖）
#    FC21/22
# ─────────────────────────────────────────────

class TestWriteNewFunctionCodes:
    """测试 CHG-133 新增的 2 个写入功能码。"""

    def test_write_file_record_fc21(self, svc: ModbusService) -> None:
        """FC21 写文件记录应成功并返回报文。"""
        result = svc.write_register("21", 0, 100)
        assert result.success is True
        assert result.tx_hex
        assert "FC21" in result.message

    def test_write_mask_write_register_fc22(self, svc: ModbusService) -> None:
        """FC22 掩码写寄存器应成功并返回报文。"""
        result = svc.write_register("22", 10, 255)
        assert result.success is True
        assert result.tx_hex
        assert "FC22" in result.message
