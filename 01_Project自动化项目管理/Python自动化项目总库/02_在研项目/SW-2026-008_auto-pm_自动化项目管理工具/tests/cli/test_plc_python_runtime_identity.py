"""TD-SW008-214: plc / python write commands: ordinary writes refuse a runtime-identity conflict, repairs only warn."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import plc as plc_cli
from auto_pm.ui.cli import python as python_cli
from auto_pm.ui.cli.plc import plc_group
from auto_pm.ui.cli.python import python_group

# Refuse on a conflict (formal project assets are written).
PLC_REFUSE = {"promote", "ingest", "standardize"}
# Repairs: they mend a broken project, so a conflict only warns.
PLC_WARN = {"repair", "check"}
PLC_OTHER = {"init", "docs"}  # init builds a new project (no identity yet); docs is its own group (read/generate, no project write path here)
PYTHON_WARN = {"repair"}
PYTHON_OTHER = {"init", "check"}


def test_every_plc_and_python_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert set(plc_group.commands) == PLC_REFUSE | PLC_WARN | PLC_OTHER
    assert set(python_group.commands) == PYTHON_WARN | PYTHON_OTHER


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


CASES = (
    ("promote", ["P-1"]),
    ("ingest", ["--src", "x", "--pid", "P-1"]),
    ("standardize", ["P-1", "--apply"]),
)


@pytest.mark.parametrize(("command", "args"), CASES, ids=[case[0] for case in CASES])
def test_a_refused_identity_stops_the_plc_write(
    command: str, args: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[str] = []
    touched: list[str] = []
    monkeypatch.setattr(plc_cli, "require_runtime_identity", _refuse(asked))
    monkeypatch.setattr(plc_cli, "ProjectService", _Projects)
    monkeypatch.setattr(plc_cli, "PlcService", lambda *_a, **_k: _Untouchable(touched))
    result = CliRunner().invoke(plc_group, [command, *args], obj=_obj(tmp_path))
    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert asked == ["P-1"]
    assert touched == []


def test_preview_modes_do_not_ask_the_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked: list[str] = []
    touched: list[str] = []
    monkeypatch.setattr(plc_cli, "require_runtime_identity", _refuse(asked))
    monkeypatch.setattr(plc_cli, "warn_runtime_identity", lambda _ctx, project: asked.append(project))
    monkeypatch.setattr(plc_cli, "ProjectService", _Projects)
    monkeypatch.setattr(plc_cli, "PlcService", lambda *_a, **_k: _Untouchable(touched))
    for args in (["standardize", "P-1"], ["repair", "P-1", "--dry-run"]):
        CliRunner().invoke(plc_group, args, obj=_obj(tmp_path))
    assert asked == []


def test_repairs_only_warn_and_still_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    warned: list[str] = []
    touched: list[str] = []
    monkeypatch.setattr(plc_cli, "warn_runtime_identity", lambda _ctx, project: warned.append(project))
    monkeypatch.setattr(plc_cli, "ProjectService", _Projects)
    monkeypatch.setattr(plc_cli, "PlcService", lambda *_a, **_k: _Untouchable(touched))
    CliRunner().invoke(plc_group, ["repair", "P-1"], obj=_obj(tmp_path))
    assert warned == ["P-1"]
    assert touched == ["repair"]  # the repair itself was still attempted


def test_python_repair_only_warns_and_still_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    warned: list[str] = []
    monkeypatch.setattr(python_cli, "warn_runtime_identity", lambda _ctx, project: warned.append(project))

    class _PyProjects:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def get_project(self, _project_id: str) -> SimpleNamespace:
            return SimpleNamespace(path="/nowhere", stack="python", project_id="P-1")

    monkeypatch.setattr(python_cli, "ProjectService", _PyProjects)
    CliRunner().invoke(python_group, ["repair", "P-1"], obj=_obj(tmp_path))
    CliRunner().invoke(python_group, ["repair", "P-1", "--dry-run"], obj=_obj(tmp_path))
    assert warned == ["P-1"]


def test_plc_docs_writes_are_refused_but_previews_and_isolated_copies_are_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:

    from auto_pm.ui.cli.plc import docs as docs_cli
    from auto_pm.ui.cli.plc.docs import docs_group

    assert set(docs_group.commands) == {"check", "sync", "confirm", "plan"}  # check reads; the other three can write
    asked: list[str] = []
    calls: list[str] = []
    monkeypatch.setattr(docs_cli, "require_runtime_identity", _refuse(asked))
    monkeypatch.setattr(docs_cli, "ProjectService", _Projects)

    def recorder(name: str):  # noqa: ANN202
        def call(*_a: object, **_k: object) -> None:
            calls.append(name)
            raise RuntimeError("stop here")  # CliRunner turns this into a non-zero exit; only the call matters

        return call

    monkeypatch.setattr(docs_cli.dc, "sync_project", recorder("sync"))
    monkeypatch.setattr(docs_cli.dc, "confirm_project", recorder("confirm"))
    plan = ["plan", "P-1", "--start", "2026-01-01", "--type", docs_cli.cp.MAIN_TYPES[0], "--scale", "单机", "--write"]
    for args in (["sync", "P-1"], ["confirm", "P-1"], plan):
        result = CliRunner().invoke(docs_group, args, obj=_obj(tmp_path))
        assert result.exit_code != 0
        assert "已拒绝写入" in result.output
    assert asked == ["P-1", "P-1", "P-1"]
    assert calls == []

    asked.clear()
    CliRunner().invoke(docs_group, ["sync", "P-1", "--dry-run"], obj=_obj(tmp_path))
    CliRunner().invoke(docs_group, ["confirm", "--project-path", str(tmp_path)], obj=_obj(tmp_path))
    assert asked == []
    assert calls == ["sync", "confirm"]  # the preview and the isolated copy did run


def test_ingest_stage_only_does_not_ask_the_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--stage-only fills only the isolated .ingest_staging area, so a conflict must not stop it."""

    asked: list[str] = []
    monkeypatch.setattr(plc_cli, "require_runtime_identity", _refuse(asked))

    class _Projects:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def get_project(self, project_id: str) -> SimpleNamespace:
            return SimpleNamespace(path=str(tmp_path / project_id))

    monkeypatch.setattr(plc_cli, "ProjectService", _Projects)
    monkeypatch.setattr(
        "auto_pm.application.plc.ingest_service.PlcIngestService",
        lambda *_a, **_k: SimpleNamespace(
            ingest_to_staging=lambda **_kw: SimpleNamespace(total_variables=0, total_alarms=0, total_servos=0, total_ios=0)
        ),
    )
    result = CliRunner().invoke(plc_group, ["ingest", "--src", "x", "--pid", "P-1", "--stage-only"], obj=_obj(tmp_path))
    assert asked == []
    assert "已拒绝写入" not in result.output
    assert result.exit_code == 0


def test_plc_docs_plan_on_an_isolated_copy_does_not_ask_the_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.ui.cli.plc import docs as docs_cli
    from auto_pm.ui.cli.plc.docs import docs_group

    asked: list[str] = []
    monkeypatch.setattr(docs_cli, "require_runtime_identity", _refuse(asked))
    args = ["plan", "P-1", "--project-path", str(tmp_path), "--start", "2026-01-01", "--type", docs_cli.cp.MAIN_TYPES[0], "--scale", "单机", "--write"]
    CliRunner().invoke(docs_group, args, obj=_obj(tmp_path))
    assert asked == []
