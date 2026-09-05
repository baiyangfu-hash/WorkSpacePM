# ruff: noqa: N802, N815
"""PLC-HMI 概念映射：HMI 变量表（Modbus 域）

像 HMI 触摸屏的变量表，定义了 QML 画面能访问的所有 Modbus 联调相关变量和方法：
- @Signal = HMI 变量变化事件（Python 推送数据回 QML 刷新画面）
- @Slot   = HMI 按钮触发的脚本（QML 调用 → 后台 ModbusService 执行）

V1.0.0 接口设计原则：
- 所有 Slot 返回类型与 QML 兼容（bool/str/list/"QVariant"）
- 耗时操作（scan）在 QThread 中执行并通过 Signal 异步回传进度
- 轮询模式使用 QTimer 定时触发（频率：1000ms，由 QML 控制开关）

设计参考：02_设计/Html原型预览/018_UI架构原型_V13.html
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from auto_pm.domain.modbus.modbus_service import ModbusService
from auto_pm.infrastructure.error_handling.error_mapper import IndustrialErrorMapper

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 后台扫描任务（QRunnable → QThreadPool）
# ─────────────────────────────────────────────


class _ScanWorkerSignals(QObject):
    """扫描任务信号容器（QRunnable 不能继承 QObject，故独立）"""

    cellResult = Signal(int, bool)  # (offset, is_active)
    finished = Signal()


class _ScanWorker(QRunnable):
    """在线程池后台执行寄存器扫描探测。"""

    def __init__(self, service: ModbusService, start: int, end: int) -> None:
        super().__init__()
        self.service = service
        self.start_offset = start
        self.end_offset = end
        self.signals = _ScanWorkerSignals()

    def run(self) -> None:
        import time as _time

        cells = self.service.scan_registers(self.start_offset, self.end_offset)
        for cell in cells:
            self.signals.cellResult.emit(cell.offset, cell.is_active)
            _time.sleep(0.05)  # 渐进展示节奏（50ms/格）
        self.signals.finished.emit()


class _PingWorkerSignals(QObject):
    """Ping 任务信号容器"""

    finished = Signal(bool, str)


class _PingWorker(QRunnable):
    """在后台执行 Ping 探测，不阻塞 UI 线程。"""

    def __init__(self, service: ModbusService, ip: str, source_ip: str = "") -> None:
        super().__init__()
        self.service = service
        self.ip = ip
        self.source_ip = source_ip
        self.signals = _PingWorkerSignals()

    def run(self) -> None:
        result = self.service.ping_host(self.ip, self.source_ip)
        self.signals.finished.emit(result.success, result.message)


# ─────────────────────────────────────────────
# QML Bridge
# ─────────────────────────────────────────────


class ModbusBridge(QObject):
    """Modbus TCP 联调工坊 QML 桥接层。

    通过 rootContext().setContextProperty("modbusBridge", bridge)
    暴露给 QML，使用命名规范：camelCase（对齐 QML 惯例）。

    Signals（Python → QML，异步数据推送）：
        registerDataReceived(list)      — 寄存器扫描结果批量推送
        consoleLogAppended(str, str)    — 报文日志追加 (type, hex_str)
        connectionStateChanged(bool)    — 连接状态变更
        pingResultReceived(bool, str)   — Ping 探测结果
        scanCellUpdated(int, bool)      — 单格扫描进度 (offset, is_active)
        scanFinished()                  — 扫描完成
    """

    # ── Signals ──────────────────────────────────────────
    registerDataReceived = Signal(list)
    consoleLogAppended = Signal(str, str)
    connectionStateChanged = Signal(bool)
    pingResultReceived = Signal(bool, str)
    scanCellUpdated = Signal(int, bool)
    scanFinished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = ModbusService()
        self._poll_timer: QTimer | None = None
        self._pool = QThreadPool.globalInstance()

    # ── 内部工具 ─────────────────────────────────────────

    def _log(self, log_type: str, hex_str: str) -> None:
        """推送报文到 QML 控制台。log_type: 'TX'/'RX'/'SYS'/'PING'"""
        self.consoleLogAppended.emit(log_type, hex_str)

    # ── Ping 诊断 ─────────────────────────────────────────

    @Slot(str)
    @Slot(str, str)
    def pingHost(self, ip: str, source_ip: str = "") -> None:
        """执行 Ping 探测，结果通过 pingResultReceived Signal 异步推送。

        Args:
            ip: 目标 PLC IP 地址
            source_ip: 本地网卡 IP
        """
        self._log(
            "PING",
            f"发起 ICMP PING 探测 → {ip} (网卡绑定: {source_ip if source_ip else '自动'})...",
        )
        worker = _PingWorker(self._service, ip, source_ip)
        worker.signals.finished.connect(self._on_ping_finished)
        self._pool.start(worker)

    def _on_ping_finished(self, success: bool, msg: str) -> None:
        self._log("PING" if success else "ERR", msg)
        self.pingResultReceived.emit(success, msg)

    # ── 网卡管理 ─────────────────────────────────────────

    @Slot(result="QVariant")
    def getNetworkInterfaces(self) -> list[dict[str, str]]:
        """获取本地全部 IPv4 物理网卡列表，供 QML 绑定选择。"""
        import socket

        interfaces = []
        # 默认自动选择项
        interfaces.append({"name": "自动选择 (Auto Default)", "ip": ""})
        try:
            import psutil

            for name, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        interfaces.append({"name": f"{name} ({addr.address})", "ip": addr.address})
        except ImportError:
            # 正常无 psutil 时直接使用标准库 socket，无需警告
            try:
                hostname = socket.gethostname()
                _, _, ip_list = socket.gethostbyname_ex(hostname)
                for ip in ip_list:
                    interfaces.append({"name": f"LAN ({ip})", "ip": ip})
            except Exception:
                pass
        except Exception as e:
            log.debug(f"获取网卡列表异常: {e}")
            try:
                hostname = socket.gethostname()
                _, _, ip_list = socket.gethostbyname_ex(hostname)
                for ip in ip_list:
                    interfaces.append({"name": f"LAN ({ip})", "ip": ip})
            except Exception:
                pass
        return interfaces

    # ── 连接管理 ─────────────────────────────────────────

    @Slot(str, int, int, bool, str)
    def connectDevice(
        self, ip: str, port: int, slave_id: int, sim_mode: bool, source_ip: str
    ) -> None:
        """建立 Modbus TCP 连接。

        Args:
            ip: 目标 PLC IP
            port: 端口（通常 502）
            slave_id: 站号
            sim_mode: 是否启用仿真模式
            source_ip: 本地绑定网卡 IP
        """
        try:
            self._log(
                "SYS",
                f"发起 TCP Socket 握手 → {ip}:{port} Unit={slave_id} sim={sim_mode} bind={source_ip if source_ip else 'Auto'}",
            )
            ok, msg = self._service.connect(ip, port, slave_id, sim_mode, source_ip)
            if not ok:
                msg = IndustrialErrorMapper.format_exception(msg)
            self._log("SYS" if ok else "ERR", msg)
            self.connectionStateChanged.emit(ok)
        except Exception as e:
            log.warning("connectDevice error: %s", e, exc_info=True)
            self._log("ERR", IndustrialErrorMapper.format_exception(e))
            self.connectionStateChanged.emit(False)

    @Slot()
    def disconnectDevice(self) -> None:
        """断开连接，停止轮询和趋势图定时器。"""
        self._stop_poll()
        self._service.disconnect()
        self._log("SYS", "已断开 Modbus TCP 连接，所有定时任务已终止。")
        self.connectionStateChanged.emit(False)

    # ── 读取操作 ─────────────────────────────────────────

    @Slot(str, int, int, str, str)
    def readRegisters(
        self,
        fc: str,
        start: int,
        count: int,
        endian: str,
        preset: str,
    ) -> None:
        """读取寄存器，结果通过 registerDataReceived Signal 推送。

        Args:
            fc: 功能码字符串
            start: 起始偏移
            count: 读取数量
            endian: 字节序
            preset: 预设名称
        """
        try:
            result = self._service.read_registers(fc, start, count, endian, preset)
            if result.tx_hex:
                self._log("TX", result.tx_hex)
            if result.rx_hex:
                self._log("RX", result.rx_hex)
            if result.success:
                # 转为 list[dict] 推送给 QML
                data = [asdict(r) for r in result.registers]
                self.registerDataReceived.emit(data)
            else:
                self._log("ERR", IndustrialErrorMapper.format_exception(result.message))
        except Exception as e:
            log.warning("readRegisters error: %s", e, exc_info=True)
            self._log("ERR", IndustrialErrorMapper.format_exception(e))

    # ── 写入操作 ─────────────────────────────────────────

    @Slot(str, int, str)
    def writeRegister(self, write_fc: str, addr: int, value_str: str) -> None:
        """写入寄存器数据。

        Args:
            write_fc: 写入功能码
            addr: 偏移地址
            value_str: 数值（字符串，支持整数或浮点）
        """
        try:
            value = int(float(value_str))
        except ValueError:
            self._log(
                "ERR", IndustrialErrorMapper.format_exception(f"写入数值格式错误: '{value_str}'")
            )
            return

        try:
            result = self._service.write_register(write_fc, addr, value)
            if result.tx_hex:
                self._log("TX", result.tx_hex)
            if result.rx_hex:
                self._log("RX", result.rx_hex)
            if result.success:
                self._log("SYS", result.message)
            else:
                self._log("ERR", IndustrialErrorMapper.format_exception(result.message))
        except Exception as e:
            log.warning("writeRegister error: %s", e, exc_info=True)
            self._log("ERR", IndustrialErrorMapper.format_exception(e))

    # ── 轮询控制 ─────────────────────────────────────────

    @Slot(bool, str, int, int, str, str)
    def setPolling(
        self,
        enabled: bool,
        fc: str,
        start: int,
        count: int,
        endian: str,
        preset: str,
    ) -> None:
        """启动或停止周期性轮询（1000ms）。

        Args:
            enabled: True=启动, False=停止
            其余参数透传给 readRegisters
        """
        if enabled:
            self._start_poll(fc, start, count, endian, preset)
        else:
            self._stop_poll()

    def _start_poll(self, fc: str, start: int, count: int, endian: str, preset: str) -> None:
        self._stop_poll()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(
            lambda: self.readRegisters(fc, start, count, endian, preset)
        )
        self._poll_timer.start()
        self._log("SYS", "周期性轮询已启动（间隔 1000ms）。")

    def _stop_poll(self) -> None:
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None
            self._log("SYS", "周期性轮询已停止。")

    # ── 寄存器扫描 ───────────────────────────────────────

    @Slot(int, int)
    def scanRegisters(self, start_offset: int, end_offset: int) -> None:
        """在后台线程池中执行寄存器扫描探测。

        进度通过 scanCellUpdated(offset, is_active) 逐格推送，
        完成后发射 scanFinished()。
        """
        if not self._service.is_connected:
            self._log("ERR", "请先连接 Modbus TCP 设备再执行扫描！")
            return

        self._log(
            "SYS",
            f"[扫描开始] 并发探测保持寄存器 [{40001 + start_offset} - {40001 + end_offset}]...",
        )
        worker = _ScanWorker(self._service, start_offset, end_offset)
        worker.signals.cellResult.connect(self.scanCellUpdated)
        worker.signals.finished.connect(self.scanFinished)
        worker.signals.finished.connect(
            lambda: self._log(
                "SYS", "[扫描完成] 活跃物理通道已用绿色标出，不可达通道已用红色标出。"
            )
        )
        self._pool.start(worker)

    # ── JSON 配置 ─────────────────────────────────────────

    @Slot(str, result=bool)
    def exportConfig(self, path: str) -> bool:
        """导出配置到 JSON 文件。"""
        try:
            ok, msg = self._service.export_config(path)
            if not ok:
                msg = IndustrialErrorMapper.format_exception(msg)
            self._log("SYS" if ok else "ERR", msg)
            return ok
        except Exception as e:
            log.warning("exportConfig error: %s", e, exc_info=True)
            self._log("ERR", IndustrialErrorMapper.format_exception(e))
            return False

    @Slot(str, result="QVariant")
    def importConfig(self, path: str) -> dict[str, Any]:
        """从 JSON 文件导入配置。返回配置字典供 QML 填充表单。"""
        try:
            ok, msg, config = self._service.import_config(path)
            if not ok:
                msg = IndustrialErrorMapper.format_exception(msg)
            self._log("SYS" if ok else "ERR", msg)
            return config if ok else {}
        except Exception as e:
            log.warning("importConfig error: %s", e, exc_info=True)
            self._log("ERR", IndustrialErrorMapper.format_exception(e))
            return {}

    # ── 连接状态查询 ─────────────────────────────────────

    @Slot(result=bool)
    def isConnected(self) -> bool:
        """供 QML 同步查询连接状态。"""
        return self._service.is_connected
