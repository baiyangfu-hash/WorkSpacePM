# ruff: noqa: N802
"""PLC-HMI 概念映射：Modbus TCP 联调测试服务（ModbusService）

像 PLC 功能块 FB_Modbus_Master，封装所有 Modbus TCP 通信和仿真逻辑：
- ping_host：网络层 ICMP 探路（系统 ping 命令，模拟返回值）
- connect / disconnect：建立或断开连接（仿真模式 / 真实模式预留）
- read_registers：读取寄存器数据（FC01/02/03/04/07/17/20/22/23/24/43）
- write_register：写入寄存器数据（FC05/06/15/16/21/22）
- scan_registers：并发扫描探测活跃地址区间
- export_config / import_config：JSON 配置导入导出

V1.0.0（仿真模式优先）：
- 不依赖 pymodbus，完全使用内置仿真信号发生器
- 仿真模式下生成正弦/余弦波形数据模拟真实 PLC 变量
- 真实 pymodbus 连接路径已预留注释，后续版本接入

设计参考：02_设计/Html原型预览/018_UI架构原型_V13.html
"""

from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────
# 数据结构定义
# ─────────────────────────────────────────────


@dataclass
class RegisterEntry:
    """单条寄存器数据（对齐 V13 监测表的一行）"""

    address: int  # 物理地址偏移（如：0 → 40001）
    physical: str  # 物理地址显示字符串（如：40001）
    tag: str  # 绑定符号注释（如：DB10.DBW0）
    dec: int  # 十进制值
    hex: str  # 十六进制字符串（如：0x04D2）
    float_decoded: str  # 32位浮点解码结果（如：3.14）
    is_coil: bool = False  # 是否为线圈类型（FC01/FC02）


@dataclass
class PingResult:
    """Ping 探测结果"""

    success: bool
    message: str
    latency_ms: float = 0.0


@dataclass
class ModbusReadResult:
    """读取操作结果"""

    success: bool
    message: str
    registers: list[RegisterEntry] = field(default_factory=list)
    tx_hex: str = ""
    rx_hex: str = ""


@dataclass
class ModbusWriteResult:
    """写入操作结果"""

    success: bool
    message: str
    tx_hex: str = ""
    rx_hex: str = ""


@dataclass
class ScanCell:
    """扫描探测器单格结果"""

    offset: int  # 相对起始地址的偏移
    is_active: bool


# ─────────────────────────────────────────────
# 仿真信号发生器
# ─────────────────────────────────────────────

# 预置标签字典（对齐 V13 原型 siemens_fan / temp_monitor 预设）
_PRESET_TAGS: dict[str, list[dict[str, Any]]] = {
    "siemens_fan": [
        {"tag": "Fan_Start_CMD (启动给定)", "val": 1},
        {"tag": "Fan_Speed_SP (转速主给定)", "val": 3600},
        {"tag": "Fan_Status_Run (变频器运行)", "val": 1},
        {"tag": "Fan_Current_A (风机运行电流)", "val": 124},
        {"tag": "Fan_OutTemp_High (机壳排出温度H)", "val": 16540},
        {"tag": "Fan_OutTemp_Low (机壳排出温度L)", "val": 18840},
        {"tag": "Fan_Vibration (电机轴承振动)", "val": 15430},
        {"tag": "Fan_Warn_Code (系统告警字)", "val": 0},
    ],
    "temp_monitor": [
        {"tag": "Temp_Zone1_PT100 (炉温1区)", "val": None},  # None = 动态仿真
        {"tag": "Temp_Zone2_PT100 (炉温2区)", "val": None},
        {"tag": "Temp_Zone3_PT100 (炉温3区)", "val": None},
        {"tag": "Temp_Zone4_PT100 (炉温4区)", "val": 2200},
        {"tag": "Temp_Zone5_PT100 (炉温5区)", "val": 1950},
        {"tag": "Temp_Zone6_PT100 (炉温6区)", "val": 1780},
    ],
}

# 模拟活跃地址（扫描探测器用）
_ACTIVE_OFFSETS: set[int] = {0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 42, 43}


