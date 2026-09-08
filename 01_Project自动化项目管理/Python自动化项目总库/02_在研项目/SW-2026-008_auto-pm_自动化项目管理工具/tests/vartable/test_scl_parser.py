"""SclParser 深化测试 - V2.3 Week3 T12

验证 SclParser 的 detect_format 方法 + VAR 块状态机解析 + 边界场景。

V0.5.x Week1 W1-S04: 扩展真实样例测试覆盖, 对 DJ-2026-005 项目的 6 个
真实 .scl 文件进行端到端解析验证 (OB1/FB_2001/FB_1002/FB_External/
FB_1004/FB_1003)。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.vartable.parsers.scl_parser import SclParser

# 工作空间根目录（从 tests/vartable 推导：7 级父目录）
_WORKSPACE_ROOT = Path(__file__).resolve().parents[6]

# DJ-2026-005 真实 SCL 样例根路径 (引用而非拷贝)
_DJ_2026_005_ST_ROOT = (
    _WORKSPACE_ROOT / "0100_PLC自动化" / "DJ-2026-005" / "02_PLC程序" / "PLC_ST"
)
OB1_SCL = _DJ_2026_005_ST_ROOT / "OB1" / "OB1.scl"
FB_2001_SCL = (
    _DJ_2026_005_ST_ROOT / "common" / "FB_2001_CommonAlarm_AllStation.scl"
)
FB_1002_SCL = (
    _DJ_2026_005_ST_ROOT
    / "conveyor"
    / "FB_1002_SingleLayerConveyor_BufferFraming.scl"
)
FB_EXTERNAL_SCL = (
    _DJ_2026_005_ST_ROOT / "external" / "FB_ExternalDeviceInteraction.scl"
)
FB_1004_SCL = (
    _DJ_2026_005_ST_ROOT
    / "feeder"
    / "FB_1004_GlueMachineFeeder_BufferFraming.scl"
)
FB_1003_SCL = (
    _DJ_2026_005_ST_ROOT
    / "pickplace"
    / "FB_1003_PickPlace_BufferFraming.scl"
)
_REAL_SAMPLES = (
    OB1_SCL,
    FB_2001_SCL,
    FB_1002_SCL,
    FB_EXTERNAL_SCL,
    FB_1004_SCL,
    FB_1003_SCL,
)
_REAL_SAMPLES_AVAILABLE = all(p.exists() for p in _REAL_SAMPLES)
skip_if_real_samples_missing = pytest.mark.skipif(
    not _REAL_SAMPLES_AVAILABLE,
    reason="DJ-2026-005 真实样例不存在",
)


class TestSclParserDetectFormat:
    def test_scl_detect_format_scl_extension(self, tmp_path: Path) -> None:
        """detect_format 对 .scl 文件返回 True"""
        f = tmp_path / "fb.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Test\n"
            "VAR_INPUT\n"
            "  i_bStart : BOOL;\n"
            "END_VAR\n",
            encoding="utf-8",
        )
        assert SclParser().detect_format(f) is True

    def test_scl_detect_format_non_scl(self, tmp_path: Path) -> None:
        """detect_format 对非 scl 文件返回 False（如纯 CSV）"""
        f = tmp_path / "var.csv"
        f.write_text(
            "station,signal_type,address,tag,signal_name,device,comment\n"
            "cpu,DI,X0,Tag,name,dev,comment\n",
            encoding="utf-8",
        )
        assert SclParser().detect_format(f) is False


class TestSclParserVarBlockExtraction:
    def test_scl_parse_var_blocks_with_fb_name_metadata(
        self, tmp_path: Path
    ) -> None:
        """解析 SCL 文件，验证 VAR_INPUT/VAR_OUTPUT/VAR 块变量提取 + FB 名称元数据"""
        f = tmp_path / "fb.scl"
        f.write_text(
            "FUNCTION_BLOCK FB_Conveyor\n"
            "VAR_INPUT\n"
            "  i_bStart : BOOL; // 启动按钮\n"
            "  i_bStop : BOOL; // 停止按钮\n"
            "  i_wSpeed : INT;\n"
            "END_VAR\n"
            "VAR_OUTPUT\n"
            "  q_bRunning : BOOL;\n"
            "  q_iAlarmCode : INT; // 报警码\n"
            "END_VAR\n"
            "VAR\n"
            "  stInternal : ST_Conveyor;\n"
            "END_VAR\n"
            "BEGIN\n"
            "  // 实现逻辑\n"
            "END_FUNCTION_BLOCK\n",
            encoding="utf-8",
        )
        result = SclParser().parse(f)
        assert result.success
        assert result.var_table is not None
        # 3 input + 2 output + 1 var = 6 个变量
        assert result.var_table.total_count == 6

        # 验证 FB 名称元数据
        assert result.var_table.metadata["fb_name"] == "FB_Conveyor"
        assert result.var_table.metadata["var_block_count"] == 3

        # 验证 VAR_INPUT 块变量
        input_entries = [
            e for e in result.var_table.entries if e.station == "VAR_INPUT"
        ]
        assert len(input_entries) == 3
        assert input_entries[0].tag == "i_bStart"
        assert input_entries[0].signal_type == "BOOL"
        assert input_entries[0].comment == "启动按钮"
        assert input_entries[0].device == "FB_Conveyor"

        # 验证 VAR_OUTPUT 块变量
        output_entries = [
            e for e in result.var_table.entries if e.station == "VAR_OUTPUT"
        ]
        assert len(output_entries) == 2
        assert output_entries[1].tag == "q_iAlarmCode"
        assert output_entries[1].signal_type == "INT"
        assert output_entries[1].comment == "报警码"

        # 验证 VAR 块变量（复杂类型 ST_ 顶层声明）
        var_entries = [e for e in result.var_table.entries if e.station == "VAR"]
        assert len(var_entries) == 1
        assert var_entries[0].tag == "stInternal"
        assert var_entries[0].signal_type == "ST_Conveyor"


class TestSclParserEdgeCases:
    def test_scl_parse_no_var_block_emits_warning(self, tmp_path: Path) -> None:
        """无 VAR 块的 SCL 文件：success=True + warnings 提示"""
        f = tmp_path / "ob1.scl"
        f.write_text(
            "ORGANIZATION_BLOCK OB1\n"
            "BEGIN\n"
            "  // 仅调用 FB，无 VAR 块\n"
            "  fbConveyor();\n"
            "END_ORGANIZATION_BLOCK\n",
            encoding="utf-8",
        )
        result = SclParser().parse(f)
        # SCL 解析默认 success=True（即使无 VAR 块也视为格式识别成功）
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 0
        assert result.warning_count >= 1
        # 元数据：var_block_count=0
        assert result.var_table.metadata["var_block_count"] == 0


@skip_if_real_samples_missing
class TestSclParserRealSamples:
    """DJ-2026-005 真实 .scl 样例端到端解析验证

    覆盖 6 个真实 .scl 文件: OB1/FB_2001/FB_1002/FB_External/FB_1004/FB_1003,
    验证 FB 名提取、VAR 块识别、复杂类型字段提取、中文注释处理。
    """

    def test_real_ob1_no_var_blocks(self) -> None:
        """OB1 主组织块: 无 VAR 块, fb_name=OB1, 提示 warning"""
        result = SclParser().parse(OB1_SCL)
        assert result.success
        assert result.var_table is not None
        assert result.var_table.total_count == 0
        assert result.var_table.metadata["fb_name"] == "OB1"
        assert result.var_table.metadata["var_block_count"] == 0
        assert result.warning_count >= 1
        # ORGANIZATION_BLOCK 也被 _FB_NAME_RE 识别
        assert "未识别到 VAR 块" in result.warnings[0]

    def test_real_fb_2001_common_alarm_var_blocks(self) -> None:
        """FB_2001: VAR_INPUT(4) + VAR_OUTPUT(10) + VAR(18, 含 VAR_CONSTANT 4) = 32"""
        result = SclParser().parse(FB_2001_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_2001_CommonAlarm_AllStation"
        assert vt.metadata["var_block_count"] == 4
        assert vt.total_count == 32
        # VAR_CONSTANT 因 regex (VAR_INPUT|...|VAR) 匹配优先级被归入 VAR 块
        stations = {e.station for e in vt.entries}
        assert stations == {"VAR_INPUT", "VAR_OUTPUT", "VAR"}
        # 验证 VAR_INPUT 首个变量 (中文注释)
        first_input = next(e for e in vt.entries if e.station == "VAR_INPUT")
        assert first_input.tag == "i_iConveyorAlarm"
        assert first_input.signal_type == "INT"
        assert "输送机" in first_input.comment
        # 验证 VAR_CONSTANT 常量被提取 (QUEUE_SIZE/ALM_NONE 等)
        const_tags = {
            e.tag for e in vt.entries if e.tag.startswith(("QUEUE", "ALM"))
        }
        assert {"QUEUE_SIZE", "QUEUE_MASK", "ALM_NONE", "ALM_WORD_ZERO"} == const_tags

    def test_real_fb_1002_conveyor_complex_types(self) -> None:
        """FB_1002: 验证 ST_/FB_ 复杂类型字段提取 + device 元数据"""
        result = SclParser().parse(FB_1002_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1002_SingleLayerConveyor_BufferFraming"
        assert vt.total_count == 74
        # FB_ 子功能块实例类型提取
        fb_types = {
            e.tag: e.signal_type
            for e in vt.entries
            if e.signal_type.startswith("FB_")
        }
        assert fb_types["fbBlock"] == "FB_1011_CylinderControl"
        assert fb_types["fbSeparate"] == "FB_1011_CylinderControl"
        assert fb_types["fbMotor"] == "FB_1012_ConveyorMotor"
        # ST_ 结构体类型提取 (命令/状态对)
        st_types = {
            e.tag: e.signal_type
            for e in vt.entries
            if e.signal_type.startswith("ST_")
        }
        assert st_types["stBlockCmd"] == "ST_CylinderCmd"
        assert st_types["stBlockSts"] == "ST_CylinderSts"
        assert st_types["stSeparateCmd"] == "ST_CylinderCmd"
        # device 字段填充 FB 名
        assert all(
            e.device == "FB_1002_SingleLayerConveyor_BufferFraming"
            for e in vt.entries
        )

    def test_real_fb_external_device_interaction(self) -> None:
        """FB_ExternalDeviceInteraction: VAR_INPUT(27) + VAR_OUTPUT(16) + VAR(2) = 45"""
        result = SclParser().parse(FB_EXTERNAL_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_ExternalDeviceInteraction"
        assert vt.metadata["var_block_count"] == 3
        assert vt.total_count == 45
        # 各 VAR 块条目数核查
        input_count = sum(1 for e in vt.entries if e.station == "VAR_INPUT")
        output_count = sum(1 for e in vt.entries if e.station == "VAR_OUTPUT")
        var_count = sum(1 for e in vt.entries if e.station == "VAR")
        assert input_count == 27
        assert output_count == 16
        assert var_count == 2
        # 首个 VAR_INPUT 变量含中文注释
        first_input = next(e for e in vt.entries if e.station == "VAR_INPUT")
        assert first_input.tag == "i_bEnable"
        assert first_input.signal_type == "BOOL"
        assert first_input.comment == "系统总使能"

    def test_real_fb_1004_feeder_fb_tonr_and_array(self) -> None:
        """FB_1004: 验证 FB_TONR 实例 + ARRAY 类型 (regex 截断为 ARRAY) + (* *) 注释"""
        result = SclParser().parse(FB_1004_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1004_GlueMachineFeeder_BufferFraming"
        assert vt.total_count == 46
        # FB_TONR 实例 (SysLib 共享库定时器)
        tonr_entries = {e.tag: e for e in vt.entries if e.signal_type == "FB_TONR"}
        assert "tMoveTimer" in tonr_entries
        assert "tCommTimer" in tonr_entries
        # (* *) 块注释提取
        assert tonr_entries["tMoveTimer"].comment == "X2移动超时"
        assert tonr_entries["tCommTimer"].comment == "打胶机通信超时"
        # ARRAY 类型 (regex 仅保留 ARRAY 关键字, [0..1] OF BOOL 被截断)
        array_tags = {e.tag for e in vt.entries if e.signal_type == "ARRAY"}
        assert {"tIn", "tQ", "tR", "tPt", "tEt"} <= array_tags

    def test_real_fb_1003_pickplace_var_in_out(self) -> None:
        """FB_1003: 验证 VAR_IN_OUT 块 + ST_ServoAxis 复杂类型 + // 中文注释"""
        result = SclParser().parse(FB_1003_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1003_PickPlace_BufferFraming"
        assert vt.metadata["var_block_count"] == 5
        assert vt.total_count == 81
        # VAR_IN_OUT 块识别 (FB_1003 是唯一含 VAR_IN_OUT 的样例)
        in_out_entries = [e for e in vt.entries if e.station == "VAR_IN_OUT"]
        assert len(in_out_entries) == 2
        assert in_out_entries[0].tag == "io_stZAxis"
        assert in_out_entries[0].signal_type == "ST_ServoAxis"
        assert in_out_entries[1].tag == "io_stX1Axis"
        assert in_out_entries[1].signal_type == "ST_ServoAxis"
        # // 行注释风格中文提取
        first_input = next(e for e in vt.entries if e.station == "VAR_INPUT")
        assert first_input.tag == "i_bAutoMode"
        assert first_input.comment == "自动模式"

    def test_real_all_six_files_detect_format_scl(self) -> None:
        """6 个真实 .scl 文件 detect_format 均返回 True"""
        parser = SclParser()
        for sample in _REAL_SAMPLES:
            assert parser.detect_format(sample) is True, (
                f"{sample.name} 应识别为 SCL 格式"
            )

    def test_real_fb_name_metadata_extraction(self) -> None:
        """验证 6 个真实样例的 FB 名称元数据提取 (含 ORGANIZATION_BLOCK)"""
        expected = {
            OB1_SCL: "OB1",
            FB_2001_SCL: "FB_2001_CommonAlarm_AllStation",
            FB_1002_SCL: "FB_1002_SingleLayerConveyor_BufferFraming",
            FB_EXTERNAL_SCL: "FB_ExternalDeviceInteraction",
            FB_1004_SCL: "FB_1004_GlueMachineFeeder_BufferFraming",
            FB_1003_SCL: "FB_1003_PickPlace_BufferFraming",
        }
        for path, expected_name in expected.items():
            result = SclParser().parse(path)
            assert result.success
            assert result.var_table is not None
            assert result.var_table.metadata["fb_name"] == expected_name, (
                f"{path.name} fb_name 期望 {expected_name}"
            )
            # 所有 entry 的 device 字段应等于 fb_name
            for entry in result.var_table.entries:
                assert entry.device == expected_name

    def test_real_var_block_identification(self) -> None:
        """验证 VAR_INPUT/VAR_OUTPUT/VAR/VAR_IN_OUT 块识别跨文件一致性"""
        # FB_1003 是唯一含 VAR_IN_OUT 的样例
        r1003 = SclParser().parse(FB_1003_SCL)
        assert r1003.var_table is not None
        stations_1003 = set(r1003.var_table.stations)
        assert stations_1003 == {"VAR_INPUT", "VAR_OUTPUT", "VAR", "VAR_IN_OUT"}
        # FB_2001 含 VAR_CONSTANT (regex 归为 VAR)
        r2001 = SclParser().parse(FB_2001_SCL)
        assert r2001.var_table is not None
        stations_2001 = set(r2001.var_table.stations)
        assert stations_2001 == {"VAR_INPUT", "VAR_OUTPUT", "VAR"}
        # OB1 无任何 VAR 块
        r_ob1 = SclParser().parse(OB1_SCL)
        assert r_ob1.var_table is not None
        assert r_ob1.var_table.stations == ()

    def test_real_chinese_comment_extraction(self) -> None:
        """验证中文注释提取: // 行注释 + (* *) 块注释 两种风格"""
        # FB_1003: // 行注释风格
        r1003 = SclParser().parse(FB_1003_SCL)
        assert r1003.var_table is not None
        auto_mode = next(
            e for e in r1003.var_table.entries if e.tag == "i_bAutoMode"
        )
        assert auto_mode.comment == "自动模式"
        # FB_1004: (* *) 块注释风格
        r1004 = SclParser().parse(FB_1004_SCL)
        assert r1004.var_table is not None
        move_timer = next(
            e for e in r1004.var_table.entries if e.tag == "tMoveTimer"
        )
        assert move_timer.comment == "X2移动超时"
        # FB_2001: // 行注释含中文 + 标点
        r2001 = SclParser().parse(FB_2001_SCL)
        assert r2001.var_table is not None
        reset_entry = next(
            e for e in r2001.var_table.entries if e.tag == "i_bReset"
        )
        assert "复位" in reset_entry.comment
        assert "清除所有报警状态" in reset_entry.comment
