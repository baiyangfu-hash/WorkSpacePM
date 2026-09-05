"""PLC-HMI 概念映射：SFB 库函数（文件工具（通用文件操作/编码处理））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

文件操作工具"""

from __future__ import annotations

import os
import tempfile


class StaleFileError(RuntimeError):
    """文件在读写之间被外部修改时抛出的异常"""


def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """读取文件内容，失败返回空字符串"""
    try:
        with open(file_path, encoding=encoding) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def read_file_snapshot(
    file_path: str, encoding: str = "utf-8", max_attempts: int = 3
) -> tuple[str, float]:
    """读取稳定文件快照，返回内容和 mtime

    通过"读前/读后 mtime 一致"近似保证内容与 mtime 来自同一版本，
    降低 read-modify-write 场景中的误判和漏判概率。
    """
    content = ""
    mtime = 0.0
    attempts = max(1, max_attempts)
    for _ in range(attempts):
        before = get_mtime(file_path)
        content = read_file(file_path, encoding=encoding)
        after = get_mtime(file_path)
        if before == after:
            return content, after
        mtime = after
    return content, mtime


def write_file(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
    expected_mtime: float | None = None,
) -> None:
    """原子写入文件内容，自动创建父目录

    使用"写入临时文件 → os.replace 替换"模式确保原子性（TD-T11 修复）：
    - 写入过程中中断不会损坏原文件（原文件保持不变）
    - os.replace 在 Windows 和 POSIX 上都是原子操作
    - 临时文件与目标文件在同一目录（确保 os.replace 可用）
    - 可选 expected_mtime 乐观锁，防止 read-modify-write lost update

    Args:
        file_path: 目标文件路径
        content: 文件内容
        encoding: 文件编码，默认 utf-8
        expected_mtime: 期望的文件修改时间；不一致则拒绝写入
    """
    if expected_mtime is not None:
        current_mtime = get_mtime(file_path)
        if current_mtime != expected_mtime:
            raise StaleFileError(
                f"文件已被外部修改: {file_path} "
                f"(expected_mtime={expected_mtime}, current_mtime={current_mtime})"
            )

    dir_path = os.path.dirname(file_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    # 在同目录创建临时文件（os.replace 要求源和目标在同一文件系统）
    fd, tmp_path = tempfile.mkstemp(dir=dir_path or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except Exception:
        # 写入失败时清理临时文件，原文件不受影响
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_mtime(file_path: str) -> float:
    """获取文件修改时间，失败返回0"""
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return 0.0
