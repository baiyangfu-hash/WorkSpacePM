"""The commit hook reads the change order and the project ledger as strict UTF-8: a bad byte refuses the commit, it is never repaired."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from auto_pm.infrastructure import git_hook_enforcer as hook
from auto_pm.infrastructure.git_hook_enforcer import ProjectBinding, StagedSnapshotError

CHG = "CHG-SCPT-2026-901"
BINDING = ProjectBinding("SW-2026-901", "p")
CHANGE = f"| 项目编号 | SW-2026-901 |\n{CHG}\n"
LEDGER = f"| {CHG} | 版本 |\n"


def _control_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, change: bytes, ledger: bytes) -> Path:
    change_path = tmp_path / f"{CHG}.md"
    ledger_path = tmp_path / "ledger.md"
    change_path.write_bytes(change)
    ledger_path.write_bytes(ledger)
    monkeypatch.setattr(hook, "_find_change_in_control_root", lambda *_args: change_path)
    monkeypatch.setattr(hook, "_project_ledger_file", lambda *_args: ledger_path)
    return tmp_path


@pytest.mark.parametrize("bad", ["change", "ledger"])
def test_a_control_root_document_with_a_bad_byte_refuses_the_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    good = _control_root(tmp_path, monkeypatch, change=CHANGE.encode(), ledger=LEDGER.encode())
    assert hook._validate_control_root_change_evidence(good, BINDING, CHG)  # the clean pair passes

    change = CHANGE.encode() + (b"\xff" if bad == "change" else b"")
    ledger = LEDGER.encode() + (b"\xff" if bad == "ledger" else b"")
    root = _control_root(tmp_path, monkeypatch, change=change, ledger=ledger)

    with pytest.raises(StagedSnapshotError, match="无法读取"):
        hook._validate_control_root_change_evidence(root, BINDING, CHG)


@pytest.mark.parametrize("bad", ["change", "ledger"])
def test_a_staged_document_with_a_bad_byte_refuses_the_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    blobs = {
        "change": CHANGE.encode() + (b"\xff" if bad == "change" else b""),
        "ledger": LEDGER.encode() + (b"\xff" if bad == "ledger" else b""),
    }
    monkeypatch.setattr(hook, "_change_entry", lambda *_args: "change")
    monkeypatch.setattr(hook, "_ledger_entry", lambda *_args: "ledger")
    monkeypatch.setattr(hook, "_read_staged_blob", lambda _root, entry: blobs[entry])
    monkeypatch.setattr(hook, "_working_tree_path", lambda *_args: tmp_path)
    monkeypatch.setattr(hook, "_require_working_tree_match", lambda *_args: None)

    snapshot: Any = object()
    with pytest.raises(StagedSnapshotError, match="不是合法 UTF-8"):
        hook._validate_staged_change_evidence(tmp_path, snapshot, BINDING, CHG)
    blobs.update(change=CHANGE.encode(), ledger=LEDGER.encode())
    assert hook._validate_staged_change_evidence(tmp_path, snapshot, BINDING, CHG) == tmp_path  # clean pair passes
