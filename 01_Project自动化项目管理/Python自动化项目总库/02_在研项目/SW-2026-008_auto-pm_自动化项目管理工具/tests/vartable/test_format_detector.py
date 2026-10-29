"""格式自动识别器测试 - V2.3 Week2 T11

detect_format() / get_parser_for_format() / list_supported_formats()
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.vartable.models import FormatType
from auto_pm.domain.vartable.parsers.autoshop_parser import AutoshopParser
from auto_pm.domain.vartable.parsers.codesys_parser import CodesysParser
from auto_pm.domain.vartable.parsers.communications_parser import CommunicationsParser
from auto_pm.domain.vartable.parsers.format_detector import (
    detect_format,
    get_parser_for_format,
    list_supported_formats,
)
from auto_pm.domain.vartable.parsers.intdoc_parser import IntDocParser
from auto_pm.domain.vartable.parsers.io_points_parser import IoPointsParser
from auto_pm.domain.vartable.parsers.program_blocks_parser import ProgramBlocksParser
from auto_pm.domain.vartable.parsers.scl_parser import SclParser
from auto_pm.domain.vartable.parsers.work3_parser import Work3Parser


class TestDetectFormatByFilename:
    def test_detect_io_points_csv(self, tmp_path: Path) -> None:
        """io_points.csv 文件名 → IO_POINTS_CSV"""
        f = tmp_path / "io_points.csv"
        f.write_text(
            "station,signal_type,address,tag,signal_name,device,comment\n",
            encoding="utf-8",
        )
        assert detect_format(f) == FormatType.IO_POINTS_CSV

    def test_detect_program_blocks_yml(self, tmp_path: Path) -> None:
        """program_blocks.yml 文件名 → PROGRAM_BLOCKS_YML"""
        f = tmp_path / "program_blocks.yml"
        f.write_text("blocks: []\n", encoding="utf-8")
        assert detect_format(f) == FormatType.PROGRAM_BLOCKS_YML

    def test_detect_communications_yml(self, tmp_path: Path) -> None:
        """communications.yml 文件名 → COMMUNICATIONS_YML"""
        f = tmp_path / "communications.yml"
        f.write_text("channels: []\n", encoding="utf-8")
        assert detect_format(f) == FormatType.COMMUNICATIONS_YML

    def test_detect_program_blocks_yaml_alt_ext(self, tmp_path: Path) -> None:
        """program_blocks.yaml（.yaml 扩展名）→ PROGRAM_BLOCKS_YML"""
        f = tmp_path / "program_blocks.yaml"
        f.write_text("blocks: []\n", encoding="utf-8")
        assert detect_format(f) == FormatType.PROGRAM_BLOCKS_YML


class TestDetectFormatByExtension:
    def test_detect_scl_by_extension(self, tmp_path: Path) -> None:
        """.scl 扩展名 → SCL"""
        f = tmp_path / "fb.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\nEND_FUNCTION_BLOCK\n", encoding="utf-8"
        )
        assert detect_format(f) == FormatType.SCL

    def test_detect_awl_by_extension(self, tmp_path: Path) -> None:
        """.awl 扩展名 → SCL"""
        f = tmp_path / "fb.awl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\nEND_FUNCTION_BLOCK\n", encoding="utf-8"
        )
        assert detect_format(f) == FormatType.SCL

    def test_detect_autoshop_by_extension(self, tmp_path: Path) -> None:
        """.asc 扩展名 → AUTOSHOP"""
        f = tmp_path / "var.asc"
        f.write_text("变量名,数据类型\n", encoding="utf-8")
        assert detect_format(f) == FormatType.AUTOSHOP

    def test_detect_work3_by_extension(self, tmp_path: Path) -> None:
        """.wr3 扩展名 → WORK3"""
        f = tmp_path / "var.wr3"
        f.write_text(
            "Name\tType\tAddr\tDesc\n" "Name\tType\tAddr\tDesc\n",
            encoding="utf-8",
        )
        assert detect_format(f) == FormatType.WORK3


class TestDetectFormatByContent:
    def test_detect_scl_by_content(self, tmp_path: Path) -> None:
        """无 .scl 扩展名但内容含 FUNCTION_BLOCK → SCL"""
        f = tmp_path / "fb.txt"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\n"
            "VAR_INPUT\n"
            "  i_bStart : BOOL;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n",
            encoding="utf-8",
        )
        assert detect_format(f) == FormatType.SCL

    def test_detect_intdoc_by_content(self, tmp_path: Path) -> None:
        """Markdown 含 ### 2.1 VAR_INPUT 区段 → INTDOC"""
        f = tmp_path / "接口文档.md"
        f.write_text(
            "# FB 接口文档\n\n"
            "## 2.1 VAR_INPUT\n\n"
            "| 变量名 | 类型 |\n"
            "|---|---|\n"
            "| i_bStart | BOOL |\n",
            encoding="utf-8",
        )
        assert detect_format(f) == FormatType.INTDOC

    def test_detect_unknown_empty_file(self, tmp_path: Path) -> None:
        """空文件 → UNKNOWN"""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert detect_format(f) == FormatType.UNKNOWN

    def test_detect_unknown_unrecognized(self, tmp_path: Path) -> None:
        """无法识别的内容 → UNKNOWN"""
        f = tmp_path / "random.txt"
        f.write_text("这是一段无法识别的随机文本\n", encoding="utf-8")
        assert detect_format(f) == FormatType.UNKNOWN


