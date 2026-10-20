"""``project register``: one verified entry is appended to the Workspace Registry, nothing else changes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from auto_pm.core.workspace_registry_service import WorkspaceRegistryError, WorkspaceRegistryService
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli

CONTROL = "SYS-2026-001"
CONTROL_SESSION = f"{CONTROL}_WorkspaceGovernance/PM_SESSION_{CONTROL}.md"


def _anchor(project: Path, project_id: str) -> Path:
    project.mkdir(parents=True, exist_ok=True)
    (project / ".copier-answers.yml").write_text(
        f"project_id: {project_id}\nproject_name: {project_id}\nstack: plc\n", encoding="utf-8"
    )
    return project


def _workspace(root: Path, *, runtime_root: str = "") -> Path:
    """A control project and one registered project, written the way the real registry is formatted."""
    control = root / f"{CONTROL}_WorkspaceGovernance"
    control.mkdir()
    (control / f"PM_SESSION_{CONTROL}.md").write_text(f"# {CONTROL}\n", encoding="utf-8")
    _anchor(root / "0100_PLC自动化" / "DJ-2026-005", "DJ-2026-005")
    registry = control / "workspace_registry.json"
    payload = {
        "schema_version": "workspace-registry.v1",
        "projects": [
            {
                "project_id": CONTROL,
                "project_root": control.name,
                "development_root": control.name,
                "control_project_id": "",
                "control_pm_session": "",
                "runtime_root": "",
            },
            {
                "project_id": "DJ-2026-005",
                "project_root": "0100_PLC自动化/DJ-2026-005",
                "development_root": "0100_PLC自动化/DJ-2026-005",
                "control_project_id": CONTROL,
                "control_pm_session": CONTROL_SESSION,
                "runtime_root": runtime_root,
            },
        ],
    }
    registry.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return registry


def _cli(root: Path, *args: str) -> tuple[int, str]:
    result = CliRunner().invoke(cli, ["-w", str(root), *args])
    return result.exit_code, result.output


def test_a_new_template_project_is_registered_and_pm_orient_then_knows_it(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    original = registry.read_bytes()
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)

    code, output = _cli(tmp_path, "pm", "orient", "DJ-2026-009", "--json")
    assert code != 0 and "项目未登记到 Workspace Registry" in output

    code, output = _cli(tmp_path, "project", "register", "DJ-2026-009")
    assert code == 0, output
    assert "项目已登记: DJ-2026-009" in output

    after = registry.read_bytes()
    # The existing entries are kept byte for byte; only the new entry is appended.
    assert after[: original.rindex(b"}\n  ]")] == original[: original.rindex(b"}\n  ]")]
    added = json.loads(after)["projects"][-1]
    assert added == {
        "project_id": "DJ-2026-009",
        "project_root": "0100_PLC自动化/DJ-2026-009",
        "development_root": "0100_PLC自动化/DJ-2026-009",
        "control_project_id": CONTROL,
        "control_pm_session": CONTROL_SESSION,
        "runtime_root": "",
    }

    code, output = _cli(tmp_path, "pm", "orient", "DJ-2026-009", "--json")
    assert code == 0, output
    assert "项目未登记" not in output


def test_registering_twice_changes_nothing(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")
    service = WorkspaceRegistryService(tmp_path)
    assert service.register("DJ-2026-009").written
    before = registry.read_bytes()

    again = service.register("DJ-2026-009")

    assert again.already_registered and not again.written
    assert registry.read_bytes() == before


def test_dry_run_shows_the_entry_and_writes_nothing(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    before = registry.read_bytes()
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")

    code, output = _cli(tmp_path, "project", "register", "DJ-2026-009", "--dry-run")

    assert code == 0, output
    assert "--dry-run" in output and "0100_PLC自动化/DJ-2026-009" in output
    assert registry.read_bytes() == before


def test_an_explicit_path_must_carry_the_same_project_id(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    before = registry.read_bytes()
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")

    code, output = _cli(
        tmp_path, "project", "register", "DJ-2026-010", "--path", "0100_PLC自动化/DJ-2026-009"
    )

    assert code == 1
    assert "项目编号不一致" in output
    assert registry.read_bytes() == before


@pytest.mark.parametrize(
    ("project_id", "relative", "message"),
    [
        ("DJ-2026-005", "0100_PLC自动化/DJ-2026-005-copy", "项目已登记在别的目录"),
        ("DJ-2026-019", "_archive/DJ-2026-019", "不能登记归档"),
        ("DJ-2026-019", "0100_PLC自动化/empty", "缺少项目锚点"),
    ],
)
def test_unsafe_registrations_are_refused_and_the_registry_is_unchanged(
    tmp_path: Path, project_id: str, relative: str, message: str
) -> None:
    registry = _workspace(tmp_path)
    before = registry.read_bytes()
    target = tmp_path / relative
    if relative.endswith("empty"):
        target.mkdir(parents=True)
    else:
        _anchor(target, project_id)

    with pytest.raises(WorkspaceRegistryError, match=message):
        WorkspaceRegistryService(tmp_path).register(project_id, relative)

    assert registry.read_bytes() == before


def test_a_directory_registered_for_another_project_is_refused(tmp_path: Path) -> None:
    registry = _workspace(tmp_path)
    before = registry.read_bytes()
    # The directory of DJ-2026-005 now carries another anchor (for example a copied template).
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-005", "DJ-2026-099")

    with pytest.raises(WorkspaceRegistryError, match="已登记为另一个项目"):
        WorkspaceRegistryService(tmp_path).register("DJ-2026-099", "0100_PLC自动化/DJ-2026-005")

    assert registry.read_bytes() == before


def test_a_registration_that_pm_orient_could_not_resolve_is_rolled_back(tmp_path: Path) -> None:
    # The shared runtime root exists but has no active_release.json, so the resolver refuses the new entry.
    (tmp_path / "00_Infrastructure" / "auto_pm").mkdir(parents=True)
    registry = _workspace(tmp_path, runtime_root="00_Infrastructure/auto_pm")
    before = registry.read_bytes()
    _anchor(tmp_path / "0100_PLC自动化" / "DJ-2026-009", "DJ-2026-009")

    with pytest.raises(WorkspaceRegistryError, match="已恢复原登记表"):
        WorkspaceRegistryService(tmp_path).register("DJ-2026-009")

    assert registry.read_bytes() == before
    assert not registry.with_name(registry.name + ".tmp").exists()
