"""TD-SW008 073: the inbox tables belong to the base ledger DDL, not to a lazy first-use create.

An older ledger (v8 without the tables, or with them created lazily and holding rows) must gain / keep them on ``initialize``
without a schema-version bump and without losing a row; a second ``initialize`` must be a no-op.
"""

from __future__ import annotations

import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from auto_pm.infrastructure.continuity_store import ContinuityStore

_NOW = "2026-11-08T20:00:00+00:00"
_TABLES = ("intake_items", "planning_draft_intake_bindings", "intake_notes")


def _git(root: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def _store(root: Path) -> ContinuityStore:
    _git(root, "init")
    (root / "README.md").write_text("x\n", encoding="utf-8", errors="replace")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "baseline")
    store = ContinuityStore(root)
    store.initialize(_NOW, "test")
    return store


def _tables(db: Path) -> set[str]:
    with closing(sqlite3.connect(db)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _version(db: Path) -> list[str]:
    with closing(sqlite3.connect(db)) as conn:
        return [str(row[0]) for row in conn.execute("SELECT schema_version FROM schema_meta")]


def test_a_fresh_ledger_has_the_inbox_tables_straight_after_initialize(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert set(_TABLES) <= _tables(store.db_path)


def test_an_old_ledger_without_the_tables_gains_them_and_keeps_its_version_and_rows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    before_version = _version(store.db_path)
    with closing(sqlite3.connect(store.db_path)) as conn:
        for table in reversed(_TABLES):
            conn.execute(f"DROP TABLE {table}")
        before_migrations = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        conn.commit()
    assert not set(_TABLES) & _tables(store.db_path)

    store.initialize(_NOW, "test")

    assert set(_TABLES) <= _tables(store.db_path)
    assert _version(store.db_path) == before_version  # no bump: an older release can still open this ledger
    with closing(sqlite3.connect(store.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == before_migrations


def test_initialize_keeps_inbox_rows_that_a_lazy_create_already_stored_and_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with closing(sqlite3.connect(store.db_path)) as conn:
        conn.execute(
            "INSERT INTO intake_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ITEM-1", "REQ-1", "SW-TEST-001", 1, "t", "AWAITING", "h", "{}", _NOW, _NOW),
        )
        conn.execute(  # D-357: the raw-note table follows the same rule
            "INSERT INTO intake_notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("NOTE-1", "REQ-N1", "SW-TEST-001", 1, "t", "RAW", "{}", None, _NOW, _NOW),
        )
        conn.commit()

    store.initialize(_NOW, "test")
    store.initialize(_NOW, "test")

    with closing(sqlite3.connect(store.db_path)) as conn:
        rows = conn.execute("SELECT item_id, seq FROM intake_items").fetchall()
        notes = conn.execute("SELECT note_id, seq, status FROM intake_notes").fetchall()
    assert rows == [("ITEM-1", 1)]
    assert notes == [("NOTE-1", 1, "RAW")]
