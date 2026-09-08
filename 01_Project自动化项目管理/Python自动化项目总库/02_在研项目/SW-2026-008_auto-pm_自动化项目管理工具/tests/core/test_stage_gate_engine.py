"""tests.core.test_stage_gate_engine - StageGateEngine 单元测试套件"""

from pathlib import Path

import pytest
from auto_pm.core.gates import StageGateEngine

from auto_pm.contracts.gate_dtos import StageGateResultDTO


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """创建一个符合标准的虚拟项目目录"""
    proj = tmp_path / "DJ-2026-999_测试设备"
    proj.mkdir()

    # 1. 启动阶段要素 (G1)
    pm_session = proj / "PM_SESSION_DJ-2026-999.md"
    pm_session.write_text(
        "# PM_SESSION_DJ-2026-999\n\n"
        "## 1. Positioning\n- non_goals: 本期不做MES\n\n"
        "## 8. Handoff Notes\n"
        "- current_state: 执行完成，待监控\n"
        "- skill_handoff_001: 主 Agent 已完成执行阶段交付\n",
        encoding="utf-8"
    )

    # 2. 规划阶段要素 (G2)
    plan_dir = proj / "01_需求与设计"
    plan_dir.mkdir()
    (plan_dir / "001_产品需求文档_PRD.md").write_text("# PRD 需求文档\n", encoding="utf-8")
    (plan_dir / "002_接口文档_INT.md").write_text("# INT 变量表\n", encoding="utf-8")

    hmi_dir = proj / "03_HMI设计"
    hmi_dir.mkdir()
    (hmi_dir / "HMI原型设计.html").write_text("<html></html>", encoding="utf-8")

    # 3. 执行阶段要素 (G3)
    plc_dir = proj / "02_PLC程序" / "PLC_ST"
    plc_dir.mkdir(parents=True)
    (plc_dir / "OB1.scl").write_text("PROGRAM OB1\nEND_PROGRAM", encoding="utf-8")

    # 4. 监控与收尾阶段要素 (G4)
    chg_dir = proj / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
    chg_dir.mkdir(parents=True)
    (chg_dir / "CHG-PLC-2026-001.md").write_text(
        "# CHG-001\n- status: closed\n- 状态: closed\n",
        encoding="utf-8"
    )

    # 台账文件（LedgerReconciler 对账用，含 CHG-PLC-2026-001 记录行）
    ledger_dir = proj / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "01_版本变更台帐.md").write_text(
        "# 版本变更台帐\n\n"
        "## 变更单索引\n\n"
        "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
        "|------|----------|------|--------|----------|----------|----------|------|\n"
        "| 001 | [→ CHG-PLC-2026-001](./01_变更单/CHG-PLC/CHG-PLC-2026-001.md) "
        "| PLC | fubai | 2026-07-09 | CHG-PLC-2026-001 | 2026-07-09 | ✅已关闭 |\n",
        encoding="utf-8"
    )

    return proj


def test_stage_gate_g1_initiating_to_planning(temp_project: Path):
    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(temp_project), current_stage="initiating", target_stage="planning"
    )
    assert isinstance(result, StageGateResultDTO)
    assert result.can_proceed is True
    assert result.blocker_count == 0
    assert result.passed_checks == 2


def test_stage_gate_g1_blocks_when_no_pm_session(tmp_path: Path):
    empty_proj = tmp_path / "Empty_Project"
    empty_proj.mkdir()

    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(empty_proj), current_stage="initiating", target_stage="planning"
    )
    assert result.can_proceed is False
    assert result.blocker_count >= 1
    assert any(item.id == "G1-PM-SESSION" and not item.passed for item in result.items)


def test_stage_gate_g2_planning_to_executing(temp_project: Path):
    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(temp_project), current_stage="planning", target_stage="executing"
    )
    assert result.can_proceed is True
    assert result.blocker_count == 0
    assert any(item.id == "G2-PRD-FROZEN" and item.passed for item in result.items)
    assert any(item.id == "G2-INT-FROZEN" and item.passed for item in result.items)


def test_stage_gate_g3_executing_to_monitoring(temp_project: Path):
    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(temp_project), current_stage="executing", target_stage="monitoring"
    )
    assert result.can_proceed is True
    assert result.blocker_count == 0
    assert any(item.id == "G3-SRC-EXISTS" and item.passed for item in result.items)


def test_stage_gate_g3_blocks_when_no_pm_closure(tmp_path: Path):
    proj = tmp_path / "DJ-2026-998_无落账"
    proj.mkdir()
    (proj / "PM_SESSION_DJ-2026-998.md").write_text(
        "# PM_SESSION_DJ-2026-998\n\n## 1. Positioning\n- non_goals: 本期不做MES\n",
        encoding="utf-8",
    )
    plc_dir = proj / "02_PLC程序" / "PLC_ST"
    plc_dir.mkdir(parents=True)
    (plc_dir / "OB1.scl").write_text("PROGRAM OB1\nEND_PROGRAM", encoding="utf-8")

    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(proj), current_stage="executing", target_stage="monitoring"
    )
    assert result.can_proceed is False
    assert result.blocker_count >= 1
    assert any(item.id == "G3-PM-CLOSURE" and not item.passed for item in result.items)


