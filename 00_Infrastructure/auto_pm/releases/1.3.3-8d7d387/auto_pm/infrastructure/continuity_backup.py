"""Online backup, verification and restore of the Continuity ledger (``.auto-pm/continuity.db``).

Why the SQLite backup API on top of the store's strict read snapshot, and not a plain file copy:

* The ledger runs in WAL mode, so committed events may live only in ``continuity.db-wal``.
  Copying ``continuity.db`` alone loses them; copying the pair while the cockpit writes can tear.
* Opening the live file with an ordinary connection is not side-effect free either: the last
  connection to close checkpoints the WAL into the main file and deletes the sidecars, so the
  ledger's bytes would change merely because it was backed up, and on Windows that connection
  meets the historical "database is locked" contention (TD-077).
* ``ContinuityStore._read_connection`` already solves both: it copies a byte-stable DB/WAL pair to
  a temporary directory outside the workspace (bounded retries, before/after inventories and
  content hashes; no share-deny handles, which made every read BUSY on Windows while the ledger was open) and opens that copy read-only. The SQLite backup API then turns the
  snapshot into one self-contained file (journal mode DELETE, no sidecars) that opens anywhere.

Every backup is verified before it is published: full ``integrity_check``, schema versions known
to this tool, and the whole event hash chain recomputed with the store's own formula. A manifest
next to each file records its SHA-256 so later byte tampering is reported as well.

Nothing here changes the store's schema, its hash chain or how it writes; restore only swaps
whole files, and it never deletes the ledger it replaces: those files are moved, untouched, into
the backup directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.infrastructure.continuity_store import (
    _KNOWN_SCHEMA_VERSIONS,
    ContinuityStore,
    ContinuityStoreError,
)
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    is_link_like,
    require_safe_workspace_path,
)

BACKUP_RELATIVE_DIR = Path(".auto-pm") / "backups" / "continuity"
MANIFEST_SCHEMA = "continuity-backup.v1"
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_BACKUP_NAME = re.compile(r"^continuity-(\d{8}T\d{6}Z)-e(\d+)(?:-(\d+))?\.db$")
# Checkpoint and handoff events carry caller-chosen identifiers; every other event id is derived from its hash,
# except the two event types below, whose writers derive the id from something else.  Those are checked against that
# one derivation (``_self_numbered_event_id``), not exempted: a forged id still breaks the chain.
_FREE_ID_EVENT_TYPES = frozenset({"CHECKPOINT_CREATED", "HANDOFF_CREATED"})
_SELF_NUMBERED_EVENT_TYPES = frozenset({"WORK_RELATION_ADDED", "RECLAIM_RISK_ACCEPTED"})


def _self_numbered_event_id(event_type: str, idempotency_key: str, payload: object) -> str:
    """The id the writer of this event type gives it.

    ``WORK_RELATION_ADDED`` (work_registry_service.add_relation): ``EVT-`` + first 16 hex of sha256(idempotency_key).
    ``RECLAIM_RISK_ACCEPTED`` (continuity_store, risk signature): ``RISK-`` + first 16 hex of the sha256 of the stored
    payload (which already holds ``signed_at``) dumped with sorted keys and ``ensure_ascii=False``.
    """

    if event_type == "WORK_RELATION_ADDED":
        return f"EVT-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:16].upper()}"
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f"RISK-{digest[:16].upper()}"


class ContinuityBackupError(ContinuityStoreError):
    """A backup, verification or restore step refused or failed."""


@dataclass(frozen=True)
class LedgerReport:
    """What one ledger file was found to contain; ``ok`` only when no finding was raised."""

    path: Path
    events: int
    head_event_id: str
    head_event_hash: str
    schema_versions: tuple[str, ...]
    integrity: str
    sha256: str
    size: int
    findings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "events": self.events,
            "head_event_id": self.head_event_id,
            "head_event_hash": self.head_event_hash,
            "schema_versions": list(self.schema_versions),
            "integrity": self.integrity,
            "sha256": self.sha256,
            "size": self.size,
            "ok": self.ok,
            "findings": list(self.findings),
        }


@dataclass(frozen=True)
class RestoreResult:
    """The restored ledger as re-read after the swap, and where the replaced files were kept."""

    restored_from: Path
    report: LedgerReport
    replaced_dir: Path | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    with path.open("rb+") as stream:
        os.fsync(stream.fileno())


def _chain_findings(conn: sqlite3.Connection) -> tuple[int, str, str, list[str]]:
    """Recompute every event hash in insertion order; report the first break by its 1-based position."""

    count = 0
    previous_hash = ""
    head_id = ""
    findings: list[str] = []
    rows = conn.execute(
        "SELECT event_id, aggregate_id, event_type, payload_json, previous_hash, event_hash, "
        "created_at, idempotency_key FROM events ORDER BY rowid"
    )
    for row in rows:
        count += 1
        if findings:
            continue
        event_id, aggregate_id, event_type, payload_json, stored_previous, stored_hash, created_at, idempotency_key = (
            str(value) for value in row
        )
        reason = ""
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            reason = "payload 不是合法 JSON"
        else:
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            expected = hashlib.sha256(
                f"{stored_previous}|{aggregate_id}|{event_type}|{canonical}|{created_at}".encode()
            ).hexdigest()
            if stored_previous != previous_hash:
                reason = "previous_hash 与上一条事件的 event_hash 不相接"
            elif stored_hash != expected:
                reason = "event_hash 与内容复算结果不一致（内容被改过）"
            elif event_type in _SELF_NUMBERED_EVENT_TYPES:
                if event_id != _self_numbered_event_id(event_type, idempotency_key, payload):
                    reason = "event_id 与该事件类型的编号规则不对应"
            elif event_type not in _FREE_ID_EVENT_TYPES and event_id != f"EVT-{expected[:16].upper()}":
                reason = "event_id 与 event_hash 不对应"
        if reason:
            findings.append(f"第 {count} 条链断裂（{event_id}）：{reason}")
        previous_hash = stored_hash
        head_id = event_id
    return count, head_id, previous_hash, findings


def inspect_connection(conn: sqlite3.Connection, path: Path, sha256: str, size: int) -> LedgerReport:
    """Run the full integrity check, the schema check and the hash-chain recomputation on one open ledger."""

    findings: list[str] = []
    try:
        integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as error:
        integrity_rows = [(f"无法检查: {error}",)]
    integrity = "; ".join(str(row[0]) for row in integrity_rows[:5]) or "无结果"
    if integrity != "ok":
        findings.append(f"SQLite 完整性检查失败：{integrity}")
    versions: tuple[str, ...] = ()
    try:
        versions = tuple(sorted({str(row[0]) for row in conn.execute("SELECT schema_version FROM schema_meta")}))
    except sqlite3.DatabaseError:
        findings.append("缺少 schema_meta，不是连续性账本")
    if versions and not set(versions).issubset(_KNOWN_SCHEMA_VERSIONS):
        findings.append(f"账本版本不被本工具识别：{', '.join(versions)}")
    elif not versions and not findings:
        findings.append("schema_meta 为空，不是已初始化的连续性账本")
    events, head_id, head_hash = 0, "", ""
    try:
        events, head_id, head_hash, chain = _chain_findings(conn)
        findings.extend(chain)
    except sqlite3.DatabaseError as error:
        findings.append(f"事件表无法读取：{error}")
    return LedgerReport(
        path=path,
        events=events,
        head_event_id=head_id,
        head_event_hash=head_hash,
        schema_versions=versions,
        integrity=integrity,
        sha256=sha256,
        size=size,
        findings=tuple(findings),
    )


def _backup_sort_key(path: Path) -> tuple[str, int]:
    match = _BACKUP_NAME.match(path.name)
    if match is None:
        return ("", 0)
    return (match.group(1), int(match.group(3) or 1))


def manifest_path(backup: Path) -> Path:
    """The JSON manifest that sits next to a backup file."""


    return backup.with_suffix(".json")


def verify_backup_file(path: str | Path) -> LedgerReport:
    """Verify one self-contained backup file without writing anything next to it."""

    backup = Path(path)
    if not backup.is_file() or is_link_like(backup):
        raise ContinuityBackupError(f"备份文件不存在或不是普通文件: {backup}")
    for suffix in ("-wal", "-journal"):
        sidecar = Path(f"{backup}{suffix}")
        if sidecar.exists() and sidecar.stat().st_size > 0:
            raise ContinuityBackupError(
                f"{backup.name} 旁边有未合并的 {suffix} 文件，不是本命令产出的单文件备份，拒绝校验"
            )
    digest = _sha256(backup)
    size = backup.stat().st_size
    # immutable=1: no locks, no -shm, no journal; the file is only read.
    uri = f"{backup.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            report = inspect_connection(conn, backup, digest, size)
    except sqlite3.DatabaseError as error:
        report = LedgerReport(backup, 0, "", "", (), f"无法打开: {error}", digest, size, (f"文件无法作为 SQLite 打开：{error}",))
    manifest = manifest_path(backup)
    extra: list[str] = []
    if manifest.is_file():
        try:
            recorded = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            extra.append(f"清单文件 {manifest.name} 无法读取")
        else:
            if recorded.get("sha256") != digest:
                extra.append(f"文件 SHA-256 与清单 {manifest.name} 记录的不一致（备份产生后被改动过）")
            if report.ok and recorded.get("events") != report.events:
                extra.append(f"事件条数 {report.events} 与清单记录的 {recorded.get('events')} 不一致")
    if extra:
        report = replace(report, findings=(*extra, *report.findings))
    return report


class ContinuityBackupService(ContinuityStore):
    """Back up, verify and restore this workspace's ledger; only reads the live file except during restore."""

    def __init__(self, workspace_root: str | Path, backup_dir: str | Path | None = None) -> None:
        super().__init__(workspace_root)
        selected = Path(backup_dir) if backup_dir is not None else self.workspace_root / BACKUP_RELATIVE_DIR
        try:
            self.backup_dir = require_safe_workspace_path(
                self.workspace_root, selected, label="Continuity backup directory"
            )
        except ControlRootGuardError as error:
            raise ContinuityBackupError(str(error)) from error

    # ---------------------------------------------------------------- backup
    def backup(self, *, keep: int | None = None, now: datetime | None = None) -> tuple[Path, LedgerReport]:
        """Take a consistent online copy of the live ledger, verify it, then publish it atomically."""

        self._require_control_root()
        if not self.db_path.is_file():
            raise ContinuityBackupError(f"账本不存在，无可备份: {self.db_path}")
        if keep is not None and keep < 1:
            raise ContinuityBackupError("--keep 至少为 1")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        taken_at = (now or self._utc_now()).astimezone(UTC)
        stamp = taken_at.strftime("%Y%m%dT%H%M%SZ")
        partial = self.backup_dir / f".partial-{stamp}-{os.getpid()}.db"
        try:
            with self._read_connection() as source, closing(sqlite3.connect(partial)) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=DELETE").fetchone()
            _fsync(partial)
            report = verify_backup_file(partial)
            if not report.ok:
                raise ContinuityBackupError("备份副本自检未通过：" + "；".join(report.findings))
            final = self._free_name(stamp, report.events)
            manifest = {
                "schema_version": MANIFEST_SCHEMA,
                "created_at": taken_at.isoformat(),
                "source": ".auto-pm/continuity.db",
                "file": final.name,
                "sha256": report.sha256,
                "size": report.size,
                "events": report.events,
                "head_event_id": report.head_event_id,
                "head_event_hash": report.head_event_hash,
                "schema_versions": list(report.schema_versions),
                "integrity": report.integrity,
            }
            os.replace(partial, final)
            manifest_path(final).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        finally:
            for leftover in (partial, *(Path(f"{partial}{suffix}") for suffix in _SIDECAR_SUFFIXES)):
                leftover.unlink(missing_ok=True)
        if keep is not None:
            self._prune(keep)
        return final, replace(report, path=final)

    def _free_name(self, stamp: str, events: int) -> Path:
        candidate = self.backup_dir / f"continuity-{stamp}-e{events}.db"
        serial = 2
        while candidate.exists() or manifest_path(candidate).exists():
            candidate = self.backup_dir / f"continuity-{stamp}-e{events}-{serial}.db"
            serial += 1
        return candidate

    def list_backups(self) -> list[Path]:
        """Backups produced by this command, oldest first."""

        if not self.backup_dir.is_dir():
            return []
        found = [
            path
            for path in self.backup_dir.iterdir()
            if path.is_file() and _BACKUP_NAME.match(path.name) is not None
        ]
        return sorted(found, key=_backup_sort_key)

    def _prune(self, keep: int) -> None:
        backups = self.list_backups()
        for old in backups[: max(0, len(backups) - keep)]:
            old.unlink(missing_ok=True)
            manifest_path(old).unlink(missing_ok=True)

    # ---------------------------------------------------------------- verify
    def verify_live(self) -> LedgerReport:
        """Verify the live ledger through the store's strict read snapshot (the live file is only read)."""

        if not self.db_path.is_file():
            raise ContinuityBackupError(f"账本不存在: {self.db_path}")
        with self._read_connection() as conn:
            # integrity_check inside the snapshot transaction sees the WAL-merged state.
            return inspect_connection(conn, self.db_path, "", self.db_path.stat().st_size)

    # ---------------------------------------------------------------- restore
    def restore(self, backup: str | Path, *, now: datetime | None = None) -> RestoreResult:
        """Replace the live ledger with a verified backup; the replaced files are moved aside, never deleted."""

        self._require_control_root()
        source = Path(backup).resolve()
        report = verify_backup_file(source)
        if not report.ok:
            raise ContinuityBackupError("备份未通过校验，拒绝恢复：" + "；".join(report.findings))
        db_path = self._validated_db_path()
        stamp = (now or self._utc_now()).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        staged = db_path.with_name(f"{db_path.name}.restoring")
        staged.unlink(missing_ok=True)
        shutil.copyfile(source, staged)
        _fsync(staged)
        if _sha256(staged) != report.sha256:
            staged.unlink(missing_ok=True)
            raise ContinuityBackupError("备份复制到账本目录时内容发生变化，已放弃恢复")
        replaced_dir: Path | None = None
        try:
            with self._exclusive_quiesce(db_path):
                replaced_dir = self._move_aside(db_path, stamp)
                os.replace(staged, db_path)
        finally:
            staged.unlink(missing_ok=True)
        restored = self.verify_live()
        if not restored.ok or (restored.events, restored.head_event_hash) != (
            report.events,
            report.head_event_hash,
        ):
            raise ContinuityBackupError(
                "恢复后复查与备份不一致；原账本保存在 "
                f"{replaced_dir or '（原来就没有账本）'}：" + "；".join(restored.findings)
            )
        return RestoreResult(source, restored, replaced_dir)

    @staticmethod
    @contextmanager
    def _exclusive_quiesce(db_path: Path) -> Iterator[None]:
        """Refuse while any other connection has the ledger open; fold the WAL so the moved file is whole.

        EXCLUSIVE locking mode set before the first access makes SQLite take the file lock itself
        instead of the shared-memory index, so it is refused by every other open connection, even
        an idle one, on Windows and POSIX alike.
        """

        if not db_path.exists():
            yield
            return
        try:
            with closing(sqlite3.connect(db_path, timeout=0.5, isolation_level=None)) as conn:
                conn.execute("PRAGMA locking_mode=EXCLUSIVE")
                conn.execute("BEGIN EXCLUSIVE")
                conn.execute("COMMIT")
                busy, _log, _done = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if int(busy) != 0:
                    raise ContinuityBackupError("账本正在被其他程序使用（驾驶舱开着？），请先关掉再恢复")
        except sqlite3.OperationalError as error:
            raise ContinuityBackupError(
                f"账本正在被其他程序使用（驾驶舱开着？），请先关掉再恢复：{error}"
            ) from error
        yield

    def _move_aside(self, db_path: Path, stamp: str) -> Path | None:
        present = [path for path in (db_path, *(Path(f"{db_path}{s}") for s in _SIDECAR_SUFFIXES)) if path.exists()]
        if not present:
            return None
        target = self.backup_dir / f"replaced-{stamp}"
        serial = 2
        while target.exists():
            target = self.backup_dir / f"replaced-{stamp}-{serial}"
            serial += 1
        target.mkdir(parents=True)
        moved: list[tuple[Path, Path]] = []
        try:
            for path in present:
                destination = target / path.name
                os.replace(path, destination)
                moved.append((path, destination))
        except OSError as error:
            for original, destination in reversed(moved):
                os.replace(destination, original)
            raise ContinuityBackupError(
                f"无法移开现有账本（Windows 上通常是驾驶舱还开着）：{error}"
            ) from error
        return target
