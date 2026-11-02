"""auto_pm.infrastructure.change_status_guard - a change order's status line must agree with the approval history.

The status of a change order lives in two places: the ``变更状态`` row of §3.4 in the Markdown file, and the append-only
``approval_history`` table of the control root's ``.auto-pm/index.db`` (one row per ``change transition``).  The commit hook
used to read only the file, so anyone able to edit a text file could write ``approved`` into §3.4 and have production code
accepted.  This module compares the two (audit 524, point 3):

* a status that is new relative to ``HEAD`` (an edit not committed yet) needs a history row whose last ``to_status`` is
  exactly that status -- no database, no table and no row for the order all mean "no history" and are refused;
* a status that ``HEAD`` already carries is let through: the history on this machine only holds the transitions made on this
  machine, and an order made or finished in a cloud session and merged by pull request has no row, or an older one.

Nothing here writes: the database is opened read-only and is never created, so "the database is missing" is the same answer
as "the order has no history", never a pass by itself.  Git is called only to read.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from auto_pm.domain.change.constants import ALL_STATUSES
from auto_pm.domain.change.parser import ChgParser

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
DB_RELATIVE = (".auto-pm", "index.db")
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


def last_recorded_status(control_root: Path, change_number: str, project_id: str = "") -> str | None:
    """The ``to_status`` of the newest approval-history row of this order, or None when there is none.

    None covers: no database file, no ``approval_history`` table, a database that cannot be read, and an order without rows.
    The caller must treat all of them alike -- an unreadable record never counts as approval.
    """

    database = control_root.joinpath(*DB_RELATIVE)
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    except (sqlite3.Error, OSError, ValueError):
        return None
    try:
        row = connection.execute(
            "SELECT to_status FROM approval_history WHERE change_number = ? "
            "AND (? = '' OR project_id = ? OR project_id = '') ORDER BY id DESC LIMIT 1",
            (change_number, project_id, project_id),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return str(row[0]) if row else None


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

    ``recorded`` is the newest history row (None = none); ``committed_status`` the status in ``HEAD`` (None = not committed yet).

    What this judges is a status that is NOT in ``HEAD`` yet -- an edit in the working tree or the index -- because that is the
    only status nothing else has looked at.  It needs a history row whose last ``to_status`` is exactly that status.  A status
    that ``HEAD`` already carries is let through: it came in with a commit (and a pull request, with its audit), and this
    machine's history only knows the transitions made on this machine -- an order approved here and finished in a cloud session
    legitimately ends with a row that is older than the file.  A hand edit that was already committed is the first case's
    business at the time it was committed (the staged-edit rule), not this one's.
    """

    if committed_status == file_status:
        if recorded is None:
            return Verdict(True, f"本机审批历史里没有这张单的记录，按已提交的状态 {committed_status} 放行")
        return Verdict(True)
    if recorded == file_status:
        return Verdict(True)
    seen = "没有这张单的任何记录（没有审批历史库，或这张单没在本机流转过）" if recorded is None else f"最后一条记录是 {recorded}"
    was = "还没有提交过" if committed_status is None else f"已提交的版本里是 {committed_status}"
    return Verdict(
        False,
        f"变更单状态现在是 {file_status}（{was}），但本机审批历史{seen}：状态行被手改过，没有流转依据；"
        "请用 `main.py change transition` 走流转，不要直接改变更单 §3.4",
    )


def replays_history(repository: Path) -> bool:
    """Is this commit a merge, cherry-pick, revert or rebase step?  Those carry already-committed history, not a new edit."""

    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        try:
            result = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "--git-path", marker],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        location = result.stdout.strip()
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
    return [item.decode("utf-8", errors="replace") for item in result.stdout.split(b"\0") if item]


def pending_status_problems(root: Path) -> list[str] | None:
    """Change orders whose working-tree status is new relative to ``HEAD`` and not backed by the approval history.

    The read-only counterpart of the commit hook, for ``doctor``: it sees the hand edit before anyone tries to commit it.
    Returns None when Git cannot answer (not a repository, no commit yet) -- the caller reports "not checked", not "fine".
    """

    changed = _git_names(root, "diff", "--name-only", "-z", "HEAD")
    untracked = _git_names(root, "ls-files", "--others", "--exclude-standard", "-z")
    deleted = _git_names(root, "diff", "--name-only", "--diff-filter=D", "-z", "HEAD")
    if changed is None or untracked is None or deleted is None:
        return None
    removed: dict[str, str] = {}
    for path in deleted:
        if is_change_order_path(path):
            blob = git_blob(root, "HEAD", path)
            if blob is not None:
                removed[change_number_of(path)] = status_of_bytes(blob, path)
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
        number = change_number_of(path)
        old_blob = git_blob(root, "HEAD", path)
        old_status = status_of_bytes(old_blob, path) if old_blob is not None else removed.get(number, "")
        if new_status == old_status:
            continue
        recorded = last_recorded_status(root, number, project_id_of(data.decode("utf-8", errors="replace")))
        if recorded != new_status:
            seen = "没有记录" if recorded is None else f"最后一条是 {recorded}"
            problems.append(
                f"{path}：状态改成了 {new_status}（已提交的是 {old_status or '无'}），审批历史{seen}；请用 `main.py change transition` 走流转"
            )
    return problems
