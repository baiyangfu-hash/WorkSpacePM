"""The monitoring -> closing gate also requires PLC documents to match the code and carry no unconfirmed rows (V01D)."""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.plc import doc_consistency as dc

from auto_pm.application.core.gates.stage_gate_engine import StageGateEngine
from auto_pm.contracts.gate_dtos import GateCheckItemDTO, StageGateResultDTO
from tests.plc.test_doc_consistency import IFC_DOC, VAR_DOC, build

ITEM = "G4-PLC-DOC-CODE-CONSISTENT"


def plc_project(tmp_path: Path, *, ifc: str | None = IFC_DOC, var: str | None = VAR_DOC) -> Path:
    project = build(tmp_path, ifc=ifc, var=var)
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    return project


def evaluate(project: Path) -> StageGateResultDTO:
    return StageGateEngine(str(project.parent)).evaluate_stage_transition(str(project), "monitoring", "closing")


def item(result: StageGateResultDTO) -> GateCheckItemDTO | None:
    return next((i for i in result.items if i.id == ITEM), None)


def test_s01_a_project_without_plc_json_has_no_plc_item(tmp_path: Path) -> None:
    project = build(tmp_path)
    result = evaluate(project)
    assert item(result) is None and result.can_proceed is True


def test_s02_a_consistent_plc_project_passes_the_item(tmp_path: Path) -> None:
    result = evaluate(plc_project(tmp_path))
    found = item(result)
    assert found is not None and found.passed and found.severity == "BLOCKER" and result.can_proceed is True


def test_s03_a_difference_blocks_closing_and_names_the_variable(tmp_path: Path) -> None:
    result = evaluate(plc_project(tmp_path, ifc=IFC_DOC.replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |")))
    found = item(result)
    assert found is not None and not found.passed and found.severity == "BLOCKER" and result.can_proceed is False
    assert "FB_Pump.i_bStart" in found.message and "plc docs sync" in found.fix_suggestion


def test_s04_unconfirmed_markers_block_closing(tmp_path: Path) -> None:
    project = plc_project(tmp_path)
    ifc = next(project.rglob("接口文档_IFC-FB_Pump.md"))
    ifc.write_text(ifc.read_text(encoding="utf-8").replace("| 启动命令 |", f"| {dc.MARKER}启动命令 |"), encoding="utf-8")
    result = evaluate(project)
    found = item(result)
    assert found is not None and not found.passed and "待确认标记 1" in found.message and result.can_proceed is False


def test_s05_a_failing_check_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_path: str) -> object:
        raise RuntimeError("解析器崩溃")

    monkeypatch.setattr(dc, "analyze_project", boom)
    result = evaluate(plc_project(tmp_path))
    found = item(result)
    assert found is not None and not found.passed and "解析器崩溃" in found.message and result.can_proceed is False


def test_s06_missing_documents_alone_do_not_block(tmp_path: Path) -> None:
    result = evaluate(plc_project(tmp_path, ifc=None, var=None))
    found = item(result)
    assert found is not None and found.passed and result.can_proceed is True
