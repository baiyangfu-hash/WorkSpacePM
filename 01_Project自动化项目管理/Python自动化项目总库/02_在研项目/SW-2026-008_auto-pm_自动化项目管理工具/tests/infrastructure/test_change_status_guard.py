"""TD (audit 524, point 3): a change order's status line must agree with the approval history, or the commit is refused.

Real Git repositories and the real ``enforce_commit_msg``; the transition journal is a real SQLite file with the real table.
The case that carries the risk is the cloud single-root clone: there is no transition journal (``.auto-pm/status_journal.db``), §3.4 is edited by hand to an
approved state, and the edit is staged.  A missing database and a database without a row for the order are the same answer
("no history"), never a pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.domain.change.status_journal import record_transition
from auto_pm.infrastructure import change_status_guard as guard
from auto_pm.infrastructure.git_hook_enforcer import enforce_commit_msg
from tests.infrastructure.test_git_hook_enforcer import (
    _fixture_chg_content,
    _git,
    _make_dual_root_fixture,
)

pytestmark = pytest.mark.usefixtures("identity_guard_off")

PID = "SW-2026-008"
CHG = "CHG-SCPT-2026-346"  # the number _make_dual_root_fixture gives its change order
CHG_REL = f"01_Project/{PID}/04_监控/01_变更管理/01_变更单/CHG-SCPT/{CHG}.md"
CODE_REL = f"01_Project/{PID}/src/service.py"
GATED = ("approved", "conditionally_approved", "implementing", "completed")


def _record(root: Path, *to_statuses: str, number: str = CHG, pid: str = PID) -> None:
    """Write journal rows the way ``ChangeService.transition_status`` does (one per transition, oldest first)."""

    for previous, current in zip(("", *to_statuses), to_statuses, strict=False):
        record_transition(root, change_number=number, project_id=pid, from_status=previous, to_status=current)


def _hand_edit(root: Path, status: str) -> None:
    """The bypass: write the status into §3.4 by hand and stage it."""

    (root / CHG_REL).write_text(_fixture_chg_content(CHG, PID, status), encoding="utf-8")
    _git(root, "add", CHG_REL)


def _single_root(tmp_path: Path, committed: str) -> tuple[Path, Path]:
    """A cloud-style clone: one root, the change order committed in ``committed``, no ``.auto-pm`` at all."""

    _cand, ctrl, _msg = _make_dual_root_fixture(tmp_path, chg_status=committed, candidate_has_staged_code=False)
    message = ctrl / "MSG"
    message.write_text("docs: change order\n", encoding="utf-8")
    assert not (ctrl / ".auto-pm").exists()
    return ctrl, message


# --- ③ the staged edit: the two-step bypass and the cloud single-root clone ----------------------------------------------------


@pytest.mark.parametrize("status", GATED)
def test_a_staged_hand_edit_to_an_approved_state_is_refused_when_there_is_no_database_at_all(tmp_path: Path, status: str, capsys: pytest.CaptureFixture[str]) -> None:
    ctrl, message = _single_root(tmp_path, committed="under_review")
    _hand_edit(ctrl, status)
    assert enforce_commit_msg(ctrl, message) == 1
    assert "状态行被手改过" in capsys.readouterr().out


@pytest.mark.parametrize("status", GATED)
def test_a_database_without_a_row_for_this_order_is_the_same_answer_as_no_database(tmp_path: Path, status: str) -> None:
    ctrl, message = _single_root(tmp_path, committed="under_review")
    _record(ctrl, "submitted", number="CHG-SCPT-2026-001")  # history exists, but for another order
    _hand_edit(ctrl, status)
    assert enforce_commit_msg(ctrl, message) == 1


def test_a_database_that_cannot_be_read_never_counts_as_approval(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="under_review")
    (ctrl / ".auto-pm").mkdir()
    (ctrl / ".auto-pm" / "status_journal.db").write_bytes(b"this is not a database")
    _hand_edit(ctrl, "approved")
    assert enforce_commit_msg(ctrl, message) == 1


def test_a_history_whose_last_row_says_something_else_is_refused(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="under_review")
    _record(ctrl, "submitted", "under_review")  # the order never left review
    _hand_edit(ctrl, "approved")
    assert enforce_commit_msg(ctrl, message) == 1


def test_a_conditional_approval_needs_its_own_row_not_an_approved_one(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="under_review")
    _record(ctrl, "under_review", "approved")
    _hand_edit(ctrl, "conditionally_approved")
    assert enforce_commit_msg(ctrl, message) == 1


@pytest.mark.parametrize("status", GATED)
def test_the_same_edit_made_by_a_real_transition_is_accepted(tmp_path: Path, status: str) -> None:
    """The other side: the command writes the file and the row together, so file and history agree."""

    ctrl, message = _single_root(tmp_path, committed="under_review")
    _record(ctrl, "under_review", status)
    _hand_edit(ctrl, status)
    assert enforce_commit_msg(ctrl, message) == 0


def test_a_status_that_is_not_an_approved_state_is_not_this_guards_business(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="draft")
    _hand_edit(ctrl, "submitted")
    assert enforce_commit_msg(ctrl, message) == 0


def test_an_edit_that_leaves_the_status_alone_is_accepted_without_any_history(tmp_path: Path) -> None:
    """An old order made in a cloud session has no row on this machine; editing its text is fine."""

    ctrl, message = _single_root(tmp_path, committed="approved")
    (ctrl / CHG_REL).write_text(_fixture_chg_content(CHG, PID, "approved") + "\n补充说明\n", encoding="utf-8")
    _git(ctrl, "add", CHG_REL)
    assert enforce_commit_msg(ctrl, message) == 0


def test_moving_a_change_order_is_not_a_new_status(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="approved")
    moved = ctrl / CHG_REL.replace("CHG-SCPT/", "CHG-SCPT/archive/")
    moved.parent.mkdir(parents=True)
    _git(ctrl, "mv", CHG_REL, str(moved.relative_to(ctrl)))
    assert enforce_commit_msg(ctrl, message) == 0


NEW_CHG = "CHG-SCPT-2026-347"
NEW_REL = CHG_REL.replace(CHG, NEW_CHG)


def _renumber(ctrl: Path, *, extra: str = "", status: str = "approved") -> None:
    """The project's rule for a number clash: the later merge takes a new number -- the old file goes, the new one comes."""

    _git(ctrl, "rm", "-q", CHG_REL)
    text = _fixture_chg_content(CHG, PID, status).replace(CHG, NEW_CHG) + extra
    (ctrl / NEW_REL).parent.mkdir(parents=True, exist_ok=True)
    (ctrl / NEW_REL).write_text(text, encoding="utf-8")
    _git(ctrl, "add", NEW_REL)


