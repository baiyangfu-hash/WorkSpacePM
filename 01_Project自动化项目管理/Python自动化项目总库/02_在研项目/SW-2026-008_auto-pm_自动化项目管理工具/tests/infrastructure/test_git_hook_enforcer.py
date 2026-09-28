"""Regression coverage for the control-root commit attribution contract."""

from __future__ import annotations

import pytest

from auto_pm.infrastructure.git_hook_enforcer import (
    CONTROL_ROOT_FILE_BINDINGS,
    ProjectBinding,
    StagedSnapshotError,
    _binding_for_staged_file,
)

SW008_ROOT = (
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/"
    "SW-2026-008_auto-pm_自动化项目管理工具"
)
SW009_ROOT = (
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/"
    "SW-2026-009_英语学习助手"
)


@pytest.fixture
def bindings() -> tuple[ProjectBinding, ProjectBinding]:
    """Provide two ordinary registered project roots."""
    return (
        ProjectBinding("SW-2026-008", SW008_ROOT),
        ProjectBinding("SW-2026-009", SW009_ROOT),
    )


def test_control_root_main_is_bound_to_sw008(
    bindings: tuple[ProjectBinding, ProjectBinding],
) -> None:
    """The only declared root entry resolves to its explicitly named project."""
    assert _binding_for_staged_file("main.py", bindings).project_id == "SW-2026-008"


def test_unknown_root_production_file_remains_rejected(
    bindings: tuple[ProjectBinding, ProjectBinding],
) -> None:
    """The mapping must not permit arbitrary root-level Python files."""
    with pytest.raises(StagedSnapshotError, match="归属未知或不唯一"):
        _binding_for_staged_file("unregistered_root.py", bindings)


def test_nested_project_path_uses_its_directory_binding(
    bindings: tuple[ProjectBinding, ProjectBinding],
) -> None:
    """Existing directory-based project attribution remains unchanged."""
    path = f"{SW009_ROOT}/src/main.py"
    assert _binding_for_staged_file(path, bindings).project_id == "SW-2026-009"


def test_control_root_mapping_rejects_unknown_project_id(
    bindings: tuple[ProjectBinding, ProjectBinding], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed mapping cannot create an unregistered project attribution."""
    monkeypatch.setitem(CONTROL_ROOT_FILE_BINDINGS, "main.py", "SW-9999-999")
    with pytest.raises(StagedSnapshotError, match="归属未知或不唯一"):
        _binding_for_staged_file("main.py", bindings)
