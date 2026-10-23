"""PLC-HMI 概念映射：HMI 变量表（Modbus 域）

像 HMI 触摸屏的变量表，定义了 QML 画面能访问的所有 Modbus 联调相关变量和方法：
- @Signal = HMI 变量变化事件（Python 推送数据回 QML 刷新画面）
- @Slot   = HMI 按钮触发的脚本（QML 调用 → 后台 ModbusService 执行）

V1.0.0 接口设计原则：
- 所有 Slot 返回类型与 QML 兼容（bool/str/list/"QVariant"）
- 所有碰网络的操作（连接/读/写/轮询/扫描/Ping）都在线程池执行，界面线程不等设备；
  子线程只写结果，主线程 QTimer 轮询后用 Signal 回传；后台出错一律回传失败原因
- 扫描逐格推进度，可停止；设备连续不回话或超总时限即判失败（scanFailed），不会卡在“扫描中”
- 同一 pymodbus 客户端的收发用 _io_lock 串行（扫描与轮询/手动读写不串包）
- 轮询模式使用 QTimer 定时触发（频率：1000ms，由 QML 控制开关）；上一次读取未返回时本拍跳过

设计参考：02_设计/Html原型预览/018_UI架构原型_V13.html
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from time import monotonic
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from auto_pm.domain.modbus.modbus_service import ModbusService
from auto_pm.infrastructure.error_handling.error_mapper import IndustrialErrorMapper

log = logging.getLogger(__name__)

# 扫描保护：设备连续这么多格不回话就判失败（pymodbus 每格超时 3 s × 重试，约 12 s/格）
SCAN_SILENT_CELL_LIMIT = 2
# 扫描总时限（秒）：超过即中止并报失败，已扫到的格子保留
SCAN_TIME_LIMIT_S = 60.0


# ─────────────────────────────────────────────
# 后台任务（QRunnable → QThreadPool）
# 结果回传沿用 file_watcher_bridge / pm_cockpit_bridge 的轮询方案：run() 只写普通属性，
# 不从子线程发 Qt 信号；bridge 的主线程 QTimer 读取后再发信号。run() 任何异常都落到
# error 并置 done，界面一定能退出“忙”状态。
# ─────────────────────────────────────────────

class _IoWorker(QRunnable):
    """在线程池执行一次网络操作（连接/读/写/Ping）；lock 不为空时持锁执行。"""

    def __init__(self, fn: Callable[[], Any], lock: threading.Lock | None = None) -> None:
        super().__init__()
        self._fn = fn
        self._lock = lock
        self.setAutoDelete(False)
        self.result: Any = None
        self.error: BaseException | None = None
        self.thread_id: int | None = None
        self.done = False

    def run(self) -> None:
        self.thread_id = threading.get_ident()
        try:
            if self._lock is None:
                self.result = self._fn()
            else:
                with self._lock:
                    self.result = self._fn()
        except Exception as e:  # noqa: BLE001 - worker must always release the UI
            log.warning("modbus worker failed: %s", e, exc_info=True)
            self.error = e
        finally:
            self.done = True


class _ScanWorker(QRunnable):
    """在线程池后台逐格探测寄存器；边扫边写 cells，界面逐格显示。"""

    def __init__(
        self,
        service: ModbusService,
        start: int,
        end: int,
        lock: threading.Lock,
        silent_limit: int = SCAN_SILENT_CELL_LIMIT,
        time_limit_s: float = SCAN_TIME_LIMIT_S,
    ) -> None:
        super().__init__()
        self.service = service
        self.start_offset = start
        self.end_offset = end
        self._lock = lock
        self._silent_limit = silent_limit
        self._time_limit_s = time_limit_s
        self.setAutoDelete(False)
        self.cells: list[tuple[int, bool]] = []
        self.error = ""
        self.stop_requested = False
        self.thread_id: int | None = None
        self.done = False

    def run(self) -> None:
        self.thread_id = threading.get_ident()
        try:
            deadline = monotonic() + self._time_limit_s
            silent = 0
            for offset in range(self.start_offset, self.end_offset + 1):
                if self.stop_requested:
                    self.error = f"扫描已停止（已探测 {len(self.cells)} 格）。"
                    return
                if monotonic() > deadline:
                    self.error = (
                        f"扫描超过 {self._time_limit_s:.0f} 秒未完成，已中止（已探测 {len(self.cells)} 格）。"
                        "设备应答太慢，请缩小范围或检查网络。"
                    )
                    return
                with self._lock:
                    answer = self.service.probe_register(offset)
                self.cells.append((offset, bool(answer)))
                silent = silent + 1 if answer is None else 0
                if silent >= self._silent_limit:
                    self.error = (
                        f"设备连续 {silent} 格无应答，已中止扫描。"
                        "请检查站号、网关后面的从站是否在线。"
                    )
                    return
        except Exception as e:  # noqa: BLE001 - worker must always release the scan button
            log.warning("scan worker failed: %s", e, exc_info=True)
            self.error = IndustrialErrorMapper.format_exception(e)
        finally:
            self.done = True


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
        scanFailed(str)                 — 扫描失败/停止/超时/未连接（原因），界面据此恢复按钮
    """

    # ── Signals ──────────────────────────────────────────
    registerDataReceived = Signal(list)
    consoleLogAppended   = Signal(str, str)
    connectionStateChanged = Signal(bool)
    pingResultReceived   = Signal(bool, str)
    scanCellUpdated      = Signal(int, bool)
    scanFinished         = Signal()
    scanFailed           = Signal(str)

    _POLL_INTERVAL_MS = 50  # 主线程轮询节奏；扫描结果每拍推一格（渐进展示 50ms/格）

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = ModbusService()
        self._poll_timer: QTimer | None = None
        self._pool = QThreadPool.globalInstance()
        self._io_lock = threading.Lock()
        self._scan_worker: _ScanWorker | None = None
        self._scan_next = 0
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(self._POLL_INTERVAL_MS)
        self._scan_timer.timeout.connect(self._poll_scan)
        self._io_jobs: list[tuple[_IoWorker, Callable[[_IoWorker], None]]] = []
        self._io_timer = QTimer(self)
        self._io_timer.setInterval(self._POLL_INTERVAL_MS)
        self._io_timer.timeout.connect(self._poll_io)
        self._connect_in_flight = False
        self._read_in_flight = False
        # 连接代次：每次断开 +1；迟到的连接结果代次对不上就作废，不把界面翻回“已连接”
        self._conn_gen = 0

    # ── 内部工具 ─────────────────────────────────────────

    def _log(self, log_type: str, hex_str: str) -> None:
        """推送报文到 QML 控制台。log_type: 'TX'/'RX'/'SYS'/'PING'"""
        self.consoleLogAppended.emit(log_type, hex_str)

    def _run_io(
        self,
        fn: Callable[[], Any],
        on_done: Callable[[_IoWorker], None],
        *,
        locked: bool = True,
    ) -> _IoWorker:
        """把一次网络操作放进线程池；完成后 on_done 在主线程执行。"""
        worker = _IoWorker(fn, self._io_lock if locked else None)
        self._io_jobs.append((worker, on_done))
        self._pool.start(worker)
        self._io_timer.start()
        return worker

    def _poll_io(self) -> None:
        """主线程读取已完成的网络操作并回调（对应 _IoWorker 的轮询回传）。"""
        pending: list[tuple[_IoWorker, Callable[[_IoWorker], None]]] = []
        finished: list[tuple[_IoWorker, Callable[[_IoWorker], None]]] = []
        for job in self._io_jobs:
            (finished if job[0].done else pending).append(job)
        self._io_jobs = pending
        if not pending:
            self._io_timer.stop()
        for worker, on_done in finished:
            try:
                on_done(worker)
            except Exception as e:  # noqa: BLE001 - one bad callback must not stop the others
                log.warning("modbus callback failed: %s", e, exc_info=True)
                self._log("ERR", IndustrialErrorMapper.format_exception(e))

    # ── Ping 诊断 ─────────────────────────────────────────

    @Slot(str)
    @Slot(str, str)
    def pingHost(self, ip: str, source_ip: str = "") -> None:
        """执行 Ping 探测，结果通过 pingResultReceived Signal 异步推送。

        Args:
            ip: 目标 PLC IP 地址
            source_ip: 本地网卡 IP
        """
        self._log("PING", f"发起 ICMP PING 探测 → {ip} (网卡绑定: {source_ip if source_ip else '自动'})...")
        self._run_io(lambda: self._service.ping_host(ip, source_ip), self._on_ping_done, locked=False)

    def _on_ping_done(self, worker: _IoWorker) -> None:
        if worker.error is not None:
            self._on_ping_finished(False, f"Ping 后台异常: {IndustrialErrorMapper.format_exception(worker.error)}")
            return
        self._on_ping_finished(worker.result.success, worker.result.message)

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
    def connectDevice(self, ip: str, port: int, slave_id: int, sim_mode: bool, source_ip: str) -> None:
        """建立 Modbus TCP 连接（后台执行，结果经 connectionStateChanged 推送）。

        Args:
            ip: 目标 PLC IP
            port: 端口（通常 502）
            slave_id: 站号
            sim_mode: 是否启用仿真模式
            source_ip: 本地绑定网卡 IP
        """
        if self._connect_in_flight:
            self._log("SYS", "正在连接，请稍候。")
            return
        self._connect_in_flight = True
        gen = self._conn_gen
        self._log("SYS", f"发起 TCP Socket 握手 → {ip}:{port} Unit={slave_id} sim={sim_mode} bind={source_ip if source_ip else 'Auto'}")
        self._run_io(
            lambda: self._service.connect(ip, port, slave_id, sim_mode, source_ip),
            lambda worker: self._on_connect_done(worker, gen),
        )

    def _on_connect_done(self, worker: _IoWorker, gen: int) -> None:
        self._connect_in_flight = False
        if gen != self._conn_gen:
            # 握手期间用户点了断开：结果作废；若握手刚好成功，补关一次连接
            if worker.error is None and worker.result[0]:
                self._service.disconnect()
            self._log("SYS", "连接结果到达时已断开，已作废本次连接。")
            return
        if worker.error is not None:
            self._log("ERR", IndustrialErrorMapper.format_exception(worker.error))
            self.connectionStateChanged.emit(False)
            return
        ok, msg = worker.result
        if not ok:
            msg = IndustrialErrorMapper.format_exception(msg)
        self._log("SYS" if ok else "ERR", msg)
        self.connectionStateChanged.emit(ok)

    @Slot()
    def disconnectDevice(self) -> None:
        """断开连接，停止轮询、扫描和趋势图定时器。

        不等 _io_lock：关闭 socket 会让正在等设备的后台读取立即出错返回，界面线程不被拖住。
        """
        self._conn_gen += 1
        self._stop_poll()
        if self._scan_worker is not None:
            self._scan_worker.stop_requested = True
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
        """读取寄存器（后台执行），结果通过 registerDataReceived Signal 推送。

        Args:
            fc: 功能码字符串
            start: 起始偏移
            count: 读取数量
            endian: 字节序
            preset: 预设名称
        """
        self._start_read(fc, start, count, endian, preset, from_poll=False)

    def _start_read(
        self, fc: str, start: int, count: int, endian: str, preset: str, *, from_poll: bool
    ) -> None:
        if self._read_in_flight:
            # 设备慢时轮询会追上自己：本拍跳过，不堆积请求，也不刷屏
            if not from_poll:
                self._log("SYS", "上一次读取尚未返回，本次跳过。")
            return
        self._read_in_flight = True
        self._run_io(
            lambda: self._service.read_registers(fc, start, count, endian, preset),
            self._on_read_done,
        )

    def _on_read_done(self, worker: _IoWorker) -> None:
        self._read_in_flight = False
        if worker.error is not None:
            self._log("ERR", IndustrialErrorMapper.format_exception(worker.error))
            return
        result = worker.result
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

    # ── 写入操作 ─────────────────────────────────────────

    @Slot(str, int, str)
    def writeRegister(self, write_fc: str, addr: int, value_str: str) -> None:
        """写入寄存器数据（后台执行，结果写入控制台）。

        Args:
            write_fc: 写入功能码
            addr: 偏移地址
            value_str: 数值（字符串，支持整数或浮点）
        """
        try:
            value = int(float(value_str))
        except ValueError:
            self._log("ERR", IndustrialErrorMapper.format_exception(f"写入数值格式错误: '{value_str}'"))
            return

        self._run_io(lambda: self._service.write_register(write_fc, addr, value), self._on_write_done)

    def _on_write_done(self, worker: _IoWorker) -> None:
        if worker.error is not None:
            self._log("ERR", IndustrialErrorMapper.format_exception(worker.error))
            return
        result = worker.result
        if result.tx_hex:
            self._log("TX", result.tx_hex)
        if result.rx_hex:
            self._log("RX", result.rx_hex)
        if result.success:
            self._log("SYS", result.message)
        else:
            self._log("ERR", IndustrialErrorMapper.format_exception(result.message))

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
            lambda: self._start_read(fc, start, count, endian, preset, from_poll=True)
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

        进度通过 scanCellUpdated(offset, is_active) 逐格推送，完成后发射 scanFinished()；
        未连接、停止、设备不回话、超总时限、后台出错都发 scanFailed(原因)。
        """
        if not self._service.is_connected:
            self._fail_scan("请先连接 Modbus TCP 设备再执行扫描！")
            return
        if self._scan_worker is not None:
            # 第一次扫描仍在跑：只提示，不发 scanFailed（否则界面会提前放开按钮）
            self._log("ERR", "上一次扫描尚未结束，请稍候再试。")
            return

        self._log("SYS", f"[扫描开始] 并发探测保持寄存器 [{40001 + start_offset} - {40001 + end_offset}]...")
        worker = _ScanWorker(
            self._service,
            start_offset,
            end_offset,
            self._io_lock,
            silent_limit=SCAN_SILENT_CELL_LIMIT,
            time_limit_s=SCAN_TIME_LIMIT_S,
        )
        self._scan_worker = worker
        self._scan_next = 0
        self._pool.start(worker)
        self._scan_timer.start()

    @Slot()
    def stopScan(self) -> None:
        """请求停止扫描；当前这一格探测完（最长约一格超时）后生效，经 scanFailed 回报。"""
        if self._scan_worker is not None:
            self._scan_worker.stop_requested = True
            self._log("SYS", "[扫描] 已请求停止，等当前这一格返回...")

    def _fail_scan(self, reason: str) -> None:
        self._log("ERR", f"[扫描失败] {reason}")
        self.scanFailed.emit(reason)

    def _poll_scan(self) -> None:
        """主线程推送扫描进度：每拍一格；推完后按结果发 scanFinished 或 scanFailed。"""
        worker = self._scan_worker
        if worker is None:
            self._scan_timer.stop()
            return
        if self._scan_next < len(worker.cells):
            offset, is_active = worker.cells[self._scan_next]
            self._scan_next += 1
            self.scanCellUpdated.emit(offset, is_active)
            return
        if not worker.done:
            return
        self._scan_timer.stop()
        self._scan_worker = None
        if worker.error:
            self._fail_scan(worker.error)
            return
        self.scanFinished.emit()
        self._log("SYS", "[扫描完成] 活跃物理通道已用绿色标出，不可达通道已用红色标出。")


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
