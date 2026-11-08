"""D-108 test side / D-110: a test run does not inherit the cockpit's roots and cannot open the real ledger."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from tests.ledger_isolation import INHERITED_COCKPIT_ENV, install_tripwire, real_ledger_paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE_FLAG = "LEDGER_ISOLATION_PROBE"
# Written out here on purpose: the probe must not check the list against itself (audit 1 of #617, mutants 2/3).
POLLUTION_NAMES = (
    "AUTO_PM_WORKSPACE",
    "AUTO_PM_CONTROL_ROOT",
    "AUTO_PM_RUN_WORKTREE",
    "AUTO_PM_CALLER_CWD",
)


@pytest.mark.skipif(
    PROBE_FLAG not in os.environ,
    reason="only the outer test runs this, in a child process with a polluted environment",
)
def test_probe_sees_a_clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not [name for name in POLLUTION_NAMES if name in os.environ]
    monkeypatch.undo()  # 19 tests in the suite do this midway; the inherited variables must stay gone
    leaked = [name for name in POLLUTION_NAMES if name in os.environ]
    assert not leaked, leaked


def test_the_list_of_dropped_variables_is_pinned() -> None:
    assert set(POLLUTION_NAMES) <= set(INHERITED_COCKPIT_ENV)


def test_a_polluted_parent_environment_does_not_reach_the_tests() -> None:
    env = dict(os.environ)
    env.update({name: str(PROJECT_ROOT) for name in POLLUTION_NAMES})
    env[PROBE_FLAG] = "1"
    completed = subprocess.run(  # noqa: S603 - fixed argv
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--no-cov",
            "-p",
            "no:cacheprovider",
            "-q",
            "tests/test_ledger_isolation_guard.py::test_probe_sees_a_clean_environment",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-1500:] + completed.stderr[-500:]
    assert "1 passed" in completed.stdout


def test_the_control_root_in_the_environment_is_a_forbidden_ledger(tmp_path: Path) -> None:
    root = tmp_path / "real-root"
    root.mkdir()
    paths = real_ledger_paths({"AUTO_PM_CONTROL_ROOT": str(root)}, tmp_path)
    assert (root.resolve() / ".auto-pm" / "continuity.db") in paths


def test_the_git_control_root_of_this_repository_is_a_forbidden_ledger() -> None:
    paths = real_ledger_paths({}, Path(__file__).resolve().parent)
    assert paths, "this checkout has a Git common dir, so its control root's ledger must be listed"
    assert all(path.name == "continuity.db" and path.parent.name == ".auto-pm" for path in paths)


def test_opening_a_store_on_a_forbidden_ledger_raises_and_a_tmp_ledger_still_opens(
    tmp_path: Path,
) -> None:
    forbidden_root = tmp_path / "real"
    forbidden_root.mkdir()
    allowed_root = tmp_path / "scratch"
    allowed_root.mkdir()
    remove = install_tripwire(
        ContinuityStore, frozenset({forbidden_root.resolve() / ".auto-pm" / "continuity.db"})
    )
    try:
        with pytest.raises(AssertionError, match="真账本"):
            ContinuityStore(forbidden_root)
        with pytest.raises(AssertionError, match="真账本"):
            ContinuityStore(forbidden_root, forbidden_root / ".auto-pm" / "continuity.db")
        assert ContinuityStore(allowed_root).db_path.parent.name == ".auto-pm"
        # a safe workspace with an explicit ledger path that is forbidden: the explicit path decides, not the workspace
        with pytest.raises(AssertionError, match="真账本"):
            ContinuityStore(allowed_root, forbidden_root / ".auto-pm" / "continuity.db")
    finally:
        remove()
    assert (
        ContinuityStore(forbidden_root).db_path.name == "continuity.db"
    )  # removed again: no tripwire left behind


def test_the_session_tripwire_is_installed_for_the_real_ledger() -> None:
    paths = real_ledger_paths(os.environ, Path(__file__).resolve().parent)
    victim = next(iter(paths))
    with pytest.raises((AssertionError, ContinuityStoreError)):
        ContinuityStore(victim.parent.parent)
