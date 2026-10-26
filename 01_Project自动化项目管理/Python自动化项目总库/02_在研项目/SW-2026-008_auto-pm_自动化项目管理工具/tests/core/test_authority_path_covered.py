"""TD-SW008-207: one scope rule for every "is this path authorized" check.

A root covers itself and everything under it (trailing ``/`` optional); comparison is by whole path components.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.infrastructure.control_root_guard import (
    authority_path_covered,
    authority_paths_covered,
)

DECISION_FILE = Path(__file__).resolve()
while not (DECISION_FILE / ".auto-pm" / "decisions").is_dir() and DECISION_FILE != DECISION_FILE.parent:
    DECISION_FILE = DECISION_FILE.parent


@pytest.mark.parametrize(
    ("path", "roots", "expected"),
    [
        ("src/a.py", ("src",), True),
        ("src/a.py", ("src/",), True),
        ("src/a/b.py", ("src",), True),
        ("src", ("src",), True),
        ("src/a.py", ("src/a.py",), True),
        ("srcx/a.py", ("src",), False),
        ("srcx/a.py", ("src/",), False),
        ("src/a.py", ("src/b.py",), False),
        ("src", ("src/a.py",), False),
        ("a/bc/x.py", ("a/b",), False),
        ("a\\b\\x.py", ("a/b",), True),
        ("./a//b/x.py", ("a/b/",), True),
        ("a/b.py", (), False),
        ("a/b.py", ("",), False),
        ("a/b.py", ("", "a"), True),
    ],
)
def test_scope_rule(path: str, roots: tuple[str, ...], expected: bool) -> None:
    assert authority_path_covered(path, roots, windows=False) is expected


def test_case_rule_follows_the_host() -> None:
    assert authority_path_covered("SRC/A.py", ("src",), windows=True)
    assert not authority_path_covered("SRC/A.py", ("src",), windows=False)


def test_every_path_must_be_covered() -> None:
    assert authority_paths_covered(["src/a.py", "src/b/c.py"], ["src"], windows=False)
    assert not authority_paths_covered(["src/a.py", "other/c.py"], ["src"], windows=False)
    assert authority_paths_covered([], ["src"], windows=False)


def test_real_decision_package_covers_its_child_files() -> None:
    """The stored ``approved_files`` carry no trailing slash; their children must stay covered."""

    decision = json.loads(
        (DECISION_FILE / ".auto-pm" / "decisions" / "DEC-20261016-M3HYGI01.json").read_text(encoding="utf-8")
    )
    roots = decision["approved_files"]
    assert roots and not any(root.endswith("/") for root in roots)
    for root in roots:
        assert authority_path_covered(f"{root}/child.md", roots, windows=False), root
    assert authority_path_covered(".auto-pm/decisions/DEC-20261016-M3HYGI01.json", roots, windows=False)
