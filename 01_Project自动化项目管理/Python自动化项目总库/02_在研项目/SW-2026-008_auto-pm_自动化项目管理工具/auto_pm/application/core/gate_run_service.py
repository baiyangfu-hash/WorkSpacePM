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
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "gate-run.v1"
SUMMARY_FILE = "gate_summary.json"
DEFAULT_TIMEOUT_SECONDS = 3 * 3600
LOG_TAIL_BYTES = 64 * 1024
MAX_SKIPPED = 40  # the deployment run had at most 15 skipped in one group

# Variables a test child may inherit.  Everything else is dropped, so a new cockpit variable can never leak in by default.
ENV_ALLOW = frozenset(
    {
        "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP", "TZ",
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
    argv += ["-p", "no:cacheprovider", "--no-cov", "-q"]
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


def judge_group(group: GateGroup, exit_code: int | None, log: Path) -> tuple[str, str]:
    """``("PASS"|"FAIL", why)`` for one group from its exit code and its own summary line."""

    if exit_code is None:
        return "FAIL", "没有退出码（没跑完）"
    if exit_code != 0:
        hint = (
            "（4/5：用法错误或一个用例都没收集到，通常是目录不对）" if exit_code in (4, 5) else ""
        )
        return "FAIL", f"退出码 {exit_code}{hint}"
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
    """Run one group with its output in ``log``; 124 on timeout (what ``timeout`` returns)."""

    with log.open("wb") as handle:
        try:
            return subprocess.run(  # noqa: S603 - argv is built from the group table
                list(argv),
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            handle.write(f"\n[gate run] killed after {timeout} s\n".encode())
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


def project_dir_in(worktree: Path, module_file: Path | None = None) -> Path:
    """The project folder (where ``tests/`` is) inside ``worktree``, found from where this code itself lives."""

    here = (module_file or Path(__file__)).resolve()
    top = _git(here.parent, "rev-parse", "--show-toplevel")
    if top is None:
        raise GateRunError("读不出这份代码所在的 Git 仓库根，无法定位项目目录")
    project = next((p for p in here.parents if (p / "pyproject.toml").is_file()), None)
    if project is None:
        raise GateRunError("找不到含 pyproject.toml 的项目目录")
    return worktree / project.relative_to(Path(top).resolve())


class GateRunService:
    def __init__(self, *, runner: Runner = default_runner, python: str = sys.executable) -> None:
        self._runner = runner
        self._python = python

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
    ) -> GateSummary:
        worktree = worktree.resolve()
        if not (worktree / ".git").exists():
            raise GateRunError(f"{worktree} 不是 Git 工作树")
        project = project_dir_in(worktree)
        if not (project / "tests").is_dir():
            raise GateRunError(f"{project} 下没有 tests/；门禁不会在别的目录里空跑")
        selected = self.select(only)
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
            argv = group_argv(group, python=self._python, jobs=jobs)
            result = GroupResult(group.name, argv, str(project), started=_now())
            log = out_dir / f"{group.name}.txt"
            result.exit = self._runner(argv, project, env, log, timeout_seconds)
            result.finished = _now()
            (out_dir / f"{group.name}.exit").write_text(f"{result.exit}\n", encoding="utf-8")
            result.exit_file = result.exit
            self._judge(result, group, log)
            summary.results[group.name] = result
            self._write(out_dir, summary)
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
                name, list(entry.get("argv", [])), str(entry.get("cwd", "")), exit=entry.get("exit")
            )
            if name not in groups:
                result.verdict, result.why = "FAIL", "记录里的组不在官方清单里"
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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
