"""Matrix unit tests for PlcChecker (LSP-907 / PM-042 / CHG-SCPT-2026-163)."""

import json

from auto_pm.domain.plc.checker import PlcChecker


def test_python_project_skipped(tmp_path):
    # Python project with pyproject.toml should be marked not_applicable
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test-py'\n", encoding="utf-8")
    checker = PlcChecker(str(tmp_path))
    res = checker.check_project(str(tmp_path))
    assert res.not_applicable is True
    assert "Python 项目" in res.not_applicable_reason


def test_plc_json_missing_fields(tmp_path):
    # .plc.json missing version and description
    plc_json = tmp_path / ".plc.json"
    plc_json.write_text(json.dumps({"name": "TestPLC"}), encoding="utf-8")
    (tmp_path / "PM_SESSION_TEST-001.md").write_text("# PM_SESSION\n", encoding="utf-8")

    checker = PlcChecker(str(tmp_path))
    res = checker.check_project(str(tmp_path))
    assert res.not_applicable is False
    fail_items = [i.item for i in res.items if i.status == "fail"]
    assert any(".plc.json" in item for item in fail_items)


def test_pm_session_line_count_thresholds(tmp_path):
    # Test line count threshold warning (>150)
    plc_json = tmp_path / ".plc.json"
    plc_json.write_text(json.dumps({"name": "TestPLC", "description": "desc", "version": "1.0.0"}), encoding="utf-8")

    # Create >150 lines PM_SESSION
    pm_file = tmp_path / "PM_SESSION_TEST-001.md"
    pm_file.write_text("\n".join([f"Line {i}" for i in range(160)]), encoding="utf-8")

    checker = PlcChecker(str(tmp_path))
    res = checker.check_project(str(tmp_path))
    warn_items = [i.item for i in res.items if i.status == "warn"]
    assert any("PM_SESSION" in item for item in warn_items)


def test_prd_docs_detection(tmp_path):
    # Test PRD standard set under PRD/
    plc_json = tmp_path / ".plc.json"
    plc_json.write_text(json.dumps({"name": "TestPLC", "description": "desc", "version": "1.0.0"}), encoding="utf-8")
    (tmp_path / "PM_SESSION_TEST-001.md").write_text("# PM_SESSION\n", encoding="utf-8")

    plan_dir = tmp_path / "PRD"
    plan_dir.mkdir()
    (plan_dir / "需求分析文档_REQ.md").write_text("# REQ\n", encoding="utf-8")
    (plan_dir / "接口文档_INT.md").write_text("# INT\n", encoding="utf-8")
    (plan_dir / "详细设计说明书_DSN.md").write_text("# DSN\n", encoding="utf-8")
    (plan_dir / "技术方案文档_TEC.md").write_text("# TEC\n", encoding="utf-8")

    checker = PlcChecker(str(tmp_path))
    res = checker.check_project(str(tmp_path))
    passed_items = [i.item for i in res.items if i.status == "pass"]
    assert any("PRD" in item for item in passed_items)


def test_scl_compliance_integration(tmp_path):
    # Test SCL compliance check under 02_PLC程序
    plc_json = tmp_path / ".plc.json"
    plc_json.write_text(json.dumps({"name": "TestPLC", "description": "desc", "version": "1.0.0"}), encoding="utf-8")
    (tmp_path / "PM_SESSION_TEST-001.md").write_text("# PM_SESSION\n", encoding="utf-8")

    plc_src_dir = tmp_path / "02_PLC程序" / "src"
    plc_src_dir.mkdir(parents=True)
    bad_scl = plc_src_dir / "FB_Bad.scl"
    bad_scl.write_text("""
FUNCTION_BLOCK FB_Bad
VAR
    badVarName : INT;
END_VAR
    GOTO LabelX;
END_FUNCTION_BLOCK
""", encoding="utf-8")

    checker = PlcChecker(str(tmp_path))
    res = checker.check_project(str(tmp_path))
    fail_items = [i.item for i in res.items if i.status == "fail"]
    assert any("SCL" in item for item in fail_items)
