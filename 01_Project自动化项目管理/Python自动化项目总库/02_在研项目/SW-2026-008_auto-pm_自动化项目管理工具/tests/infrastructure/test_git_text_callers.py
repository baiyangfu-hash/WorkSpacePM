"""TD-SW008-237 / D-162: every caller of the LENIENT ``run_git_bounded_text`` is listed here, with the reason it may stay lenient.

``test_no_new_lenient_decoding`` only sees ``errors="replace"`` written in a call; ``run_git_bounded_text`` hides it inside one function, so
about twenty callers decoded leniently without the ratchet noticing.  This test closes that gap: a new caller, or one that moved, must be
added below with a reason.  An entry whose call is gone fails too, so converting a caller to ``run_git_bounded_strict_text`` means deleting
its line.

The reason is one of
* ``id/exit``: only the exit code, an object id or an emptiness test is read from the output;
* ``content``: file CONTENT lines, not names (a strict decode would refuse every commit of a GBK file);
* ``shown``: text shown to a person (a refusal message), never compared;
* ``pending D-162 card 2``: the output carries paths and still has to move to the strict function (card 2).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "auto_pm"
LENIENT = "run_git_bounded_text"
PENDING = "pending D-162 card 2"

ALLOWED: dict[tuple[str, str], str] = {
    ("auto_pm/application/core/agent_worktree_service.py", "AgentWorktreeService._save_rescue_ref.run"): "id/exit: update-ref, rev-parse",
    ("auto_pm/application/core/agent_worktree_service.py", "AgentWorktreeService._git"): "id/exit: fetch, worktree add/remove/prune, show-ref, branch -D, reflog ids; status only tested for emptiness",
    ("auto_pm/application/core/dogfood_runner.py", "DogfoodRunner._run_git"): f"{PENDING}: status --porcelain lists paths, rev-parse --show-toplevel is compared",
    ("auto_pm/application/core/evidence_collection_service.py", "EvidenceCollectionService._git_output"): "shown: coordinator ruling — evidence keeps going with replacement characters rather than losing the record",
    ("auto_pm/application/core/implementation_card_service.py", "ImplementationCardService._git"): f"{PENDING}: diff --name-only -z is compared with the card's owned paths",
    ("auto_pm/application/core/pm_intake_service.py", "PmIntakeService._require_commit"): "id/exit: cat-file -e",
    ("auto_pm/application/core/pr_open_service.py", "PrOpenService._git"): f"{PENDING}: diff --name-only -z is compared with the claimed scope",
    ("auto_pm/application/core/pr_settle_service.py", "PrSettleService._git"): "id/exit: rev-parse, merge-base --is-ancestor",
    ("auto_pm/application/core/project_delete_guard.py", "uncommitted_blockers"): f"{PENDING}: status --porcelain lists paths that are shown and counted",
    ("auto_pm/application/core/workspace_context_service.py", "WorkspaceContextService._candidate_commit"): "id/exit: rev-parse --verify HEAD",
    ("auto_pm/application/core/worktree_policy_service.py", "WorktreePolicyService._run_git"): "id/exit: check-ref-format, show-ref",
    ("auto_pm/infrastructure/control_root_guard.py", "_git_output"): "id/exit: ASCII facts (ids, flags); stderr must be empty",
    ("auto_pm/infrastructure/control_root_guard.py", "_git_optional_output"): "shown: the caller already refuses U+FFFD in the paths it returns",
    ("auto_pm/infrastructure/git_hook_enforcer.py", "independent_staged_changes"): "id/exit: rev-parse --verify --quiet HEAD, only the exit code",
    ("auto_pm/infrastructure/git_hook_enforcer.py", "find_staged_secrets"): "content: the added lines are scanned for secrets; a GBK file must not make every commit fail",
    ("auto_pm/infrastructure/git_hook_enforcer.py", "_is_content_neutral_merge._rev"): "id/exit: rev-parse -q --verify <commit>",
    ("auto_pm/infrastructure/ignored_file_scan.py", "ignored_among"): f"{PENDING}: check-ignore -z echoes the paths back",
    ("auto_pm/infrastructure/local_executor.py", "LocalCodexExecutor._git_output"): f"{PENDING}: validates the microtask repository from Git's listings",
    ("auto_pm/infrastructure/plc_doc_hook.py", "_git"): f"{PENDING}: ls-files -z names are matched against .plc.json scopes",
    ("auto_pm/infrastructure/plc_git_marker_guard.py", "_git"): f"{PENDING}: ls-tree/ls-files -z names and --show-toplevel are compared",
}


def _calls(path: Path) -> list[tuple[str, int]]:
    """``(enclosing function qualname, line)`` for every call of the lenient function in ``path``."""

    found: list[tuple[str, int]] = []

    def visit(node: ast.AST, stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                visit(child, [*stack, child.name])
                continue
            if isinstance(child, ast.Call):
                func = child.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name == LENIENT:
                    found.append((".".join(stack), child.lineno))
            visit(child, stack)

    visit(ast.parse(path.read_bytes(), filename=str(path)), [])
    return found


def current_callers() -> set[tuple[str, str]]:
    callers: set[tuple[str, str]] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "git_timeout.py":
            continue
        relative = path.relative_to(ROOT).as_posix()
        callers.update((relative, qualname) for qualname, _line in _calls(path))
    return callers


def test_every_lenient_git_caller_is_listed_with_a_reason() -> None:
    unlisted = sorted(current_callers() - ALLOWED.keys())
    assert not unlisted, (
        "run_git_bounded_text decodes with errors='replace'. If the output carries paths that are compared, use "
        f"run_git_bounded_strict_text; otherwise add the caller to ALLOWED with a reason: {unlisted}"
    )


def test_no_entry_outlives_its_call() -> None:
    stale = sorted(ALLOWED.keys() - current_callers())
    assert not stale, f"these callers no longer call the lenient function (or moved): delete or fix their lines: {stale}"


def test_every_reason_says_why_and_the_pending_ones_are_few() -> None:
    assert all(reason.strip() and reason.split(":")[0] in {"id/exit", "content", "shown", PENDING} for reason in ALLOWED.values())
    assert sum(PENDING in reason for reason in ALLOWED.values()) <= 8, "card 2 should be shrinking this list, not growing it"


def test_the_detector_sees_a_call_inside_a_nested_function(tmp_path: Path) -> None:
    sample = tmp_path / "s.py"
    sample.write_text(
        "class A:\n    def m(self):\n        def inner():\n            return run_git_bounded_text(['git'])\n        return inner\n"
        "def f():\n    return git_timeout.run_git_bounded_text(['git'])\n",
        encoding="utf-8",
    )
    assert sorted(name for name, _ in _calls(sample)) == ["A.m.inner", "f"]
