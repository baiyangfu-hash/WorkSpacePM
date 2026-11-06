"""The ledger write lock is held briefly: timing is recorded, and a Run start does not run the slow git snapshot while holding it."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from auto_pm.infrastructure import continuity_store as store_module
from auto_pm.infrastructure import control_root_guard
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.control_root_guard import worktree_head_and_dirty
from tests.core.test_continuity_execution_service import Clock, _services, _start


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def test_every_write_records_how_long_it_waited_and_held_the_lock(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-11-06T00:00:00+00:00", "test")

    timing = store.last_write_timing

    assert timing["caller"] == "initialize"
    assert timing["waited_seconds"] >= 0.0
    assert timing["held_seconds"] >= 0.0


def test_a_slow_lock_is_logged_with_the_method_that_held_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    store = ContinuityStore(tmp_path)
    monkeypatch.setattr(store_module, "WRITE_LOCK_SLOW_SECONDS", -1.0)

    with caplog.at_level(logging.WARNING, logger=store_module.__name__):
        store.initialize("2026-11-06T00:00:00+00:00", "test")

    assert any(
        "写锁偏慢" in record.getMessage() and "initialize" in record.getMessage()
        for record in caplog.records
    )


def test_start_run_takes_the_full_git_snapshot_before_the_lock_and_two_git_calls_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service = _services(tmp_path, Clock())
    store = service._store
    in_lock = False
    full_snapshots_in_lock = 0
    git_calls_in_lock = 0

    original_transaction = store._transaction

    @contextmanager
    def watched_transaction() -> Iterator[Any]:
        nonlocal in_lock
        with original_transaction() as conn:
            in_lock = True
            try:
                yield conn
            finally:
                in_lock = False

    original_snapshot = store._validated_run_snapshot

    def watched_snapshot(*args: Any, **kwargs: Any) -> Any:
        nonlocal full_snapshots_in_lock
        if in_lock:
            full_snapshots_in_lock += 1
        return original_snapshot(*args, **kwargs)

    def counting(name: str) -> Any:
        original = getattr(control_root_guard, name)

        def run(*args: Any, **kwargs: Any) -> Any:
            nonlocal git_calls_in_lock
            if in_lock:
                git_calls_in_lock += 1
            return original(*args, **kwargs)

        return run

    monkeypatch.setattr(store, "_transaction", watched_transaction)
    monkeypatch.setattr(store, "_validated_run_snapshot", watched_snapshot)
    monkeypatch.setattr(control_root_guard, "_git_output", counting("_git_output"))
    monkeypatch.setattr(
        control_root_guard, "_git_optional_output", counting("_git_optional_output")
    )

    _start(service)

    assert full_snapshots_in_lock == 0
    assert 1 <= git_calls_in_lock <= 2
    assert store.list_runs("WORK-001")


def test_head_moving_between_the_snapshot_and_the_lock_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service = _services(tmp_path, Clock())
    store = service._store
    original = store._confirm_run_snapshot_in_lock

    def commit_then_confirm(*args: Any, **kwargs: Any) -> None:
        _git(tmp_path, "commit", "--allow-empty", "-m", "late")
        original(*args, **kwargs)

    monkeypatch.setattr(store, "_confirm_run_snapshot_in_lock", commit_then_confirm)

    with pytest.raises(Exception, match="git_head"):
        _start(service)
    assert store.list_runs("WORK-001") == ()


def test_a_file_edited_in_owned_paths_between_the_snapshot_and_the_lock_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service = _services(tmp_path, Clock())
    store = service._store
    original = store._confirm_run_snapshot_in_lock

    def edit_then_confirm(*args: Any, **kwargs: Any) -> None:
        target = tmp_path / "auto_pm" / "core" / "a.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("late edit\n", encoding="utf-8")
        original(*args, **kwargs)

    monkeypatch.setattr(store, "_confirm_run_snapshot_in_lock", edit_then_confirm)

    with pytest.raises(Exception, match="observed_dirty_paths"):
        _start(service)
    assert store.list_runs("WORK-001") == ()


def test_worktree_head_and_dirty_reports_changed_staged_and_untracked_inside_scope_only(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "a dir").mkdir()
    (tmp_path / "a dir" / "tracked.txt").write_text("1\n", encoding="utf-8")
    (tmp_path / "other.txt").write_text("1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "base")
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()

    (tmp_path / "a dir" / "tracked.txt").write_text("2\n", encoding="utf-8")  # modified
    (tmp_path / "a dir" / "new.txt").write_text("n\n", encoding="utf-8")  # untracked
    (tmp_path / "a dir" / "ignored.log").write_text("x\n", encoding="utf-8")  # ignored
    (tmp_path / "other.txt").write_text("2\n", encoding="utf-8")  # outside scope
    _git(tmp_path, "add", "other.txt")

    got_head, dirty = worktree_head_and_dirty(tmp_path, ("a dir",))
    assert got_head == head
    assert dirty == ("a dir/new.txt", "a dir/tracked.txt")
    assert worktree_head_and_dirty(tmp_path, ())[1] == ()
    assert worktree_head_and_dirty(tmp_path, ("other.txt",))[1] == ("other.txt",)
