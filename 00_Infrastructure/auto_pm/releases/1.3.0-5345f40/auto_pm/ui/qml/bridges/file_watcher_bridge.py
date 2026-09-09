"""PLC-HMI 概念映射：HMI 变量表（文件监听域）

像 HMI 触摸屏的变量表，定义了 QML 画面能访问的所有文件监听相关变量和方法：
- @Signal = HMI 变量变化事件（sync 完成后自动刷新画面）
- @Slot   = HMI 按钮触发的脚本（QML 调用 → 后台 sync）

CHG-SCPT-2026-141：消除 CLI 与 GUI 缓存鸿沟。

设计原则：
- 监听业务文件变化 → 1s 去抖 → QRunnable 后台 sync → Signal 通知 QML 刷新
- SyncWorker 自建 DB 连接，规避 SQLite 线程亲和性
  （connection.py:54 默认 check_same_thread=True，主线程连接不能在 worker 线程用）
- 后端 Service/CLI 零改动，纯 GUI 层增强

设计参考：modbus_bridge.py（QRunnable+QThreadPool 模式）
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)

if TYPE_CHECKING:
    pass

from auto_pm.delivery.constants import DIR_DELIVERY, DIR_PACKAGE

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 后台同步任务（QRunnable → QThreadPool）
# ─────────────────────────────────────────────


class _SyncWorker(QRunnable):
    """在 QThreadPool 后台执行 sync_to_cache。

    线程亲和性隔离：worker 线程内自建 DatabaseManager + ProjectService，
    规避 connection.py:54 默认 check_same_thread=True 的限制。
    完成后关闭连接，WAL 模式保证主线程下次查询能读到最新数据。

    生命周期：setAutoDelete(False) 禁止 QThreadPool 自动 delete，
    由 FileWatcherBridge._current_worker 持有 Python 引用控制。

    结果回传：worker 持有 bridge 引用，run() 完成后 emit bridge._workerFinished
    （bridge 是稳定 QObject，跨线程自动 queued 到主线程）。不使用 worker 自有
    signals——根因诊断证明 PySide6 6.11 下 QRunnable 子线程 run() 期间，关联的
    signals QObject（无论有无 parent）会被主线程事件循环析构（refcnt>0 但
    isValid=False），emit 报 "Signal source has been deleted"。
    """

    def __init__(self, workspace_root: str, bridge: FileWatcherBridge) -> None:
        super().__init__()
        self._workspace_root = workspace_root
        self._bridge = bridge  # 保留引用（轮询方案下未使用，预留扩展）
        # 禁止 C++ 自动 delete：worker 生命周期由 bridge._current_worker 控制
        self.setAutoDelete(False)
        # 结果回传：run() 写 result + done，bridge QTimer 轮询读取。
        # 轮询方案规避 PySide6 6.11 QRunnable 子线程 emit 信号时 QObject C++
        # 被主线程事件循环析构的问题（"Signal source has been deleted"）。
        # Python 属性读写受 GIL 保护，跨线程安全，不依赖 QObject C++ 有效性。
        self.result: tuple[int, int, int, str] | None = None
        self.done: bool = False

    def run(self) -> None:
        start = time.monotonic()
        db = None
        try:
            # 延迟导入，避免循环依赖；worker 线程内自建 DB 连接（线程亲和性隔离）
            from auto_pm.core.project_service import ProjectService
            from auto_pm.db.connection import DatabaseManager

            db = DatabaseManager(self._workspace_root)
            db.init_schema()
            svc = ProjectService(workspace_root=self._workspace_root, db=db)
            result = svc.sync_to_cache()

            ms = int((time.monotonic() - start) * 1000)
            # sync_to_cache 类型签名声明返回 dict[str, Any]（见 sync.py:68-82），
            # SyncService.sync() 的成功/异常两路径均返回 dict，直接按 dict 解析。
            projects = int(result.get("projects_found", 0))
            changes = int(result.get("changes_found", 0))
            status = result.get("status", "success")
            message = result.get("message", "")
            # 用 sync 自带的 duration_ms（更准确，含扫描耗时）
            duration = int(result.get("duration_ms", ms))
            error_msg = message if status == "failed" else ""
            self.result = (projects, changes, duration, error_msg)
        except Exception as exc:
            ms = int((time.monotonic() - start) * 1000)
            log.exception("SyncWorker 后台同步失败")
            self.result = (0, 0, ms, str(exc))
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
            self.done = True  # 轮询标志，最后设置（bridge QTimer 检测）


# ─────────────────────────────────────────────
# QML Bridge
# ─────────────────────────────────────────────


class FileWatcherBridge(QObject):
    """文件监听同步 QML 桥接层。

    通过 rootContext().setContextProperty("fileWatcherBridge", bridge)
    暴露给 QML，使用命名规范：camelCase（对齐 QML 惯例）。

    Signals（Python → QML，异步数据推送）：
        syncStarted()              — 同步开始（QML 显示 loading）
        syncFinished(int,int,int)  — 同步完成 (projects, changes, ms)
        syncError(str)             — 同步失败
        watcherToggled(bool)       — Watcher 开关状态变更
        pathsRefreshed(int)        — 监听目录数变更

    Slots（QML → Python）：
        syncNow()                  — 手动触发同步（同步按钮）
        toggleWatcher(bool)        — 开关监听（Watcher 开关）
        refreshPaths()             — 重新扫描业务目录
        watchedDirectoryCount()    — 查询当前监听目录数
        isWatcherEnabled()         — 查询 Watcher 是否启用
        lastSyncTime()             — 查询上次同步时间

    工作流：
        QFileSystemWatcher 监听业务目录
          → fileChanged/directoryChanged 重启 1s 去抖定时器
          → timeout 触发 _SyncWorker（QThreadPool 后台）
          → worker 自建 DB 连接调 sync_to_cache()
          → syncFinished Signal 回主线程
          → QML 画面自动刷新
    """

    # ── 噪声目录排除清单（基于 .gitignore + 工具产物）──────
    NOISE_DIRS: frozenset[str] = frozenset(
        {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            ".ruff_cache",
            ".mypy_cache",
            ".pytest_cache",
            ".hypothesis",
            ".dmypy.json",
            "node_modules",
            ".idea",
            ".vscode",
            DIR_DELIVERY,
            DIR_PACKAGE,
            "output",
            "test_screenshots",
            ".auto-pm",
            "dist",
            "build",
            "reports",
            "htmlcov",
            "coverage",
            ".benchmarks",
            "test_reports",
            ".trae",
            "target",
            "bin",
            "obj",
        }
    )

    # 监听目录硬上限（超限降级为精简模式，停止扫描）
    MAX_DIRECTORIES = 5000

    # ── Signals ──────────────────────────────────────────
    syncStarted = Signal()
    syncFinished = Signal(int, int, int)  # projects, changes, ms
    syncError = Signal(str)
    watcherToggled = Signal(bool)
    pathsRefreshed = Signal(int)

    def __init__(self, workspace_root: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._workspace_root = workspace_root
        self._watcher = QFileSystemWatcher(self)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(1000)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)
        self._pool = QThreadPool.globalInstance()

        # 并发控制状态
        self._sync_in_progress = False
        self._pending_sync = False
        self._reload_pending = False
        self._watcher_enabled = False
        self._last_sync_time = ""
        # 持有当前 worker 引用，防止 Python wrapper 被 GC
        self._current_worker: _SyncWorker | None = None

        # 轮询定时器：检测 worker.done，读取 result 回调 _on_sync_finished。
        # 规避 PySide6 6.11 QRunnable 子线程 emit 信号时 QObject 被析构的问题
        # （"Signal source has been deleted"）。Python 属性跨线程读写受 GIL 保护。
        self._poll_timer = QTimer(self)
        self._poll_timer.setSingleShot(False)
        self._poll_timer.setInterval(50)  # 50ms 轮询
        self._poll_timer.timeout.connect(self._poll_worker)

        # 信号连接
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

    # ── Slots（供 QML 调用）──────────────────────────────

    @Slot()
    def syncNow(self) -> None:
        """手动触发同步（同步按钮点击）。

        若 sync 进行中，标记 pending，完成后补一次。
        """
        if self._reload_pending:
            log.debug("reload_pending，忽略 syncNow")
            return
        if self._sync_in_progress:
            self._pending_sync = True
            return
        self._start_sync()

    @Slot(bool)
    def toggleWatcher(self, enabled: bool) -> None:
        """开关文件监听（Watcher 开关）"""
        if enabled and not self._watcher_enabled:
            self._watcher_enabled = True
            self._refresh_paths_impl()
            log.info("文件监听已启用")
        elif not enabled and self._watcher_enabled:
            self._watcher_enabled = False
            # 清空监听路径但保留 watcher 实例
            dirs = self._watcher.directories()
            if dirs:
                self._watcher.removePaths(dirs)
            self._debounce_timer.stop()
            log.info("文件监听已暂停")
        self.watcherToggled.emit(self._watcher_enabled)

    @Slot()
    def refreshPaths(self) -> None:
        """重新扫描业务目录并增量更新监听路径（QML 可调用）"""
        if not self._watcher_enabled:
            return
        self._refresh_paths_impl()

    @Slot(result=int)
    def watchedDirectoryCount(self) -> int:
        """查询当前监听目录数"""
        return len(self._watcher.directories())

    @Slot(result=bool)
    def isWatcherEnabled(self) -> bool:
        """查询 Watcher 是否启用"""
        return self._watcher_enabled

    @Slot(result=str)
    def lastSyncTime(self) -> str:
        """查询上次同步时间（HH:MM:SS）"""
        return self._last_sync_time

    # ── reload 支持（供 qml_main_window 调用，非 QML Slot）──

    def prepareForReload(self) -> None:
        """切换工作空间前调用：停止监听并拒绝新 sync。

        清理顺序：removePaths → 停去抖定时器 → 标记 _reload_pending
        （_reload_pending 使 in-flight worker 完成后不触发 refresh）。
        """
        self._reload_pending = True
        self._debounce_timer.stop()
        dirs = self._watcher.directories()
        if dirs:
            self._watcher.removePaths(dirs)
        log.info("FileWatcherBridge 已准备重载")

    def rebuild(self, new_workspace_root: str) -> None:
        """切换工作空间后调用：更新路径并重建监听"""
        self._workspace_root = new_workspace_root
        self._reload_pending = False
        if self._watcher_enabled:
            self._refresh_paths_impl()
        log.info("FileWatcherBridge 已重建，工作空间: %s", new_workspace_root)

    # ── 内部方法 ──────────────────────────────────────────

    def _scan_business_dirs(self) -> list[str]:
        """递归扫描工作空间，排除噪声目录，返回业务目录列表。

        使用 os.walk 的 dirs[:] prune 模式（标准高效剪枝）。
        硬上限保护：超过 MAX_DIRECTORIES 停止扫描（精简模式）。
        """
        result: list[str] = []
        for root, dirs, _files in os.walk(self._workspace_root):
            # 原地修改 dirs 实现 prune（os.walk 标准模式）
            dirs[:] = [d for d in dirs if d not in self.NOISE_DIRS]
            # 硬上限保护
            if len(result) >= self.MAX_DIRECTORIES:
                log.warning(
                    "业务目录数达上限 %d，停止扫描（精简模式）",
                    self.MAX_DIRECTORIES,
                )
                break
            result.append(root)
        return result

    def _refresh_paths_impl(self) -> int:
        """diff 算法：新扫描集 vs watcher.directories()，增量更新。

        增量 addPath 新目录、removePath 消失目录，避免全量重建抖动。
        幂等：重复 addPath 已存在目录安全（QFileSystemWatcher 忽略重复）。
        """
        new_dirs = set(self._scan_business_dirs())
        current_dirs = set(self._watcher.directories())

        to_add = new_dirs - current_dirs
        to_remove = current_dirs - new_dirs

        if to_remove:
            self._watcher.removePaths(list(to_remove))
        if to_add:
            self._watcher.addPaths(list(to_add))

        count = len(new_dirs)
        self.pathsRefreshed.emit(count)
        return count

    def _on_file_changed(self, path: str) -> None:
        """文件变化 → 重启去抖定时器"""
        self._debounce_timer.start()

    def _on_dir_changed(self, path: str) -> None:
        """目录变化 → 重启去抖定时器"""
        self._debounce_timer.start()

    def _on_debounce_timeout(self) -> None:
        """去抖超时 → 触发 sync（含并发控制）"""
        if self._reload_pending:
            return
        if not self._watcher_enabled:
            # 监听已关闭：QFileSystemWatcher.removePaths 在 Windows 上对部分路径
            # 会失败（directories() 残留），残留路径仍可能触发 fileChanged →
            # debounce。此处拦截，确保 toggleWatcher(False) 后绝不触发 sync。
            return
        if self._sync_in_progress:
            # sync 进行中，累积变化，完成后补一次
            self._pending_sync = True
            return
        self._start_sync()

    def _start_sync(self) -> None:
        """启动后台 sync worker"""
        self._sync_in_progress = True
        self.syncStarted.emit()
        worker = _SyncWorker(self._workspace_root, self)
        # 持有引用，防止 worker wrapper 被 GC
        self._current_worker = worker
        self._pool.start(worker)
        self._poll_timer.start()  # 启动轮询检测 worker.done

    def _poll_worker(self) -> None:
        """轮询 worker.done，完成后读取 result 回调 _on_sync_finished。

        worker.run() 在 QThreadPool 子线程执行，完成后设 self.done=True 并写
        self.result。主线程 QTimer 每 50ms 检测，检测到 done 后读取 result，
        回调 _on_sync_finished（主线程），释放 worker 引用。
        """
        worker = self._current_worker
        if worker is None:
            return
        if not worker.done:
            return
        self._poll_timer.stop()
        result = worker.result
        self._current_worker = None  # 释放 worker 引用
        if result is not None:
            projects, changes, ms, error_msg = result
            self._on_sync_finished(projects, changes, ms, error_msg)

    def _on_sync_finished(
        self, projects: int, changes: int, ms: int, error_msg: str
    ) -> None:
        """sync 完成（主线程，QThreadPool 信号回调）"""
        self._sync_in_progress = False
        self._current_worker = None  # 释放 worker 引用
        self._last_sync_time = datetime.now().strftime("%H:%M:%S")

        if error_msg:
            self.syncError.emit(error_msg)
            log.warning("同步失败: %s", error_msg)
        else:
            self.syncFinished.emit(projects, changes, ms)
            log.info("同步完成: %d 项目, %d 变更, %dms", projects, changes, ms)
            # 补一次 refreshPaths 捕获新建子目录（QFileSystemWatcher 非递归）
            if self._watcher_enabled:
                self._refresh_paths_impl()

        # 检查累积的 pending sync（sync 期间又有文件变化）
        if self._pending_sync and not self._reload_pending:
            self._pending_sync = False
            self._debounce_timer.start()
