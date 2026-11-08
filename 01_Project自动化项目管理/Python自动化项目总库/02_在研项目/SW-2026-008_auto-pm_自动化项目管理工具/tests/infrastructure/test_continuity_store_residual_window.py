"""D-95: characterization of the one residual window left by the lock slimming (#589).

``start_run`` takes the full governed-worktree snapshot BEFORE the ledger write lock, which includes the git-ownership
checks (top-level, common-dir, git-dir must belong to the control root). Inside the lock only three cheap facts are
re-checked: path identity, HEAD and dirty paths in scope. So if the worktree's git directory is swapped for a foreign
one between the two points, and the foreign repository has the same HEAD and a clean scope, the lock-side re-check
cannot see it.

This is a KNOWN, ACCEPTED gap (D-95, risk accepted by the coordinator 2026-11-08; the swap needs write access to the
user's own work tree, and the window is the time between two adjacent calls). These tests pin today's behaviour so
that it cannot change silently:

* the same swap done BEFORE the snapshot is refused (the ownership check works);
* the same swap done between the snapshot and the lock is NOT refused (the gap).

If a later change closes the gap (for example by repeating the ownership check in the lock), the second test fails on
purpose: flip its assertion to ``pytest.raises`` and update D-95 in the debt register.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from tests.core.test_continuity_execution_service import Clock, _services, _start


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=T", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def _external_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A linked worktree outside the control root, and a foreign clone of the control root with the same HEAD."""

    root = tmp_path / "root"
    root.mkdir()
    return root, tmp_path / "linked"


def _swap_git_marker_to_foreign_clone(worktree: Path, foreign_clone: Path) -> None:
    (worktree / ".git").write_text(f"gitdir: {foreign_clone / '.git'}\n", encoding="utf-8")


def _prepare(tmp_path: Path) -> tuple[Any, Path, Path]:
    root, linked = _external_worktree(tmp_path)
    _, service = _services(root, Clock())
    _git(root, "worktree", "add", "--detach", str(linked))
    foreign = tmp_path / "foreign"
    subprocess.run(["git", "clone", "-q", str(root), str(foreign)], check=True, capture_output=True)
    return service, linked, foreign


def test_a_git_directory_swapped_before_the_snapshot_is_refused(tmp_path: Path) -> None:
    service, linked, foreign = _prepare(tmp_path)
    _swap_git_marker_to_foreign_clone(linked, foreign)

    with pytest.raises(Exception, match="common-dir|git-dir|top-level|控制"):
        _start(service, worktree_path=str(linked))
    assert service._store.list_runs("WORK-001") == ()


def test_known_gap_d95_a_git_directory_swapped_between_the_snapshot_and_the_lock_is_not_noticed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, linked, foreign = _prepare(tmp_path)
    store = service._store
    original = store._confirm_run_snapshot_in_lock

    def swap_then_confirm(*args: Any, **kwargs: Any) -> None:
        _swap_git_marker_to_foreign_clone(linked, foreign)
        original(*args, **kwargs)

    monkeypatch.setattr(store, "_confirm_run_snapshot_in_lock", swap_then_confirm)

    try:
        _start(service, worktree_path=str(linked))
    except ContinuityStoreError as error:  # pragma: no cover - only if the gap gets closed
        pytest.fail(
            "D-95 gap looks closed (the lock now notices a swapped git directory): "
            f"turn this test into a pytest.raises and update the debt register. Refusal was: {error}"
        )

    assert [run.run_id for run in store.list_runs("WORK-001")] == ["RUN-001"]
