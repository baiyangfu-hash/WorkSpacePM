"""Governance tool: change requests on disk must be tracked by Git (TD-SW008-113).

Why: `ledger reconcile` only compares "a CHG file exists on disk" with "the ledger has a row"; it never asks whether the file is in a commit. That is how 164 change requests lived
only on one disk and in no commit. This tool asks exactly that, read-only:

* every file named `CHG-<DOMAIN>-<YEAR>-<NNN>.md` under the change-request folders (default: every folder named `01_变更单`, or the folders given with --dir) is looked up in the tree of
  `--ref` (default HEAD);
* a file that is not in that tree is `untracked`; a file that is in the tree but whose content differs (line endings are normalised, as Git does on add) is `modified`.

Usage: python -B chg_tracking_check.py --repo DIR [--ref REF] [--dir RELATIVE_DIR ...] [--json]
Exit codes: 0 = every change request is tracked and unmodified, 2 = at least one is untracked or modified, 3 = bad input (not a repository, unknown ref, unreadable directory).
The tool never writes to the repository and never runs `git add`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

CHG_NAME = re.compile(r"^CHG-[A-Z]+-\d{4}-\d{3}\.md$")
DEFAULT_FOLDER = "01_变更单"
SKIP_DIRS = {".git", ".auto-pm", ".venv", "node_modules", "__pycache__"}


class InputError(Exception):
    """The repository, the ref or a directory cannot be used."""


@dataclass
class Report:
    """What was checked and what is not in the commit."""

    repo: str
    ref: str
    checked: int = 0
    untracked: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.untracked and not self.modified

    def as_dict(self) -> dict[str, object]:
        return {"repo": self.repo, "ref": self.ref, "checked": self.checked, "untracked": self.untracked, "modified": self.modified, "clean": self.clean}


def _git(repo: Path, *args: str) -> bytes:
    done = subprocess.run(["git", "-C", str(repo), "-c", "core.quotePath=false", *args], capture_output=True)
    if done.returncode != 0:
        raise InputError("git " + " ".join(args) + ": " + done.stderr.decode("utf-8", errors="replace").strip()[:200])
    return done.stdout


def _normalise(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _walk(root: Path, only_change_folders: bool) -> Iterator[tuple[str, list[str]]]:
    """(directory, file names) pairs; with only_change_folders, files outside a `01_变更单` folder are not offered."""

    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        inside = DEFAULT_FOLDER in Path(current).parts
        yield current, (names if inside or not only_change_folders else [])


def find_change_files(repo: Path, folders: list[str] | None) -> list[str]:
    """Repository-relative POSIX paths of the change-request files on disk."""

    top = repo.resolve()
    roots: list[Path] = []
    if folders:
        for folder in folders:
            root = (top / folder).resolve()
            if not root.is_dir() or top not in [root, *root.parents]:
                raise InputError(f"not a directory inside the repository: {folder}")
            roots.append(root)
    else:
        roots = [top]
    found: set[str] = set()
    for root in roots:
        for current, names in _walk(root, folders is None):
            for name in names:
                if CHG_NAME.match(name):
                    found.add((Path(current) / name).resolve().relative_to(top).as_posix())
    return sorted(found)


def check(repo: Path, ref: str, folders: list[str] | None = None) -> Report:
    try:
        _git(repo, "rev-parse", "--show-toplevel")
        _git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    except InputError as error:
        raise InputError(f"{repo} is not a usable repository at {ref}: {error}") from error
    tracked = {line for line in _git(repo, "ls-tree", "-r", "--name-only", ref).decode("utf-8", errors="replace").split("\n") if line}
    report = Report(repo=str(repo), ref=ref)
    files = find_change_files(repo, folders)
    report.checked = len(files)
    for rel in files:
        if rel not in tracked:
            report.untracked.append(rel)
            continue
        committed = _git(repo, "show", f"{ref}:{rel}")
        if _normalise(committed) != _normalise((repo / rel).read_bytes()):
            report.modified.append(rel)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--dir", action="append", default=None, dest="folders")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        report = check(args.repo, args.ref, args.folders)
    except InputError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 3
    if args.as_json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"checked {report.checked} change request file(s) against {report.ref}: {len(report.untracked)} untracked, {len(report.modified)} modified")
        for rel in report.untracked:
            print(f"  untracked: {rel}")
        for rel in report.modified:
            print(f"  modified: {rel}")
    return 0 if report.clean else 2


if __name__ == "__main__":
    sys.exit(main())
