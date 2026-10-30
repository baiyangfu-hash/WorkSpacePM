"""The PR audit's protected paths must also be protected by ``pm verify`` (audit 376).

#294 added ``roles/*`` to ``audit_pr.PROTECTED_PATTERNS`` only; the test that keeps the two lists in step lives in the
cockpit's own suite (sw008-ci), which does not run for a PR that touches nothing but ``reviews/tools``, so main went red.
``reviews-tools`` runs on every PR, so the same rule is checked here too.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_pr

REPO = Path(__file__).resolve().parents[2]
PM_VERIFY_LIST = next(REPO.glob("01_Project*/Python*/02_在研项目/SW-2026-008*/auto_pm/contracts/protected_files.py"))


def pm_verify_patterns(path: Path = PM_VERIFY_LIST) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROTECTED_PATTERNS" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"PROTECTED_PATTERNS not found in {path}")


def test_every_audit_protected_path_is_also_protected_by_pm_verify() -> None:
    verify = set(pm_verify_patterns())
    missing = [p for p in audit_pr.PROTECTED_PATTERNS if p not in verify]
    assert not missing, f"{missing} protected by the PR audit but not by pm verify (auto_pm/contracts/protected_files.py)"


def test_the_reader_finds_the_list_and_rejects_a_file_without_one(tmp_path: Path) -> None:
    assert "roles/*" in pm_verify_patterns()
    empty = tmp_path / "protected_files.py"
    empty.write_text("OTHER = ()\n", encoding="utf-8")
    try:
        pm_verify_patterns(empty)
    except AssertionError as error:
        assert "not found" in str(error)
    else:
        raise AssertionError("a file without PROTECTED_PATTERNS must not pass")
