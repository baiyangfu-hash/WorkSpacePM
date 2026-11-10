"""Official multi-group gate (D-107a / D-108 / D-105): one command that runs the eleven pytest invocations of the regression gate and judges each one.

Why it exists: the formal gate used to be a hand-written script around ``long-run``.  It failed three times in a row for
three symptoms with one root: nothing official owned the groups and nothing owned the test environment.

* the groups ran in the release folder, found no ``tests/`` and ended "no tests ran" (exit 4/5) while the wrapper said DONE;
* the cockpit's ``AUTO_PM_WORKSPACE`` / ``AUTO_PM_CONTROL_ROOT`` / ``AUTO_PM_RUN_WORKTREE`` leaked into the e2e tests, which
  then ran against the real control root (rest: 45 failed, 11 errors);
* the pytest summary of a multi-group run could not be accepted by ``pm verify`` (D-107; the verify side is a separate PR).

Here the group list is code (and its SHA-256 is part of the evidence), each group's child process gets a white-listed
environment with no ``AUTO_PM_*`` variable at all, every group is judged from its own exit code and its own pytest summary
line (zero tests, a missing summary line, an unexpected deselect and exit codes 4/5 are failures), and the verdict is PASS only
when every group of the manifest ran, each above its case floor, on a worktree that was clean and unchanged from start to end.
Nothing here writes the ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.gate_env_preflight import (
    UNFIT_HEADLINE,
    looks_like_environment_error,
    preflight_problems,
)
from auto_pm.infrastructure import memory_preflight

SCHEMA = "gate-run.v1"
SUMMARY_FILE = "gate_summary.json"
DEFAULT_TIMEOUT_SECONDS = 3 * 3600
LOG_TAIL_BYTES = 64 * 1024
MAX_SKIPPED = 40  # the deployment run had at most 15 skipped in one group

# D-235: every test process notes the case it is in (``tests/tools/gate_progress.py``), so a group killed for overrunning can say where it
# was.  The plugin is named on the command line; the directory travels in this variable, which the gate sets itself for each group.
PROGRESS_PLUGIN = "tests.tools.gate_progress"
PROGRESS_ENV = "GATE_RUN_PROGRESS_DIR"
PROGRESS_SUFFIX = ".running"
KILLED_MARK = "[gate run] killed after"
RUNNING_MARK = "[gate run] running when killed:"
NO_NOTE_MARK = "[gate run] no case was noted as running when killed"
MAX_RUNNING_SHOWN = 16
# D-235: when the gate lowers a group's workers it says so on the first line of the group's log.  The sentence travels to the runner in
# this variable, which the runner takes out again before it starts the tests.
NOTE_ENV = "GATE_RUN_NOTE"
NOTE_MARK = "[gate run] note:"
REFUSED = "REFUSED"

# Variables a test child may inherit.  Everything else is dropped, so a new cockpit variable can never leak in by default.
ENV_ALLOW = frozenset(
    {
        "PATH", "HOME", "USER", "LOGNAME", "LNAME", "USERNAME", "HOMEDRIVE", "HOMEPATH", "USERDOMAIN", "COMPUTERNAME", "SYSTEMDRIVE", "ALLUSERSPROFILE", "PUBLIC", "OS", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP", "TZ",
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
        "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
        "VIRTUAL_ENV", "QT_QPA_PLATFORM", "XDG_RUNTIME_DIR", "DISPLAY", "SSL_CERT_FILE",
    }
)  # fmt: skip
ENV_FORCED = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "NO_COLOR": "1",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "core.quotepath",
    "GIT_CONFIG_VALUE_0": "off",
}


class GateRunError(Exception):
    """A gate that cannot even start (bad worktree, unknown group)."""


@dataclass(frozen=True)
class GateGroup:
    """One pytest invocation.  Paths are relative to the project folder (where ``tests/`` lives)."""

    name: str
    targets: tuple[str, ...]
    ignore: tuple[str, ...] = ()
    deselect: tuple[str, ...] = ()
    parallel: bool = True
    min_cases: int = (
        1  # floor for "passed"; a group that collects far fewer tests than usual is not a pass
    )
    deselected: int = (
        0  # the exact number the summary line must show (0 when nothing is deselected)
    )

    def __post_init__(self) -> None:
        if self.deselect and not self.deselected:
            raise ValueError(f"组 {self.name} 声明了 deselect，必须同时写明期望被剔除的用例数")


_DIR_GROUPS = ("application", "change", "cli", "contracts", "core", "infrastructure", "plc")
_BASIS = "tests/core/test_implementation_card_basis.py"
_DEBOUNCE = "tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events"

# The regression groups of the formal gate (the 11-07 deployment run: eleven pytest invocations; the floors are about 80 % of that run's
# counts, so a mistyped path or an over-wide ignore is caught while ordinary growth and small removals are not).  ``rest`` is everything
# the other groups did not take; the two serial groups hold tests that cannot share a process with their neighbours.
_FLOORS = {
    "application": 160,
    "change": 240,
    "cli": 800,
    "contracts": 210,
    "core": 2500,
    "infrastructure": 520,
    "plc": 250,
}
GROUPS: tuple[GateGroup, ...] = (
    *(
        GateGroup(
            name,
            (f"tests/{name}",),
            ignore=(_BASIS,) if name == "core" else (),
            min_cases=_FLOORS[name],
        )
        for name in _DIR_GROUPS
    ),
    GateGroup("core_basis_serial", (_BASIS,), parallel=False, min_cases=15),
    GateGroup(
        "qml", ("tests/qml",), deselect=(_DEBOUNCE,), deselected=1, parallel=False, min_cases=260
    ),
    GateGroup("qml_debounce_alone", (_DEBOUNCE,), parallel=False, min_cases=1),
    GateGroup(
        "rest",
        ("tests",),
        ignore=tuple(f"tests/{name}" for name in (*_DIR_GROUPS, "qml")),
        min_cases=800,
    ),
)


def manifest_sha256(groups: Sequence[GateGroup] = GROUPS) -> str:
    """Fingerprint of the group list; the evidence records it so a gate that quietly ran fewer groups is visible."""

    payload = [
        [
            g.name,
            list(g.targets),
            list(g.ignore),
            list(g.deselect),
            g.parallel,
            g.min_cases,
            g.deselected,
        ]
        for g in sorted(groups, key=lambda g: g.name)
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """White-listed environment for a test child: no ``AUTO_PM_*`` variable, no lease, no agent marker, ever."""

    source = os.environ if base is None else base
    env = {
        key: value
        for key, value in source.items()
        if key.upper() in ENV_ALLOW and not key.upper().startswith("AUTO_PM_")
    }
    env.update(ENV_FORCED)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def group_argv(group: GateGroup, *, python: str, jobs: int) -> list[str]:
    argv = [python, "-B", "-m", "pytest", *group.targets]
    argv += [f"--ignore={path}" for path in group.ignore]
    argv += [f"--deselect={node}" for node in group.deselect]
    argv += ["-p", "no:cacheprovider", "-p", PROGRESS_PLUGIN, "--no-cov", "-q"]
    if group.parallel and jobs > 1:
        argv += ["-n", str(jobs), "--dist", "loadfile"]
    return argv


# ── judging ─────────────────────────────────────────────

_TOKEN = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)")
_TIMING = re.compile(r"\bin \d+(\.\d+)?s\b")


def pytest_counts(log: Path) -> dict[str, int] | None:
    """Counts on the last pytest summary line of ``log`` (singular keys), or ``None`` when there is no such line."""

    try:
        with log.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(handle.tell() - LOG_TAIL_BYTES, 0))
            tail = handle.read()
    except OSError:
        return None
    text = tail.decode(
        "utf-8", errors="replace"
    )  # lenient-decode: log tail only feeds the summary regex; exit code and log hash are judged apart
    for line in reversed(text.splitlines()):
        tokens = _TOKEN.findall(line)
        if tokens and _TIMING.search(line):
            counts: dict[str, int] = {}
            for number, kind in tokens:
                key = kind.rstrip("s") if kind in {"errors", "warnings"} else kind
                counts[key] = counts.get(key, 0) + int(number)
            return counts
    return None


def _says_no_tests(log: Path) -> bool:
    try:
        with log.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(handle.tell() - LOG_TAIL_BYTES, 0))
            return b"no tests ran" in handle.read()
    except OSError:
        return False


def _environment_error_line(log: Path) -> str:
    """A log line showing the group died of its environment; empty when pytest got as far as passing tests (D-196)."""

    counts = pytest_counts(log)
    if counts is not None and counts.get("passed", 0) > 0:
        return ""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")  # lenient-decode: diagnostic scan of a log
    except OSError:
        return ""
    return looks_like_environment_error(text)


def judge_group(group: GateGroup, exit_code: int | None, log: Path) -> tuple[str, str]:
    """``("PASS"|"FAIL", why)`` for one group from its exit code and its own summary line."""

    if exit_code is None:
        return "FAIL", "没有退出码（没跑完）"
    if exit_code != 0:
        env_line = _environment_error_line(log)
        if env_line:
            return "ENV_ERROR", f"环境错误（测试没能开始跑，不是用例失败）：{env_line}"
        hint = (
            "（4/5：用法错误或一个用例都没收集到，通常是目录不对）" if exit_code in (4, 5) else ""
        )
        return "FAIL", f"退出码 {exit_code}{hint}{_killed_note(log) if exit_code == 124 else ''}"
    counts = pytest_counts(log)
    if counts is None and _says_no_tests(log):
        return "FAIL", "一个用例都没跑（no tests ran）"
    if counts is None:
        return "FAIL", "日志里找不到 pytest 收尾行，这不是一次跑完的 pytest 输出"
    passed = counts.get("passed", 0)
    if passed == 0:
        return "FAIL", "一个用例都没跑（没有 passed；xfail 和 skipped 不算跑过）"
    if counts.get("failed", 0) or counts.get("error", 0):
        return "FAIL", f"收尾行有失败或错误：{counts}"
    if passed < group.min_cases:
        return (
            "FAIL",
            f"只有 {passed} 个用例通过，这一组的下限是 {group.min_cases}（目录写错或 ignore 过宽？）",
        )
    deselected = counts.get("deselected", 0)
    if deselected != group.deselected:
        return "FAIL", f"被 deselect 的用例是 {deselected} 个，清单规定恰好 {group.deselected} 个"
    if counts.get("skipped", 0) > MAX_SKIPPED:
        return "FAIL", f"skipped 有 {counts['skipped']} 个，超过上限 {MAX_SKIPPED}"
    return "PASS", ""


def running_cases(progress_dir: Path, now: float | None = None) -> list[str]:
    """One line per test process that was inside a case: ``<node id> (<worker>, running for <n> s)``, longest first (D-235)."""

    now = time.time() if now is None else now
    found: list[tuple[float, str]] = []
    try:
        notes = sorted(progress_dir.glob(f"*{PROGRESS_SUFFIX}"))
    except OSError:
        return []
    for note in notes:
        try:
            text = note.read_text(encoding="utf-8", errors="replace").strip()  # lenient-decode: a damaged node id is still shown; nothing is judged from it
        except OSError:
            continue
        started, _, node = text.partition("\t")
        if not node.strip():
            continue  # between two cases
        try:
            seconds = max(now - float(started), 0.0)
        except ValueError:
            seconds = 0.0
        worker = note.name[: -len(PROGRESS_SUFFIX)].rsplit("-", 1)[0]
        found.append((seconds, f"{node.strip()} ({worker}, running for {seconds:.0f} s)"))
    return [line for _seconds, line in sorted(found, key=lambda pair: (-pair[0], pair[1]))]


def _killed_note(log: Path) -> str:
    """What the log says the group was doing when the gate killed it, for the verdict's reason (D-235); empty when it says nothing."""

    try:
        with log.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(handle.tell() - LOG_TAIL_BYTES, 0))
            tail = handle.read()
    except OSError:
        return ""
    text = tail.decode("utf-8", errors="replace")  # lenient-decode: only quoted into the reason; the exit code already decided the verdict
    lines = text.splitlines()
    running = [line[len(RUNNING_MARK) :].strip() for line in lines if line.startswith(RUNNING_MARK)]
    if running:
        more = f" 等 {len(running)} 条" if len(running) > 3 else ""
        return "（超时被杀；被杀时在跑：" + "；".join(running[:3]) + more + "）"
    if any(line.startswith(NO_NOTE_MARK) for line in lines):
        return "（超时被杀；被杀时没有用例登记为在跑，可能卡在收集、夹具收尾或进程退出）"
    if any(line.startswith(KILLED_MARK) for line in lines):
        return "（超时被杀）"
    return ""


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# ── running ─────────────────────────────────────────────

