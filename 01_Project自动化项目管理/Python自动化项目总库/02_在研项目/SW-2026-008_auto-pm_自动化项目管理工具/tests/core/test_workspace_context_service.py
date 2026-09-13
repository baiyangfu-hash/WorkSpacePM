"""Regression tests for registry-backed, fail-closed workspace context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.core.pm_resume_service import PmResumeService
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli


def _project(root: Path, project_id: str) -> Path:
    project = root / project_id
    project.mkdir(parents=True)
    (project / ".copier-answers.yml").write_text(
        f"project_id: {project_id}\nproject_name: {project_id}\nstack: python\n",
        encoding="utf-8",
    )
    (project / f"PM_SESSION_{project_id}.md").write_text(
        f"# {project_id}\n",
        encoding="utf-8",
    )
    return project


def _mapping(project_id: str, **overrides: str) -> dict[str, str]:
    result = {
        "project_id": project_id,
        "project_root": project_id,
        "development_root": project_id,
        "control_project_id": "",
        "control_pm_session": "",
        "runtime_root": "",
    }
    result.update(overrides)
    return result


def _registry(root: Path, *projects: dict[str, str]) -> Path:
    path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": "workspace-registry.v1", "projects": projects}),
        encoding="utf-8",
    )
    return path


def _runtime_package(runtime: Path, release_id: str) -> Path:
    package = runtime / "releases" / release_id / "auto_pm"
    package.mkdir(parents=True)
    package_file = package / "__init__.py"
    package_file.write_text("# test package\n", encoding="utf-8")
    return package_file


def test_resolves_registered_project_from_nested_directory(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    _registry(tmp_path, _mapping("SW-2026-008"))
    nested = project / "auto_pm" / "application"
    nested.mkdir(parents=True)

    result = WorkspaceContextService(str(tmp_path)).resolve(start_path=nested)

    assert result.schema_version == "workspace-context.v2"
    assert result.resolution_source == "directory"
    assert result.subject_project_id == "SW-2026-008"
    assert result.subject.project_id == "SW-2026-008"
    assert result.development_root == "SW-2026-008"
    assert [item.path for item in result.read_set] == [
        "SYS-2026-001_WorkspaceGovernance/workspace_registry.json",
        "SW-2026-008/.copier-answers.yml",
    ]


def test_explicit_identity_uses_registry_not_nearby_scan(tmp_path: Path) -> None:
    _project(tmp_path, "SW-2026-008")
    _project(tmp_path, "SW-2026-009")
    _registry(tmp_path, _mapping("SW-2026-008"), _mapping("SW-2026-009"))
    unmanaged = tmp_path / "notes"
    unmanaged.mkdir()

    result = WorkspaceContextService(str(tmp_path)).resolve(
        project_id="SW-2026-009",
        start_path=unmanaged,
    )

    assert result.resolution_source == "explicit"
    assert result.subject_project_id == "SW-2026-009"


def test_unmanaged_directory_without_explicit_identity_fails_closed(tmp_path: Path) -> None:
    _project(tmp_path, "SW-2026-008")
    _registry(tmp_path, _mapping("SW-2026-008"))
    unmanaged = tmp_path / "notes"
    unmanaged.mkdir()

    with pytest.raises(WorkspaceContextError, match="未解析到项目"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=unmanaged)


def test_unregistered_directory_anchor_fails_closed(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    _registry(tmp_path)

    with pytest.raises(WorkspaceContextError, match="未登记"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=project)


def test_registry_path_conflict_fails_closed(tmp_path: Path) -> None:
    first = _project(tmp_path, "SW-2026-008")
    second = _project(tmp_path, "SW-2026-009")
    _registry(
        tmp_path,
        _mapping(
            "SW-2026-008",
            project_root="SW-2026-009",
            development_root="SW-2026-009",
        ),
    )

    with pytest.raises(WorkspaceContextError, match="目录锚点"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=first)
    with pytest.raises(WorkspaceContextError, match="不一致"):
        WorkspaceContextService(str(tmp_path)).resolve(
            project_id="SW-2026-008",
            start_path=second,
        )


def test_control_mapping_comes_from_registry(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    _project(tmp_path, "SYS-2026-001")
    _registry(
        tmp_path,
        _mapping("SYS-2026-001"),
        _mapping(
            "SW-2026-008",
            control_project_id="SYS-2026-001",
            control_pm_session="SYS-2026-001/PM_SESSION_SYS-2026-001.md",
        ),
    )

    result = WorkspaceContextService(str(tmp_path)).resolve(start_path=project)

    assert result.control_project_id == "SYS-2026-001"
    assert result.control_pm_session == "SYS-2026-001/PM_SESSION_SYS-2026-001.md"


def test_partial_control_mapping_fails_closed(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    _registry(
        tmp_path,
        _mapping("SW-2026-008", control_project_id="SYS-2026-001"),
    )

    with pytest.raises(WorkspaceContextError, match="必须同时声明"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=project)


def test_release_pointer_is_bounded_evidence(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    runtime = tmp_path / "runtime"
    package_file = _runtime_package(runtime, "1.2.4-test")
    (runtime / "active_release.json").write_text(
        json.dumps({"release_id": "1.2.4-test"}),
        encoding="utf-8",
    )
    _registry(tmp_path, _mapping("SW-2026-008", runtime_root="runtime"))

    result = WorkspaceContextService(
        str(tmp_path), package_file_provider=lambda: package_file
    ).resolve(start_path=project)

    assert result.runtime_root == "runtime"
    assert result.release_id == "1.2.4-test"
    assert result.configured_release_id == "1.2.4-test"
    assert result.effective_release_id == "1.2.4-test"
    assert result.runtime_load_path == "runtime/releases/1.2.4-test/auto_pm/__init__.py"
    assert result.runtime_fallback_reason == ""
    assert result.conflicts == ()
    assert [item.path for item in result.read_set] == [
        "SYS-2026-001_WorkspaceGovernance/workspace_registry.json",
        "SW-2026-008/.copier-answers.yml",
        "runtime/active_release.json",
        "runtime/releases/1.2.4-test/auto_pm/__init__.py",
    ]


def test_runtime_identity_reports_loaded_release_divergence(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    runtime = tmp_path / "runtime"
    _runtime_package(runtime, "1.2.4-configured")
    loaded_package_file = _runtime_package(runtime, "1.2.3-loaded")
    (runtime / "active_release.json").write_text(
        json.dumps({"release_id": "1.2.4-configured"}),
        encoding="utf-8",
    )
    _registry(tmp_path, _mapping("SW-2026-008", runtime_root="runtime"))

    result = WorkspaceContextService(
        str(tmp_path), package_file_provider=lambda: loaded_package_file
    ).resolve(start_path=project)

    assert result.configured_release_id == "1.2.4-configured"
    assert result.effective_release_id == "1.2.3-loaded"
    assert result.runtime_load_path == "runtime/releases/1.2.3-loaded/auto_pm/__init__.py"
    assert result.runtime_fallback_reason == ""
    assert result.conflicts == ("RUNTIME_IDENTITY_DIVERGENCE",)


def test_runtime_identity_fails_closed_when_loaded_package_file_is_unavailable(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    runtime = tmp_path / "runtime"
    _runtime_package(runtime, "1.2.4-configured")
    (runtime / "active_release.json").write_text(
        json.dumps({"release_id": "1.2.4-configured"}),
        encoding="utf-8",
    )
    _registry(tmp_path, _mapping("SW-2026-008", runtime_root="runtime"))

    result = WorkspaceContextService(
        str(tmp_path), package_file_provider=lambda: None
    ).resolve(start_path=project)

    assert result.release_id == "1.2.4-configured"
    assert result.configured_release_id == "1.2.4-configured"
    assert result.effective_release_id == ""
    assert result.runtime_load_path == ""
    assert result.runtime_fallback_reason == "loaded_package_file_unavailable"
    assert result.conflicts == ("RUNTIME_IDENTITY_UNVERIFIED",)
    assert result.read_set[-1].path == "runtime/active_release.json"


def test_duplicate_registry_identity_fails_closed(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    _registry(tmp_path, _mapping("SW-2026-008"), _mapping("SW-2026-008"))

    with pytest.raises(WorkspaceContextError, match="重复项目"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=project)


def test_absolute_registry_path_fails_closed(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    _registry(
        tmp_path,
        _mapping(
            "SW-2026-008",
            project_root=str(project),
            development_root=str(project),
        ),
    )

    with pytest.raises(WorkspaceContextError, match="工作区相对路径"):
        WorkspaceContextService(str(tmp_path)).resolve(start_path=project)


def test_platform_neutral_context_resolve_cli(tmp_path: Path) -> None:
    project = _project(tmp_path, "SW-2026-008")
    _registry(tmp_path, _mapping("SW-2026-008"))

    result = CliRunner().invoke(
        cli,
        ["-w", str(tmp_path), "context", "resolve", "--path", str(project)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "workspace-context.v2"
    assert payload["subject_project_id"] == "SW-2026-008"


def test_sys_resume_keeps_its_own_control_session(tmp_path: Path) -> None:
    subject = tmp_path / "PM_SESSION_SYS-2026-001.md"
    subject.write_text("# SYS\n", encoding="utf-8")

    result = PmResumeService(str(tmp_path))._find_control_session(
        "SYS-2026-001",
        subject,
        "",
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
        "SW-2026-008",
        subject,
        "",
    )

    assert result == control.resolve()
