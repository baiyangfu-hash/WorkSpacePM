"""Auto-PM 启动崩溃防御、单实例互斥与数据库锁探测守护器（纯标准库实现）。

本模块仅使用 Python 标准库，不导入 auto_pm 核心模块及第三方依赖，
确保在系统启动最前置阶段能够安全执行，避免因依赖损坏导致诊断留痕失效。
"""

from __future__ import annotations

import atexit
import json
import os
import sqlite3
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

# 统一退出码定义
EXIT_OK = 0
EXIT_CRASH = 1
EXIT_CONTAINER_INVALID = 2
EXIT_POINTER_INVALID = 3
EXIT_RELEASE_INVALID = 4
EXIT_PROVENANCE_INVALID = 5
EXIT_INSTANCE_LOCKED = 6
EXIT_DB_LOCKED = 7

# 默认相对路径
DEFAULT_LOG_REL_PATH = Path(".auto-pm") / "logs" / "startup_crash.log"
DEFAULT_LOCK_REL_PATH = Path(".auto-pm") / "app.instance.lock"
DEFAULT_META_REL_PATH = Path(".auto-pm") / "app.instance.json"
DEFAULT_DB_REL_PATH = Path(".auto-pm") / "index.db"


class StartupGuardError(Exception):
    """启动防护基础异常。"""

    exit_code: int = EXIT_CRASH


class InstanceLockError(StartupGuardError):
    """单实例锁冲突异常（已有实例持锁）。"""

    exit_code: int = EXIT_INSTANCE_LOCKED


class DatabaseLockConflictError(StartupGuardError):
    """数据库锁冲突异常（SQLite 被独占占用）。"""

    exit_code: int = EXIT_DB_LOCKED


def format_crash_report(
    category: str,
    message: str,
    exc_type: type[BaseException] | None = None,
    exc_val: BaseException | None = None,
    exc_tb: TracebackType | None = None,
    *,
    workspace_root: Path | None = None,
) -> str:
    """格式化结构化崩溃报告，包含 UTC 时间戳、系统环境、命令行参数及完整 Traceback。"""
    now_utc = datetime.now(UTC).isoformat()
    if exc_val is not None:
        tb_lines = traceback.format_exception(exc_type or type(exc_val), exc_val, exc_tb)
        tb_str = "".join(tb_lines)
    else:
        tb_str = "(无 Python 异常堆栈，可能由非零退出码或外部信号引发)"

    ws = str(workspace_root) if workspace_root else os.environ.get("AUTO_PM_WORKSPACE", os.getcwd())
    cmd = " ".join(sys.argv) if sys.argv else "(empty)"

    return (
        f"\n{'=' * 80}\n"
        f"[{now_utc}] [STARTUP_CRASH] [{category}]\n"
        f"Workspace:  {ws}\n"
        f"Executable: {sys.executable} (Python {sys.version.split()[0]})\n"
        f"Platform:   {sys.platform}\n"
        f"PID:        {os.getpid()}\n"
        f"Command:    {cmd}\n"
        f"Message:    {message}\n"
        f"{'-' * 80}\n"
        f"Traceback:\n{tb_str.strip()}\n"
        f"{'=' * 80}\n"
    )


def write_crash_log(
    log_path: str | Path,
    category: str,
    message: str,
    exc_info: (
        tuple[type[BaseException] | None, BaseException | None, TracebackType | None] | None
    ) = None,
    *,
    workspace_root: Path | None = None,
) -> Path:
    """向指定路径追加崩溃日志，保证目录存在且编码为 UTF-8。"""
    target = Path(log_path).resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        exc_type, exc_val, exc_tb = exc_info if exc_info else (None, None, None)
        report = format_crash_report(
            category,
            message,
            exc_type,
            exc_val,
            exc_tb,
            workspace_root=workspace_root,
        )
        with open(target, "a", encoding="utf-8", errors="replace") as f:
            f.write(report)
            f.flush()
    except Exception as err:
        sys.stderr.write(f"[WARNING] 写入崩溃日志失败 ({target}): {err}\n")
    return target


