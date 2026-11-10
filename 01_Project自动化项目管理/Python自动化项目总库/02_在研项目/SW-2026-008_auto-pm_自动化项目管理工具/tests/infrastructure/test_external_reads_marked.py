"""Tests that read real files outside the project directory must say so (D-200).

``sw008-ci`` only starts for changes under the project directory, so a test that reads a spec, a template or a script elsewhere in the
workspace is not run when only that file changes (PR #551 broke ``test_905_long_region_example_passes_the_linter`` that way).  Such tests carry
``pytest.mark.external_reads`` and are listed in ``tests/tools/sw008_ci/external_reads_manifest.txt``, which a dedicated workflow can run on its own
paths.  These checks keep the list, the markers and the tests in step:

* every file in the manifest exists and carries the marker, and no other file carries it;
* no other test file climbs out of the project directory from ``__file__`` (``Path(__file__).resolve().parents[N]`` past the project root, or a
  walk over ``.parents``): it is either added to the manifest and marked, or it does not read outside.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
TESTS = PROJECT / "tests"
MANIFEST = TESTS / "tools" / "sw008_ci" / "external_reads_manifest.txt"
MARKER = "external_reads"

# Files that should be in the manifest but are held back by an open claim on them.  Remove an entry once the file is marked.
PENDING: dict[str, str] = {
    "tests/core/test_pr_body_builder.py": "card 254 (D-194) holds this file; mark it and move it to the manifest when that PR is merged",
}


def _climb(node: ast.AST) -> int | None:
    """How many directory levels the expression climbs above ``__file__``; ``None`` when it is not a path built from ``__file__``."""

    if isinstance(node, ast.Name) and node.id == "__file__":
        return 0
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"resolve", "absolute", "expanduser"}:
            return _climb(func.value)
        if len(node.args) == 1:
            return _climb(node.args[0])
        return None
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        inner = _climb(node.value)
        return None if inner is None else inner + 1
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
        index = node.slice
        inner = _climb(node.value.value)
        if inner is not None and isinstance(index, ast.Constant) and isinstance(index.value, int):
            return inner + index.value + 1
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _climb(node.left)
    return None


def climbs_out_of_project(source: str, depth: int) -> bool:
    """True when the module builds a path above the project directory from ``__file__`` (``depth`` = path parts below the project dir)."""

    tree = ast.parse(source)
    parent_of = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        levels = _climb(node)
        if levels is not None and levels > depth:
            return True
        if isinstance(node, ast.Attribute) and node.attr == "parents" and _climb(node.value) is not None:
            if not isinstance(parent_of.get(node), ast.Subscript):
                return True  # a walk over every ancestor looks for a marker file somewhere above
    return False


def has_marker(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in targets):
            value = getattr(node, "value", None)
            if value is not None and any(isinstance(sub, ast.Attribute) and sub.attr == MARKER for sub in ast.walk(value)):
                return True
    return False


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _manifest() -> list[str]:
    lines = (line.strip() for line in _read(MANIFEST).splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _test_modules() -> list[Path]:
    return sorted(path for path in TESTS.rglob("*.py") if "__pycache__" not in path.parts and path.name != "conftest.py")


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT).as_posix()


def test_the_manifest_lists_each_file_once_and_only_existing_ones() -> None:
    entries = _manifest()
    assert entries, "the manifest is empty"
    assert len(entries) == len(set(entries)), "a file is listed twice"
    missing = [entry for entry in entries if not (PROJECT / entry).is_file()]
    assert not missing, f"listed but not found: {missing}"


def test_every_manifest_file_carries_the_marker() -> None:
    unmarked = [entry for entry in _manifest() if not has_marker(_read(PROJECT / entry))]
    assert not unmarked, f"add `pytestmark = pytest.mark.{MARKER}` to: {unmarked}"


def test_no_file_carries_the_marker_without_being_listed() -> None:
    listed = set(_manifest())
    stray = [_relative(path) for path in _test_modules() if has_marker(_read(path)) and _relative(path) not in listed]
    assert not stray, f"marked but missing from external_reads_manifest.txt: {stray}"


def test_a_test_that_climbs_out_of_the_project_is_listed() -> None:
    listed = set(_manifest()) | set(PENDING)
    offenders = []
    for path in _test_modules():
        relative = _relative(path)
        if relative in listed:
            continue
        if climbs_out_of_project(_read(path), len(path.relative_to(PROJECT).parts)):
            offenders.append(relative)
    assert not offenders, (
        "these tests build a path above the project directory from __file__; mark them with "
        f"pytest.mark.{MARKER} and list them in external_reads_manifest.txt (or stop reading outside): {offenders}"
    )


def test_pending_entries_are_real_and_still_unmarked() -> None:
    for relative, reason in PENDING.items():
        path = PROJECT / relative
        assert path.is_file(), f"{relative} is gone: drop it from PENDING ({reason})"
        assert not has_marker(_read(path)), f"{relative} is marked now: move it from PENDING to the manifest"
        assert relative not in set(_manifest())


@pytest.mark.parametrize(
    ("source", "depth", "expected"),
    [
        ("from pathlib import Path\nROOT = Path(__file__).resolve().parents[6]\n", 3, True),
        ("from pathlib import Path\nROOT = Path(__file__).resolve().parents[2]\n", 3, False),
        ("from pathlib import Path\nROOT = Path(__file__).resolve().parents[2].parents[3]\n", 3, True),
        ("from pathlib import Path\nROOT = Path(__file__).parent.parent.parent.parent\n", 3, True),
        ("from pathlib import Path\nROOT = Path(__file__).resolve().parent.parent\n", 3, False),
        ("from pathlib import Path\nfor p in Path(__file__).resolve().parents:\n    pass\n", 3, True),
        ("from pathlib import Path\nROOT = (Path(__file__).resolve().parents[1] / 'x').name\n", 2, False),
        ("from pathlib import Path\nROOT = Path(__file__).resolve().parents[2]\n", 2, True),
        ("import tmp\nROOT = tmp.parents[9]\n", 3, False),
    ],
)
def test_the_scanner_tells_climbing_out_from_staying_inside(source: str, depth: int, expected: bool) -> None:
    assert climbs_out_of_project(source, depth) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import pytest\npytestmark = pytest.mark.external_reads\n", True),
        ("import pytest\npytestmark = [pytest.mark.usefixtures('x'), pytest.mark.external_reads]\n", True),
        ("import pytest\npytestmark = pytest.mark.usefixtures('x')\n", False),
        ("import pytest\n\n\n@pytest.mark.external_reads\ndef test_a() -> None: ...\n", False),
    ],
)
def test_the_marker_is_recognised_only_at_module_level(source: str, expected: bool) -> None:
    assert has_marker(source) is expected
