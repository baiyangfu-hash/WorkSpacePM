"""文件操作工具"""

from __future__ import annotations

import os


def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """读取文件内容，失败返回空字符串"""
    try:
        with open(file_path, encoding=encoding) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def write_file(file_path: str, content: str, encoding: str = "utf-8") -> None:
    """写入文件内容，自动创建父目录"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding=encoding) as f:
        f.write(content)


def get_mtime(file_path: str) -> float:
    """获取文件修改时间，失败返回0"""
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return 0.0
