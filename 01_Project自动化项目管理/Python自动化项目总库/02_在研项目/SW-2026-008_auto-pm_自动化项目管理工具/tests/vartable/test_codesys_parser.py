"""CodesysParser 深化测试 - V2.3 Week3 T12

验证 CodesysParser 的 detect_format 方法 + 英文列名 CSV 字段提取 + 错误处理。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.vartable.parsers.codesys_parser import CodesysParser


class TestCodesysParserDetectFormat:
    def test_codesys_detect_format_csv_with_english_columns(
        self, tmp_path: Path
    ) -> None:
        """detect_format 对含 Name+Type 列的 CSV 返回 True"""
        f = tmp_path / "var.csv"
        f.write_text(
            "Name,Type,Address,Comment,Scope\n"
            "i_bStart,BOOL,X0,Start,VAR_INPUT\n",
            encoding="utf-8",
        )
        assert CodesysParser().detect_format(f) is True

    def test_codesys_detect_format_non_codesys(self, tmp_path: Path) -> None:
        """detect_format 对非 codesys 文件返回 False"""
        f = tmp_path / "var.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\nVAR_INPUT\n  i_bStart : BOOL;\nEND_VAR\n",
            encoding="utf-8",
        )
        assert CodesysParser().detect_format(f) is False


class TestCodesysParserFieldExtraction:
    def test_codesys_parse_english_columns_extraction(self, tmp_path: Path) -> None:
        """解析 Codesys 英文列名 CSV，验证字段提取正确性"""
        f = tmp_path / "var.csv"
        f.write_text(
            "Name,Type,Address,Comment,Scope\n"
            "i_bStart,BOOL,X0,Start button,VAR_INPUT\n"
            "i_bStop,BOOL,X1,Stop button,VAR_INPUT\n"
            "q_bRun,BOOL,Y0,Running,VAR_OUTPUT\n"
            "i_wCounter,INT,D100,Counter value,VAR_INPUT\n",
            encoding="utf-8",
        )
        result = CodesysParser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 4

        # 验证字段提取
        entry0 = result.var_table.entries[0]
        assert entry0.tag == "i_bStart"
        assert entry0.signal_type == "BOOL"
        assert entry0.address == "X0"
        assert entry0.comment == "Start button"
        assert entry0.station == "VAR_INPUT"
        assert entry0.source_format == "codesys"
        assert entry0.line_number == 2

        # 验证 INT 类型条目
        entry3 = result.var_table.entries[3]
        assert entry3.tag == "i_wCounter"
        assert entry3.signal_type == "INT"
        assert entry3.address == "D100"

        # 派生属性
        assert set(result.var_table.stations) == {"VAR_INPUT", "VAR_OUTPUT"}
        assert set(result.var_table.signal_types) == {"BOOL", "INT"}


class TestCodesysParserErrorHandling:
    def test_codesys_parse_missing_name_records_error(self, tmp_path: Path) -> None:
        """Name 字段为空的行计入 errors，不中断整体解析"""
        f = tmp_path / "var.csv"
        f.write_text(
            "Name,Type,Address,Comment,Scope\n"
            "i_bStart,BOOL,X0,Start,VAR_INPUT\n"
            ",BOOL,X1,Missing name,VAR_INPUT\n"
            "q_bRun,BOOL,Y0,Running,VAR_OUTPUT\n",
            encoding="utf-8",
        )
        result = CodesysParser().parse(f)
        # 部分成功：2 个有效条目 + 1 个错误
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 2
        assert result.error_count == 1
        assert result.errors[0].field == "name"
        assert result.errors[0].line_number == 3
