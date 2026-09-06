"""Fail-closed dual-slot deployment container services (NG-WP-12).

The stable deployment container holds immutable releases under ``releases/``
and two pointer files (``active_release.json`` / ``previous_release.json``).
Release identifiers must be single path components, every resolved release
directory must stay physically contained in ``releases/``, pointer writes are
atomic (same-volume temp file, flush, ``os.replace``), and manifest
verification compares per-file SHA-256 digests.  Any doubt fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final

__all__ = [
    "DeploymentContainer",
    "DeploymentError",
    "DeploymentFileError",
    "DeploymentStateError",
    "ReleasePointer",
]

RELEASE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
POINTER_SCHEMA: Final[str] = "release_pointer.v1"
MANIFEST_SCHEMA: Final[str] = "deployment_manifest.v1"
ACTIVE_POINTER: Final[str] = "active_release.json"
PREVIOUS_POINTER: Final[str] = "previous_release.json"
POINTER_FILES: Final[tuple[str, ...]] = (ACTIVE_POINTER, PREVIOUS_POINTER)
MANIFEST_FILE: Final[str] = "deployment_manifest.json"
RELEASES_DIR: Final[str] = "releases"
LOCK_FILE: Final[str] = ".lock"

_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


class DeploymentError(Exception):
    """Base error for deployment container operations."""


class DeploymentStateError(DeploymentError):
    """Raised when an operation is invalid for the container state."""


class DeploymentFileError(DeploymentError):
    """Raised when containment, pointer, manifest or lock integrity fails."""


def _is_reparse_point(path: Path) -> bool:
    """Return whether *path* is a Windows reparse point without following it."""
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


class ReleasePointer:
    """A parsed pointer file state; ``release_id`` is ``None`` when uninitialized."""

    __slots__ = ("slot", "release_id", "updated_at")

    def __init__(self, slot: str, release_id: str | None, updated_at: str | None) -> None:
        self.slot = slot
        self.release_id = release_id
        self.updated_at = updated_at

    def __repr__(self) -> str:
        return f"ReleasePointer(slot={self.slot!r}, release_id={self.release_id!r})"


class DeploymentContainer(AbstractContextManager["DeploymentContainer"]):
    """A fail-closed view of a dual-slot deployment container."""

    def __init__(self, container_root: Path) -> None:
        self.container_root = Path(container_root).resolve()
        if not self.container_root.is_dir():
            raise DeploymentFileError(f"容器根不存在或不是目录: {self.container_root}")
        self.releases_root = self.container_root / RELEASES_DIR
        if self.releases_root.is_symlink() or _is_reparse_point(self.releases_root):
            raise DeploymentFileError(f"releases 目录不允许是链接: {self.releases_root}")
        self.releases_root = self.releases_root.resolve()
        if not self.releases_root.is_dir():
            raise DeploymentFileError(f"releases 目录不存在或不是目录: {self.releases_root}")

    def __enter__(self) -> DeploymentContainer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    # -- release identifiers -------------------------------------------------

    def validate_release_id(self, release_id: str) -> str:
        """Return *release_id* only when it is a safe single path component."""
        if not isinstance(release_id, str) or not RELEASE_ID_PATTERN.fullmatch(release_id):
            raise DeploymentFileError(
                f"非法 release-id（仅允许字母/数字/./_/-，且不以符号开头）: {release_id!r}"
            )
        return release_id

    def release_dir(self, release_id: str, *, must_exist: bool = False) -> Path:
        """Return the contained release directory for *release_id*.

        With ``must_exist`` the directory must physically exist as a plain
        directory (no symlink/reparse indirection anywhere on the final
        component).
        """
        validated = self.validate_release_id(release_id)
        candidate = self.releases_root / validated
        try:
            candidate.relative_to(self.releases_root)
        except ValueError as exc:  # pragma: no cover - regex already forbids escapes
            raise DeploymentFileError(f"release 路径越界: {release_id!r}") from exc
        if must_exist:
            if candidate.is_symlink() or _is_reparse_point(candidate):
                raise DeploymentFileError(f"release 目录不允许是链接: {candidate}")
            resolved = candidate.resolve()
            try:
                resolved.relative_to(self.releases_root)
            except ValueError as exc:
                raise DeploymentFileError(f"release 路径解析后越界: {release_id!r}") from exc
            if not resolved.is_dir():
                raise DeploymentFileError(f"release 目录不存在或不是目录: {resolved}")
            return resolved
        return candidate

    # -- pointers ------------------------------------------------------------

    def pointer_path(self, name: str) -> Path:
        """Return the pointer file path for a known pointer name."""
        if name not in POINTER_FILES:
            raise DeploymentStateError(f"未知指针文件: {name!r}（允许: {POINTER_FILES}）")
        return self.container_root / name

    def read_pointer(self, name: str) -> ReleasePointer:
        """Read a pointer file; a missing file is an uninitialized pointer."""
        path = self.pointer_path(name)
        if not path.exists():
            return ReleasePointer(slot=name, release_id=None, updated_at=None)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeploymentFileError(f"指针文件损坏: {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise DeploymentFileError(f"指针文件顶层必须是对象: {path}")
        if raw.get("schema_version") != POINTER_SCHEMA:
            raise DeploymentFileError(f"指针 schema_version 不符: {path}")
        if raw.get("slot") != name:
            raise DeploymentFileError(f"指针 slot 字段与文件名不符: {path}")
        release_id = raw.get("release_id")
        if release_id is not None:
            if not isinstance(release_id, str):
                raise DeploymentFileError(f"指针 release_id 必须是字符串或 null: {path}")
            self.validate_release_id(release_id)
        updated_at = raw.get("updated_at")
        if updated_at is not None and not isinstance(updated_at, str):
            raise DeploymentFileError(f"指针 updated_at 必须是字符串或 null: {path}")
        return ReleasePointer(slot=name, release_id=release_id, updated_at=updated_at)

    def write_pointer(self, name: str, release_id: str) -> None:
        """Atomically point *name* at an existing release directory."""
        validated = self.validate_release_id(release_id)
        release_path = self.release_dir(validated, must_exist=True)
        pointer = self.pointer_path(name)
        payload: dict[str, object] = {
            "schema_version": POINTER_SCHEMA,
            "slot": name,
            "release_id": validated,
            "release_path": release_path.name,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._atomic_write_json(pointer, payload)

    # -- manifest ------------------------------------------------------------

    def read_manifest(self) -> dict[str, dict[str, dict[str, str]]]:
        """Read ``deployment_manifest.json``; missing file is an empty manifest."""
        path = self.container_root / MANIFEST_FILE
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeploymentFileError(f"manifest 损坏: {path}: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != MANIFEST_SCHEMA:
            raise DeploymentFileError(f"manifest schema_version 不符: {path}")
        releases = raw.get("releases")
        if not isinstance(releases, dict):
            raise DeploymentFileError(f"manifest releases 必须是对象: {path}")
        parsed: dict[str, dict[str, dict[str, str]]] = {}
        for release_id, entry in releases.items():
            self.validate_release_id(release_id)
            if not isinstance(entry, dict):
                raise DeploymentFileError(f"manifest release 条目必须是对象: {release_id}")
            files = entry.get("files")
            if not isinstance(files, dict):
                raise DeploymentFileError(f"manifest files 必须是对象: {release_id}")
            digests: dict[str, str] = {}
            for rel_path, digest in files.items():
                if not isinstance(rel_path, str) or not isinstance(digest, str):
                    raise DeploymentFileError(f"manifest files 键值必须是字符串: {release_id}")
                digests[rel_path] = digest
            parsed[release_id] = {"files": digests}
        return parsed

    def verify_release(self, release_id: str) -> int:
        """Verify the exact manifest tree of *release_id*; return file count.

        Every payload node must be accounted for: registered paths must be
        regular files with matching SHA-256 digests, while directories are
        allowed only when they are parents of registered files.  Any extra
        regular file, directory, link/reparse point, or non-regular node
        fails closed before the release can be trusted.
        """
        validated = self.validate_release_id(release_id)
        manifest = self.read_manifest()
        entry = manifest.get(validated)
        if entry is None:
            raise DeploymentStateError(f"manifest 中不存在 release: {validated}")
        release_path = self.release_dir(validated, must_exist=True)
        offenders: list[str] = []
        expected_files: set[str] = set()
        expected_directories: set[str] = set()
        for rel_path, digest in entry["files"].items():
            requested = Path(rel_path)
            if requested.is_absolute() or requested == Path(".") or ".." in requested.parts:
                offenders.append(f"{rel_path}（路径越界）")
                continue
            target = release_path / requested
            try:
                target.resolve().relative_to(release_path)
            except ValueError:
                offenders.append(f"{rel_path}（路径越界）")
                continue
            normalized = requested.as_posix()
            expected_files.add(normalized)
            parent = requested.parent
            while parent != Path("."):
                expected_directories.add(parent.as_posix())
                parent = parent.parent
            if target.is_symlink() or _is_reparse_point(target):
                offenders.append(f"{rel_path}（不允许链接或重解析点）")
                continue
            if not target.is_file():
                offenders.append(f"{rel_path}（文件缺失）")
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != digest:
                offenders.append(f"{rel_path}（SHA-256 不匹配）")
        pending: list[Path] = [release_path]
        while pending:
            current = pending.pop()
            try:
                children = list(current.iterdir())
            except OSError as exc:
                offenders.append(f"{current.relative_to(release_path).as_posix()}（无法枚举: {exc}）")
                continue
            for child in children:
                relative = child.relative_to(release_path).as_posix()
                if child.is_symlink() or _is_reparse_point(child):
                    offenders.append(f"{relative}（不允许链接或重解析点）")
                elif child.is_dir():
                    if relative not in expected_directories:
                        offenders.append(f"{relative}（未注册目录）")
                    pending.append(child)
                elif child.is_file():
                    if relative not in expected_files:
                        offenders.append(f"{relative}（未注册文件）")
                else:
                    offenders.append(f"{relative}（不支持的有效载荷节点）")
        if offenders:
            raise DeploymentFileError(
                f"release {validated} manifest 核验失败: " + "; ".join(offenders)
            )
        return len(entry["files"])

    # -- container lock ------------------------------------------------------

    def lock_path(self) -> Path:
        """Return the container lock file path."""
        return self.container_root / LOCK_FILE

    def acquire_lock(self) -> AbstractContextManager[None]:
        """Exclusively create ``.lock``; an existing lock fails closed.

        A crashed holder leaves the lock behind on purpose: recovery is a
        deliberate human action, never an automatic steal.
        """
        return _ContainerLock(self.lock_path())

    # -- internals -----------------------------------------------------------

    def _atomic_write_json(self, target: Path, payload: dict[str, object]) -> None:
        """Write *payload* to *target* via a same-directory temp file + replace."""
        text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        directory = target.parent
        handle, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=directory)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:  # pragma: no cover - platform without dir fd support
            return
        try:
            os.fsync(dir_fd)
        except OSError:  # pragma: no cover - Windows/POSIX differences
            pass
        finally:
            os.close(dir_fd)


class _ContainerLock(AbstractContextManager[None]):
    """Exclusive ``O_CREAT|O_EXCL`` lock file guard."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    def __enter__(self) -> None:
        try:
            self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise DeploymentStateError(
                f"容器已被锁定（存在 {self._path}）；如确认无进程持锁请人工移除"
            ) from exc
        os.write(self._fd, f"pid={os.getpid()}\n".encode("ascii"))
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            self._path.unlink(missing_ok=True)
