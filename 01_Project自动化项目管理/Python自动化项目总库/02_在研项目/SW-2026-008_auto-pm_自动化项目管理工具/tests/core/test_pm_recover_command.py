"""TD-SW008-074 step 1: ``pm recover`` tells, in plain words, whether a RUNNING Run's executor is still there, and writes nothing.

Real ledger, real child process. The command must (1) say the right thing for a live process, a killed one and a reused
pid, (2) never change the ledger and never touch the process, (3) refuse a Run that is not RUNNING, and (4) end every
answer with what to do next, so a reader that has never seen the cockpit still knows.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.application.core.execution_recovery_status import RecoveryStatus, RecoveryVerdict
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.ui.cli import pm as pm_module
from auto_pm.ui.cli import pm_recover
from tests.core.test_continuity_execution_service import Clock, _services, _start, _start_evidence

SUPPORTED = sys.platform == "win32" or sys.platform.startswith("linux")
pytestmark = pytest.mark.skipif(not SUPPORTED, reason="the process probe observes Windows and Linux only")


@pytest.fixture
def child() -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    yield process
    if process.poll() is None:
        process.kill()
    process.wait(30)


def _running_run(root: Path, pid: int, started_at: datetime) -> Any:
    """A ledger whose RUN-001 is RUNNING with ``pid`` recorded as its executor."""
    _, service = _services(root, Clock())
    _start(service)
    _start_evidence(service, evidence=ExecutionStartEvidence(process_id=pid, session_id="session-td074", started_at=started_at))
    return service


def _events(root: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return conn.execute("SELECT event_id, event_type, aggregate_id FROM events ORDER BY event_id").fetchall()


def _recover(root: Path, *args: str) -> Any:
    return CliRunner().invoke(pm_recover.recover_pm, list(args), obj=SimpleNamespace(workspace_root=root))


def test_a_live_executor_is_reported_alive_and_nothing_is_changed(tmp_path: Path, child: subprocess.Popen[bytes]) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC))
    before = _events(tmp_path)

    result = _recover(tmp_path, "--run-id", "RUN-001")

    assert result.exit_code == 0, result.output
    assert "结论: ALIVE" in result.output
    assert "下一步: 什么都不用敲" in result.output
    assert "不要自己开新 Run" not in result.output
    assert _events(tmp_path) == before
    assert service._store.get_run("RUN-001").state.value == "RUNNING"
    assert child.poll() is None  # the process was only looked at


def test_a_killed_executor_is_reported_dead_with_the_next_step_in_plain_words(
    tmp_path: Path, child: subprocess.Popen[bytes]
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC))
    child.kill()
    child.wait(30)
    before = _events(tmp_path)

    result = _recover(tmp_path, "--run-id", "RUN-001")

    assert result.exit_code == 0, result.output
    assert "结论: DEAD" in result.output
    assert "现在的情况: 记录里的执行进程已经不在了" in result.output
    assert "不要自己开新 Run" in result.output
    assert "先确认你就在跑执行代理的那台电脑上" in result.output  # on another computer the pid is missing too: a false DEAD
    assert " MST" in result.output and "+00:00" not in result.output  # the user reads MST
    assert "工位里可能留着它没做完的半成品，先别清理" in result.output
    assert _events(tmp_path) == before
    assert service._store.get_run("RUN-001").state.value == "RUNNING"  # reporting does not settle the Run


def test_a_reused_pid_is_reported_and_the_unrelated_process_is_left_alone(
    tmp_path: Path, child: subprocess.Popen[bytes]
) -> None:
    """The ledger says the executor started an hour before the process that now owns this pid was created."""
    _running_run(tmp_path, child.pid, datetime.now(UTC) - timedelta(hours=1))

    result = _recover(tmp_path, "--run-id", "RUN-001")

    assert result.exit_code == 0, result.output
    assert "结论: PID_REUSED" in result.output
    assert "不会去碰它" in result.output
    assert child.poll() is None


def test_json_output_states_that_the_ledger_was_not_written(tmp_path: Path, child: subprocess.Popen[bytes]) -> None:
    _running_run(tmp_path, child.pid, datetime.now(UTC))

    result = _recover(tmp_path, "--run-id", "RUN-001", "--json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["verdict"] == "ALIVE" and payload["run_id"] == "RUN-001" and payload["wrote_ledger"] is False


def test_a_run_that_is_not_running_is_refused_with_its_real_state(tmp_path: Path) -> None:
    _, service = _services(tmp_path, Clock())
    _start(service)  # READY: no executor was ever started

    result = _recover(tmp_path, "--run-id", "RUN-001")

    assert result.exit_code != 0
    assert "现在不在 RUNNING 状态（READY）" in result.output and "不用对账" in result.output
    assert "python main.py pm orient" in result.output
    assert "BLOCKED" not in result.output  # no jargon from recover-status


def test_an_unknown_run_is_refused(tmp_path: Path) -> None:
    _services(tmp_path, Clock())

    result = _recover(tmp_path, "--run-id", "RUN-NOPE")

    assert result.exit_code != 0
    assert "没有 RUN-NOPE" in result.output and "python main.py pm orient" in result.output
    assert "BLOCKED" not in result.output


@pytest.mark.parametrize("args", [[], ["--operation-id", "OP-1", "--run-id", "RUN-001"]])
def test_exactly_one_of_operation_id_and_run_id_is_required(tmp_path: Path, args: list[str]) -> None:
    result = _recover(tmp_path, *args)

    assert result.exit_code == 2
    assert "必须给一个，且只给一个" in result.output


@pytest.mark.parametrize(
    ("verdict", "must_say", "must_not_say"),
    [
        (RecoveryVerdict.ALIVE, "什么都不用敲", "不要自己开新 Run"),
        (RecoveryVerdict.UNKNOWN, "什么都不要改", "已经不在了"),
        (RecoveryVerdict.DEAD, "不要自己开新 Run", "什么都不用敲"),
        (RecoveryVerdict.PID_REUSED, "不会去碰它", "什么都不用敲"),
    ],
)
def test_each_verdict_has_its_own_plain_next_step(verdict: RecoveryVerdict, must_say: str, must_not_say: str) -> None:
    text = pm_recover.plain_report(
        run_id="RUN-9",
        run_state="RUNNING",
        process_id=7,
        status=RecoveryStatus(verdict, "原因"),
        recorded_started_at=datetime(2026, 11, 1, 17, 0, tzinfo=UTC),
        observed_created_at=None,
    )
    assert must_say in text and must_not_say not in text
    assert "现在的情况:" in text and "下一步:" in text
    assert "2026-11-01 10:00:00 MST" in text  # 17:00 UTC is 10:00 MST


@pytest.mark.parametrize("verdict", [RecoveryVerdict.DEAD, RecoveryVerdict.PID_REUSED])
def test_a_gone_process_says_to_check_the_computer_first(verdict: RecoveryVerdict) -> None:
    text = pm_recover.plain_report(
        run_id="RUN-9",
        run_state="RUNNING",
        process_id=7,
        status=RecoveryStatus(verdict, "原因"),
        recorded_started_at=datetime(2026, 11, 1, 17, 0, tzinfo=UTC),
        observed_created_at=None,
    )
    assert "先确认你就在跑执行代理的那台电脑上" in text


def test_the_state_in_the_text_is_the_ledgers_real_state_not_a_fixed_word() -> None:
    """A VERIFYING Run must not be described as RUNNING."""
    for verdict in (RecoveryVerdict.ALIVE, RecoveryVerdict.DEAD):
        text = pm_recover.plain_report(
            run_id="RUN-9",
            run_state="VERIFYING",
            process_id=7,
            status=RecoveryStatus(verdict, "原因"),
            recorded_started_at=datetime(2026, 11, 1, 17, 0, tzinfo=UTC),
            observed_created_at=None,
        )
        assert "VERIFYING" in text and "RUNNING" not in text


def _resume_stub(run_state: str | None) -> Any:
    run = None if run_state is None else SimpleNamespace(run_id="RUN-7", state=SimpleNamespace(value=run_state))
    return SimpleNamespace(
        evidence_id="RESUME-X",
        context=SimpleNamespace(subject_project_id="SW-2026-008", control_project_id="", release_id=""),
        work=None,
        run=run,
        mission_candidates=(),
        next_legal_action="",
        conflicts=(),
        hold_warnings=(),
        intake=SimpleNamespace(is_empty=True),
        read_set=(),
        query=None,
    )


def test_orient_points_a_running_run_at_pm_recover_and_only_that(capsys: pytest.CaptureFixture[str]) -> None:
    pm_module._echo_resume_text(_resume_stub("RUNNING"))
    assert "pm recover --run-id RUN-7" in capsys.readouterr().out

    pm_module._echo_resume_text(_resume_stub("READY"))
    assert "pm recover" not in capsys.readouterr().out

    pm_module._echo_resume_text(_resume_stub(None))
    assert "pm recover" not in capsys.readouterr().out


def test_operation_id_finds_the_run_through_the_dispatch_receipt(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Run in the answer must be the one named by the receipt (a fake dispatch: the receipt lookup is stubbed, the rest is real)."""
    _running_run(tmp_path, child.pid, datetime.now(UTC))
    run = SimpleNamespace(state=SimpleNamespace(value="RUNNING"))
    evidence = ExecutionStartEvidence(process_id=child.pid, session_id="s", started_at=datetime.now(UTC))
    monkeypatch.setattr(
        ContinuityExecutionService,
        "resolve_started_run",
        lambda _self, operation_id: (SimpleNamespace(run_id="RUN-FROM-RECEIPT"), run, evidence),
    )

    result = _recover(tmp_path, "--operation-id", "OP-1")

    assert result.exit_code == 0, result.output
    assert "Run: RUN-FROM-RECEIPT" in result.output and "结论: ALIVE" in result.output


def test_an_unknown_operation_id_is_explained_in_plain_words(tmp_path: Path) -> None:
    _services(tmp_path, Clock())

    result = _recover(tmp_path, "--operation-id", "OP-NOPE")

    assert result.exit_code != 0
    assert "没有操作编号 OP-NOPE 的派发记录" in result.output and "--run-id" in result.output
    assert "BLOCKED" not in result.output


def test_a_start_record_owned_by_someone_else_is_refused(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process on record must belong to the Run's own executor; otherwise we would judge somebody else's process."""
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    _running_run(tmp_path, child.pid, datetime.now(UTC))
    real = ContinuityStore.get_run_started_evidence
    monkeypatch.setattr(
        ContinuityStore, "get_run_started_evidence", lambda self, run_id: ("someone-else", real(self, run_id)[1])
    )

    result = _recover(tmp_path, "--run-id", "RUN-001")

    assert result.exit_code != 0
    assert "启动记录对不上" in result.output and "原样报告用户" in result.output