def test_renumbering_after_a_number_clash_is_not_a_new_status(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="approved")
    _renumber(ctrl)
    assert enforce_commit_msg(ctrl, message) == 0


def test_a_renumbered_order_with_any_other_text_is_a_new_order_and_is_refused(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="approved")
    _renumber(ctrl, extra="\n批准人另加了一行\n")
    assert enforce_commit_msg(ctrl, message) == 1


def test_a_renumbered_order_that_also_changes_the_status_is_refused(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="under_review")
    _renumber(ctrl, status="approved")
    assert enforce_commit_msg(ctrl, message) == 1


def test_renumbering_a_real_transition_still_needs_nothing_but_adding_a_forged_order_is_refused(tmp_path: Path) -> None:
    """Deleting an approved order does not hand its approval to a different order made up on the spot."""

    ctrl, message = _single_root(tmp_path, committed="approved")
    _git(ctrl, "rm", "-q", CHG_REL)
    forged = _fixture_chg_content("CHG-SCPT-2026-999", PID, "approved")
    (ctrl / NEW_REL).parent.mkdir(parents=True, exist_ok=True)
    (ctrl / NEW_REL).write_text(forged, encoding="utf-8")
    _git(ctrl, "add", NEW_REL)
    assert enforce_commit_msg(ctrl, message) == 1


