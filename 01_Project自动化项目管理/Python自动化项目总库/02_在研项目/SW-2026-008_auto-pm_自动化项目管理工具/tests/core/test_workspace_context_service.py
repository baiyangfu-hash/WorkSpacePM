"""Regression tests for fail-closed per-invocation project context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.core.pm_resume_service import PmResumeService
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli


def _project(
    root: Path,
    project_id: str,
    *,
    control_project_id: str = "",
    control_session: str = "",
) -> Path:
    project = root / project_id
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        f"project_id: {project_id}\nproject_name: {project_id}\nstack: python\n",
        encoding="utf-8",
    )
    lines = [f"# {project_id}"]
    if control_project_id:
        lines.append(f"- control_project_id: {control_project_id}")
    if control_session:
        lines.append(f"- control_pm_session: {control_session}")
    (project / f"PM_SESSION_{project_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return project


def test_resolves_project_from_nested_directory(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    nested = project / "auto_pm" / "application"
    nested.mkdir(parents=True)

    result = WorkspaceContextService(str(tmp_path)).resolve(start_path=nested)

    assert result.resolution_source == "directory"
    assert result.subject.project_id == "SW-2026-008"
    assert result.development_root == "SW-2026-008"
    assert result.control_project_id == ""
    assert len(result.read_set) == 2
    assert result.evidence_id.startswith("CTX-")


def test_explicit_identity_overrides_directory(tmp_path: Path) -> None:
    second = _project(tmp_path, "SW-2026-009")

    result = WorkspaceContextService(str(tmp_path)).resolve(
        project_id="SW-2026-009", start_path=second
    )

    assert result.resolution_source == "explicit"
    assert result.subject.project_id == "SW-2026-009"
    assert result.subject.path == "SW-2026-009"


def test_unmanaged_directory_fails_closed(tmp_path: Path) -> None:
    _project(tmp_path, "SW-2026-008")
    unmanaged = tmp_path / "notes"
    unmanaged.mkdir()

    with pytest.raises(WorkspaceContextError, match="未解析到项目"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=unmanaged)


def test_control_requires_structured_mapping(tmp_path: Path) -> None:
    _project(tmp_path, "SYS-2026-001")
    project = _project(
        tmp_path,
        "SW-2026-008",
        control_project_id="SYS-2026-001",
        control_session="SYS-2026-001/PM_SESSION_SYS-2026-001.md",
    )

    result = WorkspaceContextService(str(tmp_path)).resolve(start_path=project)

    assert result.control_project_id == "SYS-2026-001"
    assert result.control_pm_session == "SYS-2026-001/PM_SESSION_SYS-2026-001.md"


def test_partial_control_mapping_fails_closed(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008", control_project_id="SYS-2026-001")

    with pytest.raises(WorkspaceContextError, match="必须同时声明"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=project)


def test_release_pointer_is_bounded_evidence(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "active_release.json").write_text(
        json.dumps({"release_id": "1.2.4-test"}), encoding="utf-8"
    )
    session = project / "PM_SESSION_SW-2026-008.md"
    session.write_text(session.read_text(encoding="utf-8") + "- runtime_root: runtime\n", encoding="utf-8")

    result = WorkspaceContextService(str(tmp_path)).resolve(start_path=project)

    assert result.runtime_root == "runtime"
    assert result.release_id == "1.2.4-test"
    assert [item.path for item in result.read_set] == [
        "SW-2026-008/.copier-answers.yml",
        "SW-2026-008/PM_SESSION_SW-2026-008.md",
        "runtime/active_release.json",
    ]


def test_session_anchor_is_not_duplicated(tmp_path: Path) -> None:
    project = tmp_path / "SYS-2026-001"
    project.mkdir()
    (project / "PM_SESSION_SYS-2026-001.md").write_text("# SYS\n", encoding="utf-8")

    result = WorkspaceContextService(str(tmp_path)).resolve(start_path=project)

    assert [item.path for item in result.read_set] == ["SYS-2026-001/PM_SESSION_SYS-2026-001.md"]


def test_platform_neutral_context_resolve_cli(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")

    result = CliRunner().invoke(
        cli,
        ["-w", str(tmp_path), "context", "resolve", "--path", str(project)],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["subject"]["project_id"] == "SW-2026-008"


def test_sys_resume_keeps_its_own_control_session(tmp_path: Path) -> None:
    subject = tmp_path / "PM_SESSION_SYS-2026-001.md"
    subject.write_text("# SYS\n", encoding="utf-8")

    result = PmResumeService(str(tmp_path))._find_control_session(
        "SYS-2026-001", subject, ""
    )

    assert result == subject


def test_resume_uses_structured_control_mapping(tmp_path: Path) -> None:
    control = tmp_path / "SYS-2026-001" / "PM_SESSION_SYS-2026-001.md"
    control.parent.mkdir()
    control.write_text("# SYS\n", encoding="utf-8")
    subject = tmp_path / "SW-2026-008" / "PM_SESSION_SW-2026-008.md"
    subject.parent.mkdir()
    subject.write_text(
        "- control_project_id: SYS-2026-001\n"
        "- control_pm_session: SYS-2026-001/PM_SESSION_SYS-2026-001.md\n",
        encoding="utf-8",
    )

    result = PmResumeService(str(tmp_path))._find_control_session(
        "SW-2026-008", subject, ""
    )

    assert result == control.resolve()
