"""D-107a: ``main.py gate`` command line."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

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


def test_plan_preview_reports_tier_reasons_executors_and_next_step() -> None:
    result = CliRunner().invoke(cli, ["gate", "plan", "--worktree", str(_repo_top()), "--preview"])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)
    assert preview["tier"] in {"L1", "L2", "L3"}
    assert isinstance(preview["groups"], list)
    assert isinstance(preview["reasons"], list) and preview["reasons"]
    assert isinstance(preview["executors"], list)
    assert preview["next_step"]
    assert preview["base"] and preview["commit"]


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
    from auto_pm.ui.cli import gate as gate_module

    order: list[str] = []

    def require_heavy(label: str) -> str:
        order.append(f"arm:{label}")
        return ""

    monkeypatch.setattr(gate_module, "require_for_heavy_job", require_heavy)
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


def test_gate_refuses_to_start_a_heavy_job_when_the_memory_gate_has_no_headroom(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from auto_pm.application.core.gate_precheck_service import PrecheckService
    from auto_pm.application.core.memory_gate_arming import MemoryPreflightRefusedError
    from auto_pm.ui.cli import gate as gate_module

    def refuse(_label: str) -> str:
        raise MemoryPreflightRefusedError("拒绝启动：内存不足")

    monkeypatch.setattr(gate_module, "require_for_heavy_job", refuse)
    ran: list[str] = []
    monkeypatch.setattr(PrecheckService, "run", lambda *_a, **_k: ran.append("run"))

    result = CliRunner().invoke(cli, ["gate", "precheck", "--worktree", str(tmp_path)])

    assert result.exit_code == 2
    assert "拒绝启动" in result.output
    assert ran == []



def _gate_run_with_low_memory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *extra: str) -> tuple[Result, dict[str, int]]:
    """``gate run --jobs 3`` over a stand-in tree on a machine whose memory carries one worker; the runner records each group's time limit."""

    from auto_pm.application.core import gate_run_service as service_module
    from auto_pm.ui.cli import gate as gate_module

    timeouts: dict[str, int] = {}

    def runner(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, timeout: int) -> int:
        group = next(g for g in service_module.GROUPS if g.name == log.stem)
        timeouts[log.stem] = timeout
        log.write_text(
            f"{group.min_cases + 5} passed{f', {group.deselected} deselected' if group.deselected else ''} in 4.20s\n", encoding="utf-8"
        )
        return 0

    def service(**kwargs: Any) -> Any:
        return service_module.GateRunService(
            runner=runner, available_memory=lambda: 5 * 2**30, preflight=lambda _python, _worktree: ([], []), **kwargs
        )

    clean = service_module.TreeState(commit="c" * 40, dirty=False, ignored_code=())
    monkeypatch.setattr(gate_module, "require_runtime_identity_for_workspace", lambda _ctx, candidate_release="": None)
    monkeypatch.setattr(gate_module, "require_for_heavy_job", lambda _label: "")
    monkeypatch.setattr(gate_module, "GateRunService", service)
    monkeypatch.setattr(service_module, "tree_state", lambda _worktree, _project: clean)
    monkeypatch.setattr(service_module, "project_dir_in", lambda worktree: worktree)
    (tmp_path / ".git").mkdir()
    (tmp_path / "tests").mkdir()
    result = CliRunner().invoke(cli, ["gate", "run", "--worktree", str(tmp_path), "--out", str(tmp_path / "out"), "--jobs", "3", *extra])
    return result, timeouts


