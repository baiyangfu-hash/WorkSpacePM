"""Lifecycle behavior independent of the invoking agent."""

from pathlib import Path

import pytest

from auto_pm.application.core.gate_run_service import GateRunError
from auto_pm.application.core.gate_task_service import GateCandidate, GateTaskService, Observation
from auto_pm.infrastructure.gate_task_store import GateAttempt, GateTaskStore


class Executor:
    def __init__(self, initial: str = "unknown") -> None:
        self.launches: list[str] = []
        self.state = initial
        self.handle = ""

    def launch(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation:
        self.launches.append(attempt.id)
        return Observation(self.state)

    def inspect(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation:
        return Observation(self.state, self.handle)

    def stop(self, attempt: GateAttempt) -> None:
        self.state = "stopped"


def candidate(base: str = "c" * 40) -> GateCandidate:
    return GateCandidate("a" * 40, "b" * 40, base, "d" * 64, "gate-full-v1")


def test_second_session_recovers_dispatch_without_sending_again(tmp_path: Path) -> None:
    cloud = Executor()
    local = Executor()
    first = GateTaskService(GateTaskStore(tmp_path), cloud, local)
    second = GateTaskService(GateTaskStore(tmp_path), cloud, local)
    attempt = first.start(candidate())
    for session in (first, second):
        assert session.start(candidate()).id == attempt.id
    with pytest.raises(GateRunError, match="无法重试"):
        second.retry(attempt.id, candidate(), local=True, approval="user-confirmation:42")
    cloud.state, cloud.handle = "running", "4321"
    assert second.status(attempt.id).handle == "4321"
    assert second.stop(attempt.id).state == "stopped"
    assert cloud.launches == [attempt.id]


def test_explicit_local_switch_requires_same_candidate_and_confirmation(tmp_path: Path) -> None:
    cloud = Executor("unavailable")
    local = Executor("running")
    service = GateTaskService(GateTaskStore(tmp_path), cloud, local)
    attempt = service.start(candidate())
    with pytest.raises(GateRunError, match="已变更"):
        service.retry(attempt.id, candidate("e" * 40), local=True, approval="user-confirmation:42")
    with pytest.raises(GateRunError, match="用户确认"):
        service.retry(attempt.id, candidate(), local=True)
    new = service.retry(attempt.id, candidate(), local=True, approval="user-confirmation:42")
    assert new.number == 2
    assert new.state == "running"
    assert new.approval == "user-confirmation:42"
    assert service.start(candidate()).id == new.id
    assert local.launches == [new.id]


def test_changed_base_has_no_matching_receipt(tmp_path: Path) -> None:
    service = GateTaskService(GateTaskStore(tmp_path), Executor("passed"), Executor())
    passed = service.start(candidate())
    assert service.current(candidate()) == passed
    assert service.current(candidate("e" * 40)) is None
