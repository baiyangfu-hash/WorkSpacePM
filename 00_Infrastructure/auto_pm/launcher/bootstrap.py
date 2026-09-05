"""Dual-slot release resolver for the stable deployment container (stdlib-only).

Shared by ``launcher/launch.py`` and the workspace-root ``main.py`` bootstrap.
This module must never import ``auto_pm``: it runs before any release has been
located, so only the Python standard library is allowed.

Resolution order (NG-WP-13): the active pointer is the only production source;
when the active slot is invalid, the approved previous pointer is the sole
fallback; when both slots fail, the caller must exit non-zero.

Failure exit codes (mirrored by consumers):
    2  container layout invalid
    3  pointer uninitialized or unreadable (both slots exhausted)
    4  release invalid: illegal id, path escape, missing dir, not manifest-listed
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
POINTER_SCHEMA = "release_pointer.v1"
MANIFEST_SCHEMA = "deployment_manifest.v1"
ACTIVE_POINTER = "active_release.json"
PREVIOUS_POINTER = "previous_release.json"
MANIFEST_FILE = "deployment_manifest.json"
RELEASES_DIR = "releases"

EXIT_CONTAINER_INVALID = 2
EXIT_POINTER_INVALID = 3
EXIT_RELEASE_INVALID = 4


class BootstrapError(Exception):
    """Resolution failure carrying the process exit code for fail-closed consumers."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _read_pointer_release_id(container: Path, name: str) -> str | None:
    """Return the release-id stored in pointer *name* (``None`` when null)."""
    path = container / name
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


def _resolve_slot(container: Path, slot: str, release_id: str) -> Path:
    """Fully validate one slot and return the contained release directory."""
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} 非法 release-id: {release_id!r}")
    candidate = container / RELEASES_DIR / release_id
    resolved = candidate.resolve()
    releases_root = (container / RELEASES_DIR).resolve()
    if os.path.islink(candidate) or not resolved.is_relative_to(releases_root):
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} release 路径越界: {release_id!r}")
    if not resolved.is_dir():
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} release 目录缺失: {release_id!r}")
    try:
        manifest = json.loads((container / MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(EXIT_RELEASE_INVALID, f"deployment manifest 无法读取: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != MANIFEST_SCHEMA
        or not isinstance(manifest.get("releases"), dict)
        or release_id not in manifest["releases"]
    ):
        raise BootstrapError(EXIT_RELEASE_INVALID, f"{slot} release 未登记于 manifest: {release_id!r}")
    return resolved


def resolve_slot(container: Path, slot: str) -> tuple[Path, str]:
    """Resolve one pointer slot; raise :class:`BootstrapError` on any failure."""
    if slot not in (ACTIVE_POINTER, PREVIOUS_POINTER):
        raise BootstrapError(EXIT_POINTER_INVALID, f"未知指针: {slot!r}")
    if not container.is_dir() or not (container / RELEASES_DIR).is_dir():
        raise BootstrapError(EXIT_CONTAINER_INVALID, f"容器布局无效: {container}")
    release_id = _read_pointer_release_id(container, slot)
    if release_id is None:
        raise BootstrapError(EXIT_POINTER_INVALID, f"{slot} 未初始化（release_id 为 null）")
    return _resolve_slot(container, slot, release_id), slot


def resolve_with_fallback(container: Path) -> tuple[Path, str]:
    """Resolve active, falling back to previous only when active is invalid.

    Returns ``(release_dir, slot_used)``.  When both slots fail, a combined
    error is raised with the worst (highest) failure exit code so the consumer
    exits non-zero with the full diagnosis.
    """
    failures: list[tuple[int, str]] = []
    for slot in (ACTIVE_POINTER, PREVIOUS_POINTER):
        try:
            return resolve_slot(container, slot)
        except BootstrapError as exc:
            failures.append((exc.exit_code, f"[{slot}] {exc}"))
    worst = max(code for code, _ in failures)
    raise BootstrapError(worst, "双槽均无效: " + " | ".join(message for _, message in failures))
