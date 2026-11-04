"""Off-site ledger backup: the copy that leaves the computer holds no lease token, still verifies, and comes back intact."""

from __future__ import annotations

import gzip
import json
import shutil
import socket
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from auto_pm.contracts.continuity import RunState
from auto_pm.infrastructure import state_backup as sb
from auto_pm.infrastructure.continuity_backup import verify_backup_file
from auto_pm.infrastructure.state_backup import StateBackupError, StateBackupService
from tests.core.test_continuity_execution_service import Clock, _checkpoint, _services, _start

TOKEN = "Tok-9fA3kLm2PqRsTuVwXyZ0123456789-live-lease-secret"
T0 = datetime(2026, 11, 4, 18, 0, 0, tzinfo=UTC)


def _ledger(root: Path) -> Path:
    return root / ".auto-pm" / "continuity.db"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A real ledger: a work item, a run holding a live lease (plaintext token), a checkpoint; plus one fenced (released) lease row."""

    root = tmp_path / "ws"
    root.mkdir()
    clock = Clock()
    _work, execution = _services(root, clock)
    _start(execution, lease_token=TOKEN)
    execution.transition_run("RUN-001", RunState.RUNNING, "agent-a", TOKEN, "to-running")
    _checkpoint(execution, lease_token=TOKEN)
    with closing(sqlite3.connect(_ledger(root))) as conn:
        conn.execute(
            "INSERT INTO execution_leases (run_id, owner_id, lease_token, expires_at, version, updated_at) VALUES (?,?,?,?,?,?)",
            ("RUN-OLD", "agent-z", "RELEASED:" + "ab" * 32, "2026-09-09T12:00:00+00:00", 3, "2026-09-09T12:00:00+00:00"),
        )
        conn.commit()
    return root


def _gunzip(archive: Path, target: Path) -> Path:
    with gzip.open(archive, "rb") as packed, target.open("wb") as out:
        out.write(packed.read())
    return target


def _tokens(db: Path) -> dict[str, str]:
    with closing(sqlite3.connect(db)) as conn:
        return {str(run): str(token) for run, token in conn.execute("SELECT run_id, lease_token FROM execution_leases")}


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        check=True,
        timeout=120,
    )
    return done.stdout.decode("utf-8", errors="backslashreplace").strip()


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """A bare repository with one commit on ``main`` (the private repository is like this)."""

    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--quiet", "-b", "main")
    (seed / "README.md").write_text("state\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "--quiet", "-m", "initial")
    _git(tmp_path, "init", "--quiet", "--bare", "-b", "main", str(bare))
    _git(seed, "push", "--quiet", str(bare), "main")
    return bare


# ---------------------------------------------------------------- the sanitised copy
def test_the_copy_holds_no_live_lease_token_and_the_live_ledger_is_untouched(workspace: Path) -> None:
    before = _tokens(_ledger(workspace))
    assert before["RUN-001"] == TOKEN

    snapshot = sb._build_snapshot(workspace, T0)  # noqa: SLF001
    try:
        copy = _gunzip(snapshot.gz, snapshot.stage / "check.db")
        tokens = _tokens(copy)
    finally:
        shutil.rmtree(snapshot.stage)

    assert tokens["RUN-001"].startswith("REDACTED:") and tokens["RUN-001"] != TOKEN and TOKEN not in tokens["RUN-001"]
    assert tokens["RUN-OLD"] == before["RUN-OLD"]  # a fenced row holds no secret and keeps its meaning
    assert snapshot.manifest["redacted_lease_tokens"] == 1
    assert _tokens(_ledger(workspace)) == before  # the live ledger is never changed by a backup


def test_the_event_hash_chain_of_the_redacted_copy_still_verifies(workspace: Path) -> None:
    """The mandatory check: redacting leases must not break the chain (the chain covers ``events`` only, which hold fingerprints)."""

    snapshot = sb._build_snapshot(workspace, T0)  # noqa: SLF001
    try:
        copy = _gunzip(snapshot.gz, snapshot.stage / "check.db")
        report = verify_backup_file(copy)
    finally:
        shutil.rmtree(snapshot.stage)

    assert report.ok, report.findings
    with closing(sqlite3.connect(_ledger(workspace))) as live:
        assert report.events == int(live.execute("SELECT COUNT(*) FROM events").fetchone()[0]) > 0
    assert report.head_event_hash == snapshot.manifest["head_event_hash"]


def test_no_original_token_survives_anywhere_in_the_file_not_even_in_free_pages(workspace: Path) -> None:
    snapshot = sb._build_snapshot(workspace, T0)  # noqa: SLF001
    try:
        raw = _gunzip(snapshot.gz, snapshot.stage / "check.db").read_bytes()
    finally:
        shutil.rmtree(snapshot.stage)

    assert TOKEN.encode() not in raw


def test_a_token_that_is_still_in_the_copy_refuses_the_push_and_leaves_nothing_behind(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb, "sanitize_ledger_copy", lambda db: (0, [TOKEN]))  # a redaction that did nothing

    with pytest.raises(StateBackupError) as refused:
        sb._build_snapshot(workspace, T0)  # noqa: SLF001

    assert "原始租约口令" in str(refused.value) and TOKEN not in str(refused.value)
    assert not (workspace / sb.STAGE_RELATIVE).exists()


def test_a_known_secret_format_in_the_ledger_refuses_the_push_and_is_reported_by_label_only(workspace: Path) -> None:
    secret = "ghp_" + "A1b2C3d4E5" * 4
    with closing(sqlite3.connect(_ledger(workspace))) as conn:
        conn.execute(
            "INSERT INTO execution_leases (run_id, owner_id, lease_token, expires_at, version, updated_at) VALUES (?,?,?,?,?,?)",
            ("RUN-LEAK", "agent-z", f"PARKED:{secret}", "2026-09-09T12:00:00+00:00", 1, "2026-09-09T12:00:00+00:00"),
        )
        conn.commit()

    with pytest.raises(StateBackupError) as refused:
        sb._build_snapshot(workspace, T0)  # noqa: SLF001

    assert "GitHub 令牌" in str(refused.value) and secret not in str(refused.value)
    assert not (workspace / sb.STAGE_RELATIVE).exists()


def test_the_manifest_says_what_the_file_is_and_nothing_about_this_computer(workspace: Path) -> None:
    snapshot = sb._build_snapshot(workspace, T0)  # noqa: SLF001
    try:
        text = snapshot.manifest_file.read_text(encoding="utf-8")
        manifest: dict[str, Any] = json.loads(text)
        digest = sb._sha256_file(_gunzip(snapshot.gz, snapshot.stage / "check.db"))  # noqa: SLF001
        gz_digest = sb._sha256_file(snapshot.gz)  # noqa: SLF001
    finally:
        shutil.rmtree(snapshot.stage)

    assert manifest["schema_version"] == "state-backup.v1" and manifest["sanitized"] is True
    assert manifest["created_at"] == T0.isoformat() and snapshot.base == f"continuity-20261104T180000Z-e{manifest['events']}"
    assert manifest["sha256"] == digest and manifest["gz_sha256"] == gz_digest and manifest["integrity"] == "ok"
    assert {"events", "head_event_id", "head_event_hash", "schema_versions", "size", "gz_size", "file"} <= set(manifest)
    for private in (socket.gethostname(), str(workspace), str(workspace.parent), TOKEN):
        assert private not in text


# ---------------------------------------------------------------- configuration
def test_the_repository_config_is_valid_and_strictly_parsed() -> None:
    config = sb.load_config(Path(__file__).resolve().parents[2])
    assert config.remote_url == "https://github.com/baiyangfu-hash/WorkSpacePM-state" and config.branch == "main"

    userinfo = "name" + ":" + "word"  # built at run time: a literal user:password@ address in the source would (rightly) trip the repository's secret scan
    for bad in (
        {"remote_url": f"https://{userinfo}@github.com/a/b"},
        {"remote_url": f"https://{'ghp_' + 'x' * 30}@github.com/a/b"},
        {"remote_url": "http://github.com/a/b"},
        {"remote_url": "https://github.com/a/b?x=1"},
        {"remote_url": "https://github.com/a/b", "token": "x"},
        {"remote_url": "https://github.com/a/b", "stale_after_hours": 0},
        {"remote_url": "https://github.com/a/b", "branch": "../x"},
        ["https://github.com/a/b"],
    ):
        with pytest.raises(StateBackupError):
            sb.parse_config(bad)


# ---------------------------------------------------------------- push -> pull round trip against a local bare repository
def test_a_dry_run_writes_nothing_anywhere(workspace: Path, remote: Path) -> None:
    service = StateBackupService(workspace, remote_url=str(remote))

    result = service.push(dry_run=True, now=T0)

    assert result.dry_run and result.redacted_tokens == 1 and result.events > 0
    assert not (workspace / sb.MARKER_RELATIVE).exists() and not (workspace / sb.STAGE_RELATIVE).exists()
    assert not (workspace / sb.REPO_RELATIVE).exists()
    assert _git(remote, "ls-tree", "-r", "--name-only", "main") == "README.md"


def test_push_then_pull_in_another_workspace_brings_the_same_verified_ledger_home(workspace: Path, remote: Path, tmp_path: Path) -> None:
    pushed = StateBackupService(workspace, remote_url=str(remote)).push(now=T0)
    again = StateBackupService(workspace, remote_url=str(remote)).push(now=T0 + timedelta(minutes=5))  # a second backup never replaces the first

    files = _git(remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert f"backups/continuity/20261104T180000Z/{pushed.name}.db.gz" in files
    assert f"backups/continuity/20261104T180500Z/{again.name}.json" in files and "README.md" in files
    assert _git(remote, "rev-parse", "main") == again.remote_commit  # the remote head was checked after the push
    marker = json.loads((workspace / sb.MARKER_RELATIVE).read_text(encoding="utf-8"))
    assert marker["remote_commit"] == again.remote_commit and marker["events"] == pushed.events

    other = tmp_path / "new-computer"
    other.mkdir()
    brought = StateBackupService(other, remote_url=str(remote)).pull()

    assert brought.report.ok and brought.report.events == pushed.events and brought.source_name == "20261104T180500Z"
    assert brought.path.parent == other / ".auto-pm" / "backups" / "continuity"
    assert not _ledger(other).exists()  # pull never creates or replaces the live ledger
    assert verify_backup_file(brought.path).ok
    assert "REDACTED:" in _tokens(brought.path)["RUN-001"]

    first = StateBackupService(other, remote_url=str(remote)).pull(name="20261104T180000Z")
    assert first.source_name == "20261104T180000Z" and first.path != brought.path


def test_a_push_after_another_computer_pushed_first_is_replayed_on_top(workspace: Path, remote: Path, tmp_path: Path) -> None:
    StateBackupService(workspace, remote_url=str(remote)).push(now=T0)
    rival = tmp_path / "rival"
    _git(tmp_path, "clone", "--quiet", str(remote), str(rival))
    (rival / "NOTES.md").write_text("other computer\n", encoding="utf-8")
    _git(rival, "add", "NOTES.md")
    _git(rival, "commit", "--quiet", "-m", "other computer")
    _git(rival, "push", "--quiet", "origin", "main")

    StateBackupService(workspace, remote_url=str(remote)).push(now=T0 + timedelta(minutes=1))

    files = _git(remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert "NOTES.md" in files and sum(1 for name in files if name.endswith(".db.gz")) == 2


@pytest.mark.parametrize("damage", ["archive", "db_digest", "not_sanitized"])
def test_a_tampered_backup_is_refused_on_pull(workspace: Path, remote: Path, tmp_path: Path, damage: str) -> None:
    StateBackupService(workspace, remote_url=str(remote)).push(now=T0)
    editor = tmp_path / "editor"
    _git(tmp_path, "clone", "--quiet", str(remote), str(editor))
    folder = editor / "backups" / "continuity" / "20261104T180000Z"
    archive = next(folder.glob("*.db.gz"))
    manifest_file = next(folder.glob("*.json"))
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if damage == "archive":
        archive.write_bytes(archive.read_bytes() + b"x")
    elif damage == "db_digest":
        manifest["sha256"] = "0" * 64
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        manifest["sanitized"] = False
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    _git(editor, "commit", "--quiet", "-am", "tamper")
    _git(editor, "push", "--quiet", "origin", "main")

    other = tmp_path / "new-computer"
    other.mkdir()
    with pytest.raises(StateBackupError):
        StateBackupService(other, remote_url=str(remote)).pull()

    assert not list((other / ".auto-pm" / "backups" / "continuity").glob("*.db")) if (other / ".auto-pm" / "backups").exists() else True


def test_pull_from_a_repository_without_backups_says_so(tmp_path: Path, remote: Path) -> None:
    other = tmp_path / "new-computer"
    other.mkdir()

    with pytest.raises(StateBackupError, match="还没有任何账本备份"):
        StateBackupService(other, remote_url=str(remote)).pull()


# ---------------------------------------------------------------- the line in ``pm orient``
def test_the_status_line_follows_the_local_marker_only(tmp_path: Path) -> None:
    now = T0 + timedelta(hours=3)
    assert sb.read_state_backup_status(tmp_path, now=now).state == "none"
    assert "还没有做过异地备份" in sb.read_state_backup_status(tmp_path, now=now).line()

    marker = tmp_path / sb.MARKER_RELATIVE
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"schema_version": sb.MARKER_SCHEMA, "pushed_at": T0.isoformat(), "events": 202}), encoding="utf-8")
    fresh = sb.read_state_backup_status(tmp_path, now=now)
    assert fresh.state == "fresh" and "3 小时前" in fresh.line() and "202 条事件" in fresh.line() and not fresh.line().startswith("⚠️")

    stale = sb.read_state_backup_status(tmp_path, now=T0 + timedelta(hours=30))
    assert stale.state == "stale" and stale.line().startswith("⚠️") and "30 小时前" in stale.line()

    marker.write_text("{not json", encoding="utf-8")
    assert sb.read_state_backup_status(tmp_path, now=now).state == "unreadable"
