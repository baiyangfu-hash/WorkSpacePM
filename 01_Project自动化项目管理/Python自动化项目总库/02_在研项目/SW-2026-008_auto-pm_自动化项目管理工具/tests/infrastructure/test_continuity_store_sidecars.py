"""The store tolerates a WAL sidecar that is briefly in a half-created, delete-pending or locked state, and still refuses a real anomaly (card CARD-SW008-M2-V04, scenarios sc01-sc08; card CARD-SW008-M3-RACE, scenarios sc09-sc12: the second place that meets the same instants, the inventory of the strict read).

SQLite creates and deletes ``-wal``, ``-shm`` and ``-journal`` while other processes use the database, so the path check that runs before every transaction can
meet such a file at the wrong instant, and on Windows the ``-shm`` file cannot even be read while another process has a transaction open. These tests make those
instants deterministic; the real-process counterparts are scenarios r08 and r09 of the recovery end-to-end file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from auto_pm.infrastructure.continuity_store import (
    _SIDECAR_ATTEMPTS,
    ContinuityStore,
    ContinuityStoreError,
    _ReadSnapshotAnomalyError,
    _ReadSnapshotDriftError,
)
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    require_safe_workspace_path,
)

STORE_PATH_CHECK = "auto_pm.infrastructure.continuity_store.require_safe_workspace_path"
ORIGINAL_STAT = Path.stat
ORIGINAL_OPEN = Path.open


def _make_root(root: Path) -> ContinuityStore:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Sidecar Test", "-c", "user.email=sidecar@example.invalid", "commit", "-m", "baseline"],
        check=True, capture_output=True,
    )
    store = ContinuityStore(root)
    store.initialize("2026-10-05T00:00:00+00:00", "test")
    return store


class _Probe:
    """Counts validation attempts (one per check of the database path) and the pauses between them."""

    def __init__(self) -> None:
        self.attempts = 0
        self.sleeps = 0


def _probe(monkeypatch: pytest.MonkeyPatch, *, fail_label: str = "", failures: int | None = 0) -> _Probe:
    """Wrap the path check: count attempts; make the check of the labelled sidecar fail ``failures`` times (always when None)."""

    probe = _Probe()
    failed = 0

    def wrapped(workspace_root: str | Path, candidate: str | Path, *, label: str) -> Path:
        nonlocal failed
        if label == "Continuity Store path":
            probe.attempts += 1
        if fail_label and label.endswith(fail_label) and (failures is None or failed < failures):
            failed += 1
            raise ControlRootGuardError(f"{label} 解析后位于 workspace 外")
        return require_safe_workspace_path(workspace_root, candidate, label=label)

    def sleep(_seconds: float) -> None:
        probe.sleeps += 1

    monkeypatch.setattr(STORE_PATH_CHECK, wrapped)
    monkeypatch.setattr(time, "sleep", sleep)
    return probe


def _stat_with_links(monkeypatch: pytest.MonkeyPatch, probe: _Probe, name: str, links: int, attempts: int | None) -> None:
    """Report another link count for the named file during the first ``attempts`` validation attempts (always when None); ``lstat`` is left alone."""

    def fake(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = ORIGINAL_STAT(self, follow_symlinks=follow_symlinks)
        if self.name == name and follow_symlinks:
            if attempts is None or probe.attempts <= attempts:
                return os.stat_result(
                    (result.st_mode, result.st_ino, result.st_dev, links, result.st_uid, result.st_gid, result.st_size, int(result.st_atime), int(result.st_mtime), int(result.st_ctime))
                )
        return result

    monkeypatch.setattr(Path, "stat", fake)


def _unreadable(monkeypatch: pytest.MonkeyPatch, name: str, failures: int | None) -> list[str]:
    """Make opening the named file for reading fail with a permission error (what Windows reports while another process holds a SQLite transaction open) ``failures`` times (always when None); returns the failed opens."""

    failed: list[str] = []

    def fake(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if self.name == name and "r" in mode and (failures is None or len(failed) < failures):
            failed.append(self.name)
            raise PermissionError(13, "Permission denied", str(self))
        return ORIGINAL_OPEN(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake)
    return failed


def _strict_read(store: ContinuityStore) -> int:
    with store._read_connection() as conn:
        return int(conn.execute("SELECT 1").fetchone()[0])


def test_sc01_a_sidecar_that_briefly_resolves_wrongly_is_tolerated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    probe = _probe(monkeypatch, fail_label="-shm", failures=2)

    assert store._validated_db_path() == store.db_path.resolve()
    assert probe.attempts == 3 and probe.sleeps == 2


def test_sc02_a_sidecar_that_briefly_reports_the_wrong_link_count_is_tolerated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    (tmp_path / ".auto-pm" / "continuity.db-wal").write_bytes(b"")
    probe = _probe(monkeypatch)
    _stat_with_links(monkeypatch, probe, "continuity.db-wal", 0, attempts=2)

    assert store._validated_db_path() == store.db_path.resolve()
    assert probe.attempts == 3 and probe.sleeps == 2


def test_sc03_a_sidecar_anomaly_that_persists_is_still_refused_after_bounded_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    (tmp_path / ".auto-pm" / "continuity.db-shm").write_bytes(b"")
    probe = _probe(monkeypatch)
    _stat_with_links(monkeypatch, probe, "continuity.db-shm", 2, attempts=None)

    with pytest.raises(ContinuityStoreError, match="唯一链接的普通文件: continuity.db-shm"):
        store._validated_db_path()
    assert probe.attempts == _SIDECAR_ATTEMPTS and probe.sleeps == _SIDECAR_ATTEMPTS - 1


def test_sc04_a_sidecar_that_persistently_resolves_outside_the_workspace_is_still_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    probe = _probe(monkeypatch, fail_label="-wal", failures=None)

    with pytest.raises(ContinuityStoreError, match="解析后位于 workspace 外"):
        store._validated_db_path()
    assert probe.attempts == _SIDECAR_ATTEMPTS and probe.sleeps == _SIDECAR_ATTEMPTS - 1


def test_sc05_the_database_file_itself_is_never_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    probe = _probe(monkeypatch)
    _stat_with_links(monkeypatch, probe, "continuity.db", 2, attempts=None)

    with pytest.raises(ContinuityStoreError, match="唯一链接的普通文件: continuity.db"):
        store._validated_db_path()
    assert probe.attempts == 1 and probe.sleeps == 0


def test_sc06_a_sidecar_that_another_process_holds_for_a_moment_does_not_fail_the_strict_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    (tmp_path / ".auto-pm" / "continuity.db-shm").write_bytes(b"")
    probe = _probe(monkeypatch)
    failed = _unreadable(monkeypatch, "continuity.db-shm", failures=2)

    assert _strict_read(store) == 1
    assert len(failed) == 2 and probe.sleeps == 2


def test_sc07_a_sidecar_that_stays_locked_is_refused_busy_after_bounded_retries_without_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    (tmp_path / ".auto-pm" / "continuity.db-shm").write_bytes(b"")
    snapshot_parent = tmp_path.parent / f"{tmp_path.name}-snapshot-temp"
    snapshot_parent.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(snapshot_parent))
    probe = _probe(monkeypatch)
    failed = _unreadable(monkeypatch, "continuity.db-shm", failures=None)

    with pytest.raises(ContinuityStoreError, match="BUSY"):
        _strict_read(store)
    assert len(failed) == _SIDECAR_ATTEMPTS and probe.sleeps == _SIDECAR_ATTEMPTS - 1
    assert list(snapshot_parent.iterdir()) == []


def test_sc07b_a_persistent_busy_names_the_file_and_the_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TD-SW008-180：Windows 上驾驶舱开着时的 BUSY 以前只说“取不到稳定快照”，现在要带出是哪个文件、什么系统错误。"""

    store = _make_root(tmp_path)
    (tmp_path / ".auto-pm" / "continuity.db-shm").write_bytes(b"")
    _probe(monkeypatch)
    _unreadable(monkeypatch, "continuity.db-shm", failures=None)

    with pytest.raises(ContinuityStoreError, match="BUSY") as busy:
        _strict_read(store)
    assert "最后一次原因" in str(busy.value)
    assert "continuity.db-shm" in str(busy.value) and "PermissionError" in str(busy.value)


