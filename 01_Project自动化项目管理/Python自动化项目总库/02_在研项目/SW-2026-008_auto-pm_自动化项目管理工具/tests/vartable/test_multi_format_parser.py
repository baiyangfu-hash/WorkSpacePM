"""多格式解析器骨架测试 - V2.3 Week2 T10

BaseParser 抽象基类 + 5 种格式 Parser（Autoshop/Codesys/SCL/Work3/IntDoc）接口验证。

任务 T10 要求 multi_format_parser.py，实际实现拆为 base_parser.py + 5 个独立格式 parser
文件（更合理的模块化设计）。本测试验证基类接口 + 各格式 parser 的基本解析流程。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.vartable.parsers.autoshop_parser import AutoshopParser
from auto_pm.vartable.parsers.base_parser import BaseParser
from auto_pm.vartable.parsers.codesys_parser import CodesysParser
from auto_pm.vartable.parsers.intdoc_parser import IntDocParser
from auto_pm.vartable.parsers.scl_parser import SclParser
from auto_pm.vartable.parsers.work3_parser import Work3Parser


class TestBaseParserAbstract:
    def test_base_parser_is_abstract(self) -> None:
        """BaseParser 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            BaseParser()  # type: ignore[abstract]

    def test_all_format_parsers_inherit_base(self) -> None:
        """5 种格式 Parser 都继承 BaseParser"""
        for parser_cls in (
            AutoshopParser,
            CodesysParser,
            SclParser,
            Work3Parser,
            IntDocParser,
        ):
            assert issubclass(parser_cls, BaseParser)


class TestFormatParserInterfaces:
    def test_autoshop_parser_parse_basic(self, tmp_path: Path) -> None:
        """AutoshopParser 解析 .asc 基本流程（中文列名 CSV）"""
        f = tmp_path / "var.asc"
        f.write_text(
            "变量名,数据类型,地址,注释,作用域\n"
            "i_bStart,BOOL,X0,启动按钮,VAR_INPUT\n"
            "i_bStop,BOOL,X1,停止按钮,VAR_INPUT\n",
            encoding="utf-8",
        )
        result = AutoshopParser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 2
        assert result.var_table.entries[0].tag == "i_bStart"
        assert result.var_table.entries[0].station == "VAR_INPUT"
        assert result.var_table.source_format == "autoshop"

    def test_codesys_parser_parse_basic(self, tmp_path: Path) -> None:
        """CodesysParser 解析 .csv 基本流程（英文列名 CSV）"""
        f = tmp_path / "var.csv"
        f.write_text(
            "Name,Type,Address,Comment,Scope\n"
            "i_bStart,BOOL,X0,Start,VAR_INPUT\n",
            encoding="utf-8",
        )
        result = CodesysParser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 1
        assert result.var_table.entries[0].tag == "i_bStart"
        assert result.var_table.source_format == "codesys"

    def test_scl_parser_parse_basic(self, tmp_path: Path) -> None:
        """SclParser 解析 .scl 基本流程（VAR_INPUT/VAR_OUTPUT 块提取）"""
        f = tmp_path / "fb.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\n"
            "VAR_INPUT\n"
            "  i_bStart : BOOL; // 启动\n"
            "  i_bStop : BOOL; // 停止\n"
            "END_VAR\n"
            "VAR_OUTPUT\n"
            "  q_bRunning : BOOL;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n",
            encoding="utf-8",
        )
        result = SclParser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 3  # 2 input + 1 output
        tags = {e.tag for e in result.var_table.entries}
        assert tags == {"i_bStart", "i_bStop", "q_bRunning"}
        assert result.var_table.source_format == "scl"
        # FB 名称元数据
        assert result.var_table.metadata["fb_name"] == "FB_Test"

    def test_work3_parser_parse_basic(self, tmp_path: Path) -> None:
        """Work3Parser 解析 .wr3 基本流程（tab 分隔，跳前 2 行表头）"""
        f = tmp_path / "var.wr3"
        # 前 2 行表头 + 数据行（8 字段 tab 分隔）
        f.write_text(
            "Header1\tHeader2\tHeader3\tHeader4\tHeader5\tHeader6\tHeader7\tHeader8\n"
            "Name\tType\tExtra\tExtra\tExtra\tExtra\tAddress\tDescription\n"
            "VAR_INPUT\ti_bStart\tBOOL\t\t\t\tX0\t启动按钮\n"
            "VAR_OUTPUT\tq_bRun\tBOOL\t\t\t\tY0\t运行中\n",
            encoding="utf-8",
        )
        result = Work3Parser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 2
        assert result.var_table.entries[0].tag == "i_bStart"
        assert result.var_table.entries[0].address == "X0"
        assert result.var_table.source_format == "work3"

    def test_intdoc_parser_parse_basic(self, tmp_path: Path) -> None:
        """IntDocParser 解析 .md 接口文档基本流程（VAR_INPUT/VAR_OUTPUT 区段表格）"""
        f = tmp_path / "接口文档.md"
        f.write_text(
            "# FB_Test 接口文档\n\n"
            "## 2.1 VAR_INPUT\n\n"
            "| 变量名 | 类型 | 注释 |\n"
            "|---|---|---|\n"
            "| i_bStart | BOOL | 启动 |\n"
            "| i_bStop | BOOL | 停止 |\n\n"
            "## 2.2 VAR_OUTPUT\n\n"
            "| 变量名 | 类型 | 注释 |\n"
            "|---|---|---|\n"
            "| q_bRun | BOOL | 运行 |\n",
            encoding="utf-8",
        )
        result = IntDocParser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 3
        tags = {e.tag for e in result.var_table.entries}
        assert tags == {"i_bStart", "i_bStop", "q_bRun"}
        assert result.var_table.source_format == "intdoc"


class TestFormatParserErrorHandling:
    def test_parser_file_not_found(self, tmp_path: Path) -> None:
        """各 parser 文件不存在 → success=False, field='file'"""
        for parser_cls in (
            AutoshopParser,
            CodesysParser,
            SclParser,
            Work3Parser,
            IntDocParser,
        ):
            result = parser_cls().parse(tmp_path / "not_exist")
            assert not result.success, f"{parser_cls.__name__} 应失败"
            assert result.errors[0].field == "file"

    def test_parser_empty_content(self, tmp_path: Path) -> None:
        """各 parser 空文件 → success=False（content 错误）

        Work3Parser 空文件因行数不足 2 走 header 错误，也属失败。
        """
        for parser_cls in (
            AutoshopParser,
            CodesysParser,
            SclParser,
            Work3Parser,
            IntDocParser,
        ):
            f = tmp_path / f"empty_{parser_cls.__name__}.ext"
            f.write_text("", encoding="utf-8")
            result = parser_cls().parse(f)
            assert not result.success, f"{parser_cls.__name__} 空文件应失败"
