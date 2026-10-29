"""Protected-file policy for verification (TD-SW008-201, AGENTS.md 第 8 条 反捷径与测试作弊铁律).

A Run may legitimately list a test, a gate script or a rule file in its own scope, which is exactly how a test gets edited to turn
green.  Verification therefore compares these paths with what the Run started from and reports any difference.  Only the pure
rules live here; reading Git is the caller's job.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from datetime import UTC, datetime

__all__ = [
    "PROTECTED_BLOCK_FROM",
    "PROTECTED_FILE_ENFORCEMENT",
    "PROTECTED_PATTERNS",
    "enforcement_for_run",
    "protected_changes",
    "unauthorised_protected_changes",
    "protected_files_message",
]

# "warn": report on `pm verify` and keep going.  "block": a difference not authorised by the user refuses the verification.
# Runs created before ``PROTECTED_BLOCK_FROM`` keep "warn" (they were approved without a declaration to check, coordinator decision
# 2026-10-29); every Run created at or after it is "block".  The cut-over is the Run's own ``created_at`` written by the ledger, so a
# Run cannot relabel itself as old; a ``created_at`` that cannot be read counts as new (fail closed).
PROTECTED_FILE_ENFORCEMENT = "warn"
PROTECTED_BLOCK_FROM = "2026-10-30T00:00:00+00:00"

# Shared in spirit with reviews/tools/audit_pr.py PROTECTED_PATTERNS (a test keeps that list a subset of this one), plus the places
# where a test or a rule can be edited to make a check pass.
PROTECTED_PATTERNS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".github/workflows/*",
    "00_Obsidian_Base*",
    "00_Infrastructure/auto_pm/*",
    ".auto-pm/*",
    ".trae/*",
    ".cursor/rules/*",
    ".agent/rules/*",
    "roles/*",
    ".claude/*",
    "*.mdc",
    "*CHG-*",
    "*DEC-*",
    "*_WBS_PM.md",
    "*台账*",
    "tests/*",
    "*/tests/*",
    "scripts/*",
    "*/scripts/*",
    "test_*.py",
    "*_test.py",
    "conftest.py",
)


def _normal(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def _is_protected(path: str) -> bool:
    normal = _normal(path)
    base = normal.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatchcase(normal, pattern) or fnmatch.fnmatchcase(base, pattern)
        for pattern in PROTECTED_PATTERNS
    )


def protected_changes(changed: Iterable[str], authorised: Iterable[str] = ()) -> tuple[str, ...]:
    """The changed paths that are protected and not authorised, sorted."""

    allowed = {_normal(path) for path in authorised}
    return tuple(sorted({_normal(p) for p in changed if _is_protected(p)} - allowed))


def protected_files_message(
    paths: Iterable[str], *, enforcement: str = PROTECTED_FILE_ENFORCEMENT
) -> str:
    """One sentence for the person reading `pm verify`; empty when nothing was touched."""

    listed = list(paths)
    if not listed:
        return ""
    shown = "、".join(listed[:5]) + (f" 等共 {len(listed)} 个" if len(listed) > 5 else "")
    head = (
        "受保护文件被改动，且批准范围没有逐字点名它们（新增测试须在批准范围点名的目录下）"
        if enforcement == "block"
        else "警告：受保护文件被改动（本轮只警告，不拦验证）"
    )
    return f"{head}：{shown}。请核对这些改动是任务本身需要的，而不是为了让检查通过。"


# Only a new test module (``test_*.py`` / ``*_test.py``) may live in a directory the approved scope names.  ``conftest.py`` and helper files
# under ``tests/`` can change what every test does, so they need their own path named like any other protected file.
_NEW_TEST_PATTERNS = ("test_*.py", "*_test.py")


def enforcement_for_run(created_at: object) -> str:
    """"block" for a Run created at or after ``PROTECTED_BLOCK_FROM`` (or whose creation time cannot be read), else "warn"."""

    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return "block" if created >= datetime.fromisoformat(PROTECTED_BLOCK_FROM) else PROTECTED_FILE_ENFORCEMENT
    except ValueError:
        return "block"


def _is_test_path(path: str) -> bool:
    base = _normal(path).rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(base, p) for p in _NEW_TEST_PATTERNS)


def unauthorised_protected_changes(
    changed: Iterable[str], owned_paths: Iterable[str], added: Iterable[str] = ()
) -> tuple[str, ...]:
    """Protected changed paths the approved scope does not allow.

    Allowed: a protected path named verbatim in ``owned_paths`` (a directory is not enough), or a *new* test file under a directory
    ``owned_paths`` names.  Everything else protected is returned, sorted.
    """

    owned = {_normal(p).rstrip("/") for p in owned_paths}
    new = {_normal(p) for p in added}
    allowed = {
        path
        for path in {_normal(p) for p in changed}
        if path in owned or (path in new and _is_test_path(path) and any(path.startswith(f"{o}/") for o in owned))
    }
    return protected_changes(changed, allowed)
