"""Regression coverage for canonical-only root-entry runtime resolution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[6]
ROOT_ENTRY = WORKSPACE_ROOT / "main.py"


def _run_entry(entry: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(entry), "--resolve-only"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_managed_candidate_root_entry_fails_closed(tmp_path: Path) -> None:
    candidate_entries = (
        tmp_path / ".auto-pm" / "worktrees" / "candidate" / "main.py",
        tmp_path / ".codex" / "worktrees" / "candidate" / "My_Workspace" / "main.py",
    )

    for candidate_entry in candidate_entries:
        candidate_entry.parent.mkdir(parents=True)
        candidate_entry.write_text(
            ROOT_ENTRY.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        result = _run_entry(candidate_entry)

        assert result.returncode == 2
        assert "managed candidate is execution-only" in result.stderr
        assert "canonical control root" in result.stderr


def test_unknown_root_without_stable_launcher_fails_closed(tmp_path: Path) -> None:
    unknown_entry = tmp_path / "unknown-root" / "main.py"
    unknown_entry.parent.mkdir(parents=True)
    unknown_entry.write_text(ROOT_ENTRY.read_text(encoding="utf-8"), encoding="utf-8")

    result = _run_entry(unknown_entry)

    assert result.returncode == 2
    assert "stable launcher missing" in result.stderr