def install_crash_handler(log_path: str | Path | None = None) -> Path:
    """挂载全局未捕获异常钩子 sys.excepthook，异常时写入 startup_crash.log 并打印。

    :param log_path: 崩溃日志绝对/相对路径，若为 None 则基于 AUTO_PM_WORKSPACE 或 cwd 定位。
    :return: 实际生效的日志文件 Path。
    """
    if log_path is None:
        ws = os.environ.get("AUTO_PM_WORKSPACE")
        base = Path(ws) if ws else Path.cwd()
        target_log_path = base / DEFAULT_LOG_REL_PATH
    else:
        target_log_path = Path(log_path)

    target_log_path = target_log_path.resolve()
    target_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _crash_excepthook(
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_val, exc_tb)
            return

        msg = f"{exc_type.__name__}: {exc_val}"
        write_crash_log(
            target_log_path,
            "UNCAUGHT_EXCEPTION",
            msg,
            exc_info=(exc_type, exc_val, exc_tb),
        )
        sys.__excepthook__(exc_type, exc_val, exc_tb)

    sys.excepthook = _crash_excepthook
    return target_log_path


class InstanceLock:
    """单实例互斥文件锁句柄，支持上下文管理器协议与显式 release。"""

    def __init__(
        self,
        lock_path: Path,
        fd: int,
        meta_path: Path | None = None,
    ) -> None:
        self.lock_path = lock_path.resolve()
        self.meta_path = meta_path.resolve() if meta_path is not None else None
        self.fd: int | None = fd
        self._released = False
        self._atexit_registered = False
        try:
            atexit.register(self.release)
            self._atexit_registered = True
        except Exception:
            pass

    def release(self) -> None:
        """释放文件锁并关闭句柄，清理元数据文件。"""
        if self._released or self.fd is None:
            return
        self._released = True
        if self._atexit_registered:
            try:
                atexit.unregister(self.release)
            except Exception:
                pass
        fd = self.fd
        self.fd = None
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                try:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            if self.meta_path is not None:
                try:
                    if self.meta_path.is_file():
                        self.meta_path.unlink()
                except OSError:
                    pass

    def close(self) -> None:
        self.release()

    def __enter__(self) -> InstanceLock:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


