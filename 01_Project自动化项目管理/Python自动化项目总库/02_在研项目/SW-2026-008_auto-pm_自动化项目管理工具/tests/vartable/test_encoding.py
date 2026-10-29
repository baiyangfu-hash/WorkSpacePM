"""编码检测测试 - V2.3 Week1 T05

detect_encoding / read_file_with_detection / normalize_encoding
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.vartable.utils.encoding import (
    SUPPORTED_ENCODINGS,
    detect_encoding,
    normalize_encoding,
    read_file_with_detection,
)


class TestDetectEncoding:
    def test_utf8_no_bom(self, tmp_path: Path) -> None:
        """UTF-8 无 BOM"""
        f = tmp_path / "u8.txt"
        f.write_text("hello 你好", encoding="utf-8")
        assert detect_encoding(f) == "utf-8"

    def test_utf8_with_bom(self, utf8_bom_csv: Path) -> None:
        """UTF-8 BOM"""
        assert detect_encoding(utf8_bom_csv) == "utf-8-sig"

    def test_gbk_file(self, gbk_csv: Path) -> None:
        """GBK 编码"""
        assert detect_encoding(gbk_csv) == "gbk"

    def test_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在"""
        import pytest

        with pytest.raises(FileNotFoundError):
            detect_encoding(tmp_path / "not_exist.txt")


class TestReadFileWithDetection:
    def test_read_utf8(self, tmp_path: Path) -> None:
        """读取 UTF-8 文件"""
        f = tmp_path / "r.txt"
        f.write_text("content 你好", encoding="utf-8")
        content, enc = read_file_with_detection(f)
        assert enc == "utf-8"
        assert "你好" in content

    def test_read_gbk(self, gbk_csv: Path) -> None:
        """读取 GBK 文件"""
        content, enc = read_file_with_detection(gbk_csv)
        assert enc == "gbk"
        assert "信号名" in content


class TestNormalizeEncoding:
    def test_alias_utf8(self) -> None:
        """UTF8 → utf-8"""
        assert normalize_encoding("UTF8") == "utf-8"

    def test_alias_gb18030(self) -> None:
        """GB18030 → gbk"""
        assert normalize_encoding("GB18030") == "gbk"

    def test_empty_returns_utf8(self) -> None:
        """空字符串 → utf-8"""
        assert normalize_encoding("") == "utf-8"

    def test_supported_encodings_list(self) -> None:
        """SUPPORTED_ENCODINGS 非空"""
        assert len(SUPPORTED_ENCODINGS) >= 5
        assert "utf-8" in SUPPORTED_ENCODINGS
        assert "gbk" in SUPPORTED_ENCODINGS
