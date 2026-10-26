"""X02: ``continuity backup`` / ``verify-backup`` / ``restore-backup`` keep a verifiable spare copy of the ledger."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner, Result

from auto_pm.infrastructure.continuity_backup import (
    BACKUP_RELATIVE_DIR,
    ContinuityBackupError,
    ContinuityBackupService,
    verify_backup_file,
)

PROJECT = "SW-2026-008"


def _workspace(root: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    git("init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    git("add", "README.md", ".gitignore")
    git("-c", "user.name=Backup Test", "-c", "user.email=backup@example.invalid", "commit", "-m", "baseline")
    project = root / PROJECT
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        f"project_id: {PROJECT}\nproject_name: Backup Test\nstack: python\n", encoding="utf-8"
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [{"project_id": PROJECT, "project_root": PROJECT, "development_root": PROJECT}],
            }
        ),
        encoding="utf-8",
    )
    return root


def _cli(root: Path, *args: str, input_text: str | None = None) -> Result:
    return CliRunner().invoke(cli, ["-w", str(root), *args], input=input_text)


def _create_work(root: Path, work_id: str) -> None:
    result = _cli(
        root,
        "continuity",
        "work",
        "create",
        "--work-id",
        work_id,
        "--pid",
        PROJECT,
        "--kind",
        "TEST",
        "--title",
        f"Backup {work_id}",
        "--owner",
        "agent-a",
        "--scope",
        "README.md",
        "--idempotency-key",
        f"create-{work_id}",
        "--read-only",
    )
    assert result.exit_code == 0, result.output


def _resume(root: Path) -> Any:
    result = _cli(root, "pm", "resume", PROJECT, "--json")
    assert result.exit_code == 0, result.output
    start = result.output.index("{")
    return json.JSONDecoder().raw_decode(result.output[start:])[0]


def _ledger(root: Path) -> Path:
    return root / ".auto-pm" / "continuity.db"


def _files_state(db: Path) -> dict[str, tuple[bytes, int]]:
    state: dict[str, tuple[bytes, int]] = {}
    for path in (db, Path(f"{db}-wal"), Path(f"{db}-shm")):
        if path.exists():
            state[path.name] = (path.read_bytes(), path.stat().st_mtime_ns)
    return state


def _event_count(db: Path) -> int:
    with closing(sqlite3.connect(db)) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def _only_backup(root: Path) -> Path:
    backups = sorted((root / BACKUP_RELATIVE_DIR).glob("continuity-*.db"))
    assert len(backups) == 1, backups
    return backups[0]


def test_backup_while_the_ledger_is_open_copies_wal_events_and_leaves_the_ledger_byte_identical(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    db = _ledger(root)
    # A second open connection stands in for the running cockpit: it keeps the WAL un-merged.
    with closing(sqlite3.connect(db)) as cockpit:
        cockpit.execute("SELECT COUNT(*) FROM events").fetchone()
        _create_work(root, "WORK-BK-002")
        assert Path(f"{db}-wal").stat().st_size > 0
        expected_events = _event_count(db)
        before = _files_state(db)

        result = _cli(root, "continuity", "backup")

        assert result.exit_code == 0, result.output
        assert _files_state(db) == before
    backup = _only_backup(root)
    assert result.output.startswith(f"备份完成：{expected_events} 条事件，链头 EVT-")
    assert "完整性 ok" in result.output
    assert backup.name.endswith(f"-e{expected_events}.db")
    # One self-contained file plus its manifest: no -wal/-shm next to the copy.
    assert sorted(path.name for path in backup.parent.iterdir()) == sorted([backup.name, backup.with_suffix(".json").name])
    manifest = json.loads(backup.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifest["events"] == expected_events and manifest["schema_version"] == "continuity-backup.v1"
    report = verify_backup_file(backup)
    assert report.ok and report.events == expected_events and report.head_event_id == manifest["head_event_id"]


def test_a_tampered_event_in_the_copy_is_reported_by_position_and_fails(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    _create_work(root, "WORK-BK-002")
    assert _cli(root, "continuity", "backup").exit_code == 0
    backup = _only_backup(root)
    with closing(sqlite3.connect(backup)) as conn, conn:
        rowids = [row[0] for row in conn.execute("SELECT rowid FROM events ORDER BY rowid")]
        target = rowids[1]
        conn.execute(
            "UPDATE events SET payload_json=replace(payload_json, 'WORK-BK', 'WORK-XX') WHERE rowid=?",
            (target,),
        )

    result = _cli(root, "continuity", "verify-backup", str(backup))

    assert result.exit_code == 1
    assert "第 2 条链断裂" in result.output
    assert "SHA-256" in result.output


def test_verify_backup_without_an_argument_checks_the_live_ledger_read_only(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    before = _files_state(_ledger(root))

    result = _cli(root, "continuity", "verify-backup")

    assert result.exit_code == 0, result.output
    assert "账本校验：" in result.output and "0 处断裂" in result.output
    assert _files_state(_ledger(root)) == before


def test_restore_brings_back_the_exact_resume_view_and_keeps_the_replaced_ledger(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    saved_view = _resume(root)
    assert _cli(root, "continuity", "backup").exit_code == 0
    backup = _only_backup(root)
    _create_work(root, "WORK-BK-002")
    newer_events = _event_count(_ledger(root))
    assert _resume(root) != saved_view

    result = _cli(root, "continuity", "restore-backup", str(backup), "--yes")

    assert result.exit_code == 0, result.output
    assert result.output.startswith("恢复完成：")
    assert _resume(root) == saved_view
    replaced = sorted((root / BACKUP_RELATIVE_DIR).glob("replaced-*"))
    assert len(replaced) == 1
    assert _event_count(replaced[0] / "continuity.db") == newer_events
    # The restored ledger keeps working as a normal ledger afterwards.
    _create_work(root, "WORK-BK-003")


def test_restore_asks_first_and_does_nothing_on_no(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    assert _cli(root, "continuity", "backup").exit_code == 0
    backup = _only_backup(root)
    before = _files_state(_ledger(root))

    result = _cli(root, "continuity", "restore-backup", str(backup), input_text="n\n")

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert _files_state(_ledger(root)) == before


def test_restore_refuses_a_tampered_backup_and_leaves_the_ledger_alone(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    assert _cli(root, "continuity", "backup").exit_code == 0
    backup = _only_backup(root)
    with closing(sqlite3.connect(backup)) as conn, conn:
        conn.execute("UPDATE events SET created_at='2000-01-01T00:00:00+00:00' WHERE rowid=1")
    before = _files_state(_ledger(root))

    result = _cli(root, "continuity", "restore-backup", str(backup), "--yes")

    assert result.exit_code == 1
    assert "拒绝恢复" in result.output and "第 1 条链断裂" in result.output
    assert _files_state(_ledger(root)) == before
    assert not list((root / BACKUP_RELATIVE_DIR).glob("replaced-*"))


def test_restore_refuses_while_another_connection_is_reading(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    service = ContinuityBackupService(root)
    backup, _report = service.backup()
    _create_work(root, "WORK-BK-002")
    with closing(sqlite3.connect(_ledger(root))) as reader:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM events").fetchone()
        with pytest.raises(ContinuityBackupError, match="正在被其他程序使用"):
            service.restore(backup)
        reader.rollback()
    assert not list((root / BACKUP_RELATIVE_DIR).glob("replaced-*"))
    assert _event_count(_ledger(root)) > verify_backup_file(backup).events


def test_restore_onto_a_machine_that_lost_its_ledger(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    saved_view = _resume(root)
    backup, _report = ContinuityBackupService(root).backup()
    kept = tmp_path.parent / f"{tmp_path.name}-kept.db"
    _ledger(root).replace(kept)

    result = ContinuityBackupService(root).restore(backup)

    assert result.replaced_dir is None and result.report.ok
    assert _resume(root) == saved_view


def test_keep_prunes_only_when_asked(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    for _ in range(3):
        assert _cli(root, "continuity", "backup").exit_code == 0
    backups = ContinuityBackupService(root).list_backups()
    assert len(backups) == 3

    assert _cli(root, "continuity", "backup", "--keep", "2").exit_code == 0

    remaining = ContinuityBackupService(root).list_backups()
    assert len(remaining) == 2 and backups[0] not in remaining and backups[1] not in remaining
    assert all(path.with_suffix(".json").is_file() for path in remaining)
    listed = _cli(root, "continuity", "list-backups")
    assert listed.exit_code == 0 and listed.output.count("条事件") == 2


def test_backup_without_a_ledger_is_refused(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    result = _cli(root, "continuity", "backup")

    assert result.exit_code == 1
    assert "账本不存在" in result.output
    assert not (root / BACKUP_RELATIVE_DIR).exists()


def test_a_file_that_is_not_a_ledger_fails_verification(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _create_work(root, "WORK-BK-001")
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all" * 100)

    result = _cli(root, "continuity", "verify-backup", str(junk))

    assert result.exit_code == 1
    assert "未通过" in result.output
