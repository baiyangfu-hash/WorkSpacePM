"""AutoshopParser 深化测试 - V2.3 Week3 T12

验证 AutoshopParser 的 detect_format 方法 + 真实字段提取 + 错误处理 + 编码兼容。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.vartable.parsers.autoshop_parser import AutoshopParser


class TestAutoshopParserDetectFormat:
    def test_autoshop_detect_format_asc_extension(self, tmp_path: Path) -> None:
        """detect_format 对 .asc 文件返回 True"""
        f = tmp_path / "var.asc"
        f.write_text(
            "变量名,数据类型,地址,注释,作用域\n"
            "i_bStart,BOOL,X0,启动,VAR_INPUT\n",
            encoding="utf-8",
        )
        assert AutoshopParser().detect_format(f) is True

    def test_autoshop_detect_format_non_autoshop(self, tmp_path: Path) -> None:
        """detect_format 对非 autoshop 文件返回 False"""
        f = tmp_path / "var.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\nVAR_INPUT\n  i_bStart : BOOL;\nEND_VAR\n",
            encoding="utf-8",
        )
        assert AutoshopParser().detect_format(f) is False


class TestAutoshopParserFieldExtraction:
    def test_autoshop_parse_multiline_with_chinese_columns(
        self, tmp_path: Path
    ) -> None:
        """解析多行含中文列名 CSV，验证字段提取正确性"""
        f = tmp_path / "var.asc"
        f.write_text(
            "变量名,数据类型,地址,注释,作用域\n"
            "i_bStart,BOOL,X0,启动按钮,VAR_INPUT\n"
            "i_bStop,BOOL,X1,停止按钮,VAR_INPUT\n"
            "q_bRun,BOOL,Y0,运行中,VAR_OUTPUT\n",
            encoding="utf-8",
        )
        result = AutoshopParser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 3

        # 验证第 1 个条目字段
        entry0 = result.var_table.entries[0]
        assert entry0.tag == "i_bStart"
        assert entry0.signal_type == "BOOL"
        assert entry0.address == "X0"
        assert entry0.comment == "启动按钮"
        assert entry0.station == "VAR_INPUT"
        assert entry0.source_format == "autoshop"
        assert entry0.line_number == 2  # 表头是第 1 行

        # 验证 station/signal_types 派生属性
        assert set(result.var_table.stations) == {"VAR_INPUT", "VAR_OUTPUT"}
        assert result.var_table.signal_types == ("BOOL",)

    def test_autoshop_parse_gbk_encoding(self, tmp_path: Path) -> None:
        """GBK 编码的 Autoshop 文件能正确解析（detect_encoding 兼容）"""
        f = tmp_path / "var_gbk.asc"
        content = (
            "变量名,数据类型,地址,注释,作用域\n"
            "i_bStart,BOOL,X0,启动按钮,VAR_INPUT\n"
        )
        f.write_bytes(content.encode("gbk"))
        result = AutoshopParser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 1
        assert result.var_table.entries[0].tag == "i_bStart"
        assert result.var_table.entries[0].comment == "启动按钮"
        # 编码检测应识别为 gbk 或 gb2312
        assert result.var_table.encoding in ("gbk", "gb2312", "utf-8")


class TestAutoshopParserErrorHandling:
    def test_autoshop_parse_missing_name_records_error(self, tmp_path: Path) -> None:
        """变量名为空的行计入 errors，不中断整体解析"""
        f = tmp_path / "var.asc"
        f.write_text(
            "变量名,数据类型,地址,注释,作用域\n"
            "i_bStart,BOOL,X0,启动,VAR_INPUT\n"
            ",BOOL,X1,缺变量名,VAR_INPUT\n"
            "q_bRun,BOOL,Y0,运行,VAR_OUTPUT\n",
            encoding="utf-8",
        )
        result = AutoshopParser().parse(f)
        # 部分成功：2 个有效条目 + 1 个错误
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 2
        assert result.error_count == 1
        assert result.errors[0].field == "name"
        assert result.errors[0].line_number == 3


# 真实样例 fixture 路径（tests/vartable/samples/Autoshop-FB变量表导出.csv）
_AUTOSHOP_REAL_SAMPLE = (
    Path(__file__).parent / "samples" / "Autoshop-FB变量表导出.csv"
)


class TestAutoshopParserRealSample:
    """W1-S05：真实样例（02_设计/Autoshop-FB变量表导出.csv）端到端测试

    样例特征：GBK 编码 + 逗号分隔 + 9 列中文表头（序号/类别/名称/数据类型/...）
    预期：90 entries, 0 errors（W1-S02 _AUTOSHOP_HEADER 第二分支识别）
    """

    def test_autoshop_parse_real_sample_gbk(self) -> None:
        """真实样例端到端解析：success + 90 entries + 0 errors + GBK 编码"""
        assert _AUTOSHOP_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = AutoshopParser().parse(_AUTOSHOP_REAL_SAMPLE)
        assert result.success
        assert result.var_table is not None
        assert result.error_count == 0
        assert result.var_table.total_count == 90
        # 编码检测应识别 GBK（chardet 可能返回 gbk 或 gb2312）
        assert result.var_table.encoding.lower() in ("gbk", "gb2312")

    def test_autoshop_parse_real_sample_entries_count(self) -> None:
        """验证真实样例解析出 90 个条目"""
        assert _AUTOSHOP_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = AutoshopParser().parse(_AUTOSHOP_REAL_SAMPLE)
        assert result.var_table is not None
        assert result.var_table.total_count == 90
        assert result.var_table.metadata["total_rows_read"] == 90

    def test_autoshop_parse_real_sample_in_scope(self) -> None:
        """验证 station 字段含 IN/OUT/INOUT/VAR 等 scope（来自"类别"列）"""
        assert _AUTOSHOP_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = AutoshopParser().parse(_AUTOSHOP_REAL_SAMPLE)
        assert result.var_table is not None
        # 真实样例"类别"列值：IN/OUT/INOUT/VAR + 数组展开行的 autoshop 默认值
        stations = set(result.var_table.stations)
        assert "IN" in stations
        assert "OUT" in stations
        assert "INOUT" in stations
        assert "VAR" in stations
        # 第 1 个条目（第 2 行）类别为 IN
        first = result.var_table.entries[0]
        assert first.station == "IN"
        assert first.source_format == "autoshop"

    def test_autoshop_parse_real_sample_i_start(self) -> None:
        """验证具体变量名 i_Start/i_Stop/i_Reset 等被正确提取"""
        assert _AUTOSHOP_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = AutoshopParser().parse(_AUTOSHOP_REAL_SAMPLE)
        assert result.var_table is not None
        tags = {e.tag for e in result.var_table.entries}
        # 真实样例前几行的变量名
        assert "i_Start" in tags
        assert "i_Stop" in tags
        assert "i_Reset" in tags
        assert "i_DriveAlarm" in tags
        # 第 1 个条目（第 2 行）应为 i_Start
        first = result.var_table.entries[0]
        assert first.tag == "i_Start"
        assert first.line_number == 2  # 表头第 1 行，数据从第 2 行开始

    def test_autoshop_parse_real_sample_comment_extraction(self) -> None:
        """验证 comment 字段正确提取中文注释（来自"注释"列）"""
        assert _AUTOSHOP_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = AutoshopParser().parse(_AUTOSHOP_REAL_SAMPLE)
        assert result.var_table is not None
        # 第 1 个条目注释 = 启动按钮信号
        first = result.var_table.entries[0]
        assert first.comment == "启动按钮信号"
        # 第 2 个条目注释 = 停止按钮信号
        second = result.var_table.entries[1]
        assert second.comment == "停止按钮信号"
        # 按 tag 查找 i_DriveAlarm 的注释
        alarm_entry = next(
            e for e in result.var_table.entries if e.tag == "i_DriveAlarm"
        )
        assert alarm_entry.comment == "驱动器报警信号"

    def test_autoshop_parse_real_sample_data_types(self) -> None:
        """验证数据类型含 BOOL/INT/REAL/DINT 等真实类型"""
        assert _AUTOSHOP_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = AutoshopParser().parse(_AUTOSHOP_REAL_SAMPLE)
        assert result.var_table is not None
        types = set(result.var_table.signal_types)
        # 真实样例覆盖的信号类型
        assert "BOOL" in types
        assert "INT" in types
        assert "REAL" in types
        assert "DINT" in types
        # 数组类型（i_tTimer1: BOOL[10] 等）
        assert "BOOL[10]" in types
        assert "DINT[10]" in types
        # i_SpeedFrequency 是 REAL 类型
        speed_entry = next(
            e for e in result.var_table.entries if e.tag == "i_SpeedFrequency"
        )
        assert speed_entry.signal_type == "REAL"