def test_removing_the_status_row_and_leaving_only_the_approval_table_is_judged_by_the_status_it_reads_as(tmp_path: Path) -> None:
    """The cockpit also infers a status from §8; a hand-written approval table is the same bypass by another door."""

    ctrl, message = _single_root(tmp_path, committed="under_review")
    text = _fixture_chg_content(CHG, PID, "under_review").replace("| 变更状态 | under_review |\n", "")
    text += "\n## 8. 变更审批\n\n| 审批环节 | 审批人 | 审批意见 | 日期 | 签字 |\n| --- | --- | --- | --- | --- |\n| **批准** | someone | 同意 | 2026-11-02 | someone |\n"
    (ctrl / CHG_REL).write_text(text, encoding="utf-8")
    _git(ctrl, "add", CHG_REL)
    assert guard.status_of_bytes(text.encode("utf-8"), CHG_REL) == "approved"  # no §3.4 row, read from the approval table
    assert enforce_commit_msg(ctrl, message) == 1


# --- history replays are not new edits ------------------------------------------------------------------------------------------


def _branch_with_hand_edit(ctrl: Path) -> None:
    _git(ctrl, "checkout", "-q", "-b", "other")
    (ctrl / CHG_REL).write_text(_fixture_chg_content(CHG, PID, "approved"), encoding="utf-8")
    _git(ctrl, "add", CHG_REL)
    _git(ctrl, "commit", "-q", "-m", "committed elsewhere")
    _git(ctrl, "checkout", "-q", "-")


def test_a_merge_in_progress_brings_committed_history_and_is_not_judged(tmp_path: Path) -> None:
    ctrl, message = _single_root(tmp_path, committed="under_review")
    _branch_with_hand_edit(ctrl)
    _git(ctrl, "merge", "--no-commit", "--no-ff", "other")
    assert guard.replays_history(ctrl)
    assert enforce_commit_msg(ctrl, message) == 0


def test_the_same_change_staged_outside_a_merge_is_refused(tmp_path: Path) -> None:
    """Control for the merge case: identical staged content, no MERGE_HEAD, refused."""

    ctrl, message = _single_root(tmp_path, committed="under_review")
    _branch_with_hand_edit(ctrl)
    _git(ctrl, "checkout", "other", "--", CHG_REL)
    assert not guard.replays_history(ctrl)
    assert enforce_commit_msg(ctrl, message) == 1


# --- ① ② the change order a code commit is bound to ----------------------------------------------------------------------------


def test_bound_order_edited_after_its_last_commit_without_history_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_status="approved")
    (ctrl / CHG_REL).write_text(_fixture_chg_content(CHG, PID, "implementing"), encoding="utf-8")  # working tree only
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1
    assert "没有流转依据" in capsys.readouterr().out


def test_bound_order_with_a_matching_last_row_is_accepted(tmp_path: Path) -> None:
    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_status="approved")
    (ctrl / CHG_REL).write_text(_fixture_chg_content(CHG, PID, "implementing"), encoding="utf-8")
    _record(ctrl, "approved", "implementing")
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


def test_bound_order_edited_in_the_working_tree_against_a_history_that_stops_earlier_is_refused(tmp_path: Path) -> None:
    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_status="approved")
    _record(ctrl, "under_review", "approved")
    (ctrl / CHG_REL).write_text(_fixture_chg_content(CHG, PID, "completed"), encoding="utf-8")  # skips implementing, no row
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


def test_a_committed_status_is_not_second_guessed_by_an_older_local_history(tmp_path: Path) -> None:
    """Approved here, finished in a cloud session and merged: the file is ahead of this machine's last row, and that is fine.

    The committed status came in through a commit and its pull request; what the hook judges is a status that is new.
    """

    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_status="completed")
    _record(ctrl, "under_review", "approved")
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


