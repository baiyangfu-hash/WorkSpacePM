"""IntDocParser 深化测试 - V2.3 Week3 T12

验证 IntDocParser 的 detect_format 方法 + Markdown 表格解析 + 区段识别。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.vartable.parsers.intdoc_parser import IntDocParser


class TestIntDocParserDetectFormat:
    def test_intdoc_detect_format_md_with_var_section(self, tmp_path: Path) -> None:
        """detect_format 对含 ### VAR_INPUT 区段的 .md 文件返回 True"""
        f = tmp_path / "接口文档.md"
        f.write_text(
            "# FB_Test 接口文档\n\n"
            "## 2.1 VAR_INPUT\n\n"
            "| 变量名 | 类型 | 注释 |\n"
            "|---|---|---|\n"
            "| i_bStart | BOOL | 启动 |\n",
            encoding="utf-8",
        )
        assert IntDocParser().detect_format(f) is True

    def test_intdoc_detect_format_non_intdoc(self, tmp_path: Path) -> None:
        """detect_format 对非 intdoc 文件返回 False"""
        f = tmp_path / "var.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\nVAR_INPUT\n  i_bStart : BOOL;\nEND_VAR\n",
            encoding="utf-8",
        )
        assert IntDocParser().detect_format(f) is False


class TestIntDocParserTableExtraction:
    def test_intdoc_parse_table_with_column_name_identification(
        self, tmp_path: Path
    ) -> None:
        """解析 Markdown 表格，验证表头列名识别 + 字段提取"""
        f = tmp_path / "接口文档.md"
        f.write_text(
            "# FB_Conveyor 接口文档\n\n"
            "## 2.1 VAR_INPUT\n\n"
            "| 变量名 | 类型 | 注释 |\n"
            "|---|---|---|\n"
            "| i_bStart | BOOL | 启动按钮 |\n"
            "| i_bStop | BOOL | 停止按钮 |\n"
            "| i_wSpeed | INT | 速度设定 |\n\n"
            "## 2.2 VAR_OUTPUT\n\n"
            "| 变量名 | 类型 | 注释 |\n"
            "|---|---|---|\n"
            "| q_bRunning | BOOL | 运行中 |\n"
            "| q_iAlarmCode | INT | 报警码 |\n",
            encoding="utf-8",
        )
        result = IntDocParser().parse(f)
        assert result.success
        assert result.var_table is not None
        # 3 input + 2 output = 5 个变量
        assert result.var_table.total_count == 5

        # 验证 VAR_INPUT 区段变量
        input_entries = [
            e for e in result.var_table.entries if e.station == "VAR_INPUT"
        ]
        assert len(input_entries) == 3
        assert input_entries[0].tag == "i_bStart"
        assert input_entries[0].signal_type == "BOOL"
        assert input_entries[0].comment == "启动按钮"
        assert input_entries[0].source_format == "intdoc"

        # 验证 VAR_OUTPUT 区段变量
        output_entries = [
            e for e in result.var_table.entries if e.station == "VAR_OUTPUT"
        ]
        assert len(output_entries) == 2
        assert output_entries[1].tag == "q_iAlarmCode"
        assert output_entries[1].signal_type == "INT"
        assert output_entries[1].comment == "报警码"

        # 元数据：识别到 2 个区段
        assert result.var_table.metadata["section_count"] == 2


class TestIntDocParserEdgeCases:
    def test_intdoc_parse_no_var_section_emits_warning(
        self, tmp_path: Path
    ) -> None:
        """无 VAR 区段的 Markdown：success=True + warnings 提示"""
        f = tmp_path / "无变量文档.md"
        f.write_text(
            "# 概述文档\n\n"
            "## 1. 项目背景\n\n"
            "本项目用于边框缓存机控制。\n\n"
            "## 2. 工艺流程\n\n"
            "1. 上料\n2. 缓存\n3. 下料\n",
            encoding="utf-8",
        )
        result = IntDocParser().parse(f)
        # IntDoc 解析默认 success=True（即使无 VAR 区段也视为格式识别成功）
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 0
        assert result.warning_count >= 1
        assert result.var_table.metadata["section_count"] == 0


class TestIntDocParserVarConstant:
    def test_intdoc_var_constant_section_is_separate_scope(
        self, tmp_path: Path
    ) -> None:
        """### VAR CONSTANT 区段归为 VAR_CONSTANT（常量类），不再并入 VAR"""
        f = tmp_path / "接口文档.md"
        f.write_text(
            "# FB_Demo 接口文档\n\n"
            "## 2.1 VAR\n\n"
            "| 变量名 | 类型 | 注释 |\n"
            "|---|---|---|\n"
            "| s_iStep | INT | 当前步号 |\n\n"
            "## 2.2 VAR CONSTANT\n\n"
            "| 变量名 | 类型 | 注释 |\n"
            "|---|---|---|\n"
            "| STEP_IDLE | INT | 空闲步 |\n"
            "| T_TIMEOUT | DINT | 超时 5s |\n",
            encoding="utf-8",
        )
        result = IntDocParser().parse(f)
        assert result.success
        assert result.var_table is not None
        scope_by_tag = {e.tag: e.station for e in result.var_table.entries}
        assert scope_by_tag == {
            "s_iStep": "VAR",
            "STEP_IDLE": "VAR_CONSTANT",
            "T_TIMEOUT": "VAR_CONSTANT",
        }
