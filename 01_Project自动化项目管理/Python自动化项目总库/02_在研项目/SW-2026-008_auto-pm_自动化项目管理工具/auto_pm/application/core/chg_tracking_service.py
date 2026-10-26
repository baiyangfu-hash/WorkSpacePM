"""Read-only check that change-request files are tracked by Git (TD-SW008-113).

`ledger reconcile` compares "a CHG file exists on disk" with "the ledger has a row" and never asks whether the file is in a commit; that is how
164 change requests once lived on one disk only.  This reports, for one project, the change requests that are not in ``ref`` (untracked) or
differ from it (modified).  It never writes, never runs ``git add`` and never raises: when Git cannot answer it says why in ``skipped_reason``.

It is a warning source, not a verdict: callers print it and keep their own exit code.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_CHG_NAME = re.compile(r"^CHG-[A-Z]+-\d{4}-\d{3}\.md$")
_CHANGE_FOLDER = "01_变更单"
_SKIP_DIRS = {".git", ".auto-pm", ".venv", "node_modules", "__pycache__"}
_GIT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class ChgTrackingReport:
    """What was looked at and which change requests are not in the commit."""

    ref: str
    checked: int = 0
    untracked: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    skipped_reason: str = ""
    base: str = ""
    """The project folder relative to the repository root; ``untracked``/``modified`` paths start with it."""

    def relative(self, name: str) -> str:
        """Return ``name`` relative to the project folder (the form people see)."""

        prefix = f"{self.base}/" if self.base else ""
        return name[len(prefix):] if prefix and name.startswith(prefix) else name

    @property
    def clean(self) -> bool:
        return not (self.untracked or self.modified or self.skipped_reason)


def check_project_chg_tracking(project_path: str | Path, ref: str = "HEAD") -> ChgTrackingReport:
    """Compare the project's change-request files on disk with the tree of ``ref``."""

    project = Path(project_path).resolve()
    try:
        top = Path(_git(project, "rev-parse", "--show-toplevel").decode("utf-8", errors="replace").strip()).resolve()
        _git(top, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        relative = project.relative_to(top).as_posix()
        listing = _git(top, "ls-tree", "-r", "-z", "--name-only", ref, "--", relative or ".")
    except (OSError, ValueError, subprocess.SubprocessError, _GitError) as error:
        return ChgTrackingReport(ref=ref, skipped_reason=f"无法用 Git 检查（{error}）")
    tracked = {name for name in listing.decode("utf-8", errors="replace").split("\0") if name}
    files = sorted(_change_files(project, top))
    untracked: list[str] = []
    modified: list[str] = []
    for name in files:
        if name not in tracked:
            untracked.append(name)
            continue
        try:
            committed = _git(top, "show", f"{ref}:{name}")
            current = (top / name).read_bytes()
        except (OSError, _GitError):
            modified.append(name)
            continue
        if committed.replace(b"\r\n", b"\n") != current.replace(b"\r\n", b"\n"):
            modified.append(name)
    return ChgTrackingReport(
        ref=ref, checked=len(files), untracked=tuple(untracked), modified=tuple(modified), base=relative
    )


class _GitError(Exception):
    """A Git call failed."""


def _git(cwd: Path, *arguments: str) -> bytes:
    done = subprocess.run(
        ["git", "-C", str(cwd), "-c", "core.quotePath=false", *arguments],
        capture_output=True,
        check=False,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if done.returncode != 0:
        raise _GitError(done.stderr.decode("utf-8", errors="replace").strip()[:200] or f"git {arguments[0]} 失败")
    return done.stdout


def _change_files(project: Path, top: Path) -> list[str]:
    found: list[str] = []
    for current, directories, names in os.walk(project):
        directories[:] = sorted(name for name in directories if name not in _SKIP_DIRS)
        if _CHANGE_FOLDER not in Path(current).relative_to(project).parts:
            continue
        found.extend((Path(current) / name).relative_to(top).as_posix() for name in names if _CHG_NAME.match(name))
    return found
