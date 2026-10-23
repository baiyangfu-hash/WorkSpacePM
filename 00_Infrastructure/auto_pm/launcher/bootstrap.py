"""Stdlib-only, fail-closed release resolution and exact-tree verification."""
from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from typing import NamedTuple

RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
POINTER_SCHEMA = "release_pointer.v1"
MANIFEST_SCHEMA = "deployment_manifest.v1"
ACTIVE_POINTER = "active_release.json"
PREVIOUS_POINTER = "previous_release.json"
MANIFEST_FILE = "deployment_manifest.json"
RELEASES_DIR = "releases"
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400

EXIT_CONTAINER_INVALID = 2
EXIT_POINTER_INVALID = 3
EXIT_RELEASE_INVALID = 4
BYTECODE_DIR = "__pycache__"
BYTECODE_SUFFIX = ".pyc"
PURGE_COMMAND = "python -B 00_Infrastructure/auto_pm/launcher/launch.py --purge-bytecode"


class BootstrapError(Exception):
    """Resolution failure carrying a fail-closed process exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class BytecodeResidueError(BootstrapError):
    """Payload matches the manifest, but someone left Python bytecode caches in the release."""

    def __init__(self, slot: str, release_id: str, residue: list[str]) -> None:
        self.slot = slot
        self.release_id = release_id
        self.residue = tuple(residue)
        shown = "、".join(self.residue[:3]) + (" 等" if len(self.residue) > 3 else "")
        super().__init__(
            EXIT_RELEASE_INVALID,
            f"{slot} 发布 {release_id} 里有 {len(self.residue)} 处 Python 缓存（{shown}）："
            "有人在发布目录里不带 -B 运行过 Python。载荷文件本身完好，启动器不会退回旧版本。"
            f"清除方法（只删这些缓存，再重新校验）：{PURGE_COMMAND}",
        )


class Resolution(NamedTuple):
    """A verified release, the slot it came from, and why active was skipped (empty if it was not)."""

    release_dir: Path
    slot: str
    fallback_reason: str


def _is_link_or_reparse(path: Path) -> bool:
    """Identify a symlink or Windows reparse point without following it."""
    try:
        info = path.lstat()
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _read_pointer_release_id(container: Path, name: str) -> str | None:
    path = container / name
    if _is_link_or_reparse(path):
        raise BootstrapError(EXIT_POINTER_INVALID, f"{name} 不允许链接或重解析点")
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(EXIT_POINTER_INVALID, f"{name} 无法读取: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != POINTER_SCHEMA:
        raise BootstrapError(EXIT_POINTER_INVALID, f"{name} schema 不符")
    release_id = raw.get("release_id")
    if release_id is None:
        return None
    if not isinstance(release_id, str):
        raise BootstrapError(EXIT_POINTER_INVALID, f"{name} release_id 必须是字符串或 null")
    return release_id


def _manifest_files(container: Path, release_id: str) -> dict[str, str]:
    manifest_path = container / MANIFEST_FILE
    if _is_link_or_reparse(manifest_path):
        raise BootstrapError(EXIT_RELEASE_INVALID, "deployment manifest 不允许链接或重解析点")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(EXIT_RELEASE_INVALID, f"deployment manifest 无法读取: {exc}") from exc
    releases = manifest.get("releases") if isinstance(manifest, dict) else None
    entry = releases.get(release_id) if isinstance(releases, dict) else None
    files = entry.get("files") if isinstance(entry, dict) else None
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA or not isinstance(files, dict):
        raise BootstrapError(EXIT_RELEASE_INVALID, f"release 未登记于 manifest: {release_id!r}")
    parsed: dict[str, str] = {}
    for raw_path, digest in files.items():
        if not isinstance(raw_path, str) or not isinstance(digest, str):
            raise BootstrapError(EXIT_RELEASE_INVALID, "manifest files 必须为字符串映射")
        requested = Path(raw_path)
        if requested.is_absolute() or requested == Path(".") or ".." in requested.parts:
            raise BootstrapError(EXIT_RELEASE_INVALID, f"manifest 路径越界: {raw_path!r}")
        normalized = requested.as_posix()
        if normalized in parsed or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BootstrapError(EXIT_RELEASE_INVALID, f"manifest 条目无效: {raw_path!r}")
        parsed[normalized] = digest
    return parsed


def _is_bytecode_residue(directory: Path) -> bool:
    """A ``__pycache__`` directory holding nothing but plain ``*.pyc`` files."""
    if directory.name != BYTECODE_DIR:
        return False
    try:
        children = list(directory.iterdir())
    except OSError:
        return False
    for child in children:
        if _is_link_or_reparse(child) or not child.name.endswith(BYTECODE_SUFFIX):
            return False
        try:
            if not stat.S_ISREG(child.lstat().st_mode):
                return False
        except OSError:
            return False
    return True


def _verify_exact_tree(release_dir: Path, files: dict[str, str]) -> list[str]:
    """Require every payload node to match the manifest-derived exact tree.

    Unregistered ``__pycache__`` directories of plain ``*.pyc`` files are not raised on the spot:
    they are returned, so the caller can name them as bytecode residue instead of generic damage.
    Any other deviation raises first.
    """
    expected_files = set(files)
    expected_dirs: set[str] = set()
    for raw_path, expected_digest in files.items():
        requested = Path(raw_path)
        target = release_dir / requested
        if _is_link_or_reparse(target):
            raise BootstrapError(EXIT_RELEASE_INVALID, f"release 节点不允许链接或重解析点: {raw_path}")
        try:
            info = target.lstat()
        except OSError as exc:
            raise BootstrapError(EXIT_RELEASE_INVALID, f"release 文件缺失: {raw_path}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise BootstrapError(EXIT_RELEASE_INVALID, f"release 节点不是普通文件: {raw_path}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected_digest:
            raise BootstrapError(EXIT_RELEASE_INVALID, f"release SHA-256 不匹配: {raw_path}")
        parent = requested.parent
        while parent != Path("."):
            expected_dirs.add(parent.as_posix())
            parent = parent.parent

    residue: list[str] = []
    pending = [release_dir]
    while pending:
        directory = pending.pop()
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise BootstrapError(EXIT_RELEASE_INVALID, f"release 目录无法枚举: {directory}") from exc
        for child in children:
            relative = child.relative_to(release_dir).as_posix()
            if _is_link_or_reparse(child):
                raise BootstrapError(EXIT_RELEASE_INVALID, f"release 节点不允许链接或重解析点: {relative}")
            try:
                mode = child.lstat().st_mode
            except OSError as exc:
                raise BootstrapError(EXIT_RELEASE_INVALID, f"release 节点无法读取: {relative}") from exc
            if stat.S_ISDIR(mode):
                if relative not in expected_dirs and _is_bytecode_residue(child):
                    residue.append(relative)
                    continue
                if relative not in expected_dirs:
                    raise BootstrapError(EXIT_RELEASE_INVALID, f"release 存在未登记目录: {relative}")
                pending.append(child)
            elif stat.S_ISREG(mode):
                if relative not in expected_files:
                    raise BootstrapError(EXIT_RELEASE_INVALID, f"release 存在未登记文件: {relative}")
            else:
                raise BootstrapError(EXIT_RELEASE_INVALID, f"release 存在非普通节点: {relative}")
    return sorted(residue)


def _release_dir(container: Path, slot: str, release_id: str) -> Path:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} 非法 release-id: {release_id!r}")
    releases_root = container / RELEASES_DIR
    if _is_link_or_reparse(releases_root):
        raise BootstrapError(EXIT_CONTAINER_INVALID, "releases 目录不允许链接或重解析点")
    candidate = releases_root / release_id
    if _is_link_or_reparse(candidate):
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} release 不允许链接或重解析点")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(releases_root.resolve())
    except ValueError as exc:
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} release 路径越界: {release_id!r}") from exc
    if not resolved.is_dir():
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} release 目录缺失: {release_id!r}")
    return resolved


def _resolve_slot(container: Path, slot: str, release_id: str) -> Path:
    resolved = _release_dir(container, slot, release_id)
    residue = _verify_exact_tree(resolved, _manifest_files(container, release_id))
    if residue:
        raise BytecodeResidueError(slot, release_id, residue)
    return resolved


def _slot_release_id(container: Path, slot: str) -> str:
    if slot not in (ACTIVE_POINTER, PREVIOUS_POINTER):
        raise BootstrapError(EXIT_POINTER_INVALID, f"未知指针: {slot!r}")
    if _is_link_or_reparse(container) or not container.is_dir():
        raise BootstrapError(EXIT_CONTAINER_INVALID, f"容器布局无效: {container}")
    release_id = _read_pointer_release_id(container, slot)
    if release_id is None:
        raise BootstrapError(EXIT_POINTER_INVALID, f"{slot} 未初始化（release_id 为 null）")
    return release_id


def resolve_slot(container: Path, slot: str) -> tuple[Path, str]:
    return _resolve_slot(container, slot, _slot_release_id(container, slot)), slot


def resolve_release(container: Path) -> Resolution:
    """Resolve active, else previous, and say why active was skipped.

    Bytecode residue in active never falls back: the payload is intact and the fix is a cache purge,
    whereas silently running an older release hides the problem behind confusing downstream refusals.
    """
    try:
        release_dir, slot = resolve_slot(container, ACTIVE_POINTER)
        return Resolution(release_dir, slot, "")
    except BytecodeResidueError:
        raise
    except BootstrapError as active_error:
        active_failure = (active_error.exit_code, f"[{ACTIVE_POINTER}] {active_error}")
    try:
        release_dir, slot = resolve_slot(container, PREVIOUS_POINTER)
    except BootstrapError as previous_error:
        failures = [active_failure, (previous_error.exit_code, f"[{PREVIOUS_POINTER}] {previous_error}")]
        worst = max(code for code, _ in failures)
        raise BootstrapError(worst, "双槽均无效: " + " | ".join(message for _, message in failures)) from None
    return Resolution(release_dir, slot, active_failure[1])


def resolve_with_fallback(container: Path) -> tuple[Path, str]:
    """Resolve active then previous; every resolved release is exact-verified.

    Callers that run the release must use :func:`resolve_release` and report ``fallback_reason``.
    """
    resolution = resolve_release(container)
    return resolution.release_dir, resolution.slot


def purge_bytecode(container: Path) -> list[str]:
    """Delete bytecode residue from the active and previous releases; touch nothing else.

    A release is purged only when its payload otherwise matches the manifest exactly, so a damaged
    release is never modified. Active problems raise; a damaged previous is left for
    :func:`resolve_release` to report. Returns removed directories as ``<release-id>/<path>``.
    """
    if _is_link_or_reparse(container) or not container.is_dir():
        raise BootstrapError(EXIT_CONTAINER_INVALID, f"容器布局无效: {container}")
    removed: list[str] = []
    for slot in (ACTIVE_POINTER, PREVIOUS_POINTER):
        try:
            release_id = _read_pointer_release_id(container, slot)
            if release_id is None:
                continue
            release_dir = _release_dir(container, slot, release_id)
            residue = _verify_exact_tree(release_dir, _manifest_files(container, release_id))
        except BootstrapError:
            if slot == ACTIVE_POINTER:
                raise
            continue
        for relative in residue:
            directory = release_dir / relative
            if not _is_bytecode_residue(directory):
                raise BootstrapError(EXIT_RELEASE_INVALID, f"缓存目录在清除前被改动，已停止: {release_id}/{relative}")
            for child in directory.iterdir():
                child.unlink()
            directory.rmdir()
            removed.append(f"{release_id}/{relative}")
    return removed
