"""file_utils 工具函数测试"""

from __future__ import annotations

import glob
import os
import time
from pathlib import Path

import pytest
from auto_pm.utils.file_utils import (
    StaleFileError,
    get_mtime,
    read_file,
    read_file_snapshot,
    write_file,
)


class TestReadFile:
    """read_file 测试"""

    def test_read_existing_file(self, tmp_path: Path) -> None:
        """读取存在的文件"""
        tmp = tmp_path
        f = tmp / "test.txt"
        f.write_text("hello", encoding="utf-8")
        assert read_file(str(f)) == "hello"

    def test_read_nonexistent_file(self, tmp_path: Path) -> None:
        """读取不存在的文件返回空字符串"""
        tmp = tmp_path
        assert read_file(str(tmp / "nonexistent.txt")) == ""

    def test_read_file_with_encoding_error(self, tmp_path: Path) -> None:
        """读取编码错误的文件返回空字符串"""
        tmp = tmp_path
        f = tmp / "binary.bin"
        f.write_bytes(b"\xff\xfe\x80\x81")
        result = read_file(str(f))
        # UnicodeDecodeError 被捕获，返回空字符串
        assert result == ""


class TestWriteFile:
    """write_file 测试"""

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        """写入文件时自动创建父目录"""
        tmp = tmp_path
        f = tmp / "sub" / "dir" / "test.txt"
        write_file(str(f), "hello")
        assert f.read_text(encoding="utf-8") == "hello"

    def test_write_overwrites_existing(self, tmp_path: Path) -> None:
        """写入覆盖已有文件"""
        tmp = tmp_path
        f = tmp / "test.txt"
        f.write_text("old", encoding="utf-8")
        write_file(str(f), "new")
        assert f.read_text(encoding="utf-8") == "new"


class TestWriteFileAtomic:
    """write_file 原子写入测试（TD-T11 修复）"""

    def test_write_preserves_original_on_success(self, tmp_path: Path) -> None:
        """写入成功后原文件被新内容替换"""
        tmp = tmp_path
        f = tmp / "test.txt"
        f.write_text("old content", encoding="utf-8")
        write_file(str(f), "new content")
        assert f.read_text(encoding="utf-8") == "new content"

    def test_no_temp_file_left_after_write(self, tmp_path: Path) -> None:
        """写入完成后无临时文件残留"""
        tmp = tmp_path
        f = tmp / "test.txt"
        write_file(str(f), "content")
        # 检查目录中无 .tmp 文件残留
        tmp_files = glob.glob(str(tmp / "*.tmp"))
        assert len(tmp_files) == 0, f"发现临时文件残留: {tmp_files}"

    def test_write_unicode_content(self, tmp_path: Path) -> None:
        """写入 Unicode 内容（中文+emoji）"""
        tmp = tmp_path
        f = tmp / "unicode.txt"
        content = "# 变更台帐\n| ✅已关闭 | 🔄实施中 |\n"
        write_file(str(f), content)
        assert f.read_text(encoding="utf-8") == content

    def test_write_empty_content(self, tmp_path: Path) -> None:
        """写入空内容"""
        tmp = tmp_path
        f = tmp / "empty.txt"
        write_file(str(f), "")
        assert f.read_text(encoding="utf-8") == ""

    def test_write_large_content(self, tmp_path: Path) -> None:
        """写入大内容（验证 fsync 不中断）"""
        tmp = tmp_path
        f = tmp / "large.txt"
        content = "x" * 100000  # 100KB
        write_file(str(f), content)
        result = f.read_text(encoding="utf-8")
        assert len(result) == 100000
        assert result == content

    def test_write_to_nested_dir(self, tmp_path: Path) -> None:
        """写入深层嵌套目录（自动创建父目录 + 原子替换）"""
        tmp = tmp_path
        f = tmp / "a" / "b" / "c" / "d" / "test.txt"
        write_file(str(f), "nested")
        assert f.read_text(encoding="utf-8") == "nested"
        # 确认无临时文件残留
        for dirpath, _dirs, files in os.walk(str(tmp)):
            for fname in files:
                assert not fname.endswith(".tmp"), f"临时文件残留: {dirpath}/{fname}"

    def test_overwrite_does_not_corrupt(self, tmp_path: Path) -> None:
        """覆盖写入不会损坏文件（原子替换保证）"""
        tmp = tmp_path
        f = tmp / "test.txt"
        f.write_text("original", encoding="utf-8")
        write_file(str(f), "replacement")
        # 文件应该完整包含新内容
        assert f.read_text(encoding="utf-8") == "replacement"
        # 确认没有额外的临时文件
        all_files = list(tmp.iterdir())
        assert len(all_files) == 1, f"目录中有额外文件: {all_files}"

    def test_write_rejects_stale_mtime(self, tmp_path: Path) -> None:
        """expected_mtime 不匹配时拒绝覆盖外部更新"""
        tmp = tmp_path
        f = tmp / "stale.txt"
        write_file(str(f), "v1")
        expected_mtime = get_mtime(str(f))
        time.sleep(1.1)
        write_file(str(f), "v2")

        with pytest.raises(StaleFileError):
            write_file(str(f), "v1+client", expected_mtime=expected_mtime)

        assert f.read_text(encoding="utf-8") == "v2"

    def test_write_allows_matching_expected_mtime(self, tmp_path: Path) -> None:
        """expected_mtime 匹配时允许写入"""
        tmp = tmp_path
        f = tmp / "match.txt"
        write_file(str(f), "v1")
        expected_mtime = get_mtime(str(f))
        write_file(str(f), "v2", expected_mtime=expected_mtime)
        assert f.read_text(encoding="utf-8") == "v2"


class TestGetMtime:
    """get_mtime 测试"""

    def test_get_mtime_existing_file(self, tmp_path: Path) -> None:
        """获取存在文件的修改时间"""
        tmp = tmp_path
        f = tmp / "test.txt"
        f.write_text("hello", encoding="utf-8")
        assert get_mtime(str(f)) > 0

    def test_get_mtime_nonexistent_file(self, tmp_path: Path) -> None:
        """获取不存在文件的修改时间返回 0"""
        tmp = tmp_path
        assert get_mtime(str(tmp / "nonexistent.txt")) == 0.0


class TestReadFileSnapshot:
    """read_file_snapshot 测试"""

    def test_snapshot_returns_content_and_mtime(self, tmp_path: Path) -> None:
        """稳定文件应返回同一版本的内容和 mtime"""
        tmp = tmp_path
        f = tmp / "snapshot.txt"
        f.write_text("hello", encoding="utf-8")

        content, mtime = read_file_snapshot(str(f))

        assert content == "hello"
        assert mtime == get_mtime(str(f))