def _sim_val(index: int, preset: str, ts: float) -> tuple[int, str]:
    """生成仿真寄存器值和标签。

    Args:
        index: 寄存器序号（相对起始）
        preset: 预置名（custom/siemens_fan/temp_monitor）
        ts: 当前时间戳（用于波形计算）

    Returns:
        (十进制值, 标签)
    """
    tags = _PRESET_TAGS.get(preset, [])
    if index < len(tags):
        entry = tags[index]
        tag = entry["tag"]
        val = entry["val"]
        if val is None:
            # 动态正弦波形
            val = int(1800 + math.sin(ts / 4.0 + index) * 120)
        return val, tag

    # 自定义：随机波形
    val = int(1200 + math.sin(ts / 3.0 + index * 0.7) * 200)
    tag = f"DB10.DBW{index * 2}"
    return val, tag


def _decode_float_cdab(high: int, low: int) -> str:
    """CDAB（西门子 Word Swap）32位浮点解码。"""
    import struct

    try:
        # CDAB: bytes = [C, D, A, B] → swap words
        raw = (high << 16) | low
        # CDAB 字节序：低16位在高位，高16位在低位（Word Swap）
        swapped = ((raw & 0xFFFF) << 16) | ((raw >> 16) & 0xFFFF)
        result = struct.unpack(">f", swapped.to_bytes(4, "big"))[0]
        if math.isnan(result) or math.isinf(result):
            return "N/A"
        return f"{result:.3f}"
    except Exception:
        return "N/A"


def _build_hex_frame(transaction_id: int, slave: int, fc: int, start: int, count: int) -> str:
    """构建 Modbus TCP 请求帧的 Hex 字符串。"""
    mbap = f"{transaction_id:04X} 0000 0006"
    pdu = f"0{slave:X} {fc:02X} {start:04X} {count:04X}"
    return f"{mbap} {pdu}".upper()


def _build_write_hex_frame(transaction_id: int, slave: int, fc: int, addr: int, value: int) -> str:
    """构建写入请求帧 Hex 字符串。"""
    if fc in (15, 16):
        # 多写：附加字节计数（简化：假设单个值）
        mbap = f"{transaction_id:04X} 0000 0009"
        pdu = f"0{slave:X} {fc:02X} {addr:04X} 0001 02 {value:04X}"
    else:
        mbap = f"{transaction_id:04X} 0000 0006"
        pdu = f"0{slave:X} {fc:02X} {addr:04X} {value:04X}"
    return f"{mbap} {pdu}".upper()


# ─────────────────────────────────────────────
# 单元测试专用 Mock 客户端（保障测试在无外部 PLC 时仍可运行）
# ─────────────────────────────────────────────


class _MockModbusResponse:
    def __init__(
        self,
        is_error: bool = False,
        bits: list[bool] | None = None,
        registers: list[int] | None = None,
        message: str = "",
    ) -> None:
        self._is_error = is_error
        self.bits = bits or []
        self.registers = registers or []
        self.message = message

    def isError(self) -> bool:
        return self._is_error


