"""TD-SW008-074: ``pm recover`` tells, in plain words, whether a RUNNING Run's executor is still there; ``--apply`` settles it only when it is gone.

Real ledger, real child process. The command must (1) say the right thing for a live process, a killed one and a reused
pid, (2) never change the ledger without ``--apply`` and never touch the process, (3) refuse a Run that is not RUNNING, and
(4) end every answer with what to do next, so a reader that has never seen the cockpit still knows. ``--apply`` writes
exactly one FAILED/EXECUTOR_LOST transition, only for a gone process, only with the holder's lease.
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

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
    StartedRunLookupError,
)
from auto_pm.application.core.execution_recovery_status import RecoveryStatus, RecoveryVerdict
from auto_pm.contracts.continuity import RunState
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.infrastructure import process_probe
from auto_pm.ui.cli import pm as pm_module
from auto_pm.ui.cli import pm_recover
from tests.core.test_continuity_execution_service import Clock, _services, _start, _start_evidence

SUPPORTED = sys.platform == "win32" or sys.platform.startswith("linux")
pytestmark = [
    pytest.mark.skipif(not SUPPORTED, reason="the process probe observes Windows and Linux only"),
    # these ledgers have no registered project anchor; the guard itself is covered in test_runtime_identity_guard.py
    pytest.mark.usefixtures("identity_guard_off"),
]


@pytest.fixture
def child() -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    yield process
    if process.poll() is None:
        process.kill()
    process.wait(30)


def _running_run(root: Path, pid: int, started_at: datetime, *, lease_is_live: bool = False) -> Any:
    """A ledger whose RUN-001 is RUNNING with ``pid`` recorded as its executor.

    The command reads the real clock, so a lease is only live for it when the ledger was written at "now"; the default
    (a fixed September clock) leaves an expired lease, which is what an overnight restart looks like.
    """
    clock = Clock()
    if lease_is_live:
        clock.value = datetime.now(UTC)
    _, service = _services(root, clock)
    _start(service)
    _start_evidence(service, evidence=ExecutionStartEvidence(process_id=pid, session_id="session-td074", started_at=started_at))
    return service


def _events(root: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return conn.execute("SELECT event_id, event_type, aggregate_id FROM events ORDER BY event_id").fetchall()


def _recover(root: Path, *args: str) -> Any:
    return CliRunner().invoke(pm_recover.recover_pm, list(args), obj=SimpleNamespace(workspace_root=root, control_root=root))


def test_a_live_executor_is_reported_alive_and_nothing_is_changed(tmp_path: Path, child: subprocess.Popen[bytes]) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC))
    before = _events(tmp_path)

    result = _recover(tmp_path, "--run-id", "RUN-001")

    assert result.exit_code == 0, result.output
    assert "结论: ALIVE" in result.output
    assert "下一步: 什么都不用敲" in result.output
    assert "先别自己开新 Run" not in result.output
    assert "--apply" not in result.output
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
    assert "先别自己开新 Run" in result.output
    assert "pm recover --run-id RUN-001 --apply --lease-wallet" in result.output
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
    assert "现在是 READY，已经不在运行" in result.output and "不用对账" in result.output
    assert "python main.py pm orient" in result.output
    assert "原样报告用户" not in result.output  # a finished Run is not a ledger fault: do not alarm the reader
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
        (RecoveryVerdict.ALIVE, "什么都不用敲", "--apply"),
        (RecoveryVerdict.UNKNOWN, "什么都不要改", "--apply"),
        (RecoveryVerdict.DEAD, "--apply --lease-wallet", "什么都不用敲"),
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
    # a container or another system user cannot see the executor's process either: the same false "gone" (review 505 a)
    assert "容器" in text and "另一个系统用户" in text and "不要 --apply" in text


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


# ---- --apply -------------------------------------------------------------------------------------------------------------

TOKEN_ENV = "TD074_LEASE_TOKEN"


def _apply(root: Path, *args: str, token: str | None = "lease-secret", monkeypatch: pytest.MonkeyPatch | None = None) -> Any:
    if token is not None and monkeypatch is not None:
        monkeypatch.setenv(TOKEN_ENV, token)
    token_args = ["--lease-token-env", TOKEN_ENV] if token is not None else []
    return _recover(root, *args, "--apply", *token_args)


def _last_failure(service: Any) -> Any:
    activities = service._store.list_run_activities("RUN-001")
    return activities[-1].failure


@pytest.mark.parametrize("by", ["--run-id", "--operation-id"])
def test_apply_settles_a_dead_executor_as_executor_lost_and_only_that(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch, by: str
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)
    before = _events(tmp_path)
    value = "RUN-001"
    if by == "--operation-id":
        # the operation id only matters for finding the Run; reuse the same trusted lookup without a real dispatch
        monkeypatch.setattr(
            ContinuityExecutionService,
            "resolve_started_run",
            lambda self, operation_id: (SimpleNamespace(run_id="RUN-001"), *self.resolve_started_run_by_run_id("RUN-001")),
        )
        value = "OP-1"

    result = _apply(tmp_path, by, value, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "已把 RUN-001 在账上记为失败" in result.output and "EXECUTOR_LOST" in result.output
    assert "没有动工位里的任何文件，也没有开新 Run" in result.output
    assert " MST" in result.output and "+00:00" not in result.output  # the evidence lines are in MST too
    # the failure record keeps only the code, so the evidence is printed in full for the change record (review 505 b)
    assert "请把以下 4 行贴进这个 Run 的变更单或报告" in result.output
    for label in ("账本记的进程号:", "账本记的启动时刻:", "这台电脑观察到的进程创建时刻:", "判定结论: DEAD"):
        assert label in result.output
    assert f"账本记的进程号: {child.pid}" in result.output
    after = _events(tmp_path)
    added = set(after) - set(before)
    assert set(before) <= set(after) and len(added) == 1  # exactly one new event, nothing rewritten
    assert next(iter(added))[1] == "RUN_TRANSITIONED"
    assert service._store.get_run("RUN-001").state.value == "FAILED"
    failure = _last_failure(service)
    assert failure is not None and failure.code.value == "EXECUTOR_LOST"


def test_apply_json_says_the_ledger_was_written(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)

    result = _apply(tmp_path, "--run-id", "RUN-001", "--json", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["wrote_ledger"] is True and payload["failure_code"] == "EXECUTOR_LOST" and payload["run_state"] == "FAILED"


def test_apply_on_a_reused_pid_settles_the_run_and_leaves_the_unrelated_process_alone(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC) - timedelta(hours=1), lease_is_live=True)

    result = _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert service._store.get_run("RUN-001").state.value == "FAILED"
    assert child.poll() is None  # the process that now owns the pid is not ours and is not touched


def test_apply_refuses_a_live_executor_and_changes_nothing(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    before = _events(tmp_path)

    result = _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch)

    assert result.exit_code != 0
    assert "已拒绝落账" in result.output and "ALIVE" in result.output and "账本一个字都没改" in result.output
    assert _events(tmp_path) == before
    assert service._store.get_run("RUN-001").state.value == "RUNNING"
    assert child.poll() is None


def test_apply_refuses_when_the_process_cannot_be_judged(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)
    monkeypatch.setattr(process_probe, "observe", lambda pid: None)  # the process table cannot be read
    before = _events(tmp_path)

    result = _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch)

    assert result.exit_code != 0 and "UNKNOWN" in result.output
    assert _events(tmp_path) == before
    assert service._store.get_run("RUN-001").state.value == "RUNNING"


def test_apply_with_a_wrong_token_is_refused_and_changes_nothing(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)
    before = _events(tmp_path)

    result = _apply(tmp_path, "--run-id", "RUN-001", token="not-the-holders-token", monkeypatch=monkeypatch)

    assert result.exit_code != 0 and "已拒绝落账" in result.output and "lease ownership" in result.output
    assert _events(tmp_path) == before
    assert service._store.get_run("RUN-001").state.value == "RUNNING"


def test_apply_with_an_expired_lease_points_at_reclaim_instead_of_forcing(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restart that outlasts the lease: the holder's right to write is gone, so --apply refuses and names the real exit."""
    service = _running_run(tmp_path, child.pid, datetime.now(UTC))  # ledger written in September: the lease ran out long ago
    child.kill()
    child.wait(30)

    result = _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch)

    assert result.exit_code != 0 and "lease 已过期" in result.output and "RECLAIM_EXPIRED_RUN" in result.output
    assert service._store.get_run("RUN-001").state.value == "RUNNING"


