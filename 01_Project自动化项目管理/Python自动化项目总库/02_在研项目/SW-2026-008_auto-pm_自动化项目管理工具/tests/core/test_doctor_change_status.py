"""doctor: a change-order status edited by hand shows up before it is ever committed (audit 524, point 3)."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.infrastructure.db.schema import DDL_APPROVAL_HISTORY
from auto_pm.ui.cli.doctor import check_change_status_history, doctor_command

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
    (root / ".auto-pm").mkdir(exist_ok=True)
    with sqlite3.connect(root / ".auto-pm" / "index.db") as connection:
        connection.execute(DDL_APPROVAL_HISTORY)
        for previous, current in zip(("", *to_statuses), to_statuses, strict=False):
            connection.execute(
                "INSERT INTO approval_history (project_id, change_number, from_status, to_status, transition_date) VALUES (?, ?, ?, ?, ?)",
                (PID, CHG, previous, current, "2026-11-02"),
            )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A cloud-style clone: one root, the order committed under review, no ``.auto-pm`` database."""

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
    assert "变更单状态与审批历史" in result.output and "FAIL" in result.output


def test_a_text_edit_of_an_approved_order_that_keeps_its_status_needs_no_history(repo: Path) -> None:
    """Only a NEW status needs a row: an order that arrived approved by pull request can be edited on this machine."""

    (repo / REL).write_text(_order("approved"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "arrived by pull request")
    (repo / REL).write_text(_order("approved") + "\n补充说明\n", encoding="utf-8")
    assert check_change_status_history(str(repo)) == {"status": "ok", "reasons": []}
