"""TD-SW008-201: protected files are compared with what the Run started from when ``pm verify`` runs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.contracts import protected_files
from auto_pm.contracts.protected_files import (
    PROTECTED_PATTERNS,
    protected_changes,
    protected_files_message,
    unauthorised_protected_changes,
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


def test_note_warns_for_an_old_run_and_blocks_a_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    facade = PmFacadeService.__new__(PmFacadeService)
    monkeypatch.setattr(PmFacadeService, "_protected_file_changes", staticmethod(lambda _run: ("tests/test_a.py",)))
    old = SimpleNamespace(run_id="RUN-X", created_at="2026-10-01T00:00:00+00:00")
    note, block = facade._protected_file_note(old)
    assert "tests/test_a.py" in note and "警告" in note and block is False

    new = SimpleNamespace(run_id="RUN-Y", created_at="2026-11-01T00:00:00+00:00")
    note, block = facade._protected_file_note(new)
    assert "tests/test_a.py" in note and "警告" not in note and block is True

    monkeypatch.setattr(PmFacadeService, "_protected_file_changes", staticmethod(lambda _run: ()))
    assert facade._protected_file_note(new) == ("", False)
    monkeypatch.setattr(PmFacadeService, "_protected_file_changes", staticmethod(lambda _run: None))
    note, block = facade._protected_file_note(new)
    assert "无法核对" in note and block is False


def test_the_cut_over_comes_from_the_ledger_creation_time_and_unreadable_counts_as_new() -> None:
    cut = protected_files.PROTECTED_BLOCK_FROM
    assert protected_files.enforcement_for_run("2026-10-29T13:00:00+00:00") == "warn"
    assert protected_files.enforcement_for_run(cut) == "block"
    assert protected_files.enforcement_for_run("2026-12-01T00:00:00Z") == "block"
    assert protected_files.enforcement_for_run("2026-12-01T00:00:00") == "block"  # naive time is read as UTC
    for unreadable in ("", "garbage", None):
        assert protected_files.enforcement_for_run(unreadable) == "block"  # a Run cannot dodge the block by hiding its time


def test_a_protected_file_is_allowed_only_when_the_approved_scope_names_it_verbatim() -> None:
    changed = ["tests/test_old.py", "tests/new/test_new.py", "scripts/gate.py", ".github/workflows/x.yml"]
    owned = ["auto_pm/", "tests/new", "tests/test_old.py"]
    added = ["tests/new/test_new.py"]
    # tests/test_old.py is named; tests/new/test_new.py is a new test under a named directory; the rest are not named
    assert unauthorised_protected_changes(changed, owned, added) == (".github/workflows/x.yml", "scripts/gate.py")
    # a directory does not authorise editing an existing protected file inside it
    assert unauthorised_protected_changes(["tests/new/test_exist.py"], ["tests/new"], []) == ("tests/new/test_exist.py",)
    # a new non-test protected file under a named directory is not allowed either
    assert unauthorised_protected_changes(["scripts/new.py"], ["scripts"], ["scripts/new.py"]) == ("scripts/new.py",)
    assert unauthorised_protected_changes(["tests/test_a.py"], [], ["tests/test_a.py"]) == ("tests/test_a.py",)


def test_a_new_run_without_a_declaration_is_blocked_end_to_end(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("assert 1 == 2\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    head = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "tests" / "test_a.py").write_text("assert 1 == 1\n", encoding="utf-8")  # edited to go green
    facade = PmFacadeService.__new__(PmFacadeService)
    undeclared = SimpleNamespace(worktree_path=str(tmp_path), git_head=head, run_id="R", owned_paths=("auto_pm",), created_at="2026-11-02T00:00:00+00:00")
    note, block = facade._protected_file_note(undeclared)
    assert block is True and "tests/test_a.py" in note
    declared = SimpleNamespace(worktree_path=str(tmp_path), git_head=head, run_id="R", owned_paths=("tests/test_a.py",), created_at="2026-11-02T00:00:00+00:00")
    assert facade._protected_file_note(declared) == ("", False)
    old = SimpleNamespace(worktree_path=str(tmp_path), git_head=head, run_id="R", owned_paths=("auto_pm",), created_at="2026-10-20T00:00:00+00:00")
    note, block = facade._protected_file_note(old)
    assert block is False and "警告" in note
