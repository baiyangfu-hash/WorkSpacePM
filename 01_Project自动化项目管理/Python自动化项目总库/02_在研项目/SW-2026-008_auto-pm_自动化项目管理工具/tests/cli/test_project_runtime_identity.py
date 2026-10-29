"""TD-SW008-214: project commands that rewrite an existing project refuse a runtime-identity conflict before they write."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import project as project_cli
from auto_pm.ui.cli.project import project_group

# Rewrite an existing project: guarded.
GUARDED = {"edit", "snapshot", "hooks install", "hooks uninstall"}
# Bootstrap the project anchor or the registry entry itself (identity cannot exist yet), or carry their own approval
# gate and recycle area (delete: a broken project must still be removable).  retrofit is guarded once the anchor
# (.copier-answers.yml) exists (TD-230); with no anchor it is the command that builds it.
BOOTSTRAP_OR_SELF_GATED = {"create", "import", "register", "retrofit", "delete"}
READ_ONLY = {"list", "show", "hooks status"}


def _all_commands() -> set[str]:
    names: set[str] = set()
    for name, command in project_group.commands.items():
        if isinstance(command, click.Group):
            names |= {f"{name} {sub}" for sub in command.commands}
        else:
            names.add(name)
    return names


def test_every_project_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert _all_commands() == GUARDED | BOOTSTRAP_OR_SELF_GATED | READ_ONLY


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __getattr__(self, name: str) -> object:
        self._touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


class _Projects:
    """Finds the project; any write method is a failure of the test."""

    touched: list[str]

    def __init__(self, *_a: object, **_k: object) -> None: ...

    def get_project(self, _project_id: str) -> SimpleNamespace:
        return SimpleNamespace(path="/nowhere", stack="plc", project_id="P-1")

    def __getattr__(self, name: str) -> object:
        _Projects.touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


CASES = (
    ("edit", ["P-1", "--phase", "x"]),
    ("snapshot", ["P-1"]),
    ("hooks install", ["P-1"]),
    ("hooks uninstall", ["P-1"]),
)


@pytest.mark.parametrize(("command", "args"), CASES, ids=[case[0] for case in CASES])
def test_a_refused_identity_stops_the_command_before_a_write(
    command: str, args: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[str] = []
    _Projects.touched = []

    def refuse(_ctx: click.Context, project: str) -> None:
        asked.append(project)
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    monkeypatch.setattr(project_cli, "require_runtime_identity", refuse)
    monkeypatch.setattr(project_cli, "ProjectService", _Projects)

    result = CliRunner().invoke(
        project_group, [*command.split(), *args], obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    )

    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert asked == ["P-1"]
    assert [name for name in _Projects.touched if name.startswith(("update", "install", "uninstall"))] == []


def test_snapshot_dry_run_and_hooks_status_stay_reads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked: list[str] = []
    _Projects.touched = []
    monkeypatch.setattr(project_cli, "require_runtime_identity", lambda _ctx, project: asked.append(project))
    monkeypatch.setattr(project_cli, "ProjectService", _Projects)
    for args in (["snapshot", "P-1", "--dry-run"], ["hooks", "status", "P-1"]):
        CliRunner().invoke(project_group, args, obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path))
    assert asked == []


def _retrofit_projects(project_dir: Path) -> type:
    class Projects:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def get_project(self, _project_id: str) -> SimpleNamespace:
            return SimpleNamespace(
                path=str(project_dir), stack="software", project_id="P-1", name="n", description="", version="1.0.0"
            )

    return Projects


def test_retrofit_with_an_existing_anchor_refuses_a_runtime_identity_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    anchor = project_dir / ".copier-answers.yml"
    anchor.write_text("project_id: P-1\n", encoding="utf-8")
    asked: list[str] = []

    def refuse(_ctx: click.Context, project: str) -> None:
        asked.append(project)
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    monkeypatch.setattr(project_cli, "require_runtime_identity", refuse)
    monkeypatch.setattr(project_cli, "ProjectService", _retrofit_projects(project_dir))

    result = CliRunner().invoke(
        project_group, ["retrofit", "P-1"], obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    )

    assert result.exit_code != 0 and "已拒绝写入" in result.output
    assert asked == ["P-1"]
    assert anchor.read_text(encoding="utf-8") == "project_id: P-1\n"


def test_retrofit_without_an_anchor_still_builds_it_and_does_not_ask_for_an_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    asked: list[str] = []
    monkeypatch.setattr(project_cli, "require_runtime_identity", lambda _ctx, project: asked.append(project))
    monkeypatch.setattr(project_cli, "ProjectService", _retrofit_projects(project_dir))

    result = CliRunner().invoke(
        project_group, ["retrofit", "P-1"], obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    )

    assert result.exit_code == 0, result.output
    assert (project_dir / ".copier-answers.yml").is_file()
    assert asked == []
