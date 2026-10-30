"""TD-SW008-074 step 1: the read-only restart verdict tells a live executor from a dead one and from a reused pid."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core.continuity_execution_service import ContinuityExecutionError
from auto_pm.application.core.execution_recovery_status import (
    START_SKEW,
    RecoveryVerdict,
    judge_started_process,
)
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.contracts.lease_reclaim import ProcessObservation
from auto_pm.infrastructure import process_probe
from auto_pm.ui.cli import pm_recover

NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
SUPPORTED = sys.platform == "win32" or sys.platform.startswith("linux")


def _evidence(started_at: datetime = NOW, pid: int = 4242) -> ExecutionStartEvidence:
    return ExecutionStartEvidence(process_id=pid, session_id="session-1", started_at=started_at)


def test_a_missing_process_is_dead() -> None:
    result = judge_started_process(_evidence(), ProcessObservation(pid_exists=False), None)
    assert result.verdict is RecoveryVerdict.DEAD


def test_an_unreadable_process_table_is_unknown_never_dead() -> None:
    assert judge_started_process(_evidence(), None, None).verdict is RecoveryVerdict.UNKNOWN


def test_a_live_process_without_a_creation_time_is_unknown() -> None:
    result = judge_started_process(_evidence(), ProcessObservation(pid_exists=True), None)
    assert result.verdict is RecoveryVerdict.UNKNOWN


def test_a_naive_creation_time_is_unknown() -> None:
    result = judge_started_process(_evidence(), ProcessObservation(pid_exists=True), datetime(2026, 10, 27, 11, 0))
    assert result.verdict is RecoveryVerdict.UNKNOWN


def test_a_process_created_before_the_recorded_start_is_alive() -> None:
    observation = ProcessObservation(pid_exists=True)
    result = judge_started_process(_evidence(), observation, NOW - timedelta(seconds=3))
    assert result.verdict is RecoveryVerdict.ALIVE


def test_the_skew_boundary_is_inclusive_and_one_microsecond_later_is_a_reused_pid() -> None:
    observation = ProcessObservation(pid_exists=True)
    assert judge_started_process(_evidence(), observation, NOW + START_SKEW).verdict is RecoveryVerdict.ALIVE
    later = NOW + START_SKEW + timedelta(microseconds=1)
    assert judge_started_process(_evidence(), observation, later).verdict is RecoveryVerdict.PID_REUSED


@pytest.mark.parametrize("seconds_later", [3, 30, 200, 86_400])
def test_a_process_created_more_than_the_skew_after_the_recorded_start_is_a_reused_pid(seconds_later: int) -> None:
    """2 秒容差之外（3 秒到一整天）一律判进程号被复用，不会因为“差得不多”被当成原进程。"""
    observation = ProcessObservation(pid_exists=True)
    created = NOW + timedelta(seconds=seconds_later)
    assert judge_started_process(_evidence(), observation, created).verdict is RecoveryVerdict.PID_REUSED


@pytest.mark.parametrize("seconds_before", [3, 3_600, 86_400 * 30])
def test_a_process_created_any_time_before_the_recorded_start_is_alive(seconds_before: int) -> None:
    observation = ProcessObservation(pid_exists=True)
    created = NOW - timedelta(seconds=seconds_before)
    assert judge_started_process(_evidence(), observation, created).verdict is RecoveryVerdict.ALIVE


# 2026-10-27 12:00:00 UTC 的 Windows FILETIME：1970 到 1601 的差 116444736000000000 个 100 纳秒 + Unix 秒数 1793102400 × 10^7
FILETIME_NOW = "134375760000000000"


def test_a_windows_creation_filetime_converts_to_the_exact_utc_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert process_probe.start_time_to_datetime(FILETIME_NOW) == NOW
    assert process_probe.start_time_to_datetime(str(int(FILETIME_NOW) + 15_000_000)) == NOW + timedelta(seconds=1.5)
    assert process_probe.start_time_to_datetime("0") == datetime(1601, 1, 1, tzinfo=UTC)


def test_a_filetime_beyond_the_year_9999_cannot_be_converted(monkeypatch: pytest.MonkeyPatch) -> None:
    """越界不抛错，返回 None（上层报 UNKNOWN，不是崩溃也不是 DEAD）。"""
    monkeypatch.setattr(sys, "platform", "win32")
    assert process_probe.start_time_to_datetime("9" * 30) is None


def test_the_start_time_converter_refuses_input_it_cannot_read() -> None:
    assert process_probe.start_time_to_datetime(None) is None
    assert process_probe.start_time_to_datetime("not-a-number") is None
    assert process_probe.start_time_to_datetime("") is None


@pytest.fixture
def child() -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    yield process
    if process.poll() is None:
        process.kill()
    process.wait(30)


@pytest.mark.skipif(not SUPPORTED, reason="the probe observes Windows and Linux only")
def test_a_real_process_is_alive_then_a_reused_pid_then_dead(child: subprocess.Popen[bytes]) -> None:
    observation = process_probe.observe(child.pid)
    if observation is None or not observation.pid_exists:
        pytest.skip("the process table of this host cannot be read")
    created_at = process_probe.start_time_to_datetime(observation.start_time)
    if created_at is None:
        pytest.skip("this host does not show a process creation time")
    # created a moment ago, so it cannot be later than a start recorded now
    assert abs((datetime.now(UTC) - created_at).total_seconds()) < 300
    started = datetime.now(UTC)
    assert judge_started_process(_evidence(started, child.pid), observation, created_at).verdict is RecoveryVerdict.ALIVE
    # the ledger says the executor started an hour before this pid's current owner was created
    old = _evidence(created_at - timedelta(hours=1), child.pid)
    assert judge_started_process(old, observation, created_at).verdict is RecoveryVerdict.PID_REUSED
    child.kill()
    child.wait(30)
    gone = process_probe.observe(child.pid)
    assert gone is not None and not gone.pid_exists
    assert judge_started_process(_evidence(started, child.pid), gone, None).verdict is RecoveryVerdict.DEAD


class _FakeService:
    def __init__(self, *, evidence: ExecutionStartEvidence | None) -> None:
        self._evidence = evidence

    def resolve_started_run(self, operation_id: str) -> tuple[Any, Any, ExecutionStartEvidence]:
        if self._evidence is None:
            raise ContinuityExecutionError("ExecutionIntent 不存在")
        return SimpleNamespace(run_id="RUN-1"), SimpleNamespace(state=SimpleNamespace(value="RUNNING")), self._evidence


def _invoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, service: _FakeService) -> Any:
    monkeypatch.setattr(pm_recover, "ContinuityExecutionService", lambda root: service)
    return CliRunner().invoke(pm_recover.recover_status_pm, ["--operation-id", "OP-1"], obj=SimpleNamespace(workspace_root=tmp_path))


def test_the_command_reports_a_dead_process_and_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(process_probe, "observe", lambda pid: ProcessObservation(pid_exists=False))
    result = _invoke(monkeypatch, tmp_path, _FakeService(evidence=_evidence()))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["verdict"] == "DEAD"
    assert payload["run_id"] == "RUN-1" and payload["process_id"] == 4242
    assert list(tmp_path.iterdir()) == []


def test_the_command_reports_a_reused_pid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observation = ProcessObservation(pid_exists=True, start_time="1")
    monkeypatch.setattr(process_probe, "observe", lambda pid: observation)
    monkeypatch.setattr(process_probe, "start_time_to_datetime", lambda value: NOW + timedelta(hours=1))
    result = _invoke(monkeypatch, tmp_path, _FakeService(evidence=_evidence()))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["verdict"] == "PID_REUSED"


def test_an_unrecoverable_identity_stops_with_a_clear_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _invoke(monkeypatch, tmp_path, _FakeService(evidence=None))
    assert result.exit_code != 0
    assert "BLOCKED" in result.output
