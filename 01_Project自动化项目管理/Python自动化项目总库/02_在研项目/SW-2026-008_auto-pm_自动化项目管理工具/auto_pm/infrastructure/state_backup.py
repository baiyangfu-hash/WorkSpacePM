"""Off-site backup of the Continuity ledger to a private Git repository (``pm state-backup push`` / ``pull``).

Why: the ledger (``.auto-pm/continuity.db``) lives only on one computer.  A new computer must be able to pick the cockpit up where the old
one stopped, so a sanitised copy of the ledger goes to a private repository the user owns.

What leaves the computer, and what does not:

* The copy is taken with the existing online backup (``ContinuityBackupService``), never from the live file.
* In the *copy* every live ``execution_leases.lease_token`` becomes ``REDACTED:<fingerprint>``.  The live ledger is not touched, and the
  event hash chain only covers the ``events`` table, whose payloads hold token fingerprints, so the chain still verifies; that is checked
  on every push (the redacted copy is verified again, and its event count and head hash must equal the original's).
* The copy is then scanned: no original token may remain anywhere in the file (the file is vacuumed first, so freed pages do not hide
  one) and no known secret format (``auto_pm.domain.secret_patterns``) may match.  Any hit refuses the push; only labels are reported.
* Nothing about the computer goes into the manifest (no host name, no paths).

Credentials are never handled here: Git uses the user's own credential manager.  The remote is read from ``scripts/state_backup.json``
and must be a plain ``https://host/owner/repo`` address without user information.  Old backups are never deleted and nothing is forced.

``pull`` only brings a backup home, verified, into ``.auto-pm/backups/continuity/``; it prints the ``restore-backup`` command and never
replaces the live ledger itself.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.lease_reclaim import lease_token_is_fenced
from auto_pm.domain.secret_patterns import secret_labels
from auto_pm.infrastructure.continuity_backup import (
    BACKUP_RELATIVE_DIR,
    MANIFEST_SCHEMA,
    ContinuityBackupError,
    ContinuityBackupService,
    LedgerReport,
    manifest_path,
    verify_backup_file,
)
from auto_pm.infrastructure.continuity_internal.codec import lease_token_fingerprint
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from auto_pm.infrastructure.git_timeout import run_git_bounded

STATE_MANIFEST_SCHEMA = "state-backup.v1"
MARKER_SCHEMA = "state-backup-marker.v1"
CONFIG_RELATIVE = Path("scripts") / "state_backup.json"
CACHE_RELATIVE = Path(".auto-pm") / "cache"
STAGE_RELATIVE = CACHE_RELATIVE / "state-stage"
REPO_RELATIVE = CACHE_RELATIVE / "state-repo"
MARKER_RELATIVE = CACHE_RELATIVE / "state-backup-last.json"
REMOTE_SUBDIR = Path("backups") / "continuity"
REDACTED_PREFIX = "REDACTED:"
CONFIG_KEYS = frozenset({"remote_url", "branch", "stale_after_hours"})
DEFAULT_BRANCH = "main"
DEFAULT_STALE_HOURS = 24
GIT_IDENTITY = (
    "-c",
    "user.name=auto-pm state backup",
    "-c",
    "user.email=state-backup@auto-pm.invalid",
    "-c",
    "commit.gpgsign=false",
)
_REMOTE_URL = re.compile(r"^https://[A-Za-z0-9.\-]+/[A-Za-z0-9._\-]+/[A-Za-z0-9._\-]+$")
_BRANCH = re.compile(r"^[A-Za-z0-9._/\-]{1,100}$")
_STAMP_DIR = re.compile(r"^(\d{8}T\d{6}Z)(?:-(\d+))?$")


class StateBackupError(ContinuityStoreError):
    """A push, pull or configuration step refused or failed."""


@dataclass(frozen=True)
class StateBackupConfig:
    remote_url: str
    branch: str = DEFAULT_BRANCH
    stale_after_hours: int = DEFAULT_STALE_HOURS


@dataclass(frozen=True)
class PushResult:
    name: str
    events: int
    redacted_tokens: int
    gz_size: int
    remote_commit: str
    dry_run: bool


@dataclass(frozen=True)
class PullResult:
    path: Path
    report: LedgerReport
    source_name: str


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------- configuration
def parse_config(raw: object) -> StateBackupConfig:
    """Strict, data-only parsing of ``scripts/state_backup.json``; anything unexpected is refused with the reason."""

    if not isinstance(raw, dict):
        raise StateBackupError("state_backup.json 必须是一个 JSON 对象")
    unknown = sorted(set(raw) - CONFIG_KEYS)
    if unknown:
        raise StateBackupError(f"state_backup.json 里有不认识的字段：{', '.join(unknown)}（只允许 {', '.join(sorted(CONFIG_KEYS))}）")
    url = raw.get("remote_url")
    if not isinstance(url, str) or _REMOTE_URL.match(url) is None:
        raise StateBackupError("remote_url 必须是 https://主机/账号/仓库 的形式，不得带用户名、口令、端口或查询参数")
    branch = raw.get("branch", DEFAULT_BRANCH)
    if not isinstance(branch, str) or _BRANCH.match(branch) is None or ".." in branch:
        raise StateBackupError("branch 不合法")
    hours = raw.get("stale_after_hours", DEFAULT_STALE_HOURS)
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 720:
        raise StateBackupError("stale_after_hours 必须是 1～720 之间的整数")
    return StateBackupConfig(remote_url=url, branch=branch, stale_after_hours=hours)


def load_config(workspace_root: str | Path) -> StateBackupConfig:
    path = Path(workspace_root) / CONFIG_RELATIVE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StateBackupError(f"缺少配置文件 {CONFIG_RELATIVE.as_posix()}（写明私有仓库的 https 地址）") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateBackupError(f"配置文件 {CONFIG_RELATIVE.as_posix()} 读不了或不是合法 JSON：{error}") from error
    return parse_config(raw)


# ---------------------------------------------------------------- the sanitised copy
def sanitize_ledger_copy(db: Path) -> tuple[int, list[str]]:
    """Replace every live lease token in *this copy* by its fingerprint and vacuum it; returns (count, the original tokens).

    Fenced rows (``RELEASED:`` / ``PARKED:``) and rows already redacted hold no secret and keep their meaning, so they are left alone.
    """

    originals: list[str] = []
    with closing(sqlite3.connect(db, isolation_level=None)) as conn:
        try:
            rows = conn.execute("SELECT run_id, lease_token FROM execution_leases").fetchall()
        except sqlite3.OperationalError:
            return 0, originals  # an older ledger without the table has nothing to redact
        conn.execute("BEGIN")
        for run_id, token in rows:
            text = str(token)
            if lease_token_is_fenced(text) or text.startswith(REDACTED_PREFIX):
                continue
            conn.execute(
                "UPDATE execution_leases SET lease_token=? WHERE run_id=?",
                (REDACTED_PREFIX + lease_token_fingerprint(text), run_id),
            )
            originals.append(text)
        conn.execute("COMMIT")
        conn.execute("VACUUM")  # rewrite the file: the replaced tokens must not survive in free pages
    return len(originals), originals


def leaked_secrets(db: Path, tokens: list[str]) -> list[str]:
    """What is still in the sanitised copy that must not leave: original tokens (by count) and known secret formats (by label)."""

    data = db.read_bytes()
    found: list[str] = []
    remaining = sum(1 for token in tokens if token.encode("utf-8") in data)
    if remaining:
        found.append(f"仍有 {remaining} 个原始租约口令留在副本里")
    labels = secret_labels(data.decode("utf-8", errors="backslashreplace"))
    found.extend(f"命中密钥格式：{label}" for label in labels)
    return found


@dataclass(frozen=True)
class _Snapshot:
    stage: Path
    gz: Path
    manifest_file: Path
    manifest: dict[str, object]
    base: str


def _build_snapshot(workspace: Path, taken_at: datetime) -> _Snapshot:
    """Online copy -> redact the copy -> verify -> scan -> gzip + manifest, all inside the stage folder."""

    stage = workspace / STAGE_RELATIVE
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        service = ContinuityBackupService(workspace, backup_dir=stage / "online")
        online, original = service.backup(now=taken_at)
        work = stage / "sanitised.db"
        shutil.copyfile(online, work)
        redacted, tokens = sanitize_ledger_copy(work)
        after = verify_backup_file(work)
        if not after.ok:
            raise StateBackupError("去掉租约口令后的副本没有通过校验，拒绝推送：" + "；".join(after.findings))
        if (after.events, after.head_event_hash) != (original.events, original.head_event_hash):
            raise StateBackupError("去掉租约口令后事件条数或链头与原账本不一致，拒绝推送")
        leaks = leaked_secrets(work, tokens)
        if leaks:
            raise StateBackupError("副本里仍有不该离开这台电脑的内容，拒绝推送：" + "；".join(leaks))
        base = f"continuity-{_stamp(taken_at)}-e{after.events}"
        gz = stage / f"{base}.db.gz"
        with work.open("rb") as source, gz.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as packed:
            shutil.copyfileobj(source, packed)
        manifest: dict[str, object] = {
            "schema_version": STATE_MANIFEST_SCHEMA,
            "created_at": taken_at.astimezone(UTC).isoformat(),
            "file": gz.name,
            "sha256": after.sha256,
            "size": after.size,
            "gz_sha256": _sha256_file(gz),
            "gz_size": gz.stat().st_size,
            "events": after.events,
            "head_event_id": after.head_event_id,
            "head_event_hash": after.head_event_hash,
            "schema_versions": list(after.schema_versions),
            "integrity": after.integrity,
            "sanitized": True,
            "redacted_lease_tokens": redacted,
        }
        manifest_file = stage / f"{base}.json"
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return _Snapshot(stage, gz, manifest_file, manifest, base)
    except ContinuityBackupError as error:
        shutil.rmtree(stage, ignore_errors=True)
        raise StateBackupError(str(error)) from error
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


# ---------------------------------------------------------------- the service
class StateBackupService:
    """Push a sanitised ledger copy to the private repository, bring one back, and report when the last push was."""

    def __init__(self, workspace_root: str | Path, *, remote_url: str | None = None, branch: str | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self._remote_override = remote_url
        self._branch_override = branch

    # ---- configuration
    def _config(self) -> StateBackupConfig:
        if self._remote_override is not None:
            return StateBackupConfig(self._remote_override, self._branch_override or DEFAULT_BRANCH)
        config = load_config(self.workspace_root)
        return StateBackupConfig(config.remote_url, self._branch_override or config.branch, config.stale_after_hours)

    # ---- git
    def _git(self, *args: str, cwd: Path, timeout: float = 180.0, check: bool = True) -> str:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            done = run_git_bounded(
                ["git", *GIT_IDENTITY, *args],
                default_timeout=timeout,
                error_cls=StateBackupError,
                where=cwd,
                cwd=cwd,
                capture_output=True,
                check=False,
                env=env,
            )
        except OSError as error:
            raise StateBackupError(f"无法运行 git：{error}") from error
        out = done.stdout.decode("utf-8", errors="backslashreplace").strip()
        if check and done.returncode != 0:
            err = done.stderr.decode("utf-8", errors="backslashreplace").strip()
            raise StateBackupError(f"git {args[0]} 失败（退出码 {done.returncode}）：{err or out}")
        return out

    def _sync_repo(self, config: StateBackupConfig) -> Path:
        """The local clone of the private repository, brought to the remote branch (it is a cache: nothing of value lives only here)."""

        repo = self.workspace_root / REPO_RELATIVE
        if not (repo / ".git").exists():
            if repo.exists() and any(repo.iterdir()):
                raise StateBackupError(f"{REPO_RELATIVE.as_posix()} 已存在但不是 Git 仓库；请检查后手动移走，本命令不删除它")
            repo.parent.mkdir(parents=True, exist_ok=True)
            self._git("clone", "--quiet", config.remote_url, str(repo), cwd=repo.parent, timeout=600.0)
        else:
            self._git("remote", "set-url", "origin", config.remote_url, cwd=repo)
        self._git("fetch", "--quiet", "origin", cwd=repo, timeout=600.0)
        remote_ref = f"refs/remotes/origin/{config.branch}"
        has_remote_branch = bool(self._git("for-each-ref", remote_ref, cwd=repo))
        if has_remote_branch:
            self._git("checkout", "--quiet", "--force", "-B", config.branch, f"origin/{config.branch}", cwd=repo)
        elif self._git("rev-parse", "--verify", "--quiet", "HEAD", cwd=repo, check=False):
            raise StateBackupError(f"私有仓库里没有分支 {config.branch}")
        else:
            self._git("symbolic-ref", "HEAD", f"refs/heads/{config.branch}", cwd=repo)  # an empty repository: the first push creates it
        return repo

    # ---- push
    def push(self, *, dry_run: bool = False, now: datetime | None = None) -> PushResult:
        config = self._config()
        taken_at = (now or datetime.now(UTC)).astimezone(UTC)
        snapshot = _build_snapshot(self.workspace_root, taken_at)
        try:
            events = int(str(snapshot.manifest["events"]))
            redacted = int(str(snapshot.manifest["redacted_lease_tokens"]))
            gz_size = int(str(snapshot.manifest["gz_size"]))
            if dry_run:
                return PushResult(snapshot.base, events, redacted, gz_size, "", True)
            commit = self._publish(config, snapshot, taken_at)
        finally:
            shutil.rmtree(snapshot.stage, ignore_errors=True)
        self._write_marker(taken_at, snapshot.base, snapshot.manifest, commit)
        return PushResult(snapshot.base, events, redacted, gz_size, commit, False)

    def _publish(self, config: StateBackupConfig, snapshot: _Snapshot, taken_at: datetime) -> str:
        repo = self._sync_repo(config)
        parent = repo / REMOTE_SUBDIR
        folder = parent / _stamp(taken_at)
        serial = 2
        while folder.exists():
            folder = parent / f"{_stamp(taken_at)}-{serial}"
            serial += 1
        folder.mkdir(parents=True)
        shutil.copyfile(snapshot.gz, folder / snapshot.gz.name)
        shutil.copyfile(snapshot.manifest_file, folder / snapshot.manifest_file.name)
        relative = folder.relative_to(repo).as_posix()
        self._git("add", "--", relative, cwd=repo)
        self._git("commit", "--quiet", "-m", f"账本备份 {folder.name}（{snapshot.manifest['events']} 条事件）", cwd=repo)
        refspec = f"HEAD:refs/heads/{config.branch}"
        try:
            self._git("push", "--quiet", "origin", refspec, cwd=repo, timeout=600.0)
        except StateBackupError:
            # someone (another computer) pushed first: our commit only adds a new folder, so replay it on top and try once more
            self._git("fetch", "--quiet", "origin", cwd=repo, timeout=600.0)
            self._git("rebase", "--quiet", f"origin/{config.branch}", cwd=repo)
            self._git("push", "--quiet", "origin", refspec, cwd=repo, timeout=600.0)
        head = self._git("rev-parse", "HEAD", cwd=repo)
        remote = self._git("ls-remote", "origin", f"refs/heads/{config.branch}", cwd=repo).split()
        if not remote or remote[0] != head:
            raise StateBackupError("推送后核对远程分支头与本地提交不一致，不能算备份成功")
        return head

    def _write_marker(self, taken_at: datetime, base: str, manifest: dict[str, object], commit: str) -> None:
        marker = self.workspace_root / MARKER_RELATIVE
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": MARKER_SCHEMA,
            "pushed_at": taken_at.astimezone(UTC).isoformat(),
            "backup": base,
            "events": manifest["events"],
            "head_event_hash": manifest["head_event_hash"],
            "remote_commit": commit,
        }
        partial = marker.with_name(marker.name + ".partial")
        partial.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(partial, marker)

    # ---- pull
    def pull(self, name: str | None = None) -> PullResult:
        config = self._config()
        repo = self._sync_repo(config)
        root = repo / REMOTE_SUBDIR
        folders = sorted(
            (path for path in root.iterdir() if path.is_dir() and _STAMP_DIR.match(path.name)),
            key=_folder_key,
        ) if root.is_dir() else []
        if not folders:
            raise StateBackupError("私有仓库里还没有任何账本备份")
        chosen = folders[-1]
        if name:
            matches = [path for path in folders if path.name == name or any(item.stem.startswith(name) for item in path.glob("*.json"))]
            if len(matches) != 1:
                raise StateBackupError(f"按名字 {name!r} 找到 {len(matches)} 份备份；可用的：{', '.join(path.name for path in folders[-5:])}")
            chosen = matches[0]
        manifests = sorted(chosen.glob("*.json"))
        if len(manifests) != 1:
            raise StateBackupError(f"备份目录 {chosen.name} 里应当正好有一份清单，实际 {len(manifests)} 份")
        manifest = _read_manifest(manifests[0])
        archive = chosen / str(manifest["file"])
        if not archive.is_file():
            raise StateBackupError(f"清单指向的文件 {manifest['file']} 不存在")
        if _sha256_file(archive) != manifest["gz_sha256"]:
            raise StateBackupError("压缩包的 SHA-256 与清单记录的不一致（文件被改动过或没传完整），拒绝使用")
        return self._place(archive, manifest, chosen.name)

    def _place(self, archive: Path, manifest: dict[str, object], source_name: str) -> PullResult:
        stage = self.workspace_root / STAGE_RELATIVE
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        try:
            unpacked = stage / "unpacked.db"
            with gzip.open(archive, "rb") as packed, unpacked.open("wb") as target:
                shutil.copyfileobj(packed, target)
            if _sha256_file(unpacked) != manifest["sha256"]:
                raise StateBackupError("解压后的账本 SHA-256 与清单记录的不一致，拒绝使用")
            directory = self.workspace_root / BACKUP_RELATIVE_DIR
            directory.mkdir(parents=True, exist_ok=True)
            final = _free_backup_name(directory, str(manifest["file"]).removesuffix(".db.gz"))
            shutil.copyfile(unpacked, final)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        local_manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "created_at": manifest["created_at"],
            "source": "state-backup",
            "file": final.name,
            "sha256": manifest["sha256"],
            "size": manifest["size"],
            "events": manifest["events"],
            "head_event_id": manifest["head_event_id"],
            "head_event_hash": manifest["head_event_hash"],
            "schema_versions": manifest["schema_versions"],
            "integrity": manifest["integrity"],
            "sanitized": True,
        }
        manifest_path(final).write_text(json.dumps(local_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = verify_backup_file(final)
        if not report.ok or (report.events, report.head_event_hash) != (manifest["events"], manifest["head_event_hash"]):
            final.unlink(missing_ok=True)
            manifest_path(final).unlink(missing_ok=True)
            raise StateBackupError("取回的备份没有通过校验，已放弃：" + "；".join(report.findings or ("事件条数或链头与清单不符",)))
        return PullResult(final, report, source_name)


def _folder_key(path: Path) -> tuple[str, int]:
    match = _STAMP_DIR.match(path.name)
    assert match is not None  # callers filter on the pattern first
    return (match.group(1), int(match.group(2) or 1))


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateBackupError(f"清单 {path.name} 读不了：{error}") from error
    needed = ("schema_version", "file", "sha256", "gz_sha256", "events", "head_event_id", "head_event_hash", "schema_versions", "integrity", "size", "created_at")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != STATE_MANIFEST_SCHEMA:
        raise StateBackupError(f"清单 {path.name} 不是 {STATE_MANIFEST_SCHEMA}")
    missing = [key for key in needed if key not in manifest]
    if missing:
        raise StateBackupError(f"清单 {path.name} 缺字段：{', '.join(missing)}")
    if manifest.get("sanitized") is not True:
        raise StateBackupError(f"清单 {path.name} 没有标明已去掉租约口令，拒绝使用")
    file_name = str(manifest["file"])
    if "/" in file_name or "\\" in file_name or not file_name.endswith(".db.gz"):
        raise StateBackupError(f"清单 {path.name} 里的文件名不合法")
    return manifest


def _free_backup_name(directory: Path, base: str) -> Path:
    candidate = directory / f"{base}.db"
    serial = 2
    while candidate.exists() or manifest_path(candidate).exists():
        candidate = directory / f"{base}-{serial}.db"
        serial += 1
    return candidate


# ---------------------------------------------------------------- the read-only line for ``pm orient``
@dataclass(frozen=True)
class StateBackupStatus:
    state: str  # "none" | "fresh" | "stale" | "unreadable"
    hours_ago: float
    pushed_at: str
    events: int
    stale_after_hours: int

    def line(self) -> str:
        if self.state == "none":
            return "⚠️ [账本异地备份] 还没有做过异地备份；换电脑前必须做：python main.py pm state-backup push"
        if self.state == "unreadable":
            return "⚠️ [账本异地备份] 备份记录读不了；重新做一次：python main.py pm state-backup push"
        detail = f"最近一次 {self.hours_ago:.0f} 小时前（{self.pushed_at}），{self.events} 条事件"
        if self.state == "stale":
            return f"⚠️ [账本异地备份] {detail}，已超过 {self.stale_after_hours} 小时；请重新做：python main.py pm state-backup push"
        return f"[账本异地备份] {detail}"


def read_state_backup_status(workspace_root: str | Path, *, now: datetime | None = None) -> StateBackupStatus:
    """Read only the local marker file (no network, no Git); a missing marker means no backup was ever taken here."""

    root = Path(workspace_root)
    try:
        stale_hours = load_config(root).stale_after_hours
    except StateBackupError:
        stale_hours = DEFAULT_STALE_HOURS
    marker = root / MARKER_RELATIVE
    if not marker.is_file():
        return StateBackupStatus("none", 0.0, "", 0, stale_hours)
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("schema_version") != MARKER_SCHEMA:
            raise ValueError("schema")
        pushed = datetime.fromisoformat(str(data["pushed_at"]))
        events = int(data["events"])
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
        return StateBackupStatus("unreadable", 0.0, "", 0, stale_hours)
    hours = max(0.0, ((now or datetime.now(UTC)) - pushed).total_seconds() / 3600.0)
    state = "stale" if hours > stale_hours else "fresh"
    return StateBackupStatus(state, hours, pushed.astimezone(UTC).strftime("%Y-%m-%d %H:%MZ"), events, stale_hours)
