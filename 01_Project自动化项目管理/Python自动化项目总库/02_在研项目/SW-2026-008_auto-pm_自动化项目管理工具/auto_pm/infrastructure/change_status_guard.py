"""auto_pm.infrastructure.change_status_guard - a change order's status line must agree with the recorded transitions.

The status of a change order lives in two places: the ``变更状态`` row of §3.4 in the Markdown file, and the append-only
transition journal (``auto_pm.domain.change.status_journal``, ``<control root>/.auto-pm/status_journal.db``) that
``ChangeService`` writes on every status change, before it writes the file.  The commit hook used to read only the file, so
anyone able to edit a text file could write ``approved`` into §3.4 and have production code accepted.  This module compares the
two (audit 524, point 3):

* a status that is new relative to ``HEAD`` (an edit not committed yet) needs a journal row whose last ``to_status`` is
  exactly that status -- no journal file, no table and no row for the order all mean "no record" and are refused;
* a status that ``HEAD`` already carries is let through: the journal on this machine only holds the transitions made on this
  machine, and an order made or finished in a cloud session and merged by pull request has no row, or an older one.

Reading never writes: the journal is opened read-only and is never created, so "the file is missing" is the same answer as
"the order has no record", never a pass by itself.  Git is called only to read.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from auto_pm.domain.change.constants import ALL_STATUSES
from auto_pm.domain.change.parser import ChgParser
from auto_pm.domain.change.status_journal import (
    last_recorded_status as last_recorded_status,  # re-exported: the hook and doctor read the journal through this module
)

# Approved or later: the states in which the commit hook lets production code through.
APPROVED_OR_LATER = (
    "approved",
    "conditionally_approved",
    "implementing",
    "pending_acceptance",
    "accepting",
    "completed",
    "closed",
)
GIT_TIMEOUT_SECONDS = 60
_CHG_FILE = re.compile(r"^CHG-[A-Z0-9]+-\d{4}-\d+\.md$")
_CHANGE_DIR_MARKER = "/01_变更管理/01_变更单/"
_STATUS_ROW = re.compile(r"\|\s*变更状态\s*\|\s*(\S+)\s*\|")
_PROJECT_ROW = re.compile(r"^\|\s*(?:\*\*)?项目编号(?:\*\*)?\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)


@dataclass(frozen=True)
class Verdict:
    """``ok`` False means refuse; ``note`` is a warning when ok, the reason when not."""

    ok: bool
    note: str = ""


def is_change_order_path(path: str) -> bool:
    """A change order file: ``CHG-<domain>-<year>-<n>.md`` inside a project's ``01_变更管理/01_变更单`` folder."""

    normalised = "/" + path.replace("\\", "/").lstrip("/")
    return _CHANGE_DIR_MARKER in normalised and bool(_CHG_FILE.match(normalised.rsplit("/", 1)[-1]))


def change_number_of(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".md")


def project_id_of(text: str) -> str:
    """The project number in the change order's own table; empty when it is absent or ambiguous."""

    found = {match.group(1).strip() for match in _PROJECT_ROW.finditer(text)}
    return next(iter(found)) if len(found) == 1 else ""


def text_of(data: bytes) -> str:
    """Strict UTF-8; content that is not valid UTF-8 reads as empty (no project number, no status), never as a guess."""

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def status_of_bytes(data: bytes, path: str) -> str:
    """The status the cockpit would read from this content: the §3.4 row, else the approval table (same parser).

    Returns "" when the content cannot be decoded -- the caller treats that as 'no status', which no rule lets through.
    """

    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / Path(path.replace("\\", "/")).name
        target.write_bytes(data)
        return str(ChgParser().parse(str(target)).status or "")


def explicit_status(text: str) -> str:
    """Only the §3.4 row (no inference); used where the cheap answer is enough."""

    match = _STATUS_ROW.search(text)
    status = match.group(1).strip() if match else ""
    return status if status in ALL_STATUSES else ""