def test_an_old_committed_order_without_any_history_still_passes_with_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The legacy case: made in a cloud session, merged by pull request, never transitioned on this machine."""

    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_status="approved")
    assert not (ctrl / ".auto-pm").exists()
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0
    assert "流转记录里没有这张单" in capsys.readouterr().out


def test_a_bound_order_staged_in_a_single_root_with_a_hand_written_status_is_refused(tmp_path: Path) -> None:
    """Cloud single-root clone, one commit that carries both the production code and the hand-edited order."""

    ctrl, _message = _single_root(tmp_path, committed="under_review")
    _hand_edit(ctrl, "approved")
    (ctrl / CODE_REL).write_text("VALUE = 3\n", encoding="utf-8")
    _git(ctrl, "add", CODE_REL)
    message = ctrl / "MSG2"
    message.write_text(f"feat: [{CHG}] code\n", encoding="utf-8")
    assert enforce_commit_msg(ctrl, message) == 1


# --- the building blocks ---------------------------------------------------------------------------------------------------------


def test_the_database_is_opened_read_only_and_never_created(tmp_path: Path) -> None:
    assert guard.last_recorded_status(tmp_path, CHG) is None
    assert not (tmp_path / ".auto-pm").exists()
    _record(tmp_path, "approved")
    before = (tmp_path / ".auto-pm" / "status_journal.db").read_bytes()
    assert guard.last_recorded_status(tmp_path, CHG, PID) == "approved"
    assert guard.last_recorded_status(tmp_path, CHG, "SW-OTHER") is None  # another project's order of the same number
    assert (tmp_path / ".auto-pm" / "status_journal.db").read_bytes() == before


def test_the_newest_row_wins(tmp_path: Path) -> None:
    _record(tmp_path, "approved", "implementing", "completed")
    assert guard.last_recorded_status(tmp_path, CHG, PID) == "completed"


@pytest.mark.parametrize(
    "path",
    [
        CHG_REL,
        "04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-1.md",
        "x\\y\\01_变更管理\\01_变更单\\CHG-PLC\\CHG-PLC-2026-12.md",
    ],
)
def test_change_order_paths_are_recognised(path: str) -> None:
    assert guard.is_change_order_path(path)


@pytest.mark.parametrize(
    "path",
    ["docs/CHG-SCPT-2026-346.md", "01_变更管理/01_变更单/notes.md", "01_变更管理/01_变更单/CHG-SCPT-2026-346.txt", "src/service.py"],
)
def test_other_paths_are_not_change_orders(path: str) -> None:
    assert not guard.is_change_order_path(path)


def test_renumbering_is_recognised_across_line_endings() -> None:
    """Windows: the file in the working tree is CRLF, the blob Git holds is LF -- the same text for the renumbering check."""

    old = _fixture_chg_content(CHG, PID, "approved").encode("utf-8")
    new = old.replace(CHG.encode(), NEW_CHG.encode()).replace(b"\n", b"\r\n")
    removed = {CHG_REL: (CHG, old)}
    assert guard.renumbered_status(removed, NEW_REL, NEW_CHG, new) == "approved"
    assert guard.renumbered_status(removed, NEW_REL, NEW_CHG, new + b"extra\r\n") is None


def test_renumbering_is_recognised_when_the_old_side_is_crlf_and_the_new_side_is_lf() -> None:
    """Audit 532 (the reverse direction): the removed blob carries CRLF, the renumbered file is written with LF."""

    old_lf = _fixture_chg_content(CHG, PID, "approved").encode("utf-8")
    old = old_lf.replace(b"\n", b"\r\n")
    new = old_lf.replace(CHG.encode(), NEW_CHG.encode())
    removed = {CHG_REL: (CHG, old)}
    assert guard.renumbered_status(removed, NEW_REL, NEW_CHG, new) == "approved"
    assert guard.renumbered_status(removed, NEW_REL, NEW_CHG, new + b"extra\n") is None
    assert guard.renumbered_status(removed, NEW_REL, NEW_CHG, new.replace(b"approved", b"closed")) is None