def test_sc07c_a_copy_the_os_refuses_is_named_in_the_busy_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    _probe(monkeypatch)

    def refuse(source: Any, target: Any, **kwargs: Any) -> Any:
        raise PermissionError(13, "Permission denied", str(source))

    monkeypatch.setattr(shutil, "copyfile", refuse)

    with pytest.raises(ContinuityStoreError, match="BUSY") as busy:
        _strict_read(store)
    assert "continuity.db: PermissionError" in str(busy.value)


def test_sc07d_a_sidecar_that_keeps_vanishing_while_it_is_read_names_the_file_in_the_busy_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hash pass opens a sidecar that SQLite deletes in between: retried, and the final BUSY says which file and why."""

    store = _make_root(tmp_path)
    (tmp_path / ".auto-pm" / "continuity.db-shm").write_bytes(b"")
    _probe(monkeypatch)

    def vanish(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if self.name == "continuity.db-shm" and "r" in mode:
            raise FileNotFoundError(2, "No such file or directory", str(self))
        return ORIGINAL_OPEN(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", vanish)

    with pytest.raises(ContinuityStoreError, match="BUSY") as busy:
        _strict_read(store)
    assert "continuity.db-shm: FileNotFoundError" in str(busy.value)


def test_sc07e_a_database_that_vanishes_during_the_copy_names_the_file_in_the_busy_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    _probe(monkeypatch)

    def vanish(source: Any, target: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError(2, "No such file or directory", str(source))

    monkeypatch.setattr(shutil, "copyfile", vanish)

    with pytest.raises(ContinuityStoreError, match="BUSY") as busy:
        _strict_read(store)
    assert "continuity.db: FileNotFoundError" in str(busy.value)


def test_sc08_a_database_file_that_cannot_be_read_is_never_retried_by_the_strict_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    probe = _probe(monkeypatch)
    failed = _unreadable(monkeypatch, "continuity.db", failures=None)

    with pytest.raises(ContinuityStoreError, match="文件无法读取: continuity.db"):
        _strict_read(store)
    assert len(failed) == 1 and probe.sleeps == 0


def _fake_wrong_links(monkeypatch: pytest.MonkeyPatch, names: set[str], links: int) -> None:
    """Report another link count for every ``stat`` of the named files."""

    def fake(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = ORIGINAL_STAT(self, follow_symlinks=follow_symlinks)
        if self.name in names and follow_symlinks:
            return os.stat_result(
                (result.st_mode, result.st_ino, result.st_dev, links, result.st_uid, result.st_gid, result.st_size, int(result.st_atime), int(result.st_mtime), int(result.st_ctime))
            )
        return result

    monkeypatch.setattr(Path, "stat", fake)


@pytest.mark.parametrize("links", [0, 2], ids=["links-0-delete-pending", "links-2-hard-linked"])
def test_sc09_the_inventory_treats_a_wrong_link_count_of_a_sidecar_as_a_retry_signal_and_of_the_database_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, links: int
) -> None:
    sidecar = tmp_path / "continuity.db-wal"
    sidecar.write_bytes(b"x")
    database = tmp_path / "continuity.db"
    database.write_bytes(b"x")
    _fake_wrong_links(monkeypatch, {"continuity.db-wal", "continuity.db"}, links)

    with pytest.raises(_ReadSnapshotAnomalyError, match="唯一链接的普通文件: continuity.db-wal") as caught:
        ContinuityStore._file_inventory(sidecar, required=False, transient=True)
    assert isinstance(caught.value, _ReadSnapshotDriftError)
    with pytest.raises(ContinuityStoreError, match="唯一链接的普通文件: continuity.db") as refused:
        ContinuityStore._file_inventory(database, required=True)
    assert not isinstance(refused.value, _ReadSnapshotDriftError)


def test_sc10_a_sidecar_that_is_not_a_regular_file_for_a_moment_is_retried_not_refused_by_the_inventory(tmp_path: Path) -> None:
    sidecar = tmp_path / "continuity.db-shm"
    sidecar.mkdir()

    with pytest.raises(_ReadSnapshotAnomalyError, match="唯一链接的普通文件: continuity.db-shm"):
        ContinuityStore._file_inventory(sidecar, required=False, transient=True)


def _inventory_anomaly(monkeypatch: pytest.MonkeyPatch, failures: int | None) -> list[int]:
    """Make the inventory of the source files raise the sidecar anomaly ``failures`` times (always when None); returns the calls that were failed."""

    original = ContinuityStore._source_inventory.__func__  # type: ignore[attr-defined]
    failed: list[int] = []

    def wrapped(cls: type[ContinuityStore], db_path: Path) -> Any:
        if failures is None or len(failed) < failures:
            failed.append(len(failed) + 1)
            raise _ReadSnapshotAnomalyError(f"Continuity Store 路径必须是唯一链接的普通文件: {db_path.name}-wal")
        return original(cls, db_path)

    monkeypatch.setattr(ContinuityStore, "_source_inventory", classmethod(wrapped))
    return failed


def test_sc11_a_sidecar_anomaly_met_by_the_inventory_for_a_moment_does_not_fail_the_strict_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _make_root(tmp_path)
    probe = _probe(monkeypatch)
    failed = _inventory_anomaly(monkeypatch, failures=2)

    assert _strict_read(store) == 1
    assert len(failed) == 2 and probe.sleeps == 2


def test_sc12_a_sidecar_anomaly_that_persists_through_the_inventory_is_refused_with_its_own_message_after_bounded_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _make_root(tmp_path)
    probe = _probe(monkeypatch)
    failed = _inventory_anomaly(monkeypatch, failures=None)

    with pytest.raises(ContinuityStoreError, match="唯一链接的普通文件: continuity.db-wal") as refused:
        _strict_read(store)
    assert "BUSY" not in str(refused.value)
    assert len(failed) == _SIDECAR_ATTEMPTS and probe.sleeps == _SIDECAR_ATTEMPTS - 1
