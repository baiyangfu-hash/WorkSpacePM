"""Workspace root entry routed to the stdlib stable launcher only.

The parent intentionally does not import ``auto_pm``.  The launcher resolves
and exact-verifies a release before a separate ``-B -I`` child imports it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _is_managed_candidate_root(root: Path) -> bool:
    """Return whether ``root`` is an internal execution-only Git worktree."""
    parent = root.parent
    auto_pm_candidate = (
        parent.name.casefold() == "worktrees"
        and parent.parent.name.casefold() == ".auto-pm"
    )
    codex_candidate = (
        parent.parent.name.casefold() == "worktrees"
        and parent.parent.parent.name.casefold() == ".codex"
    )
    return auto_pm_candidate or codex_candidate


def main() -> int:
    root = Path(__file__).resolve().parent
    if _is_managed_candidate_root(root):
        print(
            "root entry: managed candidate is execution-only; invoke the canonical control root instead",
            file=sys.stderr,
        )
        return 2
    launcher = root / "00_Infrastructure" / "auto_pm" / "launcher" / "launch.py"
    if not launcher.is_file():
        print(f"root entry: stable launcher missing: {launcher}", file=sys.stderr)
        return 2
    return subprocess.run([sys.executable, "-B", str(launcher), *sys.argv[1:]], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
