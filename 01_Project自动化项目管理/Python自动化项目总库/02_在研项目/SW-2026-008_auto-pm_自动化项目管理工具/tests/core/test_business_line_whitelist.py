"""D2: the business-line whitelist (SW/DJ/ZD/XT/WX) is checked before anything is written, and it has one source.

Root cause: the prefix of a project id was copied into project metadata unchecked at four places; the whitelist
itself was pasted into six; and a project whose metadata named a business line outside it made the workspace scan
(hence every other registration) fail with a raw pydantic error.
"""

from __future__ import annotations

import ast
import json
import typing
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.workspace_registry_service import (
    WorkspaceRegistryError,
    WorkspaceRegistryService,
)
from auto_pm.domain.models.project import (
    VALID_BUSINESS_LINES,
    BusinessLine,
    InvalidBusinessLineError,
    resolve_business_line,
)
from auto_pm.ui.cli.__main__ import cli
from tests.core.test_workspace_registry_service import _anchor, _workspace

PACKAGE = Path(__file__).resolve().parents[2] / "auto_pm"


def test_the_literal_type_and_the_tuple_cannot_drift_apart() -> None:
    assert set(typing.get_args(BusinessLine)) == {*VALID_BUSINESS_LINES, ""}


@pytest.mark.parametrize("project_id", ["ZZ-2026-904", "SYS-2026-001", "nohyphen", "", "-2026-001", "sw-2026-001"])
def test_an_id_prefix_outside_the_whitelist_is_refused(project_id: str) -> None:
    with pytest.raises(InvalidBusinessLineError, match="不是合法业务线"):
        resolve_business_line(project_id)
    # An explicit business line does not rescue a bad id prefix.
    with pytest.raises(InvalidBusinessLineError, match="不是合法业务线"):
        resolve_business_line(project_id, "SW")


def test_inference_explicit_and_mismatch() -> None:
    assert resolve_business_line("DJ-2026-005") == ("DJ", "")
    assert resolve_business_line("DJ-2026-005", "DJ") == ("DJ", "")
    line, notice = resolve_business_line("DJ-2026-005", "SW")
    assert line == "SW" and "不一致" in notice
    with pytest.raises(InvalidBusinessLineError, match="不合法"):
        resolve_business_line("DJ-2026-005", "ZZ")


def test_project_create_refuses_a_bad_prefix_before_writing_anything(tmp_path: Path) -> None:
    destination = tmp_path / "projects"
    result = CliRunner().invoke(
        cli,
        ["-w", str(tmp_path), "project", "create", "--stack", "python", "--id", "ZZ-2026-904",
         "--name", "drill_py_fake", "--dest-dir", str(destination)],
    )

    assert result.exit_code != 0
    assert "不是合法业务线" in result.output and "Traceback" not in result.output
    assert not destination.exists() or not any(destination.iterdir())


def test_a_dry_run_create_also_refuses_a_bad_prefix(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        ["-w", str(tmp_path), "project", "create", "--stack", "python", "--id", "ZZ-2026-904",
         "--name", "x", "--dest-dir", str(tmp_path / "p"), "--dry-run"],
    )
    assert result.exit_code != 0 and "不是合法业务线" in result.output


def test_a_project_with_a_bad_business_line_does_not_block_other_registrations(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")
    bad = _anchor(tmp_path / "0100_项目" / "ZZ-2026-904_drill", "ZZ-2026-904")
    (bad / ".copier-answers.yml").write_text(
        "project_id: ZZ-2026-904\nproject_name: drill\nstack: python\nbusiness_line: ZZ\n", encoding="utf-8"
    )
    service = WorkspaceRegistryService(tmp_path)

    # The healthy project registers although the workspace holds the broken one (no --path: the scan walks it).
    result = service.register("DJ-2026-009")
    assert result.written
    assert "DJ-2026-009" in registry.read_text(encoding="utf-8")


def test_the_bad_project_itself_gets_a_plain_sentence_and_the_registry_is_untouched(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    bad = _anchor(tmp_path / "0100_项目" / "ZZ-2026-904_drill", "ZZ-2026-904")
    (bad / ".copier-answers.yml").write_text(
        "project_id: ZZ-2026-904\nproject_name: drill\nstack: python\nbusiness_line: ZZ\n", encoding="utf-8"
    )
    before = registry.read_bytes()

    with pytest.raises(WorkspaceRegistryError, match="业务线 'ZZ' 不在白名单"):
        WorkspaceRegistryService(tmp_path).register("ZZ-2026-904")
    assert registry.read_bytes() == before


def test_broken_metadata_of_any_field_is_a_sentence_not_a_pydantic_page(tmp_path: Path) -> None:
    _workspace(tmp_path)
    bad = _anchor(tmp_path / "0100_项目" / "SW-2026-990_x", "SW-2026-990")
    (bad / ".copier-answers.yml").write_text(
        "project_id: SW-2026-990\nproject_name: x\nstack: cobol\n", encoding="utf-8"
    )
    _anchor(tmp_path / "0100_项目" / "SW-2026-991_y", "SW-2026-991")

    assert WorkspaceRegistryService(tmp_path).register("SW-2026-991").written
    with pytest.raises(WorkspaceRegistryError, match="项目元数据无效"):
        WorkspaceRegistryService(tmp_path).register("SW-2026-990")


def test_the_workbench_create_path_refuses_a_bad_prefix_too(tmp_path: Path) -> None:
    from auto_pm.application.workbench_use_cases import WorkbenchUseCases  # noqa: PLC0415

    cases = WorkbenchUseCases.__new__(WorkbenchUseCases)
    typing.cast(typing.Any, cases).template_service = object()
    outcome = cases.create_project("ZZ-2026-904", "x", "python", "", "", dest_dir=str(tmp_path / "p"))
    assert outcome.success is False and "不是合法业务线" in outcome.message
    assert not (tmp_path / "p").exists()


def test_generate_project_code_refuses_an_unknown_business_line(tmp_path: Path) -> None:
    from auto_pm.application.core.project_service import ProjectService  # noqa: PLC0415

    with pytest.raises(ValueError, match="不合法"):
        ProjectService(str(tmp_path)).generate_project_code("ZZ")


def test_the_whitelist_has_exactly_one_copy_in_the_source() -> None:
    """A machine gate for 'one source': no module other than the model may spell the five codes as a list/tuple/set."""

    wanted = set(VALID_BUSINESS_LINES)
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.relative_to(PACKAGE).as_posix() == "domain/models/project.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                values = {e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                if wanted <= values:
                    offenders.append(f"{path.relative_to(PACKAGE).as_posix()}:{node.lineno}")
    assert offenders == [], "业务线白名单只允许在 domain/models/project.py 里有一份: " + ", ".join(offenders)


def test_every_prefix_inference_goes_through_the_checked_helper() -> None:
    """The unchecked ``project_id.split("-", 1)[0]`` that fed business_line must not come back."""

    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if 'project_id.split("-", 1)[0]' in line and "business_line =" in line.replace("  ", " "):
                offenders.append(f"{path.relative_to(PACKAGE).as_posix()}:{number}")
    assert offenders == []
    assert json.dumps(sorted(VALID_BUSINESS_LINES))