def git_blob(repo: Path, revision: str, relative: str) -> bytes | None:
    """File content at a revision (``HEAD``), None when the revision or the file is not there."""

    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{revision}:{relative}"],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def judge(*, recorded: str | None, file_status: str, committed_status: str | None) -> Verdict:
    """The rule for a change order that is already in a state production code may rely on.

    ``recorded`` is the newest journal row (None = none); ``committed_status`` the status in ``HEAD`` (None = not committed yet).

    What this judges is a status that is NOT in ``HEAD`` yet -- an edit in the working tree or the index -- because that is the
    only status nothing else has looked at.  It needs a journal row whose last ``to_status`` is exactly that status.  A status
    that ``HEAD`` already carries is let through: it came in with a commit (and a pull request, with its audit), and this
    machine's journal only knows the transitions made on this machine -- an order approved here and finished in a cloud session
    legitimately ends with a row that is older than the file.  A hand edit that was already committed is the first case's
    business at the time it was committed (the staged-edit rule), not this one's.
    """

    if committed_status == file_status:
        if recorded is None:
            return Verdict(True, f"本机流转记录里没有这张单，按已提交的状态 {committed_status} 放行")
        return Verdict(True)
    if recorded == file_status:
        return Verdict(True)
    seen = "没有这张单的任何记录（没有流转记录库，或这张单没在本机流转过）" if recorded is None else f"最后一条记录是 {recorded}"
    was = "还没有提交过" if committed_status is None else f"已提交的版本里是 {committed_status}"
    return Verdict(
        False,
        f"变更单状态现在是 {file_status}（{was}），但本机流转记录{seen}：状态行被手改过，没有流转依据；"
        "请用 `main.py change transition` 走流转，不要直接改变更单 §3.4",
    )


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def renumbered_status(removed: dict[str, tuple[str, bytes]], new_path: str, new_number: str, new_data: bytes) -> str | None:
    """The status a renumbered change order carried before the rename, or None when this is not a renumbering.

    Renumbering after a number clash ("the later merge takes a new number") deletes ``CHG-X-n`` and adds ``CHG-X-m``.  It is
    the same order under a new name when the added content equals a deleted one's content with the old number replaced by the
    new one, byte for byte, in the same project folder.  Anything else -- another status, another text -- is a new order.
    """

    folder = new_path.replace("\\", "/").rsplit("/CHG-", 1)[0]
    for old_path, (old_number, old_data) in removed.items():
        if old_path.replace("\\", "/").rsplit("/CHG-", 1)[0] != folder or old_number == new_number:
            continue
        # Line endings are not content: the working-tree file may be CRLF (Windows, autocrlf) while the blob in Git is LF.
        if _lf(old_data).replace(old_number.encode(), new_number.encode()) == _lf(new_data):
            return status_of_bytes(old_data, old_path)
    return None


def replays_history(repository: Path) -> bool:
    """Is this commit a merge, cherry-pick, revert or rebase step?  Those carry already-committed history, not a new edit."""

    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        try:
            result = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "--git-path", marker],
                capture_output=True,
                timeout=GIT_TIMEOUT_SECONDS,
                check=False,
            )
            location = result.stdout.decode("utf-8").strip()
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
            return False
        if result.returncode == 0 and location:
            candidate = Path(location)
            if not candidate.is_absolute():
                candidate = repository / candidate
            if candidate.exists():
                return True
    return False


def _git_names(repository: Path, *args: str) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    except UnicodeDecodeError:
        return None


def status_before(
    removed: dict[str, tuple[str, bytes]], path: str, data: bytes, head_blob: bytes | None
) -> str:
    """The status this change order had before the edit: in ``HEAD`` at the same path; else moved or renumbered; else ''."""

    if head_blob is not None:
        return status_of_bytes(head_blob, path)
    number = change_number_of(path)
    for old_path, (old_number, old_data) in removed.items():
        if old_number == number:  # the same order moved to another folder
            return status_of_bytes(old_data, old_path)
    return renumbered_status(removed, path, number, data) or ""


def pending_status_problems(root: Path) -> list[str] | None:
    """Change orders whose working-tree status is new relative to ``HEAD`` and not backed by the transition journal.

    The read-only counterpart of the commit hook, for ``doctor``: it sees the hand edit before anyone tries to commit it.
    Returns None when Git cannot answer (not a repository, no commit yet) -- the caller reports "not checked", not "fine".
    """

    changed = _git_names(root, "diff", "--name-only", "-z", "HEAD")
    untracked = _git_names(root, "ls-files", "--others", "--exclude-standard", "-z")
    deleted = _git_names(root, "diff", "--name-only", "--diff-filter=D", "-z", "HEAD")
    if changed is None or untracked is None or deleted is None:
        return None
    removed: dict[str, tuple[str, bytes]] = {}
    for path in deleted:
        if is_change_order_path(path):
            blob = git_blob(root, "HEAD", path)
            if blob is not None:
                removed[path] = (change_number_of(path), blob)
    problems: list[str] = []
    for path in sorted({*changed, *untracked}):
        target = root / path
        if not is_change_order_path(path) or not target.is_file():
            continue
        try:
            data = target.read_bytes()
        except OSError:
            continue
        new_status = status_of_bytes(data, path)
        if new_status not in APPROVED_OR_LATER:
            continue
        old_status = status_before(removed, path, data, git_blob(root, "HEAD", path))
        if new_status == old_status:
            continue
        recorded = last_recorded_status(root, change_number_of(path), project_id_of(text_of(data)))
        if recorded != new_status:
            seen = "没有记录" if recorded is None else f"最后一条是 {recorded}"
            problems.append(
                f"{path}：状态改成了 {new_status}（已提交的是 {old_status or '无'}），流转记录{seen}；请用 `main.py change transition` 走流转"
            )
    return problems
