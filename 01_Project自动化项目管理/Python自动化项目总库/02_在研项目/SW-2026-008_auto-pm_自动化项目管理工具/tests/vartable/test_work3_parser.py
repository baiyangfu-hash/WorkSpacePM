"""Work3Parser 深化测试 - V2.3 Week3 T12

验证 Work3Parser 的 detect_format 方法 + tab 分隔字段提取 + 错误处理。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.vartable.parsers.work3_parser import Work3Parser


class TestWork3ParserDetectFormat:
    def test_work3_detect_format_wr3_extension(self, tmp_path: Path) -> None:
        """detect_format 对 .wr3 文件返回 True"""
        f = tmp_path / "var.wr3"
        # 前 2 行表头 + 1 行数据（8 字段 tab 分隔）
        f.write_text(
            "Header1\tHeader2\tHeader3\tHeader4\tHeader5\tHeader6\tHeader7\tHeader8\n"
            "Name\tType\tExtra\tExtra\tExtra\tExtra\tAddress\tDescription\n"
            "VAR_INPUT\ti_bStart\tBOOL\t\t\t\tX0\t启动\n",
            encoding="utf-8",
        )
        assert Work3Parser().detect_format(f) is True

    def test_work3_detect_format_non_work3(self, tmp_path: Path) -> None:
        """detect_format 对非 work3 文件返回 False"""
        f = tmp_path / "var.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\nVAR_INPUT\n  i_bStart : BOOL;\nEND_VAR\n",
            encoding="utf-8",
        )
        assert Work3Parser().detect_format(f) is False


class TestWork3ParserFieldExtraction:
    def test_work3_parse_address_and_description_extraction(
        self, tmp_path: Path
    ) -> None:
        """解析 Work3 文件，验证 scope/name/type/address/description 字段提取"""
        f = tmp_path / "var.wr3"
        f.write_text(
            "Header1\tHeader2\tHeader3\tHeader4\tHeader5\tHeader6\tHeader7\tHeader8\n"
            "Name\tType\tExtra\tExtra\tExtra\tExtra\tAddress\tDescription\n"
            "VAR_INPUT\ti_bStart\tBOOL\t\t\t\tX0\t启动按钮\n"
            "VAR_OUTPUT\tq_bRun\tBOOL\t\t\t\tY0\t运行中\n"
            "VAR_INPUT\ti_wCount\tINT\t\t\t\tD100\t计数器\n",
            encoding="utf-8",
        )
        result = Work3Parser().parse(f)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 3

        # 验证字段提取（索引：scope=0/name=1/type=2/address=6/desc=7）
        entry0 = result.var_table.entries[0]
        assert entry0.tag == "i_bStart"
        assert entry0.signal_type == "BOOL"
        assert entry0.address == "X0"
        assert entry0.comment == "启动按钮"
        assert entry0.station == "VAR_INPUT"
        assert entry0.source_format == "work3"
        assert entry0.line_number == 3  # 前 2 行表头，数据从第 3 行开始

        # 验证第 3 个条目（INT 类型）
        entry2 = result.var_table.entries[2]
        assert entry2.tag == "i_wCount"
        assert entry2.signal_type == "INT"
        assert entry2.address == "D100"

        # 派生属性
        assert set(result.var_table.stations) == {"VAR_INPUT", "VAR_OUTPUT"}
        assert set(result.var_table.signal_types) == {"BOOL", "INT"}


class TestWork3ParserErrorHandling:
    def test_work3_parse_insufficient_fields_records_error(
        self, tmp_path: Path
    ) -> None:
        """字段数不足 8 列的行计入 errors，不中断整体解析"""
        f = tmp_path / "var.wr3"
        f.write_text(
            "Header1\tHeader2\tHeader3\tHeader4\tHeader5\tHeader6\tHeader7\tHeader8\n"
            "Name\tType\tExtra\tExtra\tExtra\tExtra\tAddress\tDescription\n"
            "VAR_INPUT\ti_bStart\tBOOL\t\t\t\tX0\t启动\n"
            "BAD_ROW\tOnlyThreeFields\t\n"  # 仅 3 字段
            "VAR_OUTPUT\tq_bRun\tBOOL\t\t\t\tY0\t运行\n",
            encoding="utf-8",
        )
        result = Work3Parser().parse(f)
        # 部分成功：2 个有效条目 + 1 个错误
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 2
        assert result.error_count == 1
        assert result.errors[0].field == "columns"
        assert result.errors[0].line_number == 4


# 真实样例 fixture 路径（tests/vartable/samples/Work-FB变量表导出.csv）
_WORK3_REAL_SAMPLE = Path(__file__).parent / "samples" / "Work-FB变量表导出.csv"


class TestWork3ParserRealSample:
    """W1-S05：真实样例（02_设计/Work-FB变量表导出.csv）端到端测试

    样例特征：UTF-16 LE 编码 + tab 分隔 + 27 列中文表头 + 53 行（含 7 个空行）
    预期：44 entries, 0 errors（W1-S01 中文表头识别 + W1-S03 address 清理）
    """

    def test_work3_parse_real_sample_utf16_le(self) -> None:
        """真实样例端到端解析：success + 44 entries + 0 errors + UTF-16 LE 编码"""
        assert _WORK3_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = Work3Parser().parse(_WORK3_REAL_SAMPLE)
        assert result.success
        assert result.var_table is not None
        assert result.error_count == 0
        assert result.var_table.total_count == 44
        # 编码检测应识别 UTF-16 LE（chardet 可能返回 utf-16 或 utf-16-le）
        assert result.var_table.encoding.lower().startswith("utf-16")

    def test_work3_parse_real_sample_entries_count(self) -> None:
        """验证真实样例解析出 44 个条目（跳过 2 行表头 + 7 个空行后剩余数据行）"""
        assert _WORK3_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = Work3Parser().parse(_WORK3_REAL_SAMPLE)
        assert result.var_table is not None
        assert result.var_table.total_count == 44
        # metadata 记录读取行数 = entries + errors
        assert result.var_table.metadata["total_rows_read"] == 44

    def test_work3_parse_real_sample_address_no_quotes(self) -> None:
        """W1-S03 回归：address 字段不得含残留双引号字符

        真实样例空字段值为 ""（两个引号字符），未 strip('"') 前会残留引号。
        """
        assert _WORK3_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = Work3Parser().parse(_WORK3_REAL_SAMPLE)
        assert result.var_table is not None
        for entry in result.var_table.entries:
            # 真实样例地址列全空，strip('"') 后应为空串，不得残留 "
            assert '"' not in entry.address, (
                f"line {entry.line_number} address 残留引号: {entry.address!r}"
            )

    def test_work3_parse_real_sample_var_input_scope(self) -> None:
        """验证 station 字段含 VAR_INPUT/VAR_OUTPUT/VAR_IN_OUT/VAR 四种 scope"""
        assert _WORK3_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = Work3Parser().parse(_WORK3_REAL_SAMPLE)
        assert result.var_table is not None
        # 真实样例数据行第 1 列是 scope（VAR_INPUT/VAR_OUTPUT/VAR_IN_OUT/VAR）
        assert set(result.var_table.stations) == {
            "VAR_INPUT",
            "VAR_OUTPUT",
            "VAR_IN_OUT",
            "VAR",
        }
        # 第 1 个条目（第 3 行）应为 VAR_INPUT scope
        first = result.var_table.entries[0]
        assert first.station == "VAR_INPUT"
        assert first.source_format == "work3"

    def test_work3_parse_real_sample_fb_name_metadata(self) -> None:
        """验证 FB 名占位（第 1 行）与 parse metadata 结构

        真实样例第 1 行为 FB 名占位 "边框缓存机"（parser 跳过前 2 行表头）。
        当前 work3_parser 仅记录 total_rows_read，FB 名位于源文件第 1 行。
        """
        assert _WORK3_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = Work3Parser().parse(_WORK3_REAL_SAMPLE)
        assert result.var_table is not None
        # metadata 含 total_rows_read
        assert "total_rows_read" in result.var_table.metadata
        assert result.var_table.metadata["total_rows_read"] == 44
        # 源文件第 1 行为 FB 名占位（UTF-16 LE 解码）
        raw = _WORK3_REAL_SAMPLE.read_bytes()
        first_line = raw.decode("utf-16").splitlines()[0]
        assert first_line == '"边框缓存机"'

    def test_work3_parse_real_sample_data_types(self) -> None:
        """验证数据类型含 BOOL/INT/TIMER_100_FB_M/ARRAY 等真实类型"""
        assert _WORK3_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        result = Work3Parser().parse(_WORK3_REAL_SAMPLE)
        assert result.var_table is not None
        types = set(result.var_table.signal_types)
        # 真实样例覆盖的信号类型
        assert "BOOL" in types
        assert "INT" in types
        assert "TIMER_100_FB_M" in types
        assert "ARRAY [0..9] OF BOOL" in types
        assert "ARRAY [0..9] OF INT" in types
