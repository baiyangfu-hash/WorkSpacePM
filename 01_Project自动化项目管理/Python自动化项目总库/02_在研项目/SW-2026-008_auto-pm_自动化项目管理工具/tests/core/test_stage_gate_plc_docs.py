"""The monitoring -> closing gate also requires PLC documents to match the code and carry no unconfirmed rows (V01D)."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.gates.stage_gate_engine import StageGateEngine
from auto_pm.contracts.gate_dtos import GateCheckItemDTO, StageGateResultDTO
from auto_pm.domain.plc import doc_consistency as dc
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


def test_s06_missing_documents_block_the_delivery_gate(tmp_path: Path) -> None:
    """Whole missing documents are only a warning in `plc check`, but the delivery gate blocks on them (user ruling of 2026-10-13)."""
    result = evaluate(plc_project(tmp_path, ifc=None, var=None))
    found = item(result)
    assert found is not None and not found.passed and result.can_proceed is False
    assert "拦住项" in found.message and "plc docs sync" in found.fix_suggestion


def _f01a_stage_git(root: Path, *args: str) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=tester", "-c", "user.email=t@example.test", "-c", "core.autocrlf=false", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout


def _f01a_stage_scene(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "stage-repo"
    root.mkdir(parents=True)
    _f01a_stage_git(root, "init", "-q")
    project = plc_project(root / "0100_PLC自动化")
    _f01a_stage_git(root, "add", "-A")
    _f01a_stage_git(root, "commit", "-q", "-m", "PLC baseline")
    return root, project


@pytest.mark.parametrize("wrong_type", [False, True])
def test_f01a_s07_head_marker_deletion_keeps_the_original_plc_blocker(
    tmp_path: Path, wrong_type: bool
) -> None:
    root, project = _f01a_stage_scene(tmp_path)
    ifc = next(project.rglob("接口文档_IFC-FB_Pump.md"))
    if wrong_type:
        ifc.write_text(ifc.read_text(encoding="utf-8", errors="replace").replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |"), encoding="utf-8", errors="replace", newline="\n")
    marker = (project / ".plc.json").relative_to(root).as_posix()
    _f01a_stage_git(root, "rm", "--", marker)
    index_before = (root / ".git" / "index").read_bytes()
    document_before = ifc.read_bytes()

    result = StageGateEngine(str(root)).evaluate_stage_transition(str(project), "monitoring", "closing")
    found = item(result)

    assert found is not None and not found.passed and found.severity == "BLOCKER"
    assert result.can_proceed is False and "移动或退役请走 F01-b 的授权" in found.message
    assert (root / ".git" / "index").read_bytes() == index_before
    assert ifc.read_bytes() == document_before
    assert not (project / ".plc.json").exists()


def test_f01a_s08_a_worktree_deletion_blocks_even_while_the_index_retains_the_marker(tmp_path: Path) -> None:
    root, project = _f01a_stage_scene(tmp_path)
    marker = (project / ".plc.json").relative_to(root).as_posix()
    (project / ".plc.json").unlink()
    assert _f01a_stage_git(root, "ls-files", "-z", "--", marker).rstrip("\0") == marker
    index_before = (root / ".git" / "index").read_bytes()

    result = StageGateEngine(str(root)).evaluate_stage_transition(str(project), "monitoring", "closing")
    found = item(result)

    assert found is not None and not found.passed and found.severity == "BLOCKER" and result.can_proceed is False
    assert "移动或退役请走 F01-b 的授权" in found.message
    assert (root / ".git" / "index").read_bytes() == index_before


@pytest.mark.parametrize("wrong_type", [False, True])
def test_f01a_s09_an_unborn_project_uses_its_current_plc_document_contract(
    tmp_path: Path, wrong_type: bool
) -> None:
    root = tmp_path / "stage-unborn"
    root.mkdir()
    _f01a_stage_git(root, "init", "-q")
    ifc = IFC_DOC.replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |") if wrong_type else IFC_DOC
    project = plc_project(root / "0100_PLC自动化", ifc=ifc)

    result = StageGateEngine(str(root)).evaluate_stage_transition(str(project), "monitoring", "closing")
    found = item(result)

    assert found is not None and found.severity == "BLOCKER"
    assert found.passed is not wrong_type and result.can_proceed is not wrong_type
    expected_message = "FB_Pump.i_bStart" if wrong_type else "文档与代码一致"
    assert expected_message in found.message


@pytest.mark.parametrize("corruption", ["malformed_head", "missing_commit_object"])
def test_f01a_s10_a_corrupt_git_head_keeps_a_failing_plc_item(tmp_path: Path, corruption: str) -> None:
    root, project = _f01a_stage_scene(tmp_path)
    head_path = root / ".git" / "HEAD"
    if corruption == "malformed_head":
        corrupt_path = head_path
        corrupt_text = "not-a-valid-git-head\n"
    else:
        reference = _f01a_stage_git(root, "symbolic-ref", "HEAD").strip()
        corrupt_path = root / ".git" / reference
        corrupt_text = "0" * len(_f01a_stage_git(root, "rev-parse", "HEAD").strip()) + "\n"
    corrupt_path.write_text(corrupt_text, encoding="utf-8", errors="replace")
    head_before = head_path.read_bytes()
    corrupt_before = corrupt_path.read_bytes()
    index_before = (root / ".git" / "index").read_bytes()

    result = StageGateEngine(str(root)).evaluate_stage_transition(str(project), "monitoring", "closing")
    found = item(result)

    assert found is not None and not found.passed and found.severity == "BLOCKER" and result.can_proceed is False
    assert "Git" in found.message
    assert head_path.read_bytes() == head_before
    assert corrupt_path.read_bytes() == corrupt_before
    assert (root / ".git" / "index").read_bytes() == index_before


def test_f01a_s11_a_project_outside_the_selected_repository_cannot_borrow_its_head(tmp_path: Path) -> None:
    selected, _selected_project = _f01a_stage_scene(tmp_path / "selected")
    other, project = _f01a_stage_scene(tmp_path / "other")
    other_head = _f01a_stage_git(other, "rev-parse", "HEAD")

    result = StageGateEngine(str(selected)).evaluate_stage_transition(str(project), "monitoring", "closing")
    found = item(result)

    assert found is not None and not found.passed and found.severity == "BLOCKER" and result.can_proceed is False
    assert _f01a_stage_git(other, "rev-parse", "HEAD") == other_head