class TestGetParserForFormat:
    def test_get_parser_all_formats(self) -> None:
        """每个 FormatType 都能拿到对应 parser 类"""
        assert get_parser_for_format(FormatType.AUTOSHOP) is AutoshopParser
        assert get_parser_for_format(FormatType.WORK3) is Work3Parser
        assert get_parser_for_format(FormatType.CODESYS) is CodesysParser
        assert get_parser_for_format(FormatType.SCL) is SclParser
        assert get_parser_for_format(FormatType.INTDOC) is IntDocParser
        assert get_parser_for_format(FormatType.IO_POINTS_CSV) is IoPointsParser
        assert (
            get_parser_for_format(FormatType.PROGRAM_BLOCKS_YML)
            is ProgramBlocksParser
        )
        assert (
            get_parser_for_format(FormatType.COMMUNICATIONS_YML)
            is CommunicationsParser
        )

    def test_get_parser_unknown_returns_none(self) -> None:
        """UNKNOWN 格式无 parser → None"""
        assert get_parser_for_format(FormatType.UNKNOWN) is None


class TestListSupportedFormats:
    def test_list_supported_formats_completeness(self) -> None:
        """list_supported_formats 含 8 种格式（不含 UNKNOWN）"""
        formats = list_supported_formats()
        format_types = [f for f, _, _ in formats]
        assert FormatType.UNKNOWN not in format_types
        assert len(formats) == 8
        # 每项结构完整：(FormatType, str, tuple[str,...])
        for f, desc, exts in formats:
            assert isinstance(f, FormatType)
            assert isinstance(desc, str) and desc
            assert isinstance(exts, tuple) and len(exts) > 0


# 真实样例 fixture 目录（tests/vartable/samples/）
_SAMPLES_DIR = Path(__file__).parent / "samples"
_WORK3_REAL_SAMPLE = _SAMPLES_DIR / "Work-FB变量表导出.csv"
_AUTOSHOP_REAL_SAMPLE = _SAMPLES_DIR / "Autoshop-FB变量表导出.csv"


class TestDetectFormatRealSamples:
    """W1-S05：真实样例（UTF-16 LE / GBK 编码）格式识别回归测试

    真实样例特征：
    - Work-FB变量表导出.csv：UTF-16 LE + tab 分隔 + 中文表头（类/标签名/数据类型）
    - Autoshop-FB变量表导出.csv：GBK + 逗号分隔 + 中文表头（序号/类别/名称/数据类型）
    回归 W1-S01（中文表头识别）+ W1-S02（收紧 AUTOSHOP 误判）
    """

    def test_detect_format_real_work3_sample_utf16_le(self) -> None:
        """真实 Work3 样例（UTF-16 LE）→ 识别为 WORK3，不误判为 AUTOSHOP

        W1-S01 修复：_WORK3_HEADER_CN 支持中文表头 + 第 2 行嗅探
        """
        assert _WORK3_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        fmt = detect_format(_WORK3_REAL_SAMPLE)
        # 回归 W1-S02：Work3 中文表头不得误判为 AUTOSHOP（先于正向断言，避免类型收窄）
        assert fmt != FormatType.AUTOSHOP
        assert fmt == FormatType.WORK3

    def test_detect_format_real_autoshop_sample_gbk(self) -> None:
        """真实 Autoshop 样例（GBK 编码）→ 识别为 AUTOSHOP

        W1-S02 修复：_AUTOSHOP_HEADER 第二分支匹配 类别+名称+数据类型 组合
        """
        assert _AUTOSHOP_REAL_SAMPLE.exists(), "真实样例 fixture 缺失"
        fmt = detect_format(_AUTOSHOP_REAL_SAMPLE)
        assert fmt == FormatType.AUTOSHOP

    def test_detect_format_work3_with_chinese_header(self, tmp_path: Path) -> None:
        """合成中文表头 + tab 分隔的 Work3 文件 → 识别为 WORK3

        验证 _WORK3_HEADER_CN 正则匹配 "类"/"标签名"/"数据类型" 组合
        """
        f = tmp_path / "fb_var.csv"
        # 第 1 行 FB 名称占位（1 列）+ 第 2 行中文表头（tab 分隔）模拟真实结构
        f.write_text(
            '"边框缓存机"\n'
            '"类"\t"标签名"\t"数据类型"\t"常数"\t"初始值"\t"分配(软元件/标签)"'
            '\t"地址"\t"注释"\n'
            '"VAR_INPUT"\t"阻挡前到位传感器"\t"BOOL"\t""\t""\t""\t""\t""\n',
            encoding="utf-8",
        )
        assert detect_format(f) == FormatType.WORK3

    def test_detect_format_autoshop_not_misidentify_work3(
        self, tmp_path: Path
    ) -> None:
        """回归 W1-S02：Work3 中文表头（含"类"+"数据类型"但无"类别"/"名称"）不误判为 AUTOSHOP

        原 OR 逻辑 `变量名|数据类型|作用域|类别` 因含"数据类型"把 Work3 误判为 Autoshop；
        收紧后要求"变量名"或"类别+名称+数据类型"组合，单"类"不匹配。
        """
        f = tmp_path / "work3_like.csv"
        # Work3 真实表头特征：含"类"和"数据类型"但无"类别"也无"名称"
        f.write_text(
            '"类"\t"标签名"\t"数据类型"\t"常数"\t"初始值"\t"分配"\t"地址"\t"注释"\n'
            '"VAR_INPUT"\t"i_bStart"\t"BOOL"\t""\t""\t""\t"X0"\t"启动"\n',
            encoding="utf-8",
        )
        fmt = detect_format(f)
        # 不得误判为 AUTOSHOP，应识别为 WORK3
        assert fmt != FormatType.AUTOSHOP
        assert fmt == FormatType.WORK3