def test_stage_gate_g3_blocks_when_ledger_missing(tmp_path: Path):
    """有 CHG 文件（新路径）但台账缺失 → G3-PM-CLOSURE 未通过"""
    proj = tmp_path / "DJ-2026-997_缺台账"
    proj.mkdir()
    (proj / "PM_SESSION_DJ-2026-997.md").write_text(
        "# PM_SESSION_DJ-2026-997\n\n"
        "## 1. Positioning\n- non_goals: 本期不做MES\n\n"
        "## 8. Handoff Notes\n"
        "- skill_handoff_001: 主 Agent 已完成执行阶段交付\n",
        encoding="utf-8",
    )
    plc_dir = proj / "02_PLC程序" / "PLC_ST"
    plc_dir.mkdir(parents=True)
    (plc_dir / "OB1.scl").write_text("PROGRAM OB1\nEND_PROGRAM", encoding="utf-8")

    chg_dir = proj / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
    chg_dir.mkdir(parents=True)
    (chg_dir / "CHG-PLC-2026-001.md").write_text(
        "# CHG-001\n- status: closed\n- 状态: closed\n", encoding="utf-8"
    )
    # 不创建台账文件

    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(proj), current_stage="executing", target_stage="monitoring"
    )
    assert result.can_proceed is False
    assert any(item.id == "G3-PM-CLOSURE" and not item.passed for item in result.items)


def test_stage_gate_g3_blocks_when_no_skill_handoff(tmp_path: Path):
    """台账完整但 PM_SESSION §8 无 skill_handoff → G3-PM-CLOSURE 未通过"""
    proj = tmp_path / "DJ-2026-996_缺回写"
    proj.mkdir()
    (proj / "PM_SESSION_DJ-2026-996.md").write_text(
        "# PM_SESSION_DJ-2026-996\n\n"
        "## 1. Positioning\n- non_goals: 本期不做MES\n\n"
        "## 8. Handoff Notes\n"
        "- current_state: 执行完成，待监控\n",
        encoding="utf-8",
    )
    plc_dir = proj / "02_PLC程序" / "PLC_ST"
    plc_dir.mkdir(parents=True)
    (plc_dir / "OB1.scl").write_text("PROGRAM OB1\nEND_PROGRAM", encoding="utf-8")

    chg_dir = proj / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
    chg_dir.mkdir(parents=True)
    (chg_dir / "CHG-PLC-2026-001.md").write_text(
        "# CHG-001\n- status: closed\n- 状态: closed\n", encoding="utf-8"
    )

    ledger_dir = proj / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "01_版本变更台帐.md").write_text(
        "# 版本变更台帐\n\n"
        "## 变更单索引\n\n"
        "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
        "|------|----------|------|--------|----------|----------|----------|------|\n"
        "| 001 | [→ CHG-PLC-2026-001](./01_变更单/CHG-PLC/CHG-PLC-2026-001.md) "
        "| PLC | fubai | 2026-07-09 | CHG-PLC-2026-001 | 2026-07-09 | ✅已关闭 |\n",
        encoding="utf-8",
    )

    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(proj), current_stage="executing", target_stage="monitoring"
    )
    assert result.can_proceed is False
    assert any(item.id == "G3-PM-CLOSURE" and not item.passed for item in result.items)


def test_stage_gate_g4_monitoring_to_closing(temp_project: Path):
    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(temp_project), current_stage="monitoring", target_stage="closing"
    )
    assert result.can_proceed is True
    assert result.blocker_count == 0


def test_stage_gate_g4_blocks_unclosed_chg(temp_project: Path):
    # 添加一个未关闭的变更单
    chg_dir = temp_project / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
    (chg_dir / "CHG-PLC-2026-002.md").write_text(
        "# CHG-002\n- status: implementing\n", encoding="utf-8"
    )

    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(temp_project), current_stage="monitoring", target_stage="closing"
    )
    assert result.can_proceed is False
    assert result.blocker_count >= 1
    assert any(item.id == "G4-CHG-ALL-CLOSED" and not item.passed for item in result.items)


def test_stage_gate_handles_non_existent_project(tmp_path: Path):
    non_exist = tmp_path / "Non_Exist_12345"
    engine = StageGateEngine()
    result = engine.evaluate_stage_transition(
        str(non_exist), current_stage="initiating", target_stage="planning"
    )
    assert result.can_proceed is False
    assert result.blocker_count == 1
    assert result.items[0].id == "G-ROOT-EXIST"