def test_a_second_apply_on_a_settled_run_is_refused_calmly(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)
    assert _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch).exit_code == 0
    before = _events(tmp_path)

    result = _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch)

    assert result.exit_code != 0
    assert "现在是 FAILED，已经不在运行" in result.output and "原样报告用户" not in result.output
    assert _events(tmp_path) == before


def test_apply_refuses_a_run_that_is_already_verifying_even_if_its_process_is_gone(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """VERIFYING also has a started process on record, so the lookup accepts it; settling it as lost is still refused."""
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    service.transition_run("RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "to-verifying")
    child.kill()
    child.wait(30)
    before = _events(tmp_path)

    result = _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch)

    assert result.exit_code != 0 and "VERIFYING" in result.output and "只有 RUNNING" in result.output
    assert _events(tmp_path) == before


def test_the_token_options_are_checked_before_anything_is_read(tmp_path: Path) -> None:
    assert _recover(tmp_path, "--run-id", "R-1", "--apply").exit_code == 2
    both = _recover(tmp_path, "--run-id", "R-1", "--apply", "--lease-wallet", "--lease-token-env", "X")
    assert both.exit_code == 2 and "口令来源" in both.output
    without_apply = _recover(tmp_path, "--run-id", "R-1", "--lease-wallet")
    assert without_apply.exit_code == 2 and "只用于 --apply" in without_apply.output


def test_every_failure_code_has_a_cockpit_label() -> None:
    """A new failure category that the cockpit cannot name would show up as a raw code; EXECUTOR_LOST must be labelled."""
    from auto_pm.application.core import pm_cockpit_service
    from auto_pm.contracts.execution_adapter import ExecutionFailureCode

    source = Path(pm_cockpit_service.__file__).read_text(encoding="utf-8", errors="replace")
    for code in ExecutionFailureCode:
        assert f"ExecutionFailureCode.{code.name}:" in source, f"{code.name} 没有驾驶舱显示名"


# ---- refusal wording follows the error's kind, not its text (review 444 P3 x2) -------------------------------------------


def test_plain_refusal_follows_the_kind_even_when_the_technical_text_is_reworded() -> None:
    """Rewording a message in the service must not send a case to another branch: only ``kind`` decides."""
    lookup = StartedRunLookupError
    reworded = "完全不同的措辞"
    not_active = pm_recover.plain_refusal(
        lookup(lookup.NOT_ACTIVE, reworded, run_id="RUN-5", run_state="SUCCEEDED"), run_id="RUN-5", operation_id=""
    )
    assert "RUN-5 现在是 SUCCEEDED，已经不在运行" in not_active and "原样报告用户" not in not_active

    no_operation = pm_recover.plain_refusal(lookup(lookup.NO_SUCH_OPERATION, reworded), run_id="", operation_id="OP-9")
    assert "没有操作编号 OP-9 的派发记录" in no_operation

    no_run = pm_recover.plain_refusal(lookup(lookup.NO_SUCH_RUN, reworded), run_id="RUN-8", operation_id="")
    assert "没有 RUN-8 Run" in no_run

    mismatch = pm_recover.plain_refusal(lookup(lookup.RECORD_MISMATCH, reworded), run_id="RUN-1", operation_id="")
    assert "启动记录对不上" in mismatch and "原样报告用户" in mismatch

    # a plain ledger error (not from the started-run lookup) is the "ledger fault" case
    other = pm_recover.plain_refusal(ContinuityExecutionError("anything"), run_id="RUN-1", operation_id="")
    assert "原样报告用户" in other


def test_the_lookup_raises_typed_errors_for_each_cause(tmp_path: Path, child: subprocess.Popen[bytes]) -> None:
    _, service = _services(tmp_path, Clock())
    _start(service)  # READY

    with pytest.raises(StartedRunLookupError) as missing_run:
        service.resolve_started_run_by_run_id("RUN-NOPE")
    assert missing_run.value.kind == StartedRunLookupError.NO_SUCH_RUN

    with pytest.raises(StartedRunLookupError) as not_active:
        service.resolve_started_run_by_run_id("RUN-001")
    assert (not_active.value.kind, not_active.value.run_state, not_active.value.run_id) == (
        StartedRunLookupError.NOT_ACTIVE,
        "READY",
        "RUN-001",
    )

    with pytest.raises(StartedRunLookupError) as missing_operation:
        service.resolve_started_run("OP-NOPE")
    assert missing_operation.value.kind == StartedRunLookupError.NO_SUCH_OPERATION


def test_the_write_key_names_the_run_and_the_executor_process_so_a_retry_cannot_write_twice(
    tmp_path: Path, child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    started_at = datetime.now(UTC)
    _running_run(tmp_path, child.pid, started_at, lease_is_live=True)
    child.kill()
    child.wait(30)
    keys: list[str] = []
    real = ContinuityExecutionService.transition_run

    def spy(self: ContinuityExecutionService, run_id: str, new_state: RunState, owner_id: str, token: str, key: str, **kw: Any) -> Any:
        keys.append(key)
        return real(self, run_id, new_state, owner_id, token, key, **kw)

    monkeypatch.setattr(ContinuityExecutionService, "transition_run", spy)

    assert _apply(tmp_path, "--run-id", "RUN-001", monkeypatch=monkeypatch).exit_code == 0
    assert keys == [f"executor-lost:RUN-001:{child.pid}:{started_at.isoformat()}"]


# ---- --lease-wallet (the recommended way to give the token; review 505 d) ------------------------------------------------


def _save_wallet(root: Path, service: Any, token: str) -> None:
    from auto_pm.infrastructure import lease_wallet

    lease = service.current_lease("RUN-001")
    lease_wallet.save(root, run_id="RUN-001", owner_id=lease.owner_id, lease_token=token, epoch=1)


def test_apply_with_the_wallet_settles_the_run_using_the_token_saved_there(
    tmp_path: Path, child: subprocess.Popen[bytes]
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)
    _save_wallet(tmp_path, service, "lease-secret")

    result = _recover(tmp_path, "--run-id", "RUN-001", "--apply", "--lease-wallet")

    assert result.exit_code == 0, result.output
    assert service._store.get_run("RUN-001").state.value == "FAILED"


def test_apply_with_the_wallet_uses_the_wallets_token_not_a_fixed_one(
    tmp_path: Path, child: subprocess.Popen[bytes]
) -> None:
    """A wallet that holds a token the ledger does not recognise must be refused: the token really comes from the wallet."""
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)
    _save_wallet(tmp_path, service, "some-other-token")
    before = _events(tmp_path)

    result = _recover(tmp_path, "--run-id", "RUN-001", "--apply", "--lease-wallet")

    assert result.exit_code != 0 and "已拒绝落账" in result.output
    assert _events(tmp_path) == before
    assert service._store.get_run("RUN-001").state.value == "RUNNING"


def test_apply_with_the_wallet_but_no_wallet_entry_is_refused_and_changes_nothing(
    tmp_path: Path, child: subprocess.Popen[bytes]
) -> None:
    service = _running_run(tmp_path, child.pid, datetime.now(UTC), lease_is_live=True)
    child.kill()
    child.wait(30)
    before = _events(tmp_path)

    result = _recover(tmp_path, "--run-id", "RUN-001", "--apply", "--lease-wallet")

    assert result.exit_code != 0 and "已拒绝落账" in result.output and "钱包" in result.output
    assert _events(tmp_path) == before
    assert service._store.get_run("RUN-001").state.value == "RUNNING"
