"""doctor: a change-order status edited by hand shows up before it is ever committed (audit 524, point 3)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.domain.change.status_journal import record_transition
from auto_pm.ui.cli.doctor import check_change_status_history, doctor_command, run_doctor_check
from tests.core.test_doctor_worktree_floor import _healthy

PID = "SW-2026-008"
CHG = "CHG-SCPT-2026-346"
REL = f"01_Project/{PID}/04_监控/01_变更管理/01_变更单/CHG-SCPT/{CHG}.md"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=ci", "-c", "user.email=ci@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def _order(status: str) -> str:
    return (
        f"# {CHG}\n\n## 3. 变更基本信息\n\n### 3.0 编号与项目\n\n| 字段 | 内容 |\n| --- | --- |\n| 变更编号 | {CHG} |\n"
        f"| 项目编号 | {PID} |\n\n### 3.4 申请信息\n\n| 字段 | 内容 |\n| --- | --- |\n| 变更状态 | {status} |\n"
    )


def _record(root: Path, *to_statuses: str) -> None:
    for previous, current in zip(("", *to_statuses), to_statuses, strict=False):
        record_transition(root, change_number=CHG, project_id=PID, from_status=previous, to_status=current)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A cloud-style clone: one root, the order committed under review, no transition journal."""

    (tmp_path / REL).parent.mkdir(parents=True)
    (tmp_path / REL).write_text(_order("under_review"), encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "baseline")
    return tmp_path


def test_a_clean_workspace_passes(repo: Path) -> None:
    assert check_change_status_history(str(repo)) == {"status": "ok", "reasons": []}


@pytest.mark.parametrize("status", ["approved", "conditionally_approved", "implementing", "completed"])
def test_a_hand_written_approved_state_is_red_with_no_database(repo: Path, status: str) -> None:
    (repo / REL).write_text(_order(status), encoding="utf-8")
    result = check_change_status_history(str(repo))
    assert result["status"] == "fail" and CHG in result["reasons"][0] and status in result["reasons"][0]


def test_the_same_edit_after_a_real_transition_is_green(repo: Path) -> None:
    (repo / REL).write_text(_order("approved"), encoding="utf-8")
    _record(repo, "under_review", "approved")
    assert check_change_status_history(str(repo))["status"] == "ok"


def test_a_history_that_stops_before_the_edited_status_is_red(repo: Path) -> None:
    (repo / REL).write_text(_order("completed"), encoding="utf-8")
    _record(repo, "under_review", "approved")
    assert check_change_status_history(str(repo))["status"] == "fail"


def test_a_new_untracked_order_written_as_approved_is_red(repo: Path) -> None:
    other = REL.replace("346", "347")
    (repo / other).write_text(_order("approved").replace("346", "347"), encoding="utf-8")
    result = check_change_status_history(str(repo))
    assert result["status"] == "fail" and "347" in result["reasons"][0]


def test_a_committed_approved_order_without_history_is_not_a_problem(repo: Path) -> None:
    (repo / REL).write_text(_order("approved"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "arrived by pull request")
    assert check_change_status_history(str(repo))["status"] == "ok"


def test_a_status_that_is_not_approved_is_not_checked(repo: Path) -> None:
    (repo / REL).write_text(_order("submitted"), encoding="utf-8")
    assert check_change_status_history(str(repo))["status"] == "ok"


def test_without_git_nothing_is_checked_and_it_says_so(tmp_path: Path) -> None:
    assert check_change_status_history(str(tmp_path))["status"] == "info"


def test_the_doctor_command_exits_nonzero_on_a_hand_written_state(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auto_pm.ui.cli.doctor.check_release_consistency", lambda root: {"status": "info", "failures": [], "warnings": []})
    (repo / REL).write_text(_order("approved"), encoding="utf-8")
    result = CliRunner().invoke(doctor_command, ["-w", str(repo)])
    assert result.exit_code == 1, result.output
    assert "变更单状态与流转记录" in result.output and "FAIL" in result.output


def test_a_text_edit_of_an_approved_order_that_keeps_its_status_needs_no_history(repo: Path) -> None:
    """Only a NEW status needs a row: an order that arrived approved by pull request can be edited on this machine."""

    (repo / REL).write_text(_order("approved"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "arrived by pull request")
    (repo / REL).write_text(_order("approved") + "\n补充说明\n", encoding="utf-8")
    assert check_change_status_history(str(repo)) == {"status": "ok", "reasons": []}


def test_renumbering_is_not_a_new_status_but_a_forged_replacement_is_red(repo: Path) -> None:
    """Doctor sees the same renumbering rule as the commit hook: same text but the number is fine, anything else is not."""

    (repo / REL).write_text(_order("approved"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "approved")
    other = REL.replace("346", "347")
    (repo / REL).unlink()
    (repo / other).write_text(_order("approved").replace("346", "347"), encoding="utf-8")
    assert check_change_status_history(str(repo))["status"] == "ok"
    (repo / other).write_text(_order("approved").replace("346", "347") + "\n另加一行\n", encoding="utf-8")
    assert check_change_status_history(str(repo))["status"] == "fail"


def test_the_change_status_check_moves_all_passed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit 530: ``run_doctor_check`` must fold the check into ``all_passed``.  Everything else is made healthy first, so
    only this check can move the answer (the way #472 pins the worktree floor)."""

    _healthy(monkeypatch)
    healthy = run_doctor_check(str(repo))
    assert healthy["change_status"]["status"] == "ok"
    assert healthy["all_passed"] is True, "对照：其余都健康、变更单状态也对时 all_passed 必须是 True"

    (repo / REL).write_text(_order("approved"), encoding="utf-8")  # a hand-written state with no transition record
    broken = run_doctor_check(str(repo))

    assert broken["change_status"]["status"] == "fail"
    assert broken["all_passed"] is False

    _record(repo, "under_review", "approved")  # the same file after a real transition: green again
    assert run_doctor_check(str(repo))["all_passed"] is True
