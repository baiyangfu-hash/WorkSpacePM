"""Unit tests for auto_pm.infrastructure.startup_guard."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure.startup_guard import (
    EXIT_DB_LOCKED,
    EXIT_INSTANCE_LOCKED,
    DatabaseLockConflictError,
    InstanceLockError,
    StartupGuard,
    acquire_instance_lock,
    format_crash_report,
    install_crash_handler,
    probe_database_locks,
    write_crash_log,
)


def test_crash_log_formatting(tmp_path: Path) -> None:
    try:
        raise ValueError("Diagnostic simulated error for unit test")
    except ValueError as exc:
        report = format_crash_report(
            "TEST_CAT",
            "Simulated message",
            type(exc),
            exc,
            exc.__traceback__,
            workspace_root=tmp_path,
        )
    assert "[STARTUP_CRASH] [TEST_CAT]" in report
    assert "Diagnostic simulated error for unit test" in report
    assert "Workspace:" in report
    assert "Traceback:" in report
    assert "PID:" in report


def test_crash_log_writing_on_simulated_exception(tmp_path: Path) -> None:
    log_path = tmp_path / ".auto-pm" / "logs" / "startup_crash.log"
    original_excepthook = sys.excepthook

    try:
        resolved = install_crash_handler(log_path)
        assert resolved == log_path.resolve()

        try:
            raise RuntimeError("Testing startup crash hook")
        except RuntimeError as exc:
            # Simulate uncaught exception passing to sys.excepthook
            sys.excepthook(type(exc), exc, exc.__traceback__)

        assert log_path.is_file()
        content = log_path.read_text(encoding="utf-8", errors="replace")
        assert "[STARTUP_CRASH] [UNCAUGHT_EXCEPTION]" in content
        assert "RuntimeError: Testing startup crash hook" in content
        assert "Traceback:" in content
    finally:
        sys.excepthook = original_excepthook


def test_crash_log_keyboard_interrupt_bypassed(tmp_path: Path) -> None:
    log_path = tmp_path / ".auto-pm" / "logs" / "startup_crash.log"
    original_excepthook = sys.excepthook

    try:
        install_crash_handler(log_path)
        exc = KeyboardInterrupt()
        sys.excepthook(type(exc), exc, None)

        # KeyboardInterrupt should not be written to crash log
        assert not log_path.exists()
    finally:
        sys.excepthook = original_excepthook


def test_write_crash_log_appends(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "test_crash.log"
    write_crash_log(log_path, "FIRST_EVENT", "First crash message")
    write_crash_log(log_path, "SECOND_EVENT", "Second crash message")

    content = log_path.read_text(encoding="utf-8")
    assert "[FIRST_EVENT]" in content
    assert "[SECOND_EVENT]" in content
    assert content.count("[STARTUP_CRASH]") == 2


def test_instance_lock_acquisition_and_release(tmp_path: Path) -> None:
    ws = tmp_path / "test_ws"
    ws.mkdir()
    lock_file = ws / ".auto-pm" / "app.instance.lock"
    meta_file = ws / ".auto-pm" / "app.instance.json"

    lock = acquire_instance_lock(ws)
    try:
        assert lock.fd is not None
        assert lock_file.is_file()
        assert meta_file.is_file()
    finally:
        lock.release()

    fd_val: int | None = lock.fd
    assert fd_val is None
    assert not meta_file.exists()
    # Release is idempotent
    lock.release()


def test_instance_lock_reentrancy_blocking(tmp_path: Path) -> None:
    ws = tmp_path / "test_ws"
    ws.mkdir()

    lock1 = acquire_instance_lock(ws)
    try:
        with pytest.raises(InstanceLockError) as excinfo:
            acquire_instance_lock(ws)
        assert "检测到 Auto-PM 驾驶舱实例已在运行中" in str(excinfo.value)
        assert f"占用 PID: {os.getpid()}" in str(excinfo.value)
    finally:
        lock1.release()

    # Once released, acquisition succeeds again
    lock2 = acquire_instance_lock(ws)
    lock2.release()


def test_instance_lock_exit_on_error(tmp_path: Path) -> None:
    ws = tmp_path / "test_ws"
    ws.mkdir()

    lock1 = acquire_instance_lock(ws)
    try:
        with pytest.raises(SystemExit) as excinfo:
            acquire_instance_lock(ws, exit_on_error=True)
        assert excinfo.value.code == EXIT_INSTANCE_LOCKED
    finally:
        lock1.release()


def test_instance_lock_context_manager(tmp_path: Path) -> None:
    ws = tmp_path / "test_ws"
    ws.mkdir()

    with acquire_instance_lock(ws) as lock:
        assert lock.fd is not None
        with pytest.raises(InstanceLockError):
            acquire_instance_lock(ws)

    # After exit, lock can be acquired again
    with acquire_instance_lock(ws) as lock2:
        assert lock2.fd is not None


def test_probe_database_locks_missing_db_noop(tmp_path: Path) -> None:
    # Non-existent DB path should return cleanly
    probe_database_locks(tmp_path / "non_existent.db")
    # Non-existent workspace .auto-pm/index.db should return cleanly
    probe_database_locks(tmp_path)


def test_probe_database_locks_unlocked_passes(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO projects VALUES ('p1', 'Alpha');")
    conn.commit()
    conn.close()

    probe_database_locks(db_file)


def test_probe_database_locks_detects_exclusive_conflict(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    conn1 = sqlite3.connect(str(db_file))
    conn1.execute("CREATE TABLE projects (id TEXT PRIMARY KEY);")
    conn1.commit()

    conn1.execute("BEGIN EXCLUSIVE;")
    try:
        with pytest.raises(DatabaseLockConflictError) as excinfo:
            probe_database_locks(db_file, timeout_sec=0.2)
        assert "数据库锁冲突" in str(excinfo.value)
    finally:
        conn1.rollback()
        conn1.close()

    # After rollback/close, probe passes immediately
    probe_database_locks(db_file, timeout_sec=0.2)


def test_probe_database_locks_exit_on_error(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    conn1 = sqlite3.connect(str(db_file))
    conn1.execute("CREATE TABLE projects (id TEXT PRIMARY KEY);")
    conn1.commit()

    conn1.execute("BEGIN EXCLUSIVE;")
    try:
        with pytest.raises(SystemExit) as excinfo:
            probe_database_locks(db_file, timeout_sec=0.2, exit_on_error=True)
        assert excinfo.value.code == EXIT_DB_LOCKED
    finally:
        conn1.rollback()
        conn1.close()


def test_startup_guard_class(tmp_path: Path) -> None:
    guard = StartupGuard(tmp_path)
    log_p = guard.install_crash_handler()
    assert log_p == guard.crash_log_file.resolve()

    guard.log_crash("CLASS_TEST", "Test via StartupGuard instance")
    assert guard.crash_log_file.is_file()

    lock = guard.acquire_instance_lock()
    assert lock.fd is not None
    guard.release_instance_lock()
    assert guard._lock is None

    # Database probe on empty dir is noop
    guard.probe_database_lock()


def test_launcher_batch_file_crlf_line_endings() -> None:
    """防回归门禁：验证双击启动批处理文件必须严格保持 Windows CRLF 换行符。

    Windows cmd.exe 依赖 CRLF (2 字节) 计算 goto 标签字节偏移；UNIX LF 会导致跳转偏移漂移，
    产生指令撕裂与静默闪退。参见 .gitattributes 第 23 行。
    """
    targets = [
        Path(r"c:\Users\fubai\Documents\My_Workspace\双击启动驾驶舱.bat"),
        Path(
            r"C:\Users\fubai\.codex\visualizations\2026\09\05\01a06f4b-eb60-7e83-8ee7-f3d84cfec583\NG-WP-02\candidate\双击启动驾驶舱.bat"
        ),
    ]
    checked = 0
    for bat_path in targets:
        if not bat_path.is_file():
            continue
        data = bat_path.read_bytes()
        crlf_count = data.count(b"\r\n")
        lf_count = data.count(b"\n")
        cr_count = data.count(b"\r")

        assert crlf_count > 0, f"{bat_path}: 缺失 CRLF 换行符"
        assert crlf_count == lf_count, f"{bat_path}: 检测到非 CRLF 的孤立 LF 换行符"
        assert crlf_count == cr_count, f"{bat_path}: 检测到非 CRLF 的孤立 CR 换行符"
        checked += 1

    assert checked == 2, f"预期检查 2 处批处理文件，实际检查了 {checked} 处"


@pytest.mark.skipif(sys.platform != "win32", reason="仅在 Windows 原生 cmd.exe 环境下执行")
def test_launcher_batch_cmd_execution_zero_syntax_errors() -> None:
    """防回归门禁：在 Windows cmd.exe 下实测批处理无语法撕裂报错并正确捕获锁冲突退出码。"""
    import subprocess

    ws_root = Path(r"c:\Users\fubai\Documents\My_Workspace")
    bat_file = ws_root / "双击启动驾驶舱.bat"
    if not bat_file.is_file():
        pytest.skip("根目录批处理不存在")

    lock = acquire_instance_lock(ws_root)
    try:
        proc = subprocess.Popen(
            ["cmd.exe", "/c", str(bat_file)],
            cwd=str(ws_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(input=b"\r\n", timeout=10)
        assert proc.returncode == EXIT_INSTANCE_LOCKED, f"预期退出码 {EXIT_INSTANCE_LOCKED}，实际为 {proc.returncode}"

        # 验证 stderr 绝无 cmd.exe 语法截断或未知命令报错
        stderr_text = stderr.decode("utf-8", errors="replace")
        assert "is not recognized as an internal or external command" not in stderr_text
        assert "'E'" not in stderr_text
        assert "'ORLEVEL" not in stderr_text
    finally:
        lock.release()

