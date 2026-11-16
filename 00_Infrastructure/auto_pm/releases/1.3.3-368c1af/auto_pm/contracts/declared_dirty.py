"""One shared policy for declared dirty paths (改动声明口径).

Plan, approve, Run start, verification and acceptance must all judge a Run's
declared change set by the same rules, otherwise verification can open the
acceptance gate that acceptance then refuses.  Every caller uses this module
instead of re-implementing the comparison.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = [
    "DECLARED_DIRTY_MISMATCH",
    "EMPTY_DECLARATION_MESSAGE",
    "declared_dirty_mismatch",
    "declared_dirty_problem",
    "retired_session_paths",
]

DECLARED_DIRTY_MISMATCH = "Checkpoint 与最新 Run 声明差异不一致"
EMPTY_DECLARATION_MESSAGE = (
    "改动声明为空：请用 --declared-dirty 逐个列出本次要改的文件（可重复），空声明不予受理"
)

# PM_SESSION_*.md 已退役（用户 2026-10-10 裁决），只作历史证据，不得再被改动。
_RETIRED_SESSION_FILE = re.compile(r"(?:^|/)PM_SESSION_[^/]*\.md$", re.IGNORECASE)
_LISTED = 3


def retired_session_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Return the retired PM_SESSION_*.md files among ``paths`` (either slash style)."""

    return tuple(
        path for path in paths if _RETIRED_SESSION_FILE.search(path.replace("\\", "/"))
    )


def declared_dirty_problem(
    declared: Iterable[str], *, scope: Iterable[str] = ()
) -> str:
    """Explain why a declaration may not be planned, approved or started; empty when fine."""

    declared_paths = tuple(declared)
    if not declared_paths:
        return EMPTY_DECLARATION_MESSAGE
    retired = retired_session_paths((*declared_paths, *scope))
    if retired:
        return (
            "PM_SESSION_*.md 已退役，只作历史证据，不得列入改动范围或改动声明: "
            + _listing(retired)
        )
    return ""


def declared_dirty_mismatch(dirty: Iterable[str], declared: Iterable[str]) -> str:
    """Compare a Checkpoint's dirty paths with the Run declaration; empty when identical.

    Verification and acceptance both call this, so the two gates can never disagree.
    """

    dirty_set = set(dirty)
    declared_set = set(declared)
    if dirty_set == declared_set:
        return ""
    details: list[str] = []
    extra = sorted(dirty_set - declared_set)
    missing = sorted(declared_set - dirty_set)
    if not declared_set:
        details.append("Run 未声明任何改动")
    if extra:
        details.append(f"未声明却改动 {len(extra)} 个: {_listing(extra)}")
    if missing:
        details.append(f"声明了却未改动 {len(missing)} 个: {_listing(missing)}")
    retired = retired_session_paths(extra)
    if retired:
        details.append("其中含已退役的 PM_SESSION 文件")
    return f"{DECLARED_DIRTY_MISMATCH}（{'；'.join(details)}）"


def _listing(paths: Iterable[str]) -> str:
    items = list(paths)
    shown = ", ".join(items[:_LISTED])
    return shown if len(items) <= _LISTED else f"{shown} 等"
