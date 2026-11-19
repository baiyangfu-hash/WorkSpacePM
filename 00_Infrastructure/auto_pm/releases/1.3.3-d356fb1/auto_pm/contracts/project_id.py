"""One definition of a project id for the intake box (D-38).

Two shapes are valid: a numbered project (``SW-2026-008``: upper-case segments joined by hyphens) and a shared
library (``SysLib``: one word, starts upper-case, letters and digits only).  A library has no number and keeps its
name as written; the intake id, the inbox item id and every reference check use these patterns, so the box and
``project register`` (which takes any non-empty name) no longer disagree.  The directory-name matchers in the
scanner and the business-line helper stay as they are: they read the numbered prefix of a directory, not a project id.
"""

from __future__ import annotations

import re

NUMBERED_PROJECT_PATTERN = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"
LIBRARY_PROJECT_PATTERN = r"[A-Z][A-Za-z0-9]{2,31}"
PROJECT_ID_PATTERN = rf"(?:{NUMBERED_PROJECT_PATTERN}|{LIBRARY_PROJECT_PATTERN})"

_PROJECT_ID = re.compile(PROJECT_ID_PATTERN + r"\Z")
_LIBRARY_ID = re.compile(LIBRARY_PROJECT_PATTERN + r"\Z")


def is_project_id(value: str) -> bool:
    """True for a numbered project id or a library name."""

    return _PROJECT_ID.fullmatch(value) is not None


def is_library_id(value: str) -> bool:
    """True for the library shape only (no hyphen, so no number)."""

    return _LIBRARY_ID.fullmatch(value) is not None
