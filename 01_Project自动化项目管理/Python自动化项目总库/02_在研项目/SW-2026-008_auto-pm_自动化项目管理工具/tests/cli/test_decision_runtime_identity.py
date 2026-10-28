"""TD-SW008-214: ``decision create`` refuses a runtime-identity conflict after the approval PIN and before any write."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import decision as decision_cli
from auto_pm.ui.cli.decision import decision_group

WRITE_COMMANDS = {"create"}
NOT_WRITE_COMMANDS = {"show", "list"}


def test_every_decision_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert set(decision_group.commands) == WRITE_COMMANDS | NOT_WRITE_COMMANDS


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __getattr__(self, name: str) -> object:
        self._touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


def _invoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, args: list[str]) -> tuple[object, list[str], list[tuple[str, object]]]:
    order: list[str] = []
    asked: list[tuple[str, object]] = []
    touched: list[str] = []

    def refuse(_ctx: click.Context, change_id: str, project_id: object) -> None:
        order.append("identity")
        asked.append((change_id, project_id))
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    monkeypatch.setattr(decision_cli, "require_runtime_identity_for_change", refuse)
    monkeypatch.setattr(decision_cli, "require_approval_pin", lambda *_a, **_k: order.append("pin"))
    monkeypatch.setattr(decision_cli, "DecisionService", lambda *_a, **_k: _Untouchable(touched))
    monkeypatch.setattr(decision_cli, "WorktreePolicyService", lambda *_a, **_k: _Untouchable(touched))
    result = CliRunner().invoke(
        decision_group, ["create", *args], obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    )
    return result, order, asked + [("touched", touched)]


def test_a_refused_identity_stops_decision_create_before_a_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, order, asked = _invoke(monkeypatch, tmp_path, ["--change-id", "CHG-1", "--approver", "u", "--pid", "P-1"])
    assert result.exit_code != 0  # type: ignore[attr-defined]
    assert "已拒绝写入" in result.output  # type: ignore[attr-defined]
    assert asked[0] == ("CHG-1", "P-1")
    assert asked[-1] == ("touched", [])
    assert order == ["pin", "identity"]


def test_without_pid_the_change_order_decides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _result, _order, asked = _invoke(monkeypatch, tmp_path, ["--change-id", "CHG-2", "--approver", "u"])
    assert asked[0] == ("CHG-2", None)
