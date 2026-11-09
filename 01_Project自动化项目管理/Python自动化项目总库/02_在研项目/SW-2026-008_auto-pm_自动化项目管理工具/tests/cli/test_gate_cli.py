"""D-107a: ``main.py gate`` command line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli


def _repo_top() -> Path:
    here = Path(__file__).resolve()
    return next(p for p in here.parents if (p / ".git").exists())


def test_plan_lists_all_eleven_groups_with_a_cwd_that_has_tests() -> None:
    result = CliRunner().invoke(cli, ["gate", "plan", "--worktree", str(_repo_top())])
    assert result.exit_code == 0, result.output
    plan = json.loads(result.output)
    assert len(plan) == 11 and all((Path(item["cwd"]) / "tests").is_dir() for item in plan)


def test_plan_rejects_an_unknown_group() -> None:
    result = CliRunner().invoke(
        cli, ["gate", "plan", "--worktree", str(_repo_top()), "--only", "nope"]
    )
    assert result.exit_code != 0 and "未知的组" in result.output


def test_judge_on_an_empty_folder_exits_two(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["gate", "judge", str(tmp_path)])
    assert result.exit_code == 2


def _run_gate_with_a_recording_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *extra: str) -> list[str]:
    from auto_pm.application.core.gate_run_service import GateRunError, GateRunService
    from auto_pm.ui.cli import gate as gate_module

    asked: list[str] = []
    monkeypatch.setattr(gate_module, "require_runtime_identity_for_workspace", lambda _ctx, candidate_release="": asked.append(candidate_release))

    def stop(*_args: object, **_kwargs: object) -> None:
        raise GateRunError("stopped for the test")

    monkeypatch.setattr(GateRunService, "run", stop)
    CliRunner().invoke(cli, ["gate", "run", "--worktree", str(tmp_path), "--out", str(tmp_path / "out"), *extra])
    return asked


def test_gate_run_passes_the_named_candidate_release_to_the_identity_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _run_gate_with_a_recording_guard(monkeypatch, tmp_path, "--candidate-release", "1.3.3-cand000") == ["1.3.3-cand000"]


def test_gate_run_without_the_option_asks_for_no_candidate_release(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _run_gate_with_a_recording_guard(monkeypatch, tmp_path) == [""]


def test_d168_gate_run_and_precheck_arm_the_memory_gate_before_the_heavy_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.application.core.gate_precheck_service import PrecheckService
    from auto_pm.application.core.gate_run_service import GateRunError, GateRunService
    from auto_pm.infrastructure import memory_preflight
    from auto_pm.ui.cli import gate as gate_module

    order: list[str] = []
    monkeypatch.setattr(memory_preflight, "arm", lambda label, **_kw: order.append(f"arm:{label}"))
    monkeypatch.setattr(gate_module, "require_runtime_identity_for_workspace", lambda _ctx, candidate_release="": None)

    def stop_run(*_args: object, **_kwargs: object) -> None:
        order.append("run")
        raise GateRunError("stopped for the test")

    def stop_precheck(*_args: object, **_kwargs: object) -> None:
        order.append("precheck")
        raise GateRunError("stopped for the test")

    monkeypatch.setattr(GateRunService, "run", stop_run)
    monkeypatch.setattr(PrecheckService, "run", stop_precheck)
    CliRunner().invoke(cli, ["gate", "run", "--worktree", str(tmp_path), "--out", str(tmp_path / "out")])
    CliRunner().invoke(cli, ["gate", "precheck", "--worktree", str(tmp_path)])

    assert order == ["arm:long-gate", "run", "arm:full-tests", "precheck"]
