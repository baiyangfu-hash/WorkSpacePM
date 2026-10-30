"""PlcChecker wiring of the document/code consistency check (V01B): items, failures with location, skips, crash safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.plc import doc_consistency as dc
from auto_pm.domain.plc.checker import PlcChecker
from auto_pm.domain.plc.models import CheckResult

from .test_doc_consistency import FB_SCL, IFC_DOC, VAR_DOC, build, ifc_path


def make(tmp_path: Path, *, ifc: str | None = IFC_DOC, var: str | None = VAR_DOC, scl: str = FB_SCL) -> Path:
    project = build(tmp_path, ifc=ifc, var=var, scl=scl)
    (project / ".plc.json").write_text(
        json.dumps({"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}), encoding="utf-8")
    return project


def run(project: Path) -> CheckResult:
    return PlcChecker(str(project.parent)).check_project(str(project))


def consistency(result: CheckResult) -> list[tuple[str, str, str]]:
    return [(i.item, i.status, i.message) for i in result.items if i.item.startswith("文档一致性") or i.item == "文档待确认标记"]


def test_c01_consistent_project_reports_one_passing_item_per_documented_object(tmp_path: Path) -> None:
    items = consistency(run(make(tmp_path)))
    assert {name for name, _, _ in items} == {
        "文档一致性 [功能块 FB_Pump]", "文档一致性 [结构体 ST_PumpCfg]", "文档一致性 [数据块 GlobalVars]"}
    assert {status for _, status, _ in items} == {"pass"}


def test_c02_a_difference_fails_the_check_with_variable_and_location_in_the_message(tmp_path: Path) -> None:
    project = make(tmp_path, ifc=IFC_DOC.replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |"))
    result = run(project)
    fails = [(n, m) for n, s, m in consistency(result) if s == "fail"]
    assert len(fails) == 1 and fails[0][0] == "文档一致性 [功能块 FB_Pump]"
    assert "FB_Pump.i_bStart" in fails[0][1] and "类型" in fails[0][1] and ".md:" in fails[0][1]
    assert result.fail_count >= 1


def test_c03_missing_documents_of_single_objects_only_warn(tmp_path: Path) -> None:
    """Each object without a document is a draft to make with ``plc docs sync``; that the whole variable definition
    file is gone is a failure of its own (TD-SW008-129, tests/plc/test_required_documents_fail.py)."""
    result = run(make(tmp_path, ifc=None, var=None))
    items = consistency(result)
    assert items and {status for _, status, _ in items} == {"warn"}
    assert all("plc docs sync" in message for _, _, message in items)


def test_c04_leftover_confirmation_markers_warn_so_the_hook_stage_can_block_them(tmp_path: Path) -> None:
    project = make(tmp_path, ifc=None, var=None)
    dc.sync_project(str(project))
    items = consistency(run(project))
    marker = [x for x in items if x[0] == "文档待确认标记"]
    assert marker and marker[0][1] == "warn" and "plc docs confirm" in marker[0][2]
    dc.confirm_project(str(project))
    assert not [x for x in consistency(run(project)) if x[0] == "文档待确认标记"]


def test_c05_a_syslib_function_block_project_is_skipped(tmp_path: Path) -> None:
    project = tmp_path / "SysLib" / "FB_Lib"
    (project / "PRD").mkdir(parents=True)
    (project / "FB_Lib.scl").write_text(FB_SCL.replace("FB_Pump", "FB_Lib"), encoding="utf-8")
    result = PlcChecker(str(tmp_path)).check_project(str(project))
    assert result.project_type == "syslib_fb"
    assert consistency(result) == []


def test_c06_an_unexpected_error_in_the_consistency_code_becomes_a_warning_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_path: str, **_options: object) -> list[tuple[str, str, str]]:
        raise RuntimeError("boom")

    monkeypatch.setattr("auto_pm.domain.plc.checker.consistency_items", boom)
    result = run(make(tmp_path))
    items = consistency(result)
    assert items == [("文档一致性", "warn", "一致性核对异常，已跳过: boom")]


def test_c07_the_checker_never_writes_documents_or_code(tmp_path: Path) -> None:
    project = make(tmp_path, ifc=IFC_DOC.replace("启动命令", "起动命令"))
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    run(project)
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before
    assert "起动命令" in ifc_path(project).read_text(encoding="utf-8")


def test_c08_a_freshly_generated_standard_project_has_no_findings_and_no_markers(tmp_path: Path) -> None:
    templates = Path(__file__).resolve().parent.parent.parent / "templates"
    target = tmp_path / "DJ-2026-999_TestMachine"
    TemplateService(str(templates)).copy_template(
        "plc-standard-project", str(target),
        {"project_id": "DJ-2026-999", "project_name": "自动化测试机", "description": "gate", "version": "V1.0.0"})

    analysis = dc.analyze_project(str(target))

    assert analysis.findings == [] and analysis.marked_rows == []
    assert {r.obj.kind for r in analysis.reports} >= {"FB", "UDT", "DB"}
    assert sum(len(r.obj.variables) for r in analysis.reports) > 0
    result = PlcChecker(str(tmp_path)).check_project(str(target))
    assert [i for i in result.items if i.item.startswith("文档") and i.status != "pass" and "命名" not in i.item] == []
