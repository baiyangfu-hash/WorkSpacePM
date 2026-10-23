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
OB1_SCL = _DJ_2026_005_ST_ROOT / "00_主程序" / "OB1.scl"
FB_2001_SCL = (
    _DJ_2026_005_ST_ROOT / "05_公共报警" / "FB_2001_CommonAlarm_AllStation.scl"
)
FB_1002_SCL = (
    _DJ_2026_005_ST_ROOT
    / "02_输送机"
    / "FB_1002_SingleLayerConveyor_BufferFraming.scl"
)
FB_EXTERNAL_SCL = (
    _DJ_2026_005_ST_ROOT / "01_外部设备交互" / "FB_ExternalDeviceInteraction.scl"
)
FB_1004_SCL = (
    _DJ_2026_005_ST_ROOT
    / "04_打胶机送料"
    / "FB_1004_GlueMachineFeeder_BufferFraming.scl"
)
FB_1003_SCL = (
    _DJ_2026_005_ST_ROOT
    / "03_取放料"
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


@pytest.fixture
def _real_samples_present() -> None:
    """真实样例随工作空间检出提交：检出里缺任何一个即失败，不跳过。

    路径写旧曾让整类测试在所有机器上静默跳过；只有不在工作空间 Git 检出里运行时才允许跳过。
    """
    missing = [str(p.relative_to(_WORKSPACE_ROOT)) for p in _REAL_SAMPLES if not p.is_file()]
    if not missing:
        return
    if not (_WORKSPACE_ROOT / ".git").exists():
        pytest.skip("不在工作空间 Git 检出中，DJ-2026-005 真实样例不可用")
    pytest.fail(f"DJ-2026-005 真实样例缺失（路径写旧或文件被移动）: {missing}")


require_real_samples = pytest.mark.usefixtures("_real_samples_present")


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



class TestSclParserVarConstant:
    """VAR CONSTANT 常量单独归类（用户 2026-10-19 裁决：不与普通静态 VAR 混用）"""

    _FB_TEXT = (
        "FUNCTION_BLOCK FB_Demo\n"
        "VAR\n"
        "  s_iStep : INT; // 当前步号\n"
        "END_VAR\n"
        "VAR CONSTANT\n"
        "  STEP_IDLE : INT := 0; // 空闲步\n"
        "  T_TIMEOUT : DINT := 5000; (* 超时 5s *)\n"
        "END_VAR\n"
        "VAR_CONSTANT\n"
        "  MAX_SLOTS : INT := 4;\n"
        "END_VAR\n"
        "BEGIN\n"
        "END_FUNCTION_BLOCK\n"
    )

    def test_scl_var_constant_block_is_separate_scope(self, tmp_path: Path) -> None:
        """"VAR CONSTANT"（带空格）与 "VAR_CONSTANT" 都归为 VAR_CONSTANT，普通 VAR 不受影响"""
        f = tmp_path / "fb_demo.scl"
        f.write_text(self._FB_TEXT, encoding="utf-8")
        result = SclParser().parse(f)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["var_block_count"] == 3
        by_scope = {
            scope: [e.tag for e in vt.entries if e.station == scope]
            for scope in vt.stations
        }
        assert by_scope == {
            "VAR": ["s_iStep"],
            "VAR_CONSTANT": ["STEP_IDLE", "T_TIMEOUT", "MAX_SLOTS"],
        }
        t_timeout = next(e for e in vt.entries if e.tag == "T_TIMEOUT")
        assert t_timeout.signal_type == "DINT"
        assert t_timeout.comment == "超时 5s"

    def test_scl_var_constant_kept_in_csv_export(self, tmp_path: Path) -> None:
        """导出 CSV 时常量行的 station 列为 VAR_CONSTANT，普通变量仍为 VAR"""
        import csv
        import io

        from auto_pm.vartable.converter import VariableConverter

        f = tmp_path / "fb_demo.scl"
        f.write_text(self._FB_TEXT, encoding="utf-8")
        csv_text = VariableConverter().convert(SclParser().parse(f), "csv")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        scope_by_tag = {r["tag"]: r["station"] for r in rows}
        assert scope_by_tag == {
            "s_iStep": "VAR",
            "STEP_IDLE": "VAR_CONSTANT",
            "T_TIMEOUT": "VAR_CONSTANT",
            "MAX_SLOTS": "VAR_CONSTANT",
        }

@require_real_samples
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
        """FB_2001: VAR_IN_OUT(1) + VAR(14) + VAR CONSTANT(8, 单独归为常量类) = 23"""
        result = SclParser().parse(FB_2001_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_2001_CommonAlarm_AllStation"
        assert vt.metadata["var_block_count"] == 3
        assert vt.total_count == 23
        # VAR CONSTANT 单独归为 VAR_CONSTANT（常量类），不与普通静态 VAR 混用
        stations = {e.station for e in vt.entries}
        assert stations == {"VAR_IN_OUT", "VAR", "VAR_CONSTANT"}
        assert sum(1 for e in vt.entries if e.station == "VAR_IN_OUT") == 1
        assert sum(1 for e in vt.entries if e.station == "VAR") == 14
        assert sum(1 for e in vt.entries if e.station == "VAR_CONSTANT") == 8
        # 结构体整块传递: 唯一 VAR_IN_OUT 为公共报警全量结构体 (中文注释)
        io_entry = next(e for e in vt.entries if e.station == "VAR_IN_OUT")
        assert io_entry.tag == "io_stGlobal"
        assert io_entry.signal_type == "ST_CommonAlarm"
        assert io_entry.comment == "公共报警工站全量数据结构体"
        # 验证 VAR CONSTANT 常量被提取且全部落在常量类 (QUEUE_*/ALM_*)
        const_tags = {e.tag for e in vt.entries if e.station == "VAR_CONSTANT"}
        assert const_tags == {
            "QUEUE_SIZE",
            "QUEUE_MASK",
            "ALM_NONE",
            "ALM_WORD_ZERO",
            "ALM_CODE_SAFETY_TIMEOUT",
            "ALM_BIT_SAFETY_TIMEOUT",
            "ALM_CODE_HEARTBEAT_LOST",
            "ALM_BIT_HEARTBEAT_LOST",
        }

    def test_real_fb_1002_conveyor_complex_types(self) -> None:
        """FB_1002: 验证 ST_/FB_ 复杂类型字段提取 + device 元数据"""
        result = SclParser().parse(FB_1002_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1002_SingleLayerConveyor_BufferFraming"
        # VAR_IN_OUT(1) + VAR(65) + VAR CONSTANT(10, 常量类) = 76
        assert vt.total_count == 76
        assert sum(1 for e in vt.entries if e.station == "VAR_CONSTANT") == 10
        assert all(
            e.tag.startswith("STEP_")
            for e in vt.entries
            if e.station == "VAR_CONSTANT"
        )
        # FB_ 子功能块实例类型提取
        fb_types = {
            e.tag: e.signal_type
            for e in vt.entries
            if e.signal_type.startswith("FB_")
        }
        assert fb_types["fb_Block"] == "FB_1011_CylinderControl"
        assert fb_types["fb_Separate"] == "FB_1011_CylinderControl"
        assert fb_types["fb_Motor"] == "FB_1012_ConveyorMotor"
        # ST_ 结构体类型提取 (VAR_IN_OUT 全量结构体 + 命令/状态对)
        st_types = {
            e.tag: e.signal_type
            for e in vt.entries
            if e.signal_type.startswith("ST_")
        }
        assert st_types == {
            "io_stLayer": "ST_SingleLayerConveyor",
            "st_BlockCmd": "ST_CylinderCmd",
            "st_BlockSts": "ST_CylinderSts",
            "st_SeparateCmd": "ST_CylinderCmd",
            "st_SeparateSts": "ST_CylinderSts",
        }
        # device 字段填充 FB 名
        assert all(
            e.device == "FB_1002_SingleLayerConveyor_BufferFraming"
            for e in vt.entries
        )

    def test_real_fb_external_device_interaction(self) -> None:
        """FB_ExternalDeviceInteraction: VAR_IN_OUT(1) + VAR(20) + VAR CONSTANT(2, 常量类) = 23"""
        result = SclParser().parse(FB_EXTERNAL_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_ExternalDeviceInteraction"
        assert vt.metadata["var_block_count"] == 3
        assert vt.total_count == 23
        # 各 VAR 块条目数核查
        in_out_count = sum(1 for e in vt.entries if e.station == "VAR_IN_OUT")
        var_count = sum(1 for e in vt.entries if e.station == "VAR")
        const_tags = [e.tag for e in vt.entries if e.station == "VAR_CONSTANT"]
        assert in_out_count == 1
        assert var_count == 20
        assert const_tags == ["T_HEARTBEAT_PERIOD", "T_COMM_TIMEOUT"]
        assert in_out_count + var_count + len(const_tags) == vt.total_count
        # 唯一 VAR_IN_OUT 为外部设备交互全量结构体 (中文注释)
        io_entry = next(e for e in vt.entries if e.station == "VAR_IN_OUT")
        assert io_entry.tag == "io_stExternal"
        assert io_entry.signal_type == "ST_ExternalDevice"
        assert io_entry.comment == "外部设备交互全量数据结构体"
        # 首个 VAR 变量含中文注释
        first_var = next(e for e in vt.entries if e.station == "VAR")
        assert first_var.tag == "s_bSafetyConditionMet"
        assert first_var.signal_type == "BOOL"
        assert first_var.comment == "内部安全条件满足标志"

    def test_real_fb_1004_feeder_fb_tonr_and_real(self) -> None:
        """FB_1004: 验证 FB_TONR 实例 + REAL 类型 (初值 := 被剥离) + // 与 (* *) 注释"""
        result = SclParser().parse(FB_1004_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1004_GlueMachineFeeder_BufferFraming"
        # VAR_IN_OUT(2) + VAR(36) + VAR CONSTANT(7, 常量类) = 45
        assert vt.total_count == 45
        assert sum(1 for e in vt.entries if e.station == "VAR_CONSTANT") == 7
        # FB_TONR 实例 (SysLib 共享库定时器)
        tonr_entries = {e.tag: e for e in vt.entries if e.signal_type == "FB_TONR"}
        assert set(tonr_entries) == {
            "fb_tMoveTimer",
            "fb_tFullConfirmTimer",
            "fb_tReleaseTimer",
            "fb_tCommTimer",
        }
        # // 行注释提取
        assert tonr_entries["fb_tMoveTimer"].comment == "X2 移动看门狗超时 (20.0s)"
        assert tonr_entries["fb_tCommTimer"].comment == "跨机交握超时看门狗 (15.0s)"
        # (* *) 块注释提取 (VAR CONSTANT 常量)
        by_tag = {e.tag: e for e in vt.entries}
        assert by_tag["T_MOVE_DEFAULT"].signal_type == "DINT"
        assert by_tag["T_MOVE_DEFAULT"].station == "VAR_CONSTANT"
        assert by_tag["T_MOVE_DEFAULT"].comment == "移动超时 20s"
        # REAL 类型 (":= 512.0" 初值不进入类型字段)
        real_tags = {e.tag for e in vt.entries if e.signal_type == "REAL"}
        assert real_tags == {
            "s_rPickupPos",
            "s_rFeedPos",
            "s_rStandbyPos",
            "s_rFeedSpeed",
        }

    def test_real_fb_1003_pickplace_var_in_out(self) -> None:
        """FB_1003: 验证 4 个 VAR_IN_OUT 结构体 + ST_ServoAxis 复杂类型 + // 中文注释"""
        result = SclParser().parse(FB_1003_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1003_PickPlace_BufferFraming"
        assert vt.metadata["var_block_count"] == 3
        # VAR_IN_OUT(4) + VAR(37) + VAR CONSTANT(6, 常量类) = 47
        assert vt.total_count == 47
        assert sum(1 for e in vt.entries if e.station == "VAR_CONSTANT") == 6
        # VAR_IN_OUT 块识别 (FB_1003 是含 VAR_IN_OUT 最多的样例)
        in_out_entries = [e for e in vt.entries if e.station == "VAR_IN_OUT"]
        assert [(e.tag, e.signal_type) for e in in_out_entries] == [
            ("io_stPickPlace", "ST_PickPlace"),
            ("io_stRecipe", "ST_RecipeManager"),
            ("io_stZAxis", "ST_ServoAxis"),
            ("io_stX1Axis", "ST_ServoAxis"),
        ]
        # // 行注释风格中文提取
        assert in_out_entries[2].comment == "Z轴升降伺服 (对象化标准接口)"
        first_var = next(e for e in vt.entries if e.station == "VAR")
        assert first_var.tag == "fb_LiftTimer"
        assert first_var.comment == "辅助升降气缸与Z轴动作超时定时器"

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
        """验证 VAR_IN_OUT/VAR/VAR CONSTANT 块识别跨文件一致性 (结构体整块传递架构)"""
        # 5 个 FB 均为 VAR_IN_OUT 结构体 + VAR + VAR CONSTANT (常量单独成类)
        expected_in_out = {
            FB_2001_SCL: 1,
            FB_EXTERNAL_SCL: 1,
            FB_1002_SCL: 1,
            FB_1003_SCL: 4,
            FB_1004_SCL: 2,
        }
        for path, in_out_count in expected_in_out.items():
            vt = SclParser().parse(path).var_table
            assert vt is not None
            assert set(vt.stations) == {"VAR_IN_OUT", "VAR", "VAR_CONSTANT"}, path.name
            assert vt.metadata["var_block_count"] == 3, path.name
            assert (
                sum(1 for e in vt.entries if e.station == "VAR_IN_OUT")
                == in_out_count
            ), path.name
        # OB1 无任何 VAR 块
        r_ob1 = SclParser().parse(OB1_SCL)
        assert r_ob1.var_table is not None
        assert r_ob1.var_table.stations == ()

    def test_real_chinese_comment_extraction(self) -> None:
        """验证中文注释提取: // 行注释 + (* *) 块注释 两种风格"""
        # FB_1003: // 行注释风格
        r1003 = SclParser().parse(FB_1003_SCL)
        assert r1003.var_table is not None
        lift_up = next(e for e in r1003.var_table.entries if e.tag == "s_bLiftUp")
        assert lift_up.comment == "Y42 气缸上升 (高度补偿)"
        # FB_1004: (* *) 块注释风格
        r1004 = SclParser().parse(FB_1004_SCL)
        assert r1004.var_table is not None
        stable_delay = next(
            e for e in r1004.var_table.entries if e.tag == "T_STABLE_DELAY"
        )
        assert stable_delay.comment == "到位/脱离防抖延时 1.0s"
        # FB_2001: // 行注释含中文 + 标点
        r2001 = SclParser().parse(FB_2001_SCL)
        assert r2001.var_table is not None
        bit_entry = next(
            e for e in r2001.var_table.entries if e.tag == "ALM_BIT_SAFETY_TIMEOUT"
        )
        assert "报警字第3位" in bit_entry.comment
        assert bit_entry.comment == "报警字第3位: 安全回路看门狗超时"