Runner = Callable[[Sequence[str], Path, Mapping[str, str], Path, int], int]


def default_runner(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, timeout: int
) -> int:
    """Run one group with its output in ``log``; 124 on timeout (what ``timeout`` returns).

    On a timeout the log also gets the cases that were running (D-235), read from the directory in ``env[PROGRESS_ENV]`` before anything
    else is done, so the record of a killed group says where it was stuck.
    """

    child_env = {key: value for key, value in env.items() if key != NOTE_ENV}
    with log.open("wb") as handle:
        if env.get(NOTE_ENV):
            handle.write(f"{NOTE_MARK} {env[NOTE_ENV]}\n".encode())
            handle.flush()
        try:
            return subprocess.run(  # noqa: S603 - argv is built from the group table
                list(argv),
                cwd=cwd,
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            folder = env.get(PROGRESS_ENV, "")
            running = running_cases(Path(folder)) if folder else []
            lines = [f"{KILLED_MARK} {timeout} s"]
            lines += [f"{RUNNING_MARK} {line}" for line in running[:MAX_RUNNING_SHOWN]]
            if len(running) > MAX_RUNNING_SHOWN:
                lines.append(f"[gate run] ... and {len(running) - MAX_RUNNING_SHOWN} more")
            if not running:
                lines.append(f"{NO_NOTE_MARK} ({'no progress directory' if not folder else folder})")
            handle.write(("\n" + "\n".join(lines) + "\n").encode("utf-8"))
            return 124


@dataclass
class GroupResult:
    name: str
    argv: list[str]
    cwd: str
    exit: int | None = None
    verdict: str = "NOT_RUN"
    why: str = ""
    counts: dict[str, int] | None = None
    log_sha256: str | None = None
    exit_file: int | None = None
    started: str = ""
    finished: str = ""
    # D-235: what the group asked for and what it got.  ``None`` in a record written before these fields existed.
    jobs_requested: int | None = None
    jobs_used: int | None = None
    available_memory_bytes: int | None = None
    timeout_seconds: int | None = None


@dataclass
class GateSummary:
    schema: str = SCHEMA
    commit: str = ""
    git_dirty: bool | None = None
    commit_end: str = ""
    git_dirty_end: bool | None = None
    ignored_code: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    worktree: str = ""
    project_dir: str = ""
    manifest_sha256: str = ""
    groups_run: list[str] = field(default_factory=list)
    complete: bool = False
    verdict: str = "FAIL"
    results: dict[str, GroupResult] = field(default_factory=dict)


def _git(worktree: Path, *args: str) -> str | None:
    """Git's stdout, or None when git could not answer (not started, timed out, or a non-zero exit such as a broken index).

    A failed ``git status`` prints nothing; read as text that would be a clean tree, so the exit code is checked.
    """

    try:
        done = subprocess.run(  # noqa: S603
            ["git", "-C", str(worktree), *args], capture_output=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    text = done.stdout.decode(
        "utf-8", errors="replace"
    )  # lenient-decode: git output is a commit id or status text
    return text.strip()


UNREADABLE_IGNORED = "<读不出被忽略的文件：git ls-files 失败>"
_CODE_SUFFIXES = (".py", ".ini", ".cfg", ".toml", ".json", ".yaml", ".yml", ".qml")


@dataclass(frozen=True)
class TreeState:
    """What the tested tree looked like at one moment: HEAD, every tracked change *and untracked file*, and ignored code files."""

    commit: str
    dirty: bool | None
    ignored_code: tuple[str, ...]


def tree_state(worktree: Path, project: Path) -> TreeState:
    """An untracked file counts as dirty (it can be a conftest or a plugin that changes what the tests do); an *ignored* source or
    config file under ``auto_pm/`` or ``tests/`` is listed too, because ``.gitignore`` hides it from ``git status``."""

    status = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    ignored = _git(
        project,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",  # D-126: without it git quotes a non-ASCII name as "\\350..." and the suffix test below would miss it
        "--",
        "auto_pm",
        "tests",
        "pyproject.toml",
        "conftest.py",
    )
    listed = sorted(
        line
        for line in (ignored or "").split("\0")
        if line.endswith(_CODE_SUFFIXES) and "__pycache__" not in line
    )
    if ignored is None:  # git could not list them: that is "unknown", never "none"
        listed.append(UNREADABLE_IGNORED)
    return TreeState(
        _git(worktree, "rev-parse", "HEAD") or "",
        None if status is None else bool(status),
        tuple(listed),
    )


_DEPLOYED_RUNTIME = ("00_Infrastructure", "auto_pm")  # the deployed copy: releases, launcher and a mirror of tests/


def _project_candidates(worktree: Path) -> list[Path]:
    """Folders in ``worktree`` that look like this project: a tracked pyproject.toml beside main.py, auto_pm/ and tests/."""

    listed = _git(worktree, "ls-files", "-z", "--", "pyproject.toml", "*/pyproject.toml")
    if not listed:
        return []
    found: list[Path] = []
    for name in listed.split("\0"):
        if not name:
            continue
        folder = (worktree / name).parent
        if (
            (folder / "main.py").is_file()
            and (folder / "auto_pm" / "__init__.py").is_file()
            and (folder / "tests").is_dir()
        ):
            found.append(folder)
    return found


def project_dir_in(worktree: Path, module_file: Path | None = None) -> Path:
    """The project folder (where ``tests/`` is) inside ``worktree``.

    It is found from the worktree itself, not from where this code runs (D-151): a deployed release lives under
    ``00_Infrastructure/auto_pm/releases/<id>/``, whose nearest ``pyproject.toml`` is the infrastructure copy, and the gate
    would judge that folder's few hundred tests instead of the project's. Only when the worktree has no single match is
    the folder this code lives in used, and never when that is inside the deployed runtime folder.
    """

    found = _project_candidates(worktree)
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        listed = "、".join(str(path.relative_to(worktree)) for path in found)
        raise GateRunError(f"工作树里有多个像项目目录的地方，无法确定门禁该跑哪个: {listed}")
    here = (module_file or Path(__file__)).resolve()
    top = _git(here.parent, "rev-parse", "--show-toplevel")
    if top is None:
        raise GateRunError("读不出这份代码所在的 Git 仓库根，无法定位项目目录")
    project = next((p for p in here.parents if (p / "pyproject.toml").is_file()), None)
    if project is None:
        raise GateRunError("找不到含 pyproject.toml 的项目目录")
    relative = project.relative_to(Path(top).resolve())
    if relative.parts[: len(_DEPLOYED_RUNTIME)] == _DEPLOYED_RUNTIME:
        raise GateRunError(
            "工作树里找不到项目目录（含 pyproject.toml、main.py、auto_pm/、tests/），"
            "而这份代码来自已部署的发布版，不能用它的位置代替"
        )
    return worktree / relative


#: D-207: each xdist worker of a gate group holds about this much memory, and the machine keeps this much for everything else.
JOB_MEMORY_GIB = 2.0
JOB_RESERVE_GIB = 3.0


def jobs_for_memory(requested: int, available_bytes: int | None) -> int:
    """``requested`` lowered to what the available physical memory carries: ``(available - 3 GiB) // 2 GiB`` workers, at least one.

    An unreadable reading (None) leaves the request alone: the memory preflight, not this cap, is what refuses a machine it cannot read.
    """

    if available_bytes is None:
        return requested
    fits = int((available_bytes / 2**30 - JOB_RESERVE_GIB) // JOB_MEMORY_GIB)
    return max(1, min(requested, fits))


def memory_for_jobs(jobs: int) -> int:
    """Bytes of available physical memory that carry ``jobs`` workers: the reserve plus one share for each."""

    return int((JOB_RESERVE_GIB + JOB_MEMORY_GIB * jobs) * 2**30)


def timeout_for_jobs(timeout_seconds: int, requested: int, used: int) -> int:
    """The group's time limit stretched by the factor its workers were lowered by (D-235); unchanged when nothing was lowered.

    A parallel group given a third of its workers needs about three times as long.  Keeping the full-speed limit made the gate run a
    group it could not finish for three hours and then call it a timeout (local round on 0a9d2a7, core at one worker instead of three).
    """

    if used <= 0 or used >= requested:
        return timeout_seconds
    return -(-timeout_seconds * requested // used)


def _gib(value: int | None) -> str:
    return "读不出" if value is None else f"{value / 2**30:.1f} GiB"


def jobs_note(result: GroupResult) -> str:
    """One sentence for a group whose workers were lowered; empty for a group that got what it asked for or a record without the fields."""

    if result.jobs_requested is None or result.jobs_used is None or result.jobs_used >= result.jobs_requested:
        return ""
    if result.verdict == REFUSED or result.timeout_seconds is None:
        return (
            f"可用内存不足，没有开跑：请求 --jobs {result.jobs_requested}，需要可用物理内存至少 {_gib(memory_for_jobs(result.jobs_requested))}，"
            f"当时只有 {_gib(result.available_memory_bytes)}（只够 {result.jobs_used} 路）"
        )
    return (
        f"可用内存不足，--jobs 从 {result.jobs_requested} 降到 {result.jobs_used}（当时可用物理内存 {_gib(result.available_memory_bytes)}），"
        f"本组超时放大到 {result.timeout_seconds // 60} 分钟"
    )


def _available_memory() -> int | None:
    snapshot = memory_preflight.read_commit()
    return None if snapshot is None else snapshot.available


class GateRunService:
    def __init__(
        self,
        *,
        runner: Runner = default_runner,
        python: str = sys.executable,
        preflight: Callable[[str, Path], tuple[list[str], list[str]]] | None = None,
        available_memory: Callable[[], int | None] | None = None,
        announce: Callable[[str], None] | None = None,
    ) -> None:
        self._runner = runner
        self._python = python
        self._preflight = preflight or preflight_problems  # looked up now, so a test can swap the module attribute
        self.preflight_warnings: list[str] = []
        self._available_memory = available_memory or _available_memory  # looked up now, so a test can replace the module function
        self.job_notes: list[str] = []
        self._announce = announce  # told at once when a group's workers are lowered; without it the note waits in ``preflight_warnings``

    def select(self, only: Sequence[str] = ()) -> tuple[GateGroup, ...]:
        known = {g.name: g for g in GROUPS}
        unknown = [name for name in only if name not in known]
        if unknown:
            raise GateRunError(f"未知的组: {'、'.join(unknown)}；可用: {'、'.join(known)}")
        return tuple(g for g in GROUPS if not only or g.name in only)

    def plan(
        self, worktree: Path, *, jobs: int, only: Sequence[str] = ()
    ) -> list[dict[str, object]]:
        project = project_dir_in(worktree)
        return [
            {
                "name": g.name,
                "cwd": str(project),
                "argv": group_argv(g, python=self._python, jobs=jobs),
            }
            for g in self.select(only)
        ]

    def run(
        self,
        worktree: Path,
        out_dir: Path,
        *,
        jobs: int = 8,
        only: Sequence[str] = (),
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        base_env: Mapping[str, str] | None = None,
        require_full_jobs: bool = False,
    ) -> GateSummary:
        """Run the selected groups in order.

        A parallel group gets as many workers as the available physical memory carries (D-207).  When that is fewer than ``jobs`` the
        group's time limit grows by the same factor and the record says so (D-235); with ``require_full_jobs`` the group is not started
        at all and the round stops there, which is what a round that is to count as release evidence asks for.
        """

        worktree = worktree.resolve()
        if not (worktree / ".git").exists():
            raise GateRunError(f"{worktree} 不是 Git 工作树")
        project = project_dir_in(worktree)
        if not (project / "tests").is_dir():
            raise GateRunError(f"{project} 下没有 tests/；门禁不会在别的目录里空跑")
        selected = self.select(only)
        refusals, self.preflight_warnings = self._preflight(self._python, worktree)
        if refusals:
            raise GateRunError(f"{UNFIT_HEADLINE}：" + "；".join(refusals))
        out_dir.mkdir(parents=True, exist_ok=True)
        env = child_environment(base_env)
        before = tree_state(worktree, project)
        summary = GateSummary(
            commit=before.commit,
            git_dirty=before.dirty,
            ignored_code=list(before.ignored_code),
            worktree=str(worktree),
            project_dir=str(project),
            manifest_sha256=manifest_sha256(),
            groups_run=[g.name for g in selected],
        )
        for group in selected:
            available = self._available_memory() if group.parallel else None
            group_jobs = jobs_for_memory(jobs, available) if group.parallel else jobs
            argv = group_argv(group, python=self._python, jobs=group_jobs)
            result = GroupResult(
                group.name, argv, str(project), started=_now(),
                jobs_requested=jobs, jobs_used=group_jobs, available_memory_bytes=available,
            )  # fmt: skip
            if group_jobs < jobs and require_full_jobs:
                result.verdict, result.finished = REFUSED, result.started
                result.why = jobs_note(result)
                self._say(f"组 {group.name}：{result.why}")
                summary.results[group.name] = result
                summary.reasons.append(f"组 {group.name} 没有开跑，后面的组也没有跑（--require-full-jobs）：{result.why}")
                self._write(out_dir, summary)
                break
            result.timeout_seconds = timeout_for_jobs(timeout_seconds, jobs, group_jobs)
            note = jobs_note(result)
            if note:
                self._say(f"组 {group.name}：{note}")
            log = out_dir / f"{group.name}.txt"
            progress = out_dir / f"{group.name}{PROGRESS_SUFFIX}"
            shutil.rmtree(progress, ignore_errors=True)  # notes of an earlier round in the same directory are not this round's
            group_env = {**env, PROGRESS_ENV: str(progress), **({NOTE_ENV: note} if note else {})}
            result.exit = self._runner(argv, project, group_env, log, result.timeout_seconds)
            result.finished = _now()
            (out_dir / f"{group.name}.exit").write_text(f"{result.exit}\n", encoding="utf-8")
            result.exit_file = result.exit
            self._judge(result, group, log)
            summary.results[group.name] = result
            self._write(out_dir, summary)
            if result.verdict == "ENV_ERROR":  # every later group would die of the same cause; say so once and stop
                summary.reasons.append(f"第 {len(summary.results)} 组 {group.name} 出现环境错误，已停止后面的组：{result.why}")
                break
        after = tree_state(
            worktree, project
        )  # the round takes hours; the tree it judged must be the tree it started on
        summary.commit_end, summary.git_dirty_end = after.commit, after.dirty
        if after != before:
            summary.reasons.append(
                "跑的过程中工作树变了（提交号、改动或被忽略的代码文件与开跑时不一致）"
            )
        self._finalize(summary)
        self._write(out_dir, summary)
        return summary

    def _say(self, note: str) -> None:
        self.job_notes.append(note)
        if self._announce is not None:
            self._announce(note)
        else:
            self.preflight_warnings.append(note)  # the CLI prints this list in its ``finally``

    def judge_dir(
        self, out_dir: Path, *, expect_sha256: str = "", worktree: Path | None = None
    ) -> GateSummary:
        """Read-only: recompute every verdict from what is on disk (never regenerates anything).

        The record is checked against the disk, not trusted: each log's SHA-256 must equal the recorded one, the ``<group>.exit``
        file must equal the recorded exit code, the group list must be the official one.  ``expect_sha256`` pins the whole
        ``gate_summary.json`` (print it when the gate ends and keep it in a checkpoint); ``worktree`` compares the tree now with
        the tree that was judged.
        """

        record = out_dir / SUMMARY_FILE
        try:
            raw_bytes = record.read_bytes()
            data = json.loads(raw_bytes.decode("utf-8"))
        except (OSError, ValueError) as error:
            raise GateRunError(f"读不了 {record}: {error}") from error
        groups = {g.name: g for g in GROUPS}
        summary = GateSummary(
            commit=str(data.get("commit", "")),
            git_dirty=data.get("git_dirty"),
            commit_end=str(data.get("commit_end", "")),
            git_dirty_end=data.get("git_dirty_end"),
            ignored_code=list(data.get("ignored_code", [])),
            reasons=list(data.get("reasons", [])),
            worktree=str(data.get("worktree", "")),
            project_dir=str(data.get("project_dir", "")),
            manifest_sha256=str(data.get("manifest_sha256", "")),
            groups_run=list(data.get("groups_run", [])),
        )
        if expect_sha256 and hashlib.sha256(raw_bytes).hexdigest() != expect_sha256.strip().lower():
            summary.reasons.append(
                "gate_summary.json 的 SHA-256 与给定的不一致（记录被改过或不是那一轮）"
            )
        if worktree is not None:
            project = project_dir_in(worktree.resolve())
            now = tree_state(worktree.resolve(), project)
            if now.commit != summary.commit or now.dirty is not False or now.ignored_code:
                summary.reasons.append(
                    "现在的工作树与被判的那一轮不一致（提交号变了，或有未提交/未跟踪/被忽略的代码文件）"
                )
        for name, entry in dict(data.get("results", {})).items():
            result = GroupResult(
                name, list(entry.get("argv", [])), str(entry.get("cwd", "")), exit=entry.get("exit"),
                jobs_requested=_int_or_none(entry.get("jobs_requested")), jobs_used=_int_or_none(entry.get("jobs_used")),
                available_memory_bytes=_int_or_none(entry.get("available_memory_bytes")),
                timeout_seconds=_int_or_none(entry.get("timeout_seconds")),
            )  # fmt: skip
            if name not in groups:
                result.verdict, result.why = "FAIL", "记录里的组不在官方清单里"
            elif entry.get("verdict") == REFUSED:
                result.verdict = REFUSED  # never started: there is no log and no exit file to judge, and it is not a pass
                result.why = jobs_note(result) or "没有开跑"
            else:
                self._judge(result, groups[name], out_dir / f"{name}.txt")
                self._cross_check(result, out_dir, entry)
            summary.results[name] = result
        self._finalize(summary)
        return summary

    @staticmethod
    def _cross_check(result: GroupResult, out_dir: Path, entry: Mapping[str, object]) -> None:
        """The disk must agree with the record; any disagreement fails the group, whatever the log now says."""

        problems: list[str] = []
        try:
            result.exit_file = int(
                (out_dir / f"{result.name}.exit").read_text(encoding="utf-8").strip()
            )
        except (OSError, ValueError):
            problems.append(f"{result.name}.exit 缺失或读不了")
        if result.exit_file is not None and result.exit_file != entry.get("exit"):
            problems.append(
                f"{result.name}.exit 是 {result.exit_file}，记录里是 {entry.get('exit')}"
            )
        recorded = entry.get("log_sha256")
        if not isinstance(recorded, str) or recorded != result.log_sha256:
            problems.append("日志的 SHA-256 与记录不一致（日志被改过或丢了）")
        if problems:
            result.verdict, result.why = "FAIL", "；".join(problems)

    @staticmethod
    def _judge(result: GroupResult, group: GateGroup, log: Path) -> None:
        result.verdict, result.why = judge_group(group, result.exit, log)
        note = jobs_note(result)
        if note:  # a lowered group says so whatever its verdict: a timeout then names its cause, a pass names its handicap
            result.why = f"{result.why}；{note}" if result.why else note
        result.counts = pytest_counts(log)
        result.log_sha256 = sha256_file(log)

    @staticmethod
    def _finalize(summary: GateSummary) -> None:
        names = {g.name for g in GROUPS}
        summary.complete = (
            set(summary.results) == names and summary.manifest_sha256 == manifest_sha256()
        )
        all_pass = bool(summary.results) and all(
            r.verdict == "PASS" for r in summary.results.values()
        )
        problems = list(summary.reasons)
        for name, result in summary.results.items():
            if result.verdict != "PASS":
                problems.append(f"组 {name}：{result.verdict}，{result.why or '没有原因记录'}")
        if summary.git_dirty is not False or summary.git_dirty_end is not False:
            problems.append("工作树不干净（含未跟踪文件）或读不出")
        if not summary.commit or summary.commit != summary.commit_end:
            problems.append("开跑和跑完的提交号不一致或读不出")
        if summary.ignored_code:
            problems.append(
                f"有被 .gitignore 藏起来的代码或配置文件：{'、'.join(summary.ignored_code[:3])}"
            )
        if not summary.complete:
            problems.append("组不齐全")
        summary.reasons = list(dict.fromkeys(problems))
        summary.verdict = (
            "PASS" if all_pass and not summary.reasons else ("PARTIAL" if all_pass else "FAIL")
        )

    @staticmethod
    def _write(out_dir: Path, summary: GateSummary) -> None:
        text = json.dumps(asdict(summary), ensure_ascii=False, indent=2)
        tmp = out_dir / f"{SUMMARY_FILE}.tmp"
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, out_dir / SUMMARY_FILE)


def _int_or_none(value: object) -> int | None:
    return value if type(value) is int else None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
