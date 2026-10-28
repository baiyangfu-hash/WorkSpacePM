"""TD-SW008-214: ``change`` write commands refuse a runtime-identity conflict before they prompt or write."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import change as change_cli
from auto_pm.ui.cli import runtime_identity_guard as guard
from auto_pm.ui.cli.change import change_group

WRITE_COMMANDS = {"create", "edit", "transition"}
NOT_WRITE_COMMANDS = {"list", "show", "verify"}


def test_every_change_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert set(change_group.commands) == WRITE_COMMANDS | NOT_WRITE_COMMANDS


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __getattr__(self, name: str) -> object:
        self._touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


CASES = (
    ("create", ["--pid", "P-1", "--domain", "SCPT", "--nature", "DEF", "--scope", "MODULE", "--applicant", "a", "--background", "b", "--necessity", "n"], "P-1"),
    ("transition", ["CHG-1", "--to", "submitted", "--pid", "P-2"], "P-2"),
    ("edit", ["CHG-1", "--background", "x", "--pid", "P-3"], "P-3"),
)  # fmt: skip


@pytest.mark.parametrize(("command", "args", "project"), CASES, ids=[case[0] for case in CASES])
def test_a_refused_identity_stops_the_command_before_a_prompt_or_a_write(
    command: str, args: list[str], project: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[str] = []
    touched: list[str] = []

    def refuse(_ctx: click.Context, asked_project: str) -> None:
        asked.append(asked_project)
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    monkeypatch.setattr(change_cli, "require_runtime_identity", refuse)
    monkeypatch.setattr(guard, "require_runtime_identity", refuse)
    monkeypatch.setattr(change_cli, "ChangeService", lambda *_a, **_k: _Untouchable(touched))
    monkeypatch.setattr(change_cli, "require_approval_pin", lambda *_a, **_k: touched.append("pin"))

    result = CliRunner().invoke(
        change_group, [command, *args], obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    )

    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert asked == [project]
    assert touched == []


class _Ctx:
    def __init__(self, tmp_path: Path) -> None:
        self.click = click.Context(click.Command("x"), obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path))


def _lookup(monkeypatch: pytest.MonkeyPatch, result: object) -> list[str]:
    asked: list[str] = []

    class _Service:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def get_change_request(self, number: str, project_id: str | None = None) -> object:
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr("auto_pm.domain.change.change_service.ChangeService", _Service)
    monkeypatch.setattr(guard, "require_runtime_identity", lambda _ctx, project: asked.append(project))
    return asked


def test_a_given_project_is_checked_without_looking_the_change_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _lookup(monkeypatch, RuntimeError("must not be called"))
    guard.require_runtime_identity_for_change(_Ctx(tmp_path).click, "CHG-1", "P-9")
    assert asked == ["P-9"]


def test_without_a_project_the_change_order_names_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _lookup(monkeypatch, SimpleNamespace(project_id="P-FROM-CHANGE"))
    guard.require_runtime_identity_for_change(_Ctx(tmp_path).click, "CHG-1", None)
    assert asked == ["P-FROM-CHANGE"]


@pytest.mark.parametrize("result", [None, RuntimeError("ambiguous")], ids=["missing", "unreadable"])
def test_a_change_order_that_cannot_be_found_has_nothing_to_refuse(
    result: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked = _lookup(monkeypatch, result)
    guard.require_runtime_identity_for_change(_Ctx(tmp_path).click, "CHG-1", None)
    assert asked == []


def test_the_approval_pin_is_still_asked_before_the_identity_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Audit 72: a PIN refusal keeps coming first; the identity check follows it and still precedes every write."""

    order: list[str] = []

    def pin(*_a: object, **_k: object) -> None:
        order.append("pin")

    def identity(_ctx: click.Context, _number: str, _project: str | None) -> None:
        order.append("identity")
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    monkeypatch.setattr(change_cli, "require_approval_pin", pin)
    monkeypatch.setattr(change_cli, "require_runtime_identity_for_change", identity)
    monkeypatch.setattr(change_cli, "ChangeService", lambda *_a, **_k: _Untouchable(order))

    result = CliRunner().invoke(
        change_group,
        ["transition", "CHG-1", "--to", "approved", "--pid", "P-1"],
        obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path),
    )

    assert result.exit_code != 0
    assert order == ["pin", "identity"]
