"""Every cockpit subprocess call is bounded; a hung Git fails closed with the caller's own error."""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import plc_baseline, project_delete_guard, worktree_policy_service
from auto_pm.infrastructure import (
    control_root_guard,
    git_hook_enforcer,
    ignored_file_scan,
)

PACKAGE = Path(__file__).resolve().parents[1] / "auto_pm"
_BLOCKING_CALLS = {"run", "check_output", "check_call", "call"}
# Popen has no timeout argument; only code that owns the process lifetime itself may start one.
_POPEN_ALLOWED = {"infrastructure/local_executor.py": "starts the governed Codex process and terminates it itself"}


def find_unbounded_subprocess_calls(source: str) -> list[tuple[int, str]]:
    """(line, why) for every subprocess call that is not provably bounded.

    Follows ``import subprocess as sp`` and ``from subprocess import run as r``; flags ``timeout=None``
    and every ``Popen`` (the caller decides which files may own a Popen).
    """
    tree = ast.parse(source)
    modules: set[str] = set()
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.asname or alias.name for alias in node.names if alias.name == "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                names[alias.asname or alias.name] = alias.name
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in modules:
            original = func.attr
        elif isinstance(func, ast.Name) and func.id in names:
            original = names[func.id]
        else:
            continue
        if original == "Popen":
            found.append((node.lineno, "Popen"))
        elif original in _BLOCKING_CALLS:
            timeouts = [keyword for keyword in node.keywords if keyword.arg == "timeout"]
            if not timeouts:
                found.append((node.lineno, f"{original} without timeout"))
            elif isinstance(timeouts[0].value, ast.Constant) and timeouts[0].value.value is None:
                found.append((node.lineno, f"{original} with timeout=None"))
    return found


def test_every_subprocess_call_in_auto_pm_has_a_timeout() -> None:
    """Root cause of TD-087: unbounded Git calls. New unbounded calls must fail this scan."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        for line, why in find_unbounded_subprocess_calls(path.read_text(encoding="utf-8-sig", errors="replace")):
            if why == "Popen" and relative in _POPEN_ALLOWED:
                continue
            offenders.append(f"{relative}:{line} ({why})")
    assert not offenders, "subprocess 调用没有可证明的时限（Git 请用 git_timeout.run_git_bounded*）: " + ", ".join(offenders)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import subprocess\nsubprocess.run(['git'])\n", "run without timeout"),
        ("import subprocess\nsubprocess.run(['git'], timeout=None)\n", "run with timeout=None"),
        ("import subprocess as sp\nsp.check_output(['git'])\n", "check_output without timeout"),
        ("from subprocess import run\nrun(['git'])\n", "run without timeout"),
        ("from subprocess import run as r\nr(['git'], timeout=None)\n", "run with timeout=None"),
        ("import subprocess\nsubprocess.Popen(['git'])\n", "Popen"),
        ("import subprocess as sp\nsp.Popen(['git'])\n", "Popen"),
        ("from subprocess import Popen as P\nP(['git'])\n", "Popen"),
    ],
    ids=["plain", "none", "alias-module", "from-import", "from-import-alias-none", "popen", "popen-alias", "popen-from"],
)
def test_scan_catches_every_way_of_writing_an_unbounded_call(source: str, expected: str) -> None:
    assert [why for _line, why in find_unbounded_subprocess_calls(source)] == [expected]


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(['git'], timeout=5)\n",
        "import subprocess as sp\nsp.run(['git'], timeout=limit)\n",
        "from subprocess import run\nrun(['git'], timeout=30.0)\n",
        "import subprocess\nsubprocess.TimeoutExpired('git', 1)\n",
    ],
)
def test_scan_accepts_bounded_calls(source: str) -> None:
    assert find_unbounded_subprocess_calls(source) == []


def test_popen_is_only_allowed_where_the_process_lifetime_is_managed() -> None:
    """The allowlist must not rot: every entry still exists and still starts a Popen."""
    for relative in _POPEN_ALLOWED:
        text = (PACKAGE / relative).read_text(encoding="utf-8-sig", errors="replace")
        assert any(why == "Popen" for _line, why in find_unbounded_subprocess_calls(text)), relative


def _hang(*_args: Any, **kwargs: Any) -> Any:
    raise subprocess.TimeoutExpired("git", kwargs["timeout"])


_CASES: list[tuple[str, Callable[[Path], object], type[Exception]]] = [
    ("control_root_git_output", lambda p: control_root_guard._git_output(p, "status"),
     control_root_guard.ControlRootGuardError),
    ("control_root_optional_output", lambda p: control_root_guard._git_optional_output(p, "status"),
     control_root_guard.ControlRootGuardError),
    ("ignored_file_scan", lambda p: ignored_file_scan.ignored_among(p, ["a.txt"]),
     ignored_file_scan.IgnoreScanError),
    ("plc_baseline", lambda p: plc_baseline._git(p, "status"), plc_baseline.PlcBaselineError),
    ("hook_staged_files", lambda p: git_hook_enforcer.get_staged_files(p), RuntimeError),
    ("hook_staged_snapshot", lambda p: git_hook_enforcer.get_staged_snapshot(p),
     git_hook_enforcer.StagedSnapshotError),
    ("hook_secret_scan", lambda p: git_hook_enforcer.find_staged_secrets(p),
     git_hook_enforcer.StagedSnapshotError),
    ("worktree_policy", lambda p: worktree_policy_service.WorktreePolicyService(p)._run_git("status"),
     worktree_policy_service.WorktreePolicyError),
]


@pytest.mark.parametrize(("name", "call", "error"), _CASES, ids=[case[0] for case in _CASES])
def test_hung_git_fails_closed_with_callers_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, call: Callable[[Path], object], error: type[Exception]
) -> None:
    monkeypatch.setattr("auto_pm.infrastructure.git_timeout.subprocess.run", _hang)
    with pytest.raises(error, match="超时回执"):
        call(tmp_path)


def test_project_delete_guard_treats_hung_git_as_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("auto_pm.infrastructure.git_timeout.subprocess.run", _hang)
    blockers = project_delete_guard.uncommitted_blockers(tmp_path, tmp_path / "p")
    assert blockers and "超时回执" in blockers[0]


@pytest.mark.parametrize("hung", ["ls-files", "diff-files", "rev-parse", "ls-tree"])
def test_each_git_call_of_the_independent_staged_comparison_fails_closed_on_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hung: str
) -> None:
    """Only one subcommand hangs; the others run for real, so swallowing that one call's timeout turns this red."""
    real_run = subprocess.run
    for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"], ["config", "user.name", "t"]):
        real_run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    for args in (["add", "a.txt"], ["commit", "-q", "-m", "base"]):
        real_run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    def hang_only(command: Any, *args: Any, **kwargs: Any) -> Any:
        if hung in command:
            raise subprocess.TimeoutExpired("git", kwargs["timeout"])
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("auto_pm.infrastructure.git_timeout.subprocess.run", hang_only)
    with pytest.raises(git_hook_enforcer.StagedSnapshotError, match="超时回执") as caught:
        git_hook_enforcer.independent_staged_changes(tmp_path)
    assert hung in str(caught.value)

