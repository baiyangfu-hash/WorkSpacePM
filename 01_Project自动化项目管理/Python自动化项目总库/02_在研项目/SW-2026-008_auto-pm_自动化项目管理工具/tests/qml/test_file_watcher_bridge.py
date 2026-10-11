"""FileWatcherBridge 单元测试

CHG-SCPT-2026-141：验证文件监听同步 Bridge 的核心逻辑。

测试分两类：
- 逻辑测试（mock _start_sync，不启动真实 worker）：去抖合并、并发控制、开关、reload 隔离、噪声过滤
- 集成测试（真实 DB + QSignalSpy）：SyncWorker 自建 DB 连接规避线程亲和性、syncFinished 信号
"""

from __future__ import annotations

import ctypes
import gc
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from threading import Thread, get_native_id
from weakref import ReferenceType, ref

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from auto_pm.ui.qml.bridges.file_watcher_bridge import (
    FileWatcherBridge,
    _SyncWorker,
)


def _wait_for_signal(spy: QSignalSpy, timeout_ms: int = 10000) -> bool:
    """轮询等待信号，释放 GIL 让 QThreadPool worker 全速运行。

    用 time.sleep + processEvents 替代 QTest.qWait：根因诊断证明 QTest.qWait
    在 PySide6 6.11 下严重限制 worker 线程的 GIL 获取（sync_to_cache 从 19ms
    膨胀到 3700ms+，首次 import 8s 内无法完成）。time.sleep 释放 GIL 让 worker
    全速运行，processEvents 处理 Qt 事件（poll timer → syncFinished）。

    生产环境 app.exec() 正常释放 GIL（实测 worker 19ms），本函数仅修正测试
    等待机制，不影响生产行为。
    """
    app = QApplication.instance()
    for _ in range(timeout_ms // 20):
        time.sleep(0.02)
        if app is not None:
            app.processEvents()
        if spy.count() > 0:
            return True
    return False


# ── 逻辑测试 ────────────────────────────────────────────


def test_toggle_watcher_enable_disable(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """toggleWatcher 开关切换 + watcherToggled 信号"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    spy = QSignalSpy(bridge.watcherToggled)

    bridge.toggleWatcher(True)
    assert bridge.isWatcherEnabled() is True
    assert bridge.watchedDirectoryCount() > 0  # 已扫描业务目录

    bridge.toggleWatcher(False)
    assert bridge.isWatcherEnabled() is False
    assert bridge.watchedDirectoryCount() == 0  # 监听已清空

    assert spy.count() == 2  # 两次切换各发一次信号


def test_debounce_coalesces_events(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """连续多次 fileChanged 只触发 1 次 sync（1s 去抖合并）"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    bridge.toggleWatcher(True)
    calls: list[int] = []
    bridge._start_sync = lambda: calls.append(1)  # type: ignore[method-assign]  # mock，不启动真实 worker

    # 连发 3 次变化信号
    bridge._on_file_changed("/fake/a")
    bridge._on_file_changed("/fake/b")
    bridge._on_file_changed("/fake/c")

    assert len(calls) == 0  # 去抖期内未触发
    assert bridge._debounce_timer.isActive() is True

    # 等去抖超时（1s + 余量）
    QTest.qWait(1200)
    assert len(calls) == 1  # 3 次变化合并为 1 次 sync


def test_concurrent_sync_blocked(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """sync 进行中再次触发去抖，累积为 pending，不启动新 sync"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    bridge._watcher_enabled = True  # 启用监听（_on_debounce_timeout 前置条件）
    bridge._sync_in_progress = True  # 模拟 sync 进行中
    calls: list[int] = []
    bridge._start_sync = lambda: calls.append(1)  # type: ignore[method-assign]

    bridge._on_debounce_timeout()  # 去抖超时

    assert bridge._pending_sync is True  # 累积标记
    assert len(calls) == 0  # 未启动新 sync
    assert bridge._sync_in_progress is True  # 状态未变


def test_pending_sync_resubmits_after_finish(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """sync 完成后检查 pending，若有则重启去抖定时器补一次"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    bridge._sync_in_progress = True
    bridge._pending_sync = True

    # 模拟 sync 完成（无错误）
    bridge._on_sync_finished(1, 0, 50, "")

    assert bridge._sync_in_progress is False
    assert bridge._pending_sync is False  # 已消费
    assert bridge._debounce_timer.isActive() is True  # 重启去抖补一次


def test_prepare_for_reload_blocks_sync(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """prepareForReload 后拒绝新 sync + 清空监听"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    bridge.toggleWatcher(True)
    assert bridge.watchedDirectoryCount() > 0

    bridge.prepareForReload()

    assert bridge._reload_pending is True
    assert bridge.watchedDirectoryCount() == 0  # 监听已清空
    assert bridge._debounce_timer.isActive() is False

    # reload 期间 syncNow 应被忽略
    bridge.syncNow()
    assert bridge._sync_in_progress is False  # 未启动


def test_reload_pending_skips_debounce(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """reload_pending 时去抖超时不触发 sync"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    bridge._reload_pending = True
    calls: list[int] = []
    bridge._start_sync = lambda: calls.append(1)  # type: ignore[method-assign]

    bridge._on_debounce_timeout()

    assert len(calls) == 0


def test_rebuild_restores_watcher(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """rebuild 后恢复监听"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    bridge.toggleWatcher(True)
    bridge.prepareForReload()
    assert bridge.watchedDirectoryCount() == 0

    bridge.rebuild(str(tmp_workspace))

    assert bridge._reload_pending is False
    assert bridge.watchedDirectoryCount() > 0  # 监听已重建


def test_noise_dir_excluded(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """_scan_business_dirs 排除噪声目录"""
    (tmp_workspace / ".git").mkdir()
    (tmp_workspace / ".venv").mkdir()
    (tmp_workspace / "__pycache__").mkdir()
    (tmp_workspace / ".ruff_cache").mkdir()

    bridge = FileWatcherBridge(str(tmp_workspace))
    dirs = bridge._scan_business_dirs()

    # 噪声目录及其子目录不应出现
    for d in dirs:
        assert ".git" not in d
        assert ".venv" not in d
        assert "__pycache__" not in d
        assert ".ruff_cache" not in d
    # 但业务目录应存在（tmp_workspace 根 + 项目目录）
    assert len(dirs) >= 1


def test_refresh_paths_diff_idempotent(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """重复 refreshPaths 幂等，不重复 addPath"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    bridge.toggleWatcher(True)
    count1 = bridge.watchedDirectoryCount()

    bridge._refresh_paths_impl()  # 再次扫描
    count2 = bridge.watchedDirectoryCount()

    assert count1 == count2  # 幂等，数量不变


def test_last_sync_time_updated(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """sync 完成后 lastSyncTime 更新"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    assert bridge.lastSyncTime() == ""

    bridge._on_sync_finished(1, 0, 50, "")

    assert bridge.lastSyncTime() != ""  # 已更新为 HH:MM:SS


def test_sync_error_emits_signal(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """sync 失败时发 syncError 信号"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    spy = QSignalSpy(bridge.syncError)

    bridge._on_sync_finished(0, 0, 50, "DB 连接失败")

    assert spy.count() == 1
    # PySide6 QSignalSpy 用 at(0) 取参数（非 PyQt5 的 takeFirst）
    assert "DB 连接失败" in spy.at(0)[0]


# ── 集成测试（真实 DB + QSignalSpy）─────────────────────


def test_sync_worker_creates_own_db(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """SyncWorker 在 worker 线程自建 DB 连接，不抛线程亲和性异常。

    关键验证：connection.py:54 默认 check_same_thread=True，若 SyncWorker
    复用主线程连接会抛 ProgrammingError。本测试确认 worker 自建连接可行。
    同时验证轮询方案：worker 写 result/done，bridge QTimer 轮询后 emit
    syncFinished（规避 PySide6 6.11 QRunnable 子线程 emit 信号时 QObject
    被析构的问题）。
    """
    bridge = FileWatcherBridge(str(tmp_workspace))
    spy = QSignalSpy(bridge.syncFinished)
    err_spy = QSignalSpy(bridge.syncError)

    bridge.syncNow()

    # 用 qWait 轮询等待（比 spy.wait 更可靠）
    assert _wait_for_signal(spy, 10000), "syncFinished 信号未在超时内收到"
    assert spy.count() == 1
    assert err_spy.count() == 0  # 无错误

    # tmp_workspace 含 DJ-2026-TEST 项目，首次 sync projects_found >= 1
    args = spy.at(0)
    projects = args[0]
    assert projects >= 1
    # worker 引用已释放
    assert bridge._current_worker is None


def test_sync_worker_direct_instantiation(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """直接实例化 _SyncWorker 验证 run() 写 result/done（同步调用）"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    worker = _SyncWorker(str(tmp_workspace), bridge)

    worker.run()  # 同步执行（非线程池），写 result + done

    assert worker.done is True
    assert worker.result is not None
    projects, changes, ms, error_msg = worker.result
    assert isinstance(projects, int)
    assert isinstance(ms, int)
    # error_msg 应为空（sync 成功）
    assert error_msg == ""


def test_sync_finished_emits_counts(qapp, tmp_workspace) -> None:  # type: ignore[no-untyped-def]
    """syncFinished 信号携带 (projects, changes, ms) 三参数"""
    bridge = FileWatcherBridge(str(tmp_workspace))
    spy = QSignalSpy(bridge.syncFinished)

    bridge.syncNow()
    assert _wait_for_signal(spy, 10000)
    assert spy.count() == 1

    args = spy.at(0)
    projects, changes, ms = args[0], args[1], args[2]
    assert isinstance(projects, int)
    assert isinstance(changes, int)
    assert isinstance(ms, int)
    assert projects >= 1
    assert ms >= 0


def _finish_real_sync(bridge: FileWatcherBridge, *, io_error: bool) -> _SyncWorker:
    """Run the production pool and poll once, preserving real success/error results."""
    finished = QSignalSpy(bridge.syncFinished)
    failed = QSignalSpy(bridge.syncError)
    bridge.syncNow()
    worker = bridge._current_worker
    assert worker is not None
    assert bridge._pool.waitForDone(10_000), "Real sync worker did not finish"
    assert worker.done and worker.result is not None
    assert not worker.autoDelete()
    bridge._poll_worker()
    assert bridge._current_worker is None
    assert not bridge._poll_timer.isActive()
    assert not bridge._sync_in_progress
    if io_error:
        assert worker.result[0:2] == (0, 0)
        assert worker.result[3]
        assert finished.count() == 0
        assert failed.count() == 1
        assert failed.at(0)[0] == worker.result[3]
    else:
        assert worker.result[0] >= 1
        assert worker.result[3] == ""
        assert finished.count() == 1
        assert failed.count() == 0
        assert tuple(finished.at(0)) == worker.result[:3]
    return worker


def _sync_workspace(tmp_workspace: Path, *, io_error: bool) -> Path:
    """A real file in place of a directory makes DB creation fail on every platform."""
    if not io_error:
        return tmp_workspace
    blocked = tmp_workspace / "not-a-workspace-directory"
    blocked.write_text("not a directory", encoding="utf-8", errors="replace")
    return blocked


@pytest.mark.parametrize("io_error", [False, True], ids=["success", "real-io-error"])
def test_completed_real_pool_worker_does_not_retain_its_gui_bridge(
    qapp: QApplication, tmp_workspace: Path, io_error: bool,
) -> None:
    """Even a retained completed runnable must not keep its GUI bridge alive."""
    gui_thread = get_native_id()
    assert QCoreApplication.instance() is qapp
    destroyed: list[int] = []

    def on_destroyed() -> None:
        destroyed.append(get_native_id())

    bridge = FileWatcherBridge(str(_sync_workspace(tmp_workspace, io_error=io_error)))
    bridge_ref = ref(bridge)
    bridge.destroyed.connect(on_destroyed, Qt.ConnectionType.DirectConnection)
    pool = bridge._pool
    try:
        worker = _finish_real_sync(bridge, io_error=io_error)
        del bridge
        assert bridge_ref() is None, "Completed runnable retained its GUI bridge"
        assert destroyed == [gui_thread]
        assert worker.done and pool.waitForDone(0)
    finally:
        # A failing old-byte negative control must not leave a live native filter behind.
        retained = bridge_ref()
        pool_done = True
        if retained is not None:
            retained.prepareForReload()
            retained._poll_timer.stop()
            pool_done = pool.waitForDone(10_000)
            retained.deleteLater()
            QCoreApplication.sendPostedEvents(retained, QEvent.Type.DeferredDelete.value)
        assert pool_done, "Worker pool did not finish while the retained bridge was released"


def _exercise_real_sync_background_gc(workspace: Path, *, io_error: bool) -> None:
    """Isolated real sync → local release → background GC → native event dispatch."""
    app = QApplication([])
    app.processEvents()
    gui_thread = get_native_id()
    bridge_destroyed: list[int] = []
    watcher_destroyed: list[int] = []
    collector_threads: list[int] = []

    def bridge_gone() -> None:
        bridge_destroyed.append(get_native_id())

    def watcher_gone() -> None:
        watcher_destroyed.append(get_native_id())

    def collect() -> None:
        gc.collect()
        collector_threads.append(get_native_id())

    collector = Thread(target=collect, daemon=True)

    def release_completed_sync() -> tuple[ReferenceType[FileWatcherBridge], ReferenceType[QObject]]:
        bridge = FileWatcherBridge(str(_sync_workspace(workspace, io_error=io_error)))
        bridge.destroyed.connect(bridge_gone, Qt.ConnectionType.DirectConnection)
        bridge._watcher.destroyed.connect(watcher_gone, Qt.ConnectionType.DirectConnection)
        worker = _finish_real_sync(bridge, io_error=io_error)
        assert worker.done
        return ref(bridge), ref(bridge._watcher)

    bridge_ref, watcher_ref = release_completed_sync()
    # Record the boundary before GC can make an old implementation appear released.
    gui_release_before_gc = (
        bridge_ref() is None and bridge_destroyed == [gui_thread]
        and watcher_destroyed == [gui_thread]
    )
    collector.start()
    collector.join(timeout=3)
    assert not collector.is_alive()
    assert len(collector_threads) == 1 and collector_threads[0] != gui_thread
    if sys.platform == "win32":
        post = ctypes.WinDLL("user32", use_last_error=True).PostThreadMessageW
        post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        post.restype = wintypes.BOOL
        assert post(gui_thread, 0, 0, 0), ctypes.get_last_error()  # Real WM_NULL.
        print("WINDOWS_NATIVE_MESSAGE_POSTED", flush=True)
    app.processEvents()
    assert gui_release_before_gc, "GUI owners survived local release until cyclic GC"
    assert bridge_ref() is None and watcher_ref() is None
    assert bridge_destroyed == watcher_destroyed == [gui_thread]
    print("REAL_SYNC_GUI_RELEASE_AND_NATIVE_PUMP_OK", flush=True)


def _run_lifecycle_child(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Reap only this child tree on timeout, including a Windows venv interpreter."""
    child = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        stdout, stderr = child.communicate(timeout=20)
    except subprocess.TimeoutExpired as exc:
        termination = ""
        try:
            if sys.platform == "win32":
                killed = subprocess.run(
                    ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=5, check=False,
                )
                termination = f"taskkill_exit={killed.returncode} {killed.stdout}{killed.stderr}"
            else:
                child.kill()
        except (OSError, subprocess.TimeoutExpired) as stop_error:
            termination = f"termination_error={stop_error}"
        try:
            stdout, stderr = child.communicate(timeout=5)
        except subprocess.TimeoutExpired as reap_error:
            raise AssertionError(
                f"Lifecycle child pid={child.pid} timed out; reap unconfirmed: {termination}"
            ) from reap_error
        raise AssertionError(
            f"Lifecycle child pid={child.pid} exceeded 20s; {termination}\n{stdout}{stderr}"
        ) from exc
    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)


@pytest.mark.parametrize("io_error", [False, True], ids=["success", "real-io-error"])
def test_real_sync_background_gc_and_native_events_in_an_isolated_process(
    tmp_workspace: Path, io_error: bool,
) -> None:
    """Native access violations/aborts must fail a bounded child, not kill pytest."""
    command = (
        "from pathlib import Path; import sys; "
        "from tests.qml.test_file_watcher_bridge import _exercise_real_sync_background_gc; "
        "_exercise_real_sync_background_gc(Path(sys.argv[1]), io_error=sys.argv[2] == '1')"
    )
    result = _run_lifecycle_child([
        sys.executable, "-B", "-u", "-X", "faulthandler", "-c", command,
        str(tmp_workspace), str(int(io_error)),
    ])
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    if sys.platform == "win32":
        assert "WINDOWS_NATIVE_MESSAGE_POSTED" in output
    assert "REAL_SYNC_GUI_RELEASE_AND_NATIVE_PUMP_OK" in output
