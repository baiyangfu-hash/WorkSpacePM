"""Protected-file policy for verification (TD-SW008-201, AGENTS.md 第 8 条 反捷径与测试作弊铁律).

A Run may legitimately list a test, a gate script or a rule file in its own scope, which is exactly how a test gets edited to turn
green.  Verification therefore compares these paths with what the Run started from and reports any difference.  Only the pure
rules live here; reading Git is the caller's job.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable

__all__ = [
    "PROTECTED_FILE_ENFORCEMENT",
    "PROTECTED_PATTERNS",
    "protected_changes",
    "protected_files_message",
]

# "warn": report on `pm verify` and keep going.  "block": a difference not authorised by the user refuses the verification.
# The first round runs as "warn" so Runs already in flight are not stopped (coordinator decision 2026-10-26).
PROTECTED_FILE_ENFORCEMENT = "warn"

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
        "受保护文件被改动"
        if enforcement == "block"
        else "警告：受保护文件被改动（本轮只警告，不拦验证）"
    )
    return f"{head}：{shown}。请核对这些改动是任务本身需要的，而不是为了让检查通过。"
