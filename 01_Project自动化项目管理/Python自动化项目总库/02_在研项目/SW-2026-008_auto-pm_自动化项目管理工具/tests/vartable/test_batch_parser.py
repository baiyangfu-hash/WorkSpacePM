"""BatchParser 测试 - V2.3 Week3 T14

验证 BatchParser 的 parse_directory/parse_files + 递归扫描 + 错误处理。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.vartable.batch_parser import BatchParser


def _create_scl_file(dir_path: Path, name: str = "fb.scl") -> Path:
    """在指定目录创建 SCL 测试文件"""
    f = dir_path / name
    f.write_text(
        "FUNCTION_BLOCK FB_Test\n"
        "VAR_INPUT\n"
        "  i_bStart : BOOL;\n"
        "END_VAR\n"
        "END_FUNCTION_BLOCK\n",
        encoding="utf-8",
    )
    return f


def _create_io_points_csv(dir_path: Path) -> Path:
    """在指定目录创建 io_points.csv 测试文件"""
    f = dir_path / "io_points.csv"
    f.write_text(
        "station,signal_type,address,tag,signal_name,device,comment\n"
        "cpu,DI,X0,Tag1,name1,dev1,comment1\n",
        encoding="utf-8",
    )
    return f


class TestBatchParserParseFiles:
    def test_batch_parse_files_multiple_formats(self, tmp_path: Path) -> None:
        """parse_files 批量解析多格式文件列表"""
        scl_file = _create_scl_file(tmp_path, "fb1.scl")
        csv_file = _create_io_points_csv(tmp_path)

        results = BatchParser().parse_files([scl_file, csv_file])
        assert len(results) == 2

        # 第 1 个：SCL 文件
        assert results[0].success
        assert results[0].var_table is not None
        assert results[0].var_table.source_format == "scl"
        assert results[0].var_table.total_count == 1  # 1 个 VAR_INPUT 变量

        # 第 2 个：io_points.csv 文件
        assert results[1].success
        assert results[1].var_table is not None
        assert results[1].var_table.source_format == "io_points_csv"
        assert results[1].var_table.total_count == 1

    def test_batch_parse_files_with_unrecognized_format(self, tmp_path: Path) -> None:
        """parse_files 对不识别的格式返回 success=False + warning"""
        unknown_file = tmp_path / "unknown.txt"
        unknown_file.write_text("some random content\n", encoding="utf-8")

        results = BatchParser().parse_files([unknown_file])
        assert len(results) == 1
        assert not results[0].success
        assert results[0].var_table is None
        assert results[0].warning_count >= 1


class TestBatchParserParseDirectory:
    def test_batch_parse_directory_non_recursive(self, tmp_path: Path) -> None:
        """parse_directory 非递归扫描：仅扫顶层目录"""
        # 顶层 2 个支持文件
        _create_scl_file(tmp_path, "fb.scl")
        _create_io_points_csv(tmp_path)

        # 子目录 1 个文件（非递归应跳过）
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        _create_scl_file(subdir, "fb_sub.scl")

        results = BatchParser().parse_directory(tmp_path, recursive=False)
        # 非递归只扫顶层：2 个文件
        assert len(results) == 2
        # 全部成功
        assert all(r.success for r in results)

    def test_batch_parse_directory_recursive(self, tmp_path: Path) -> None:
        """parse_directory 递归扫描：含子目录文件"""
        # 顶层 2 个支持文件
        _create_scl_file(tmp_path, "fb.scl")
        _create_io_points_csv(tmp_path)

        # 子目录 1 个文件（递归应扫描）
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        _create_scl_file(subdir, "fb_sub.scl")

        results = BatchParser().parse_directory(tmp_path, recursive=True)
        # 递归扫顶层 2 + 子目录 1 = 3 个文件
        assert len(results) == 3
        assert all(r.success for r in results)

        # 验证子目录文件被扫描到
        source_formats = []
        for r in results:
            if r.var_table is not None:
                source_formats.append(r.var_table.source_path)
        assert any("subdir" in p for p in source_formats)

    def test_batch_parse_directory_not_found_raises(self, tmp_path: Path) -> None:
        """parse_directory 目录不存在抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            BatchParser().parse_directory(tmp_path / "not_exist")

    def test_batch_parse_directory_not_a_directory_raises(
        self, tmp_path: Path
    ) -> None:
        """parse_directory 路径是文件而非目录抛 NotADirectoryError"""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content", encoding="utf-8")
        with pytest.raises(NotADirectoryError):
            BatchParser().parse_directory(file_path)
