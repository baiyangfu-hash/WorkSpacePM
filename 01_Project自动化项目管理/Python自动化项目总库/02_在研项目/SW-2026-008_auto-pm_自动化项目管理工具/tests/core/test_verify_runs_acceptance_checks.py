"""``pm verify`` executes the acceptance commands the user approved (CHG-SCPT-2026-472).

Before: ``pm plan --check`` stored the commands and the agent ran them itself, so "done" could be reported without any
check having passed.  Now the verifier runs each one (from the control root, with the Run's worktree in ``AUTO_PM_RUN_WORKTREE``) and a mismatch refuses verification before any
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


def test_the_commands_run_from_the_control_root_and_are_pointed_at_the_runs_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approved commands are written from the workspace root (``.venv`` and ``main.py`` live there; cockpit commands
    refuse to run inside a worktree), so that is where they run; the Run's worktree arrives through the environment."""
    _, facade, _ = _verifying(tmp_path)
    worktree = tmp_path / "wt-elsewhere"
    worktree.mkdir()
    code = (
        "import os, pathlib; print('CWD=' + str(pathlib.Path.cwd().resolve())); "
        "print('RUN=' + os.environ['AUTO_PM_RUN_WORKTREE']); print('DATA=' + os.environ['AUTO_PM_WORKSPACE']); "
        "print('LEDGER=' + os.environ['AUTO_PM_CONTROL_ROOT'])"
    )
    _approved(monkeypatch, (_command(code), 0))

    note, block = facade._run_approved_acceptance_checks(
        facade._missions.get(MISSION), SimpleNamespace(run_id="RUN-GATE-001", worktree_path=str(worktree))
    )

    assert not block, note
    (report,) = _reports(tmp_path)
    tail = json.loads(report.read_text(encoding="utf-8"))["checks"][0]["output_tail"]
    assert tail.splitlines() == [
        f"CWD={tmp_path.resolve()}",
        f"RUN={worktree}",
        f"DATA={worktree}",
        f"LEDGER={tmp_path.resolve()}",
    ]


# ── the worktree is what gets judged, never the control root's copy of the same file ────────────────────

_PYTEST_FILE = "test_gate.py"


def _pytest_command() -> str:
    return shlex.join([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "{worktree}/" + _PYTEST_FILE])


def _isolated_run(tmp_path: Path) -> tuple[Any, Path]:
    """A VERIFYING Run whose worktree is a folder of its own, apart from the control root (tmp_path)."""
    _, facade, _ = _verifying(tmp_path)
    worktree = tmp_path / "isolated-worktree"
    worktree.mkdir()
    return facade, worktree


def _judge(facade: Any, worktree: Path, command: str, expected: int, monkeypatch: pytest.MonkeyPatch) -> tuple[bool, str]:
    _approved(monkeypatch, (command, expected))
    note, block = facade._run_approved_acceptance_checks(
        facade._missions.get(MISSION), SimpleNamespace(run_id="RUN-GATE-001", worktree_path=str(worktree))
    )
    return block, note


