"""DatabaseManager 连接隔离：不同库路径的两个实例互不串用连接。"""
import os
import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.database_manager import DatabaseManager


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_two_managers_in_one_thread_write_to_their_own_files(tmp_path: Path) -> None:
    first_path = tmp_path / "first.db"
    second_path = tmp_path / "second.db"
    first = DatabaseManager(str(first_path))
    second = DatabaseManager(str(second_path))
    try:
        with first.session() as conn:
            conn.execute("INSERT INTO daily_stats(date, study_minutes) VALUES ('2026-01-01', 7)")
        with second.session() as conn:
            rows = conn.execute("SELECT * FROM daily_stats").fetchall()
        assert rows == []
        assert second.get_connection() is not first.get_connection()
        assert "daily_stats" in _tables(second_path)
    finally:
        first.close()
        second.close()


def test_close_only_closes_its_own_connection(tmp_path: Path) -> None:
    first = DatabaseManager(str(tmp_path / "a.db"))
    second = DatabaseManager(str(tmp_path / "b.db"))
    try:
        first.close()
        with second.session() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        second.close()


def test_each_thread_gets_its_own_connection(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "t.db"))
    seen: list[sqlite3.Connection] = []

    def open_and_close_in_worker() -> None:
        connection = manager.get_connection()
        seen.append(connection)
        manager.close()

    worker = threading.Thread(target=open_and_close_in_worker)
    try:
        worker.start()
        worker.join()
        assert len(seen) == 1
        assert seen[0] is not manager.get_connection()
    finally:
        manager.close()