def acquire_instance_lock(
    workspace_root: str | Path,
    *,
    exit_on_error: bool = False,
    log_path: str | Path | None = None,
) -> InstanceLock:
    """申请工作空间单实例内核排他锁（Windows msvcrt.locking，Unix fcntl.flock）。

    :param workspace_root: 工作空间根目录或直接传入 lock 文件路径。
    :param exit_on_error: 若为 True 且冲突，直接以退出码 6 退出；若为 False 则抛出 InstanceLockError。
    :param log_path: 可选的崩溃日志留痕路径。
    :return: 成功获取的 InstanceLock 句柄。
    """
    root_or_file = Path(workspace_root).resolve()
    if root_or_file.name.endswith(".lock"):
        lock_file = root_or_file
        meta_file = root_or_file.with_suffix(".json")
    elif root_or_file.is_file():
        lock_file = root_or_file
        meta_file = root_or_file.parent / DEFAULT_META_REL_PATH.name
    else:
        lock_file = root_or_file / DEFAULT_LOCK_REL_PATH
        meta_file = root_or_file / DEFAULT_META_REL_PATH

    lock_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_log_path = Path(log_path).resolve() if log_path else (lock_file.parent / "logs" / "startup_crash.log")

    try:
        fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT)
    except OSError as exc:
        err_msg = f"无法创建/打开单实例锁文件 ({lock_file}): {exc}"
        sys.stderr.write(f"\n[错误] {err_msg}\n")
        write_crash_log(resolved_log_path, "INSTANCE_LOCK_OPEN_FAILED", err_msg)
        if exit_on_error:
            sys.exit(EXIT_INSTANCE_LOCKED)
        raise InstanceLockError(err_msg) from exc

    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # 加锁成功，记录 PID 与启动时间元数据到伴生 JSON 文件
        try:
            meta_file.parent.mkdir(parents=True, exist_ok=True)
            meta = json.dumps(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now(UTC).isoformat(),
                    "start_time": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
            meta_file.write_text(meta, encoding="utf-8", errors="replace")
        except Exception:
            pass

        return InstanceLock(lock_file, fd, meta_path=meta_file)

    except (OSError, BlockingIOError, PermissionError) as exc:
        try:
            os.close(fd)
        except OSError:
            pass

        existing_pid = "未知"
        try:
            if meta_file.is_file():
                content = meta_file.read_text(encoding="utf-8", errors="replace")
                info = json.loads(content)
                existing_pid = str(info.get("pid", "未知"))
        except Exception:
            pass

        err_msg = (
            f"检测到 Auto-PM 驾驶舱实例已在运行中 (占用 PID: {existing_pid})！\n"
            f"为防止数据冲突与数据库损坏，禁止对同一工作空间重复启动多实例。\n"
            f"提示: 请检查任务栏已打开的窗口；如前序进程已卡死，请在任务管理器中结束对应 python.exe 进程后重试。"
        )
        sys.stderr.write(f"\n[冲突告警] {err_msg}\n")
        write_crash_log(resolved_log_path, "SINGLE_INSTANCE_CONFLICT", err_msg)

        if exit_on_error:
            sys.exit(EXIT_INSTANCE_LOCKED)
        raise InstanceLockError(err_msg) from exc


def probe_database_locks(
    db_path: str | Path,
    timeout_sec: float = 1.0,
    *,
    exit_on_error: bool = False,
    log_path: str | Path | None = None,
) -> None:
    """探测 SQLite 数据库是否存在写锁/独占冲突（BEGIN IMMEDIATE / ROLLBACK）。

    :param db_path: SQLite 数据库文件路径（若传入目录则自动拼接 .auto-pm/index.db）。
    :param timeout_sec: 探测超时时间（秒）。
    :param exit_on_error: 若检测到锁死，是否直接退出码 7 终止进程。
    :param log_path: 可选的崩溃日志留痕路径。
    """
    path = Path(db_path).resolve()
    if path.is_dir():
        path = path / DEFAULT_DB_REL_PATH

    if not path.is_file():
        return

    resolved_log_path = Path(log_path).resolve() if log_path else (path.parent / "logs" / "startup_crash.log")

    try:
        conn = sqlite3.connect(str(path), timeout=timeout_sec)
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.rollback()
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        err_str = str(exc).lower()
        if "locked" in err_str or "busy" in err_str:
            err_msg = (
                f"数据库锁冲突: {path} 当前正被其他进程占用或处于独占写入状态。\n"
                f"底层异常: {exc}\n"
                f"排查建议:\n"
                f"  1. 检查是否有后台运行的 auto-pm CLI 命令、自动化测试或扫描脚本；\n"
                f"  2. 检查任务管理器中是否存在残留的孤儿 python.exe 进程；\n"
                f"  3. 检查 {path.parent} 目录下的 index.db-wal 和 index.db-shm 是否被其他工具占用。"
            )
            sys.stderr.write(f"\n[数据库锁死] {err_msg}\n")
            write_crash_log(resolved_log_path, "DB_LOCK_CONFLICT", err_msg)
            if exit_on_error:
                sys.exit(EXIT_DB_LOCKED)
            raise DatabaseLockConflictError(err_msg) from exc
        raise


class StartupGuard:
    """高层封装类，支持以对象方式集中管理启动留痕、单实例锁与数据库探测。"""

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.logs_dir = self.workspace_root / ".auto-pm" / "logs"
        self.crash_log_file = self.logs_dir / "startup_crash.log"
        self.lock_file = self.workspace_root / DEFAULT_LOCK_REL_PATH
        self.meta_file = self.workspace_root / DEFAULT_META_REL_PATH
        self.db_path = self.workspace_root / DEFAULT_DB_REL_PATH
        self._lock: InstanceLock | None = None

    def install_crash_handler(self) -> Path:
        return install_crash_handler(self.crash_log_file)

    def log_crash(
        self,
        category: str,
        message: str,
        exc_tb: TracebackType | None = None,
    ) -> Path:
        return write_crash_log(
            self.crash_log_file,
            category,
            message,
            exc_info=(None, None, exc_tb),
            workspace_root=self.workspace_root,
        )

    def acquire_instance_lock(self, *, exit_on_error: bool = False) -> InstanceLock:
        self._lock = acquire_instance_lock(
            self.lock_file,
            exit_on_error=exit_on_error,
            log_path=self.crash_log_file,
        )
        return self._lock

    def release_instance_lock(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def probe_database_lock(
        self,
        timeout_sec: float = 1.0,
        *,
        exit_on_error: bool = False,
    ) -> None:
        probe_database_locks(
            self.db_path,
            timeout_sec=timeout_sec,
            exit_on_error=exit_on_error,
            log_path=self.crash_log_file,
        )
