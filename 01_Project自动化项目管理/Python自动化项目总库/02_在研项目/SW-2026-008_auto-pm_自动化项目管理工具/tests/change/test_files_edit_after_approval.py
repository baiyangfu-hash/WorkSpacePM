"""D-154: editing §5 ``涉及文件/交付物`` after approval sends the change order back to review.

The approved file scope is read from §5.  Adding or removing a file widens or narrows that scope; if the status stayed
``approved`` the old approval would silently cover the new list (CHG-SCPT-2026-555 grew from 3 to 4 files that way).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.status_journal import TABLE, journal_path

from .test_abandon_flow import CHG, _file, _workspace

_FILES_ROW = "\n| 涉及文件/交付物 | a.py<br>b.py |\n"


def _workspace_with_files(tmp_path: Path, status: str) -> str:
    workspace = _workspace(tmp_path, status)
    path = _file(workspace)
    path.write_text(path.read_text(encoding="utf-8") + _FILES_ROW, encoding="utf-8")
    return workspace


def _status(workspace: str) -> str:
    request = ChangeService(workspace).get_change_request(CHG)
    assert request is not None
    return str(request.status)


def _journal(workspace: str) -> list[tuple[str, str, str, str]]:
    connection = sqlite3.connect(journal_path(workspace))
    try:
        return connection.execute(
            f"SELECT from_status, to_status, approver, comment FROM {TABLE} WHERE change_number = ? ORDER BY rowid", (CHG,)
        ).fetchall()
    finally:
        connection.close()


@pytest.mark.parametrize("status", ["approved", "conditionally_approved"])
def test_adding_a_file_after_approval_sends_the_change_order_back_to_review(tmp_path: Path, status: str) -> None:
    workspace = _workspace_with_files(tmp_path, status)

    ChangeService(workspace).update_change_request(CHG, files=["a.py", "b.py", "c.py"])

    assert _status(workspace) == "under_review"
    assert ChangeService(workspace).read_change_files(CHG) == ["a.py", "b.py", "c.py"]
    text = _file(workspace).read_text(encoding="utf-8")
    assert "批准失效" in text and "增 1：c.py" in text


def test_removing_a_file_after_approval_also_sends_it_back(tmp_path: Path) -> None:
    workspace = _workspace_with_files(tmp_path, "approved")

    ChangeService(workspace).update_change_request(CHG, files=["a.py"])

    assert _status(workspace) == "under_review"
    assert "减 1：b.py" in _file(workspace).read_text(encoding="utf-8")


def test_the_revocation_and_its_reason_are_journaled(tmp_path: Path) -> None:
    workspace = _workspace_with_files(tmp_path, "approved")

    ChangeService(workspace).update_change_request(CHG, files=["a.py", "b.py", "c.py"])

    (from_status, to_status, approver, comment), = _journal(workspace)
    assert (from_status, to_status) == ("approved", "under_review")
    assert approver == "系统(D-154)" and "增 1：c.py" in comment and "需重新批准" in comment


def test_the_same_files_in_another_order_keep_the_approval(tmp_path: Path) -> None:
    workspace = _workspace_with_files(tmp_path, "approved")

    ChangeService(workspace).update_change_request(CHG, files=["b.py", "a.py"])

    assert _status(workspace) == "approved"
    assert not _journal_exists(workspace)


def test_writing_the_identical_list_changes_nothing(tmp_path: Path) -> None:
    workspace = _workspace_with_files(tmp_path, "approved")
    before = _file(workspace).read_text(encoding="utf-8")

    ChangeService(workspace).update_change_request(CHG, files=["a.py", "b.py"])

    assert _status(workspace) == "approved" and _file(workspace).read_text(encoding="utf-8") == before


@pytest.mark.parametrize("status", ["draft", "submitted", "under_review"])
def test_before_approval_the_status_is_left_alone(tmp_path: Path, status: str) -> None:
    workspace = _workspace_with_files(tmp_path, status)

    ChangeService(workspace).update_change_request(CHG, files=["a.py", "z.py"])

    assert _status(workspace) == status
    assert not _journal_exists(workspace)


def test_another_field_edit_after_approval_keeps_the_approval(tmp_path: Path) -> None:
    workspace = _workspace_with_files(tmp_path, "approved")

    ChangeService(workspace).update_change_request(CHG, background="补充背景说明")

    assert _status(workspace) == "approved"


def _journal_exists(workspace: str) -> bool:
    return journal_path(workspace).exists() and bool(_journal(workspace))
