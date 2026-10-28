"""TD-SW008-214: ``ledger reconcile --fix`` refuses a runtime-identity conflict before it writes; the plain report stays a read."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import ledger as ledger_cli
from auto_pm.ui.cli.ledger import ledger_group


def test_every_ledger_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert set(ledger_group.commands) == {"reconcile"}


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __getattr__(self, name: str) -> object:
        self._touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


def _invoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, args: list[str], asked: list[str], touched: list[str]) -> object:
    def refuse(_ctx: click.Context, project: str) -> None:
        asked.append(project)
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    class _Projects:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def find_project_path(self, _project_id: str) -> Path:
            return tmp_path

    monkeypatch.setattr(ledger_cli, "require_runtime_identity", refuse)
    monkeypatch.setattr(ledger_cli, "ProjectService", _Projects)
    monkeypatch.setattr(ledger_cli, "LedgerReconciler", lambda *_a, **_k: _Untouchable(touched))
    return CliRunner().invoke(
        ledger_group, ["reconcile", "P-1", *args], obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    )


def test_fix_is_refused_before_the_ledger_is_touched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked: list[str] = []
    touched: list[str] = []
    result = _invoke(monkeypatch, tmp_path, ["--fix"], asked, touched)
    assert result.exit_code != 0  # type: ignore[attr-defined]
    assert "已拒绝写入" in result.output  # type: ignore[attr-defined]
    assert asked == ["P-1"]
    assert touched == []


def test_the_plain_report_does_not_ask_the_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked: list[str] = []
    touched: list[str] = []
    _invoke(monkeypatch, tmp_path, [], asked, touched)
    assert asked == []
    assert touched == ["reconcile"]
