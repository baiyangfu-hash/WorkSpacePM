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


def test_every_subprocess_call_in_auto_pm_has_a_timeout() -> None:
    """Root cause of TD-087: unbounded Git calls. New unbounded calls must fail this scan."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _BLOCKING_CALLS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                continue
            if "timeout" not in {keyword.arg for keyword in node.keywords}:
                offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert not offenders, "subprocess 调用没有 timeout（Git 请用 git_timeout.run_git_bounded*）: " + ", ".join(offenders)


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
