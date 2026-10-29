"""TD-SW008-214: delivery writes (build, package, archive clean) refuse a runtime-identity conflict first."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import delivery as delivery_cli
from auto_pm.ui.cli import runtime_identity_guard as guard
from auto_pm.ui.cli.delivery import delivery_group

WRITE = {"build", "package", "archive clean"}
READ = {"status", "archive list"}


def _all_commands() -> set[str]:
    names: set[str] = set()
    for name, command in delivery_group.commands.items():
        if isinstance(command, click.Group):
            names |= {f"{name} {sub}" for sub in command.commands}
        else:
            names.add(name)
    return names


def test_every_delivery_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert _all_commands() == WRITE | READ


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __getattr__(self, name: str) -> object:
        self._touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


def _obj(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(control_root=str(tmp_path), workspace_root=str(tmp_path))


CASES = (
    ("build", ["--version", "V1"]),
    ("package", ["--version", "V1"]),
    ("archive", ["clean"]),
)


@pytest.mark.parametrize(("command", "args"), CASES, ids=["build", "package", "archive clean"])
def test_a_refused_identity_stops_the_delivery_write(
    command: str, args: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[object] = []
    touched: list[str] = []

    def refuse(_ctx: click.Context, project_root: object) -> None:
        asked.append(project_root)
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    monkeypatch.setattr(delivery_cli, "require_runtime_identity_for_delivery", refuse)
    monkeypatch.setattr(delivery_cli, "DeliveryService", lambda *_a, **_k: _Untouchable(touched))
    monkeypatch.setattr(delivery_cli, "ArchiveManager", lambda *_a, **_k: _Untouchable(touched))
    result = CliRunner().invoke(delivery_group, [command, *args], obj=_obj(tmp_path))
    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert asked == [None]
    assert touched == []


def test_verify_only_and_dry_run_do_not_ask_the_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked: list[object] = []
    monkeypatch.setattr(delivery_cli, "require_runtime_identity_for_delivery", lambda *_a, **_k: asked.append(1))
    monkeypatch.setattr(delivery_cli, "DeliveryService", lambda *_a, **_k: SimpleNamespace(package=lambda **_kw: {"success": True}))
    monkeypatch.setattr(delivery_cli, "ArchiveManager", lambda *_a, **_k: SimpleNamespace(clean_archives=lambda **_kw: []))
    CliRunner().invoke(delivery_group, ["package", "--version", "V1", "--verify-only"], obj=_obj(tmp_path))
    CliRunner().invoke(delivery_group, ["archive", "clean", "--dry-run"], obj=_obj(tmp_path))
    assert asked == []


def _fake_service(monkeypatch: pytest.MonkeyPatch, conflicts: list[str]) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []

    class _Service:
        _DEFAULT_REGISTRY = Path("registry.json")

        def __init__(self, *_a: object, **_k: object) -> None: ...

        def resolve(self, project_id: str = "", start_path: object = None) -> SimpleNamespace:
            seen.append((project_id, str(start_path)))
            return SimpleNamespace(conflicts=conflicts)

    monkeypatch.setattr(guard, "WorkspaceContextService", _Service)
    return seen


def _registry(tmp_path: Path, controls: list[str]) -> None:
    projects = [
        {"project_id": f"P-{i}", "project_root": f"p{i}", "development_root": f"p{i}", "control_project_id": control,
         "control_pm_session": "x" if control else "", "runtime_root": ""}
        for i, control in enumerate(controls)
    ]
    (tmp_path / "registry.json").write_text(json.dumps({"schema_version": "workspace-registry.v1", "projects": projects}), encoding="utf-8")


def _ctx(tmp_path: Path) -> click.Context:
    return click.Context(click.Command("x"), obj=_obj(tmp_path))


def test_the_workspace_root_is_checked_as_its_control_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _registry(tmp_path, ["", "SYS-1", "SYS-1"])
    seen = _fake_service(monkeypatch, [])
    guard.require_runtime_identity_for_delivery(_ctx(tmp_path), None)
    assert [project for project, _ in seen] == ["SYS-1"]


def test_a_project_root_is_checked_through_its_own_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen = _fake_service(monkeypatch, [])
    guard.require_runtime_identity_for_delivery(_ctx(tmp_path), str(tmp_path / "proj"))
    assert seen == [("", str(tmp_path / "proj"))]


def test_a_conflict_or_an_unreadable_registry_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _registry(tmp_path, ["SYS-1"])
    _fake_service(monkeypatch, ["版本不一致"])
    with pytest.raises(click.ClickException, match="已拒绝写入.*版本不一致"):
        guard.require_runtime_identity_for_delivery(_ctx(tmp_path), None)
    (tmp_path / "registry.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(click.ClickException, match="已拒绝写入"):
        guard.require_runtime_identity_for_delivery(_ctx(tmp_path), None)


def test_a_registry_without_a_control_project_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _registry(tmp_path, ["", ""])
    _fake_service(monkeypatch, [])
    with pytest.raises(click.ClickException, match="没有声明控制项目"):
        guard.require_runtime_identity_for_delivery(_ctx(tmp_path), None)
