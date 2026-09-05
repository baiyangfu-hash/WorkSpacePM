"""工艺矩阵离线 SCL 生成器单元测试 (LSP-905 规范 / 结构体整块传递)"""

from __future__ import annotations

from pathlib import Path

from auto_pm.plc.generator import (
    ProcessMatrix,
    ProcessMatrixParser,
    ProcessMatrixStep,
    SclGenerator,
)


def test_process_matrix_parser_extracts_metadata() -> None:
    md_content = """
    # 堆垛机控制工艺

    fb_number: FB_1005
    fb_name: StackerControl
    station_name: Station_DJ005

    | 步骤ID | 步骤名称 | 触发条件 | 动作输出 | 联锁/安全 | 下一步骤 |
    | :--- | :--- | :--- | :--- | :--- | :--- |
    | 10 | MoveToPos | i_bStart | o_bMotorRun := TRUE | i_bSafetyOk | 20 |
    | 20 | ClampObject | i_bSensorPos | o_bClampClose := TRUE | - | 0 |
    """
    matrix = ProcessMatrixParser.parse_markdown(md_content)

    assert matrix.fb_number == "FB_1005"
    assert matrix.fb_name == "StackerControl"
    assert matrix.station_name == "Station_DJ005"
    assert len(matrix.steps) == 2
    assert matrix.steps[0].step_id == 10
    assert matrix.steps[0].name == "MoveToPos"
    assert matrix.steps[0].trigger == "i_bStart"
    assert "o_bMotorRun := TRUE" in matrix.steps[0].actions


def test_scl_generator_renders_valid_code(tmp_path: Path) -> None:
    matrix = ProcessMatrix(
        fb_number="FB_1002",
        fb_name="SingleLayerConveyor",
        station_name="DJ2026_005",
        steps=[
            ProcessMatrixStep(
                step_id=10,
                name="StartTransport",
                trigger="i_bStart",
                actions=["io_stStation.stActuators.bMotorFwd := TRUE"],
                interlock="i_bSafetyOk",
                next_step=20,
            ),
            ProcessMatrixStep(
                step_id=20,
                name="StopTransport",
                trigger="i_bSensorPos",
                actions=["io_stStation.stActuators.bMotorFwd := FALSE", "s_bDone := TRUE"],
                next_step=0,
            ),
        ],
    )

    gen = SclGenerator()
    out_file = tmp_path / "FB_1002_SingleLayerConveyor_DJ2026_005.scl"
    gen.generate_to_file(matrix, out_file)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")

    # 验证结构体整块传递与规范特征
    assert 'FUNCTION_BLOCK "FB_1002_SingleLayerConveyor_DJ2026_005"' in content
    assert "io_stStation : ST_DJ2026_005;" in content
    assert "io_stStation.stActuators.bMotorFwd := TRUE;" in content
    assert "CASE s_iStep OF" in content
    assert "ELSE // 安全防死锁分支" in content
    assert "io_stStation.stStatus.iStep       := s_iStep;" in content


def test_scl_generator_generates_module_with_udt(tmp_path: Path) -> None:
    matrix = ProcessMatrix(
        fb_number="FB_1001",
        fb_name="Station1",
        station_name="Station1",
        steps=[
            ProcessMatrixStep(
                step_id=10,
                name="FeedIn",
                trigger="t_bInPos",
                actions=["io_stStation.stActuators.bMotorFwd := TRUE"],
                interlock="",
                next_step=20,
            ),
        ],
    )

    gen = SclGenerator()
    fb_file, udt_file = gen.generate_module(matrix, tmp_path / "02_工位1")

    assert fb_file.exists()
    assert udt_file.exists()
    assert "TYPE ST_Station1 :" in udt_file.read_text(encoding="utf-8")
    assert "ST_Station1_Control" in udt_file.read_text(encoding="utf-8")
