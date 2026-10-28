"""TD-SW008-214: template, doc and prototype commands that rewrite a project's files refuse a runtime-identity conflict first."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import doc as doc_cli
from auto_pm.ui.cli import prototype as prototype_cli
from auto_pm.ui.cli import template as template_cli
from auto_pm.ui.cli.doc import doc_group
from auto_pm.ui.cli.prototype import prototype_cmd
from auto_pm.ui.cli.template import template_group

# command -> (guarded?, why not)
DOC = {"inject": True, "refresh": True, "sync": False, "check": False}
PROTOTYPE = {"bundle": True, "archive": True, "init": True, "check": False}
TEMPLATE = {"update": True, "list": False}
# doc sync and doc check work on the cockpit's own code and docs (no project id); prototype check and template list read.


def test_every_command_of_these_groups_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert set(doc_group.commands) == set(DOC)
    assert set(prototype_cmd.commands) == set(PROTOTYPE)
    assert set(template_group.commands) == set(TEMPLATE)


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __getattr__(self, name: str) -> object:
        self._touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


class _Projects:
    def __init__(self, *_a: object, **_k: object) -> None: ...

    def get_project(self, _project_id: str) -> SimpleNamespace:
        return SimpleNamespace(path="/nowhere", stack="plc", project_id="P-1")


def _obj(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(control_root=tmp_path, workspace_root=str(tmp_path), templates_dir=str(tmp_path))


def _refuse(asked: list[str]):  # noqa: ANN202
    def refuse(_ctx: click.Context, project: str) -> None:
        asked.append(project)
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    return refuse


def test_template_update_is_refused_before_the_template_is_applied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked: list[str] = []
    touched: list[str] = []
    monkeypatch.setattr(template_cli, "require_runtime_identity", _refuse(asked))
    monkeypatch.setattr(template_cli, "ProjectService", _Projects)
    monkeypatch.setattr(template_cli, "TemplateService", lambda *_a, **_k: _Untouchable(touched))
    result = CliRunner().invoke(template_group, ["update", "P-1"], obj=_obj(tmp_path))
    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert asked == ["P-1"]
    assert touched == []


@pytest.mark.parametrize(("command", "service"), [("inject", "DocInjectService"), ("refresh", "DocRefreshService")])
def test_doc_writers_are_refused_but_a_dry_run_is_not_asked(
    command: str, service: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[str] = []
    touched: list[str] = []
    monkeypatch.setattr(doc_cli, "require_runtime_identity", _refuse(asked))
    monkeypatch.setattr(doc_cli, "ProjectService", _Projects)
    monkeypatch.setattr(doc_cli, service, lambda *_a, **_k: _Untouchable(touched))
    refused = CliRunner().invoke(doc_group, [command, "P-1"], obj=_obj(tmp_path))
    assert refused.exit_code != 0
    assert "已拒绝写入" in refused.output
    assert asked == ["P-1"]
    assert touched == []
    asked.clear()
    CliRunner().invoke(doc_group, [command, "P-1", "--dry-run"], obj=_obj(tmp_path))
    assert asked == []


@pytest.mark.parametrize(
    ("command", "extra"), [("bundle", []), ("archive", ["--version", "V1"]), ("init", [])]
)
def test_prototype_writers_are_refused_before_the_service_is_used(
    command: str, extra: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[str] = []
    touched: list[str] = []
    monkeypatch.setattr(prototype_cli, "require_runtime_identity", _refuse(asked))
    monkeypatch.setattr(prototype_cli, "PrototypeService", lambda *_a, **_k: _Untouchable(touched))
    result = CliRunner().invoke(prototype_cmd, [command, "--pid", "P-1", *extra], obj=_obj(tmp_path))
    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert asked == ["P-1"]
    assert touched == []