def test_a_broken_file_in_the_worktree_fails_pytest_even_though_the_control_roots_copy_is_good(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facade, worktree = _isolated_run(tmp_path)
    (tmp_path / _PYTEST_FILE).write_text("def test_it():\n    assert True\n", encoding="utf-8")  # the control root's copy: good
    (worktree / _PYTEST_FILE).write_text("def test_it():\n    assert False\n", encoding="utf-8")  # what the Run produced: broken

    blocked, note = _judge(facade, worktree, _pytest_command(), 0, monkeypatch)

    assert blocked and "期望退出码 0，实际 1" in note
    (report,) = _reports(tmp_path)
    check = json.loads(report.read_text(encoding="utf-8"))["checks"][0]
    assert check["passed"] is False and check["argv"][-1] == f"{worktree}/{_PYTEST_FILE}"


def test_the_same_pytest_command_passes_when_the_worktree_is_good_and_the_control_roots_copy_is_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other direction: proof the verdict follows the worktree, not whatever happens to sit in the control root."""
    facade, worktree = _isolated_run(tmp_path)
    (tmp_path / _PYTEST_FILE).write_text("def test_it():\n    assert False\n", encoding="utf-8")
    (worktree / _PYTEST_FILE).write_text("def test_it():\n    assert True\n", encoding="utf-8")

    blocked, note = _judge(facade, worktree, _pytest_command(), 0, monkeypatch)

    assert not blocked, note


def _cockpit_control_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A control root with the cockpit's own ``main.py`` (it imports the real CLI) and a project present only there."""
    import auto_pm

    (root / "main.py").write_text("from auto_pm.ui.cli.__main__ import cli\ncli()\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(Path(auto_pm.__file__).resolve().parent.parent))
    project = root / "DJ-2026-TEST_测试项目"
    project.mkdir()
    (project / ".plc.json").write_text('{"name": "DJ-2026-TEST", "version": "V1.0.0", "description": "t", "type": "standard"}', encoding="utf-8")
    return shlex.join([sys.executable, "-B", "main.py", "project", "show", "DJ-2026-TEST"])


def test_a_cockpit_command_judges_the_worktrees_project_not_the_control_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``main.py <cockpit command> <PID>``: the project exists in the control root but not in the Run's worktree."""
    facade, worktree = _isolated_run(tmp_path)
    command = _cockpit_control_root(tmp_path, monkeypatch)

    blocked, note = _judge(facade, worktree, command, 0, monkeypatch)
    assert blocked and "期望退出码 0，实际 1" in note  # control root good, worktree without the project: must fail

    good = worktree / "DJ-2026-TEST_测试项目"
    good.mkdir()
    (good / ".plc.json").write_text('{"name": "DJ-2026-TEST", "version": "V1.0.0", "description": "t", "type": "standard"}', encoding="utf-8")
    blocked, note = _judge(facade, worktree, command, 0, monkeypatch)
    assert not blocked, note  # and it passes once the worktree has it


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
    assert block and "disk full" in note and "不能算验收命令已执行" in note


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


# ── the read-only scan of what is already approved (run on the ledger machine before a release) ──────────


def test_the_scan_lists_the_approved_commands_verify_would_refuse_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missions, facade, _ = _verifying(tmp_path)
    marker = tmp_path / "must-not-exist.txt"
    would_write = _command(f"open({str(marker)!r}, 'w').close()")
    _approved(
        monkeypatch,
        (passing_command(), 0),
        ("pytest -q && ruff check", 0),
        (".venv/bin/python -B main.py plc check DJ-2026-011", 0),
        (would_write, 0),
    )

    scan = facade.scan_approved_acceptance_commands(missions.get(MISSION).subject_project_id)

    assert (scan.missions_scanned, scan.commands_scanned) == (1, 4)
    assert [(item.mission_id, item.index) for item in scan.findings] == [(MISSION, 2), (MISSION, 3)]
    assert "shell 符号" in scan.findings[0].reason
    assert "找不到命令 .venv/bin/python" in scan.findings[1].reason
    assert not marker.exists()  # a scan looks, it does not execute


def test_the_scan_finds_nothing_to_refuse_in_a_clean_ledger_and_skips_old_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missions, facade, _ = _verifying(tmp_path)
    project = missions.get(MISSION).subject_project_id
    _approved(monkeypatch, (passing_command(), 0))
    clean = facade.scan_approved_acceptance_commands(project)
    assert (clean.missions_scanned, clean.commands_scanned, clean.findings) == (1, 1, ())

    monkeypatch.setattr(PmFacadeService, "_approved_acceptance_checks", lambda _self, _mission: None)
    old = facade.scan_approved_acceptance_commands(project)
    assert (old.missions_scanned, old.commands_scanned, old.findings) == (0, 0, ())


def test_the_scan_names_an_approval_it_cannot_read_instead_of_skipping_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missions, facade, _ = _verifying(tmp_path)

    def unreadable(_self: Any, _mission: Any) -> Any:
        raise PmFacadeError("批准的验收命令读不出来：x")

    monkeypatch.setattr(PmFacadeService, "_approved_acceptance_checks", unreadable)
    scan = facade.scan_approved_acceptance_commands(missions.get(MISSION).subject_project_id)
    assert [(item.mission_id, item.index) for item in scan.findings] == [(MISSION, 0)]
    assert "读不出来" in scan.findings[0].reason


def test_the_scan_command_exits_1_when_something_would_be_refused_and_0_when_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from auto_pm.ui.cli.__main__ import cli

    missions, _facade, _ = _verifying(tmp_path)
    project = missions.get(MISSION).subject_project_id
    args = ["-w", str(tmp_path), "pm", "acceptance-scan", "--pid", project]

    _approved(monkeypatch, (passing_command(), 0))
    ok = CliRunner().invoke(cli, args, catch_exceptions=False)
    assert ok.exit_code == 0 and json.loads(ok.output)["would_refuse"] == []

    _approved(monkeypatch, (passing_command(), 0), ("pytest | tee out.txt", 0))
    refused = CliRunner().invoke(cli, args, catch_exceptions=False)
    payload = json.loads(refused.output)
    assert refused.exit_code == 1 and payload["would_refuse"][0]["index"] == 2
    assert payload["commands_checked"] == 2 and "shell 符号" in payload["would_refuse"][0]["reason"]
