"""TD-SW008-207: one scope rule for every "is this path authorized" check.

A root ending with ``/`` is a directory prefix; any other root is exactly one file.
"""

from __future__ import annotations

import pytest

from auto_pm.infrastructure.control_root_guard import (
    authority_path_covered,
    authority_paths_covered,
)


@pytest.mark.parametrize(
    ("path", "roots", "expected"),
    [
        ("a/b.py", ("a/b.py",), True),
        ("a/b.py", ("a/",), True),
        ("a/b/c.py", ("a/",), True),
        ("a/", ("a/",), True),
        # a file root is exactly that file, not a directory prefix
        ("a/b/x.py", ("a/b",), False),
        ("a/bc/x.py", ("a/b",), False),
        # a directory root never matches a sibling that merely shares the text prefix
        ("a/bc/x.py", ("a/b/",), False),
        # a directory is not covered by a file root, nor by a deeper directory
        ("a/b/", ("a/b",), False),
        ("a/", ("a/b/",), False),
        # slash, ./ and case normalization
        ("a\\b.py", ("a/b.py",), True),
        ("./a/b.py", ("a/b.py",), True),
        ("a//b.py", ("./a/b.py",), True),
        ("a\\b\\c.py", ("a/b/",), True),
        # an empty root authorizes nothing
        ("a/b.py", ("",), False),
        ("a/b.py", ("./",), False),
        ("a/b.py", (), False),
    ],
)
def test_scope_rule(path: str, roots: tuple[str, ...], expected: bool) -> None:
    assert authority_path_covered(path, roots, windows=False) is expected


def test_case_rule_follows_the_host() -> None:
    assert authority_path_covered("A/B.py", ("a/b.py",), windows=True)
    assert not authority_path_covered("A/B.py", ("a/b.py",), windows=False)


def test_every_path_must_be_covered() -> None:
    assert authority_paths_covered(["a/x.py", "b/y.py"], ["a/", "b/y.py"], windows=False)
    assert not authority_paths_covered(["a/x.py", "b/z.py"], ["a/", "b/y.py"], windows=False)
    assert authority_paths_covered([], ["a/"], windows=False)
