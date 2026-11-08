"""Tests must never reach the real ledger (D-108 test side, D-110).

Two ways a test run used to touch the real control root:

* ``long-run --worktree`` hands the command ``AUTO_PM_WORKSPACE`` / ``AUTO_PM_CONTROL_ROOT`` / ``AUTO_PM_RUN_WORKTREE`` (right for
  an acceptance command, wrong for pytest); the e2e drills start child processes that inherit them and the cockpit then treats the
  real control root as the test fixture's root;
* a test that builds a store on the repository it runs in.

``INHERITED_COCKPIT_ENV`` is what every test drops before it starts.  ``real_ledger_paths`` + ``install_tripwire`` make the second
way loud: opening a ``ContinuityStore`` on the real ledger from inside pytest raises, naming the file, instead of writing to it.
The tripwire is a path comparison, not a snapshot of the file: another agent on the same machine may legitimately write the real
ledger while a long gate runs, so a before/after comparison would turn red for the wrong reason.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

INHERITED_COCKPIT_ENV = (
    "AUTO_PM_WORKSPACE",
    "AUTO_PM_CONTROL_ROOT",
    "AUTO_PM_RUN_WORKTREE",
    "AUTO_PM_CALLER_CWD",
)
_LEDGER_RELATIVE = Path(".auto-pm") / "continuity.db"


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def real_ledger_paths(environ: Mapping[str, str], start: Path) -> frozenset[Path]:
    """The ledger files a test run must not open: the control root named by the environment, and the one Git says ``start`` belongs to."""

    roots: list[Path] = []
    named = environ.get("AUTO_PM_CONTROL_ROOT", "").strip()
    if named:
        roots.append(Path(named))
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(start), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        common = completed.stdout.strip()
        if completed.returncode == 0 and common:
            common_path = Path(common)
            if not common_path.is_absolute():
                common_path = start / common_path
            roots.append(_resolved(common_path).parent)
    except (OSError, subprocess.SubprocessError):
        pass
    return frozenset(_resolved(root) / _LEDGER_RELATIVE for root in roots)


def install_tripwire(store_class: type, paths: frozenset[Path]) -> Callable[[], None]:
    """Make ``store_class(...)`` raise when it would open one of ``paths``; returns the function that removes the tripwire."""

    original = store_class.__init__  # type: ignore[misc]

    def guarded(
        self: object,
        workspace_root: str | Path,
        db_path: str | Path | None = None,
        **kwargs: object,
    ) -> None:
        root = _resolved(Path(workspace_root))
        selected = _resolved(Path(db_path)) if db_path is not None else root / _LEDGER_RELATIVE
        if selected in paths:
            raise AssertionError(
                f"测试打开了真账本 {selected}：测试只能用 tmp_path 里的账本（D-110）"
            )
        original(self, workspace_root, db_path, **kwargs)

    store_class.__init__ = guarded  # type: ignore[misc]

    def remove() -> None:
        store_class.__init__ = original  # type: ignore[misc]

    return remove