def test_d235_gate_run_says_at_once_that_a_group_was_lowered_and_how_long_it_may_now_take(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from auto_pm.application.core.gate_run_service import GROUPS

    result, timeouts = _gate_run_with_low_memory(monkeypatch, tmp_path)

    parallel = [g.name for g in GROUPS if g.parallel]
    assert result.exit_code == 0, result.output
    assert {timeouts[name] for name in parallel} == {540 * 60}  # three workers asked, one given: three times the 180 minutes
    assert {timeouts[name] for name in timeouts if name not in parallel} == {180 * 60}
    for name in parallel:
        assert f"⚠ 组 {name}：可用内存不足，--jobs 从 3 降到 1（当时可用物理内存 5.0 GiB），本组超时放大到 540 分钟" in result.output
    record = json.loads((tmp_path / "out" / "gate_summary.json").read_text(encoding="utf-8"))
    assert record["results"][parallel[0]]["timeout_seconds"] == 540 * 60


def test_d235_gate_run_with_require_full_jobs_stops_with_exit_one_and_says_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exit 1 (a round that is not a pass), not 2 (could not start): earlier serial groups may already have run."""

    from auto_pm.application.core.gate_run_service import GROUPS

    result, timeouts = _gate_run_with_low_memory(monkeypatch, tmp_path, "--require-full-jobs")

    names = [g.name for g in GROUPS]
    refused = next(g.name for g in GROUPS if g.parallel)
    assert result.exit_code == 1, result.output
    assert list(timeouts) == names[: names.index(refused)]
    assert f"REFUSED {refused}" in result.output
    assert "请求 --jobs 3，需要可用物理内存至少 9.0 GiB，当时只有 5.0 GiB" in result.output
    assert "总判定 FAIL" in result.output and "--require-full-jobs" in result.output
    record = json.loads((tmp_path / "out" / "gate_summary.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "FAIL" and record["results"][refused]["verdict"] == "REFUSED"
    assert set(record["results"]) == set(names[: names.index(refused) + 1])  # later groups are absent, not shown as anything


def test_gate_managed_commands_forward_full_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.application.core import gate_task_service as service_module
    from auto_pm.application.core.gate_task_service import GateCandidate
    from auto_pm.infrastructure.gate_task_store import GateAttempt
    from auto_pm.ui.cli import gate as gate_module

    calls: list[tuple[str, bool]] = []
    attempt = GateAttempt(
        id="0" * 32,
        key='{"base":"' + "c" * 40 + '","commit":"' + "a" * 40 + '","manifest":"' + "d" * 64 + '","policy":"gate-full-v1","tree":"' + "b" * 40 + '"}',
        number=1,
        backend="github",
        state="passed",
        handle="42",
        detail="ok",
        approval="",
    )

    class StubService:
        def start(self, cand: GateCandidate) -> GateAttempt:
            calls.append(("start", cand.tier == "L3"))
            return attempt

        def current(self, cand: GateCandidate) -> GateAttempt:
            calls.append(("current", cand.tier == "L3"))
            return attempt

        def retry(self, task_id: str, cand: GateCandidate, **_kw: object) -> GateAttempt:
            calls.append((f"retry:{task_id}", cand.tier == "L3"))
            return attempt

    def fake_from_worktree(_root: Path, _wt: Path, *, full: bool = False) -> GateCandidate:
        return GateCandidate(
            "a" * 40,
            "b" * 40,
            "c" * 40,
            "d" * 64,
            "gate-full-v1" if full else "gate-l2-v1",
            tier="L3" if full else "L2",
            groups=() if full else ("application",),
        )

    monkeypatch.setattr(gate_module, "require_runtime_identity_for_workspace", lambda _ctx: None)
    monkeypatch.setattr(gate_module, "_shared_gate", lambda _ctx, *_a: (tmp_path, StubService()))
    monkeypatch.setattr(service_module.GateCandidate, "from_worktree", classmethod(lambda cls, r, w, *, full=False: fake_from_worktree(r, w, full=full)))

    wt = tmp_path / "wt"
    wt.mkdir()
    runner = CliRunner()
    assert runner.invoke(cli, ["gate", "start", "--worktree", str(wt)]).exit_code == 0
    assert runner.invoke(cli, ["gate", "start", "--worktree", str(wt), "--full"]).exit_code == 0
    assert runner.invoke(cli, ["gate", "status", "--worktree", str(wt), "--full"]).exit_code == 0
    assert runner.invoke(cli, ["gate", "retry", "0" * 32, "--worktree", str(wt), "--full"]).exit_code == 0
    assert calls == [("start", False), ("start", True), ("current", True), (f"retry:{'0' * 32}", True)]