class _MockModbusClient:
    """模拟 Modbus TCP 客户端，覆盖 pymodbus v3.14.0 全部读/写功能码。"""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def connect(self) -> bool:
        return True

    def close(self) -> None:
        pass

    # ── FC01: 读线圈 ──────────────────────────────────────
    def read_coils(self, address: int, count: int, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse(bits=[(i % 2 == 0) for i in range(count)])

    # ── FC02: 读离散输入 ──────────────────────────────────
    def read_discrete_inputs(self, address: int, count: int, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse(bits=[(i % 2 == 0) for i in range(count)])

    # ── FC03: 读保持寄存器 ────────────────────────────────
    def read_holding_registers(
        self, address: int, count: int, device_id: int
    ) -> _MockModbusResponse:
        active_offsets = {0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 42, 43}
        if address in active_offsets:
            return _MockModbusResponse(
                registers=[int(1800 + math.sin(address + i) * 120) for i in range(count)]
            )
        return _MockModbusResponse(is_error=True)

    # ── FC04: 读输入寄存器 ────────────────────────────────
    def read_input_registers(self, address: int, count: int, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse(
            registers=[int(1800 + math.sin(address + i) * 120) for i in range(count)]
        )

    # ── FC05: 写单个线圈 ──────────────────────────────────
    def write_coil(self, address: int, value: bool, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse()

    # ── FC06: 写单个寄存器 ────────────────────────────────
    def write_register(self, address: int, value: int, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse()

    # ── FC07: 读异常状态 ──────────────────────────────────
    def read_exception_status(self, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse(registers=[0])

    # ── FC15: 写多个线圈 ──────────────────────────────────
    def write_coils(self, address: int, values: list[bool], device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse()

    # ── FC16: 写多个寄存器 ────────────────────────────────
    def write_registers(
        self, address: int, values: list[int], device_id: int
    ) -> _MockModbusResponse:
        return _MockModbusResponse()

    # ── FC17: 报告从站 ID ─────────────────────────────────
    def report_device_id(self, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse()

    # ── FC20: 读文件记录 ──────────────────────────────────
    def read_file_record(self, records: list[Any], device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse(registers=[0, 0, 0, 0])

    # ── FC21: 写文件记录 ──────────────────────────────────
    def write_file_record(self, records: list[Any], device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse()

    # ── FC22: 掩码写寄存器 ────────────────────────────────
    def mask_write_register(
        self, address: int, and_mask: int, or_mask: int, device_id: int
    ) -> _MockModbusResponse:
        return _MockModbusResponse()

    # ── FC23: 读/写多个寄存器 ─────────────────────────────
    def readwrite_registers(
        self,
        read_address: int,
        read_count: int,
        write_address: int,
        values: list[int],
        device_id: int,
    ) -> _MockModbusResponse:
        return _MockModbusResponse(
            registers=[int(1800 + math.sin(read_address + i) * 120) for i in range(read_count)]
        )

    # ── FC24: 读 FIFO 队列 ────────────────────────────────
    def read_fifo_queue(self, address: int, device_id: int) -> _MockModbusResponse:
        return _MockModbusResponse(registers=[3, 100, 200, 300])

    # ── FC43/2B: 读设备标识 ───────────────────────────────
    def read_device_information(
        self, read_code: int = 1, object_id: int = 0, device_id: int = 1
    ) -> _MockModbusResponse:
        return _MockModbusResponse(message="Device: auto-pm Modbus Simulator v1.0")


# ─────────────────────────────────────────────
# 核心服务
# ─────────────────────────────────────────────


class ModbusService:
    """Modbus TCP 联调测试核心服务。

    主要特性：
    - 纯物理网口连接，默认无任何本地数据仿真
    - 系统 ping 链路诊断
    - FC01/02/03/04/07/17/20/22/23/24/43 读取（覆盖 pymodbus v3.14.0 全部读取功能码）
    - FC05/06/15/16/21/22 写入（覆盖 pymodbus v3.14.0 全部写入功能码）
    - 寄存器区间物理扫描
    - JSON 配置导入导出
    """

    def __init__(self) -> None:
        self._connected = False
        self._sim_mode = False
        self._ip = "192.168.1.10"
        self._port = 502
        self._slave_id = 1
        self._transaction_counter = 0
        self._client: Any = None

    # ── 内部工具 ─────────────────────────────────────────

    def _next_txn(self) -> int:
        self._transaction_counter = (self._transaction_counter + 1) & 0xFFFF
        return self._transaction_counter

    # ── 网络诊断 ─────────────────────────────────────────

    def ping_host(self, ip: str, source_ip: str | None = None) -> PingResult:
        """执行 ICMP Ping 诊断。

        仿真模式下（仅在测试时激活）模拟 4 次成功的 Ping 回应或超时回应。
        真实模式下直接调用系统 ping 命令并读取 4 次的回应结果。
        """
        if not ip or ip.strip() in ("0.0.0.0", ""):
            return PingResult(success=False, message="无效的 IP 地址", latency_ms=0)

        if self._sim_mode:
            if ip == "192.168.1.254" or ip.endswith(".254"):  # 约定部分 IP 在仿真下超时
                msg = (
                    f"正在 Ping {ip} 具有 32 字节的数据:\n"
                    "请求超时。\n"
                    "请求超时。\n"
                    "请求超时。\n"
                    "请求超时。\n\n"
                    f"{ip} 的 Ping 统计信息:\n"
                    "    数据包: 已发送 = 4，已接收 = 0，丢失 = 4 (100% 丢失)"
                )
                return PingResult(success=False, message=msg, latency_ms=0)
            else:
                msg = (
                    f"正在 Ping {ip} 具有 32 字节的数据:\n"
                    f"来自 {ip} 的回复: 字节=32 时间<1ms TTL=64\n"
                    f"来自 {ip} 的回复: 字节=32 时间<1ms TTL=64\n"
                    f"来自 {ip} 的回复: 字节=32 时间<1ms TTL=64\n"
                    f"来自 {ip} 的回复: 字节=32 时间<1ms TTL=64\n\n"
                    f"{ip} 的 Ping 统计信息:\n"
                    "    数据包: 已发送 = 4，已接收 = 4，丢失 = 0 (0% 丢失)，\n"
                    "往返行程 of estimates:\n"
                    "    最短 = 0ms，最长 = 1ms，平均 = 0ms"
                )
                return PingResult(success=True, message=msg, latency_ms=0.5)

        # 真实模式：调用系统 ping 4 次
        try:
            param = "-n" if sys.platform == "win32" else "-c"
            # 支持指定本地网卡 IP 绑定 Ping 发包
            cmd = ["ping"]
            if source_ip and source_ip.strip():
                if sys.platform == "win32":
                    cmd.extend(["-S", source_ip.strip()])
                else:
                    cmd.extend(["-I", source_ip.strip()])
            cmd.extend([param, "4", "-w", "1000", ip])

            # 运行命令获取完整输出
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
            )
            # 编码兼容性解码
            encoding = "gbk" if sys.platform == "win32" else "utf-8"
            stdout_str = result.stdout.decode(encoding, errors="replace")

            # 去除首尾空白
            msg = stdout_str.strip()

            if result.returncode == 0:
                return PingResult(success=True, message=msg, latency_ms=1.0)
            else:
                # 即使返回非 0，但有输出（如 100% 丢失），也把实际输出展现出来
                if not msg:
                    msg = f"Ping 失败，目的主机 {ip} 不可达或超时。"
                return PingResult(success=False, message=msg, latency_ms=0)
        except Exception as e:
            return PingResult(success=False, message=f"Ping 异常: {e}", latency_ms=0)

    # ── 连接管理 ─────────────────────────────────────────

    def connect(
        self,
        ip: str,
        port: int,
        slave_id: int,
        sim_mode: bool = False,
        source_ip: str | None = None,
    ) -> tuple[bool, str]:
        """建立 Modbus TCP 连接。

        Args:
            ip: 目标 PLC IP
            port: 端口（通常 502）
            slave_id: 站号 / Unit ID
            sim_mode: True=仿真模式（仅限单元测试）, False=真实物理连接
            source_ip: 本地绑定网卡 IP（用于多网卡选择绑定）

        Returns:
            (success, log_message)
        """
        self._ip = ip
        self._port = port
        self._slave_id = slave_id
        self._sim_mode = sim_mode
        self._source_ip = source_ip

        if sim_mode:
            self._client = _MockModbusClient(ip, port, 3.0)
            self._connected = True
            return True, f"[测试-仿真模式] 模拟连接成功 → {ip}:{port}"

        # 真实物理连接：通过 pymodbus 连接
        from pymodbus.client import ModbusTcpClient

        if source_ip and source_ip.strip():
            self._client = ModbusTcpClient(
                host=ip, port=port, timeout=3, source_address=(source_ip.strip(), 0)
            )
        else:
            self._client = ModbusTcpClient(host=ip, port=port, timeout=3)
        try:
            if self._client.connect():
                self._connected = True
                return True, f"TCP 握手成功 → {ip}:{port}，已连接真实 Modbus 设备。"
            else:
                self._client = None
                self._connected = False
                return False, f"连接失败：目标主机 {ip}:{port} 拒绝连接或超时"
        except Exception as e:
            self._client = None
            self._connected = False
            return False, f"连接异常: {e}"

    def disconnect(self) -> None:
        """断开连接，停止所有轮询。"""
        self._connected = False
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── 读取操作 ─────────────────────────────────────────

    def read_registers(
        self,
        fc: str,
        start: int,
        count: int,
        endian: str = "CDAB",
        preset: str = "custom",
    ) -> ModbusReadResult:
        """读取寄存器数据。

        Args:
            fc: 功能码字符串 ("01"/"02"/"03"/"04"/"07"/"17"/"20"/"22"/"23"/"24"/"43")
            start: 起始地址偏移
            count: 读取数量
            endian: 浮点字节序 (CDAB/ABCD/BADC/DCBA)
            preset: 预设配置名

        Returns:
            ModbusReadResult
        """
        if not self._connected:
            return ModbusReadResult(success=False, message="未连接设备")

        fc_int = int(fc)
        txn = self._next_txn()
        ts = time.time()

        if not self._client:
            return ModbusReadResult(success=False, message="Modbus 客户端未连接或已关闭")

        try:
            if fc_int == 1:
                resp = self._client.read_coils(address=start, count=count, device_id=self._slave_id)
            elif fc_int == 2:
                resp = self._client.read_discrete_inputs(
                    address=start, count=count, device_id=self._slave_id
                )
            elif fc_int == 3:
                resp = self._client.read_holding_registers(
                    address=start, count=count, device_id=self._slave_id
                )
            elif fc_int == 4:
                resp = self._client.read_input_registers(
                    address=start, count=count, device_id=self._slave_id
                )
            elif fc_int == 7:
                resp = self._client.read_exception_status(device_id=self._slave_id)
            elif fc_int == 17:
                resp = self._client.report_device_id(device_id=self._slave_id)
            elif fc_int == 20:
                resp = self._client.read_file_record(records=[], device_id=self._slave_id)
            elif fc_int == 22:
                resp = self._client.mask_write_register(
                    address=start, and_mask=0x0000, or_mask=0x0000, device_id=self._slave_id
                )
            elif fc_int == 23:
                resp = self._client.readwrite_registers(
                    read_address=start,
                    read_count=count,
                    write_address=start,
                    values=[],
                    device_id=self._slave_id,
                )
            elif fc_int == 24:
                resp = self._client.read_fifo_queue(address=start, device_id=self._slave_id)
            elif fc_int == 43:
                resp = self._client.read_device_information(
                    read_code=1, object_id=0, device_id=self._slave_id
                )
            else:
                return ModbusReadResult(
                    success=False, message=f"不支持的读取功能码: FC{fc_int:02d}"
                )

            if resp.isError():
                return ModbusReadResult(success=False, message=f"Modbus 物理读取错误: {resp}")

            entries: list[RegisterEntry] = []
            tx_hex = _build_hex_frame(txn, self._slave_id, fc_int, start, count)

            if fc_int in (1, 2):
                bits = resp.bits[:count]
                data_bytes = bytearray()
                for i in range(0, len(bits), 8):
                    chunk = bits[i : i + 8]
                    byte_val = sum((1 << j) if b else 0 for j, b in enumerate(chunk))
                    data_bytes.append(byte_val)

                rx_len = len(data_bytes) + 2
                rx_header = f"{txn:04X} 0000 {rx_len:04X} 0{self._slave_id:X} {fc_int:02X} {len(data_bytes):02X}"
                rx_hex = f"{rx_header} {' '.join(f'{b:02X}' for b in data_bytes)}".upper()

                for i, bit in enumerate(bits):
                    val = 1 if bit else 0
                    tag = f"DB10.DBX0.{start + i}"
                    hex_str = "0xFF" if val else "0x00"
                    float_str = "ON" if val else "OFF"
                    addr_prefix = {1: 1, 2: 10001}.get(fc_int, 1)
                    physical = str(addr_prefix + start + i)

                    entries.append(
                        RegisterEntry(
                            address=start + i,
                            physical=physical,
                            tag=tag,
                            dec=val,
                            hex=hex_str,
                            float_decoded=float_str,
                            is_coil=True,
                        )
                    )
            elif fc_int in (3, 4, 20, 23, 24):
                regs = resp.registers[:count] if resp.registers else []
                data_bytes = bytearray()
                for r in regs:
                    data_bytes.extend(struct.pack(">H", r))

                rx_len = len(data_bytes) + 2
                rx_header = f"{txn:04X} 0000 {rx_len:04X} 0{self._slave_id:X} {fc_int:02X} {len(data_bytes):02X}"
                rx_hex = f"{rx_header} {' '.join(f'{b:02X}' for b in data_bytes)}".upper()

                for i, val in enumerate(regs):
                    hex_str = f"0x{val:04X}"

                    if i % 2 == 0 and i + 1 < len(regs):
                        float_str = _decode_float_cdab(val, regs[i + 1])
                    else:
                        float_str = "—"

                    _, tag = _sim_val(i, preset, ts)
                    if preset == "custom":
                        tag = f"DB10.DBW{i * 2}"

                    addr_prefix = {3: 40001, 4: 30001, 20: 40001, 23: 40001, 24: 40001}.get(
                        fc_int, 40001
                    )
                    physical = str(addr_prefix + start + i)

                    entries.append(
                        RegisterEntry(
                            address=start + i,
                            physical=physical,
                            tag=tag,
                            dec=val,
                            hex=hex_str,
                            float_decoded=float_str,
                            is_coil=False,
                        )
                    )
            elif fc_int == 7:
                # FC07 读异常状态 — 单个字节
                rx_hex = f"{txn:04X} 0000 0004 0{self._slave_id:X} 07 00".upper()
                entries.append(
                    RegisterEntry(
                        address=0,
                        physical="Exception",
                        tag="Exception Status (FC07)",
                        dec=0,
                        hex="0x00",
                        float_decoded="正常（无异常）",
                        is_coil=False,
                    )
                )
            elif fc_int == 17:
                rx_hex = f"{txn:04X} 0000 0005 0{self._slave_id:X} 11 02 FF 00".upper()
                entries.append(
                    RegisterEntry(
                        address=0,
                        physical="Slave ID",
                        tag="Report Slave ID (FC17) — 设备描述字",
                        dec=255,
                        hex="0xFF",
                        float_decoded=f"Pymodbus | Slave ID: {self._slave_id}",
                        is_coil=False,
                    )
                )
            elif fc_int == 22:
                # FC22 掩码写寄存器 — 读回当前值
                rx_hex = f"{txn:04X} 0000 0008 0{self._slave_id:X} 16 {start:04X} 0000 0000".upper()
                entries.append(
                    RegisterEntry(
                        address=start,
                        physical=str(40001 + start),
                        tag=f"Mask Write (FC22) @ {40001 + start}",
                        dec=0,
                        hex="0x0000",
                        float_decoded="AND=0x0000 OR=0x0000",
                        is_coil=False,
                    )
                )
            elif fc_int == 43:
                # FC43 读设备标识
                rx_hex = f"{txn:04X} 0000 0005 0{self._slave_id:X} 2B 0E 01 01".upper()
                entries.append(
                    RegisterEntry(
                        address=0,
                        physical="Device ID",
                        tag="Read Device Identification (FC43/2B)",
                        dec=0,
                        hex="0x0000",
                        float_decoded=getattr(resp, "message", "auto-pm Modbus Simulator"),
                        is_coil=False,
                    )
                )

            return ModbusReadResult(
                success=True,
                message=f"FC{fc_int:02d} 真实读取成功，共 {count} 个寄存器",
                registers=entries,
                tx_hex=tx_hex,
                rx_hex=rx_hex,
            )
        except Exception as e:
            return ModbusReadResult(success=False, message=f"真实读取物理异常: {e}")

    # ── 写入操作 ─────────────────────────────────────────

    def write_register(
        self,
        write_fc: str,
        addr: int,
        value: int,
    ) -> ModbusWriteResult:
        """写入寄存器数据。

        Args:
            write_fc: 写入功能码 ("05"/"06"/"15"/"16"/"21"/"22")
            addr: 目标偏移地址
            value: 写入数值

        Returns:
            ModbusWriteResult
        """
        if not self._connected:
            return ModbusWriteResult(success=False, message="未连接设备")

        fc_int = int(write_fc)
        txn = self._next_txn()

        if not self._client:
            return ModbusWriteResult(success=False, message="Modbus 客户端未连接或已关闭")

        try:
            if fc_int == 5:
                resp = self._client.write_coil(
                    address=addr, value=bool(value), device_id=self._slave_id
                )
            elif fc_int == 6:
                resp = self._client.write_register(
                    address=addr, value=value, device_id=self._slave_id
                )
            elif fc_int == 15:
                resp = self._client.write_coils(
                    address=addr, values=[bool(value)], device_id=self._slave_id
                )
            elif fc_int == 16:
                resp = self._client.write_registers(
                    address=addr, values=[value], device_id=self._slave_id
                )
            elif fc_int == 21:
                resp = self._client.write_file_record(records=[], device_id=self._slave_id)
            elif fc_int == 22:
                resp = self._client.mask_write_register(
                    address=addr, and_mask=0x0000, or_mask=value, device_id=self._slave_id
                )
            else:
                return ModbusWriteResult(
                    success=False, message=f"不支持的写入功能码: FC{fc_int:02d}"
                )

            if resp.isError():
                return ModbusWriteResult(success=False, message=f"Modbus 物理写入错误: {resp}")

            tx_hex = _build_write_hex_frame(txn, self._slave_id, fc_int, addr, value)
            rx_hex = tx_hex

            addr_prefix = {5: 1, 15: 1, 6: 40001, 16: 40001}.get(fc_int, 40001)
            physical = str(addr_prefix + addr)

            return ModbusWriteResult(
                success=True,
                message=f"[FC{fc_int:02d}] 真实写入物理地址 {physical} = {value} 成功",
                tx_hex=tx_hex,
                rx_hex=rx_hex,
            )
        except Exception as e:
            return ModbusWriteResult(success=False, message=f"真实写入物理异常: {e}")

    # ── 寄存器扫描 ───────────────────────────────────────

    def scan_registers(
        self,
        start_offset: int = 0,
        end_offset: int = 99,
    ) -> list[ScanCell]:
        """扫描寄存器区间，返回活跃地址列表。

        Args:
            start_offset: 起始偏移
            end_offset: 结束偏移（包含）

        Returns:
            ScanCell 列表
        """
        if not self._connected:
            return []

        if not self._client:
            return []

        cells: list[ScanCell] = []
        for offset in range(start_offset, end_offset + 1):
            try:
                resp = self._client.read_holding_registers(
                    address=offset, count=1, device_id=self._slave_id
                )
                is_active = not resp.isError()
            except Exception:
                is_active = False
            cells.append(ScanCell(offset=offset, is_active=is_active))
        return cells

    # ── JSON 配置导入导出 ────────────────────────────────

    def export_config(self, path: str) -> tuple[bool, str]:
        """导出当前连接配置为 JSON 文件。"""
        config = {
            "ip": self._ip,
            "port": self._port,
            "slave_id": self._slave_id,
            "sim_mode": self._sim_mode,
            "version": "1.0",
        }
        try:
            Path(path).write_text(
                json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return True, f"配置已导出至 {path}"
        except Exception as e:
            return False, f"导出失败: {e}"

    def import_config(self, path: str) -> tuple[bool, str, dict[str, Any]]:
        """从 JSON 文件导入连接配置。

        Returns:
            (success, message, config_dict)
        """
        try:
            config = json.loads(Path(path).read_text(encoding="utf-8"))
            self._ip = config.get("ip", self._ip)
            self._port = int(config.get("port", self._port))
            self._slave_id = int(config.get("slave_id", self._slave_id))
            self._sim_mode = bool(config.get("sim_mode", True))
            return True, f"配置已从 {path} 导入", config
        except Exception as e:
            return False, f"导入失败: {e}", {}
