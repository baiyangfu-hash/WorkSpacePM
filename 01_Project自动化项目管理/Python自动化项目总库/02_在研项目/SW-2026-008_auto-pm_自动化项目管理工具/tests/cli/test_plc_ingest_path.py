"""``plc ingest`` / ``plc promote`` must work on the project folder the registry knows, never on an invented one.

Before: ``PlcService.resolve_project_path`` did not exist, ``except Exception`` hid that, and every call used
``0100_PLC自动化/<id>`` — a folder that does not exist for a real project (``DJ-2026-009_汇川换型改造``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import plc as plc_cli
from auto_pm.ui.cli.plc import plc_group


class _Recorder:
    calls: list[tuple[str, dict[str, Any]]]

    def __init__(self) -> None:
        self.calls = []

    def factory(self, *_a: object, **_k: object) -> SimpleNamespace:
        def record(name: str) -> Any:
            def call(**kwargs: Any) -> SimpleNamespace:
                self.calls.append((name, kwargs))
                return SimpleNamespace(
                    total_variables=0, total_alarms=0, total_servos=0, total_ios=0, generated_files=[], promoted_files=[]
                )

            return call

        return SimpleNamespace(
            ingest_to_staging=record("ingest_to_staging"),
            ingest_autoshop_project=record("ingest_autoshop_project"),
            promote_staging=record("promote_staging"),
        )


def _wire(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, known: dict[str, Path]) -> _Recorder:
    recorder = _Recorder()

    class _Projects:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def get_project(self, project_id: str) -> SimpleNamespace | None:
            path = known.get(project_id)
            return SimpleNamespace(path=str(path)) if path else None

    monkeypatch.setattr(plc_cli, "ProjectService", _Projects)
    monkeypatch.setattr(plc_cli, "require_runtime_identity", lambda *_a, **_k: None)
    monkeypatch.setattr("auto_pm.application.plc.ingest_service.PlcIngestService", recorder.factory)
    return recorder


def _invoke(tmp_path: Path, args: list[str]) -> Any:
    obj = SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    return CliRunner().invoke(plc_group, args, obj=obj)


@pytest.mark.parametrize(
    ("args", "call"),
    [
        (["ingest", "--src", "x", "--pid", "DJ-1", "--stage-only"], "ingest_to_staging"),
        (["ingest", "--src", "x", "--pid", "DJ-1"], "ingest_autoshop_project"),
        (["promote", "DJ-1"], "promote_staging"),
    ],
)
def test_the_registered_folder_is_used_not_a_guessed_one(
    args: list[str], call: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = tmp_path / "0100_PLC自动化" / "DJ-1_真实名字"
    recorder = _wire(monkeypatch, tmp_path, known={"DJ-1": real})
    result = _invoke(tmp_path, args)
    assert result.exit_code == 0, result.output
    [(name, kwargs)] = recorder.calls
    assert name == call
    assert Path(kwargs["target_project_path"]) == real
    assert not (tmp_path / "0100_PLC自动化" / "DJ-1").exists()


@pytest.mark.parametrize(
    "args",
    [
        ["ingest", "--src", "x", "--pid", "DJ-404", "--stage-only"],
        ["ingest", "--src", "x", "--pid", "DJ-404"],
        ["promote", "DJ-404"],
    ],
)
def test_an_unknown_project_stops_the_command_and_writes_nothing(
    args: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _wire(monkeypatch, tmp_path, known={})
    result = _invoke(tmp_path, args)
    assert result.exit_code == 1
    assert "项目不存在" in result.output
    assert recorder.calls == []
    assert not (tmp_path / "0100_PLC自动化").exists()
