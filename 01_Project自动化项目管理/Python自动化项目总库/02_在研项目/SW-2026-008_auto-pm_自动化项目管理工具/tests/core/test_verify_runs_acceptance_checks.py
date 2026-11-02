"""``pm verify`` executes the acceptance commands the user approved (CHG-SCPT-2026-472).

Before: ``pm plan --check`` stored the commands and the agent ran them itself, so "done" could be reported without any
check having passed.  Now the verifier runs each one in the Run's worktree and a mismatch refuses verification before any
verified Checkpoint exists.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from auto_pm.application.core import pm_facade_service as facade_module
from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.plan_checklist import AcceptanceCheck
from auto_pm.domain.change.decision_service import DecisionError
from tests.core.test_declared_dirty_consistency import _verifying
from tests.plan_checklist_support import full_checklist, passing_command

MISSION = "MISSION-PM-001"


def _command(code: str) -> str:
    return shlex.join([sys.executable, "-c", code])


def _reports(root: Path) -> list[Path]:
    return sorted((root / ".auto-pm" / "reports" / "acceptance").glob("*.json"))


@pytest.fixture
def appended(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stand in for the heavy quality gates: record that a verified Checkpoint would have been written."""
    calls: list[str] = []

    def append(_self: Any, **_kwargs: Any) -> None:
        calls.append("append")
        raise ContinuityExecutionError("stop after the acceptance commands (quality gates are not under test)")

    monkeypatch.setattr(ContinuityExecutionService, "append_verified_checkpoint", append)
    return calls


def _approved(monkeypatch: pytest.MonkeyPatch, *commands: tuple[str, int]) -> None:
    checks = tuple(AcceptanceCheck(command=text, expected_exit_code=code) for text, code in commands)
    monkeypatch.setattr(PmFacadeService, "_approved_acceptance_checks", lambda _self, _mission: checks)


def test_a_mismatching_command_refuses_verification_before_any_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appended: list[str]
) -> None:
    missions, facade, _ = _verifying(tmp_path)
    _approved(monkeypatch, (passing_command(), 0), (_command("print('lint failed: x.py'); raise SystemExit(3)"), 0))

    outcome, reason = facade.verify_for_acceptance_with_reason(MISSION, lease_token="gate-lease")

    assert not outcome.verified and outcome.checkpoint_id == ""
    assert "第 2 条验收命令" in reason and "期望退出码 0，实际 3" in reason and "lint failed: x.py" in reason
    assert appended == []  # refused before the Checkpoint
    assert missions.get(MISSION).state is MissionState.ACTIVE
    (report,) = _reports(tmp_path)
    data = json.loads(report.read_text(encoding="utf-8"))
    assert [item["exit_code"] for item in data["checks"]] == [0, 3] and data["all_passed"] is False


def test_matching_commands_let_verification_go_on_and_leave_the_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appended: list[str]
) -> None:
    _, facade, _ = _verifying(tmp_path)
    _approved(monkeypatch, (passing_command(), 0), (_command("raise SystemExit(5)"), 5))

    outcome, _reason = facade.verify_for_acceptance_with_reason(MISSION, lease_token="gate-lease")

    assert appended == ["append"]  # reached the quality gates
    assert not outcome.verified  # our stand-in stops there
    (report,) = _reports(tmp_path)
    assert json.loads(report.read_text(encoding="utf-8"))["all_passed"] is True


def test_the_success_note_says_how_many_commands_ran_and_where_the_record_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, facade, _ = _verifying(tmp_path)
    _approved(monkeypatch, (passing_command(), 0))
    note, block = facade._run_approved_acceptance_checks(
        facade._missions.get(MISSION), SimpleNamespace(run_id="RUN-GATE-001", worktree_path=str(tmp_path))
    )
    assert not block and "1/1" in note and "与批准的退出码一致" in note and ".auto-pm" in note


def test_the_commands_run_in_the_runs_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appended: list[str]) -> None:
    _, facade, _ = _verifying(tmp_path)
    _approved(monkeypatch, (_command("import pathlib, sys; sys.exit(0 if pathlib.Path('pm.py').exists() else 7)"), 0))
    facade.verify_for_acceptance_with_reason(MISSION, lease_token="gate-lease")
    assert appended == ["append"]


def test_a_mission_approved_without_commands_is_said_so_not_silently_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, appended: list[str]
) -> None:
    _, facade, _ = _verifying(tmp_path)
    monkeypatch.setattr(PmFacadeService, "_approved_acceptance_checks", lambda _self, _mission: None)
    note, block = facade._run_approved_acceptance_checks(
        facade._missions.get(MISSION), SimpleNamespace(run_id="R", worktree_path=str(tmp_path))
    )
    assert not block and "旧批准" in note and "未执行" in note
    assert _reports(tmp_path) == []


def test_an_evidence_file_that_cannot_be_written_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, facade, _ = _verifying(tmp_path)
    _approved(monkeypatch, (passing_command(), 0))

    def refuse(*_a: object, **_k: object) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(facade_module, "write_report", refuse)
    note, block = facade._run_approved_acceptance_checks(
        facade._missions.get(MISSION), SimpleNamespace(run_id="R", worktree_path=str(tmp_path))
    )
    assert block and "disk full" in note and "不能当作证据" in note


# ── where the approved commands come from ───────────────────────────────────


def _service(decisions: Any) -> PmFacadeService:
    service = object.__new__(PmFacadeService)
    service._decisions = decisions
    return service


def _mission(decision_id: str | None = "DEC-1") -> Any:
    return SimpleNamespace(authority=None if decision_id is None else SimpleNamespace(decision_id=decision_id))


def _decisions(metadata: dict[str, Any]) -> Any:
    return SimpleNamespace(get_decision=lambda _id: SimpleNamespace(metadata=metadata))


def test_the_commands_are_read_from_the_approved_decisions_execution_grant() -> None:
    checklist = full_checklist(2)
    approval = {"execution_grant": {"plan_checklist": checklist.model_dump(mode="json")}}
    service = _service(_decisions({"planning_approval": approval}))
    assert service._approved_acceptance_checks(_mission()) == checklist.acceptance_checks


@pytest.mark.parametrize(
    "metadata",
    [{}, {"planning_approval": "x"}, {"planning_approval": {"execution_grant": {}}}, {"planning_approval": {"execution_grant": 3}}],
)
def test_a_decision_without_a_checklist_means_no_commands_to_run(metadata: dict[str, Any]) -> None:
    assert _service(_decisions(metadata))._approved_acceptance_checks(_mission()) is None


def test_a_mission_without_a_decision_or_with_an_unreadable_one_has_no_commands() -> None:
    assert _service(_decisions({}))._approved_acceptance_checks(_mission(None)) is None

    def missing(_id: str) -> Any:
        raise DecisionError("no such decision")

    assert _service(SimpleNamespace(get_decision=missing))._approved_acceptance_checks(_mission()) is None


def test_a_corrupt_checklist_in_the_decision_refuses_instead_of_skipping_the_checks() -> None:
    approval = {"execution_grant": {"plan_checklist": {"acceptance_checks": [{"command": "x", "expected_exit_code": 999}]}}}
    with pytest.raises(PmFacadeError, match="批准的验收命令读不出来"):
        _service(_decisions({"planning_approval": approval}))._approved_acceptance_checks(_mission())
