"""TD-SW008-201: protected files are compared with what the Run started from when ``pm verify`` runs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_pm.application.core import pm_facade_service
from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.contracts import protected_files
from auto_pm.contracts.protected_files import (
    PROTECTED_PATTERNS,
    protected_changes,
    protected_files_message,
)


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@x", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return done.stdout.strip()


def test_tests_gate_scripts_rules_and_infrastructure_are_protected_and_product_code_is_not() -> None:
    changed = [
        "tests/core/test_x.py",
        "pkg/tests/unit.py",
        "pkg/test_loose.py",
        "conftest.py",
        "scripts/long_gate.py",
        "app/scripts/run.py",
        ".trae/rules/project-rule.md",
        ".claude/settings.json",
        ".cursor/rules/workspace-ai-coexistence.mdc",
        ".github/workflows/sw008-ci.yml",
        "AGENTS.md",
        "00_Obsidian_Base全局规范文件仓库/spec_registry.json",
        "auto_pm/application/core/pm_facade_service.py",
        "README.md",
        "docs/notes.md",
    ]
    assert protected_changes(changed) == (
        ".claude/settings.json",
        ".cursor/rules/workspace-ai-coexistence.mdc",
        ".github/workflows/sw008-ci.yml",
        ".trae/rules/project-rule.md",
        "00_Obsidian_Base全局规范文件仓库/spec_registry.json",
        "AGENTS.md",
        "app/scripts/run.py",
        "conftest.py",
        "pkg/test_loose.py",
        "pkg/tests/unit.py",
        "scripts/long_gate.py",
        "tests/core/test_x.py",
    )


def test_windows_slashes_and_a_leading_dot_slash_do_not_hide_a_protected_path() -> None:
    assert protected_changes(["tests\\core\\test_x.py", "./.trae/rules/a.md"]) == (".trae/rules/a.md", "tests/core/test_x.py")


def test_an_authorised_path_is_not_reported() -> None:
    assert protected_changes(["tests/a.py", "tests/b.py"], authorised=["tests/a.py"]) == ("tests/b.py",)


def test_the_audit_script_protected_list_is_covered_by_this_one() -> None:
    here = Path(__file__).resolve()
    audit = next((p / "reviews" / "tools" / "audit_pr.py" for p in here.parents if (p / "reviews" / "tools" / "audit_pr.py").is_file()), None)
    if audit is None:
        pytest.skip("reviews/tools/audit_pr.py is not part of this checkout")
    text = audit.read_text(encoding="utf-8", errors="replace")
    block = text[text.index("PROTECTED_PATTERNS = (") :].split(")", 1)[0]
    audit_patterns = [line.strip().strip(",").strip('"') for line in block.splitlines()[1:] if line.strip().startswith('"')]
    assert audit_patterns
    for pattern in audit_patterns:
        assert pattern in PROTECTED_PATTERNS, f"{pattern} is protected by the PR audit but not by pm verify"


def test_message_names_the_files_and_the_first_round_only_warns() -> None:
    assert protected_files.PROTECTED_FILE_ENFORCEMENT == "warn"
    assert protected_files_message([]) == ""
    warn = protected_files_message(["tests/a.py"])
    assert "警告" in warn and "tests/a.py" in warn
    assert "警告" not in protected_files_message(["tests/a.py"], enforcement="block")
    many = protected_files_message([f"tests/t{i}.py" for i in range(9)])
    assert "共 9 个" in many


def test_real_git_comparison_reports_edited_deleted_and_new_protected_files_only(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("assert 1 == 2\n", encoding="utf-8")
    (tmp_path / "scripts" / "gate.py").write_text("print('gate')\n", encoding="utf-8")
    (tmp_path / "product.py").write_text("V = 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    head = _git(tmp_path, "rev-parse", "HEAD")
    run = SimpleNamespace(worktree_path=str(tmp_path), git_head=head, run_id="RUN-X")
    assert PmFacadeService._protected_file_changes(run) == ()

    (tmp_path / "tests" / "test_a.py").write_text("assert 1 == 1\n", encoding="utf-8")  # the test is edited to go green
    (tmp_path / "scripts" / "gate.py").unlink()
    (tmp_path / "conftest.py").write_text("# new\n", encoding="utf-8")  # untracked
    (tmp_path / "product.py").write_text("V = 2\n", encoding="utf-8")
    assert PmFacadeService._protected_file_changes(run) == ("conftest.py", "scripts/gate.py", "tests/test_a.py")

    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "later")  # committed after the Run started still counts
    assert PmFacadeService._protected_file_changes(run) == ("conftest.py", "scripts/gate.py", "tests/test_a.py")


def test_no_git_record_is_reported_as_unknown_not_as_clean(tmp_path: Path) -> None:
    run = SimpleNamespace(worktree_path=str(tmp_path), git_head="a" * 40, run_id="RUN-X")
    assert PmFacadeService._protected_file_changes(run) is None
    assert PmFacadeService._protected_file_changes(SimpleNamespace(worktree_path="", git_head="", run_id="R")) is None


def test_note_warns_in_warn_mode_and_asks_to_refuse_only_in_block_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    facade = PmFacadeService.__new__(PmFacadeService)
    run = SimpleNamespace(run_id="RUN-X")
    monkeypatch.setattr(PmFacadeService, "_protected_file_changes", staticmethod(lambda _run: ("tests/test_a.py",)))
    note, block = facade._protected_file_note(run)
    assert "tests/test_a.py" in note and block is False

    monkeypatch.setattr(pm_facade_service, "PROTECTED_FILE_ENFORCEMENT", "block")
    note, block = facade._protected_file_note(run)
    assert "tests/test_a.py" in note and block is True

    monkeypatch.setattr(PmFacadeService, "_protected_file_changes", staticmethod(lambda _run: ()))
    assert facade._protected_file_note(run) == ("", False)
    monkeypatch.setattr(PmFacadeService, "_protected_file_changes", staticmethod(lambda _run: None))
    note, block = facade._protected_file_note(run)
    assert "无法核对" in note and block is False
