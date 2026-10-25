"""SclParser 深化测试 - V2.3 Week3 T12

验证 SclParser 的 detect_format 方法 + VAR 块状态机解析 + 边界场景。

V0.5.x Week1 W1-S04: 扩展真实样例测试覆盖, 对 DJ-2026-005 项目的 6 个
真实 .scl 文件进行端到端解析验证 (OB1/FB_2001/FB_1002/FB_External/
FB_1004/FB_1003)。
"""

from __future__ import annotations

import re
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



_BLOCK_START_RE = re.compile(r"^(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR)\b(\s+CONSTANT\b)?", re.IGNORECASE)
_DECLARATION_RE = re.compile(r"^[A-Za-z_]\w*\s*:(?!=)")


def _declared_per_block(path: Path) -> dict[str, int]:
    """不经过 SclParser，直接数样例文件里每类 VAR 块声明了几个变量。

    真实样例会随 DJ-2026-005 的程序修改增减变量，期望值不能手写；这里用一套和解析器无关的
    逐行扫描（去掉 (* *) 与 // 注释，块内每条 `名字 : 类型` 算一个）当判卷依据。
    键与解析结果的 station 一致：VAR_INPUT / VAR_IN_OUT / VAR / VAR_CONSTANT。
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\(\*.*?\*\)", "", text, flags=re.DOTALL)
    counts: dict[str, int] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if current is None:
            start = _BLOCK_START_RE.match(line)
            if start and ":" not in line.split(None, 2)[0]:
                current = start.group(1).upper() + ("_CONSTANT" if start.group(2) else "")
                counts.setdefault(current, 0)
            continue
        if line.upper().startswith("END_VAR"):
            current = None
        elif _DECLARATION_RE.match(line):
            counts[current] += 1
    return counts


def _declared_total(path: Path) -> int:
    return sum(_declared_per_block(path).values())


def _parsed_per_station(vt: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in vt.entries:  # type: ignore[attr-defined]
        counts[entry.station] = counts.get(entry.station, 0) + 1
    return counts


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
        """FB_2001: VAR_IN_OUT + VAR + VAR CONSTANT(单独归为常量类)，个数以样例文件逐行数出的为准"""
        result = SclParser().parse(FB_2001_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_2001_CommonAlarm_AllStation"
        declared = _declared_per_block(FB_2001_SCL)
        assert vt.metadata["var_block_count"] == len(declared) == 3
        assert vt.total_count == _declared_total(FB_2001_SCL)
        assert _parsed_per_station(vt) == declared
        # VAR CONSTANT 单独归为 VAR_CONSTANT（常量类），不与普通静态 VAR 混用
        stations = {e.station for e in vt.entries}
        assert stations == {"VAR_IN_OUT", "VAR", "VAR_CONSTANT"}
        # 结构体整块传递: 4 个 VAR_IN_OUT (报警 / 模式 / 物理 IO / HMI), 带中文注释
        in_out = [(e.tag, e.signal_type) for e in vt.entries if e.station == "VAR_IN_OUT"]
        assert in_out == [
            ("io_stAlarm", "ST_Alarm"),
            ("io_stMachine", "ST_Machine"),
            ("io_stIo", "ST_Io"),
            ("io_stHmi", "ST_Hmi"),
        ]
        io_entry = next(e for e in vt.entries if e.tag == "io_stHmi")
        assert io_entry.comment == "静音 M9, 强置选项 M515"
        # VAR CONSTANT 常量被提取且全部落在常量类
        const_tags = {e.tag for e in vt.entries if e.station == "VAR_CONSTANT"}
        assert const_tags == {"NO_ALARM", "LAST_IDX", "CLK1_HALF_MS", "CLK01_HALF_MS"}

    def test_real_fb_1002_conveyor_complex_types(self) -> None:
        """FB_1002: 验证 ST_/FB_ 复杂类型字段提取 + device 元数据"""
        result = SclParser().parse(FB_1002_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1002_SingleLayerConveyor_BufferFraming"
        # VAR_INPUT + VAR_IN_OUT + VAR + VAR CONSTANT(常量类)，个数以样例文件逐行数出的为准
        declared = _declared_per_block(FB_1002_SCL)
        assert vt.metadata["var_block_count"] == len(declared) == 4
        assert vt.total_count == _declared_total(FB_1002_SCL)
        assert _parsed_per_station(vt) == declared
        assert all(
            e.tag.startswith("STEP_")
            for e in vt.entries
            if e.station == "VAR_CONSTANT"
        )
        # FB_ 定时器实例类型提取 (FB_TON / FB_R_TRIG)
        fb_types = {
            e.tag: e.signal_type
            for e in vt.entries
            if e.signal_type.startswith("FB_")
        }
        assert fb_types["fb_tInitRev"] == "FB_TON"
        assert fb_types["fb_tSlowFeed"] == "FB_TON"
        assert fb_types["fb_trUnload"] == "FB_R_TRIG"
        # ST_ 结构体类型提取: 只有一个 VAR_IN_OUT 全量结构体
        st_types = {
            e.tag: e.signal_type
            for e in vt.entries
            if e.signal_type.startswith("ST_")
        }
        assert st_types == {"io_stLayer": "ST_SingleLayer"}
        # device 字段填充 FB 名
        assert all(
            e.device == "FB_1002_SingleLayerConveyor_BufferFraming"
            for e in vt.entries
        )

    def test_real_fb_external_device_interaction(self) -> None:
        """FB_ExternalDeviceInteraction: VAR_IN_OUT + VAR + VAR CONSTANT(常量类)，个数以样例文件逐行数出的为准"""
        result = SclParser().parse(FB_EXTERNAL_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_ExternalDeviceInteraction"
        declared = _declared_per_block(FB_EXTERNAL_SCL)
        assert vt.metadata["var_block_count"] == len(declared) == 3
        assert vt.total_count == _declared_total(FB_EXTERNAL_SCL)
        # 各 VAR 块条目数核查
        assert _parsed_per_station(vt) == declared
        const_tags = [e.tag for e in vt.entries if e.station == "VAR_CONSTANT"]
        assert const_tags == ["IDX_F0", "IDX_F8", "IDX_F104", "IDX_F105"]
        # 第一个 VAR_IN_OUT 为组框机链路结构体 (中文注释)
        io_entry = next(e for e in vt.entries if e.station == "VAR_IN_OUT")
        assert io_entry.tag == "io_stExt"
        assert io_entry.signal_type == "ST_ExternalLink"
        assert io_entry.comment == "组框机链路 (本 FB 写)"
        # 首个 VAR 变量是上升沿触发器, 含中文注释
        first_var = next(e for e in vt.entries if e.station == "VAR")
        assert first_var.tag == "fb_trPermitUp"
        assert first_var.signal_type == "FB_R_TRIG"
        assert first_var.comment == "组框机允许送料 上升沿"

    def test_real_fb_1004_feeder_fb_tonr_and_real(self) -> None:
        """FB_1004: 验证 FB_TON 实例 + REAL 类型 (初值 := 被剥离) + // 行注释"""
        result = SclParser().parse(FB_1004_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1004_GlueMachineFeeder_BufferFraming"
        # VAR_IN_OUT + VAR + VAR CONSTANT(常量类)，个数以样例文件逐行数出的为准
        assert vt.total_count == _declared_total(FB_1004_SCL)
        assert _parsed_per_station(vt) == _declared_per_block(FB_1004_SCL)
        # FB_TON 实例 (SysLib 共享库定时器)
        ton_entries = {e.tag: e for e in vt.entries if e.signal_type == "FB_TON"}
        assert set(ton_entries) == {
            "fb_tSettle",
            "fb_tFull",
            "fb_tEmpty",
            "fb_tF90",
            "fb_tF91",
        }
        # // 行注释提取
        assert ton_entries["fb_tFull"].comment == "步 1: 4 光电全亮 10 s"
        assert ton_entries["fb_tF90"].comment == "F90 前光电异常"
        # VAR CONSTANT 常量: 类型与注释
        by_tag = {e.tag: e for e in vt.entries}
        assert by_tag["STEP_HOME"].signal_type == "INT"
        assert by_tag["STEP_HOME"].station == "VAR_CONSTANT"
        assert by_tag["STEP_HOME"].comment == "回取料点 D512"
        # REAL 类型 (":= 0.0" 初值不进入类型字段)
        real_tags = {e.tag for e in vt.entries if e.signal_type == "REAL"}
        assert real_tags == {"s_rX2Target", "s_rErr"}

    def test_real_fb_1003_pickplace_var_in_out(self) -> None:
        """FB_1003: 验证 6 个 VAR_IN_OUT 结构体 + ARRAY 类型 + // 中文注释"""
        result = SclParser().parse(FB_1003_SCL)
        assert result.success
        vt = result.var_table
        assert vt is not None
        assert vt.metadata["fb_name"] == "FB_1003_PickPlace_BufferFraming"
        assert vt.metadata["var_block_count"] == len(_declared_per_block(FB_1003_SCL)) == 3
        # VAR_IN_OUT + VAR + VAR CONSTANT(常量类)，个数以样例文件逐行数出的为准
        assert vt.total_count == _declared_total(FB_1003_SCL)
        assert _parsed_per_station(vt) == _declared_per_block(FB_1003_SCL)
        # VAR_IN_OUT 块识别 (FB_1003 与 FB_1004 是含 VAR_IN_OUT 最多的样例)
        in_out_entries = [e for e in vt.entries if e.station == "VAR_IN_OUT"]
        assert [(e.tag, e.signal_type) for e in in_out_entries] == [
            ("io_stPP", "ST_PickPlace"),
            ("io_stBridge", "ST_Bridge"),
            ("io_stMachine", "ST_Machine"),
            ("io_stIo", "ST_Io"),
            ("io_stAlarm", "ST_Alarm"),
            ("io_arrAxis", "ARRAY"),
        ]
        # // 行注释风格中文提取
        assert in_out_entries[0].comment == "取放料数据"
        assert in_out_entries[5].comment == "轴: 1 = Z, 2 = X1, 3 = X2"
        first_var = next(e for e in vt.entries if e.station == "VAR")
        assert first_var.tag == "fb_tSettle"
        assert first_var.comment == "步入口窗口 / S25 松开计时"

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
        for path in (FB_2001_SCL, FB_EXTERNAL_SCL, FB_1002_SCL, FB_1003_SCL, FB_1004_SCL):
            vt = SclParser().parse(path).var_table
            assert vt is not None
            declared = _declared_per_block(path)
            # FB_1002 另有 VAR_INPUT 块 (7 个 i_d*Ms 参数), 其余只有三类块
            extra = {"VAR_INPUT"} if path is FB_1002_SCL else set()
            assert set(vt.stations) == {"VAR_IN_OUT", "VAR", "VAR_CONSTANT"} | extra, path.name
            assert vt.metadata["var_block_count"] == len(declared) == 3 + len(extra), path.name
            assert _parsed_per_station(vt)["VAR_IN_OUT"] == declared["VAR_IN_OUT"], path.name
        # OB1 无任何 VAR 块
        r_ob1 = SclParser().parse(OB1_SCL)
        assert r_ob1.var_table is not None
        assert r_ob1.var_table.stations == ()

    def test_real_chinese_comment_extraction(self) -> None:
        """验证中文注释提取: // 行注释含中文 + 标点 (现样例均用 // 行注释)"""
        # FB_1003: // 行注释, 常量块里的中文
        r1003 = SclParser().parse(FB_1003_SCL)
        assert r1003.var_table is not None
        s21 = next(e for e in r1003.var_table.entries if e.tag == "STEP_S21")
        assert s21.comment == "取料准备: 升降缸上升, Z 升到取料高度"
        z_target = next(e for e in r1003.var_table.entries if e.tag == "s_rZTarget")
        assert z_target.comment == "Z 目标"
        # FB_1004: 带冒号与顿号的中文注释
        r1004 = SclParser().parse(FB_1004_SCL)
        assert r1004.var_table is not None
        wait_full = next(e for e in r1004.var_table.entries if e.tag == "STEP_WAIT_FULL")
        assert wait_full.comment == "在 D512 生成 A / B 请求"
        # FB_2001: 注释里带数字与单位的中文
        r2001 = SclParser().parse(FB_2001_SCL)
        assert r2001.var_table is not None
        clk = next(e for e in r2001.var_table.entries if e.tag == "CLK01_HALF_MS")
        assert clk.comment == "100 ms 时钟半周期"
