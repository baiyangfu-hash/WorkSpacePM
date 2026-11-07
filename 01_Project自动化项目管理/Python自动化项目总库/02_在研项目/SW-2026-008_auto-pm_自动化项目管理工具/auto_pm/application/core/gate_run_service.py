"""Official multi-group gate (D-107a / D-108 / D-105): one command that runs the nine regression groups and judges each one.

Why it exists: the formal gate used to be a hand-written script around ``long-run``.  It failed three times in a row for
three symptoms with one root: nothing official owned the groups and nothing owned the test environment.

* the groups ran in the release folder, found no ``tests/`` and ended "no tests ran" (exit 4/5) while the wrapper said DONE;
* the cockpit's ``AUTO_PM_WORKSPACE`` / ``AUTO_PM_CONTROL_ROOT`` / ``AUTO_PM_RUN_WORKTREE`` leaked into the e2e tests, which
  then ran against the real control root (rest: 45 failed, 11 errors);
* the pytest summary of a multi-group run could not be accepted by ``pm verify`` (D-107; the verify side is a separate PR).

Here the group list is code (and its SHA-256 is part of the evidence), each group's child process gets a white-listed
environment with no ``AUTO_PM_*`` variable at all, every group is judged from its own exit code and its own pytest summary
line (zero tests, a missing summary line, an unexpected deselect and exit codes 4/5 are failures), and the verdict is PASS only
when every group of the manifest ran.  Nothing here writes the ledger.
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


_DIR_GROUPS = ("application", "change", "cli", "contracts", "core", "infrastructure", "plc")
_BASIS = "tests/core/test_implementation_card_basis.py"
_DEBOUNCE = "tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events"

# The nine regression groups of the formal gate (the 11-07 deployment run: eleven pytest invocations).  ``rest`` is everything
# the other groups did not take; the two serial groups hold tests that cannot share a process with their neighbours.
GROUPS: tuple[GateGroup, ...] = (
    *(
        GateGroup(name, (f"tests/{name}",), ignore=(_BASIS,) if name == "core" else ())
        for name in _DIR_GROUPS
    ),
    GateGroup("core_basis_serial", (_BASIS,), parallel=False),
    GateGroup("qml", ("tests/qml",), deselect=(_DEBOUNCE,), parallel=False),
    GateGroup("qml_debounce_alone", (_DEBOUNCE,), parallel=False),
    GateGroup(
        "rest",
        ("tests",),
        ignore=tuple(f"tests/{name}" for name in (*_DIR_GROUPS, "qml")),
    ),
)


def manifest_sha256(groups: Sequence[GateGroup] = GROUPS) -> str:
    """Fingerprint of the group list; the evidence records it so a gate that quietly ran fewer groups is visible."""

    payload = [
        [g.name, list(g.targets), list(g.ignore), list(g.deselect), g.parallel]
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
_RAN_KINDS = ("passed", "failed", "error", "xfailed", "xpassed")


def pytest_counts(log: Path) -> dict[str, int] | None:
    """Counts on the last pytest summary line of ``log`` (singular keys), or ``None`` when there is no such line."""

    try:
        with log.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(handle.tell() - LOG_TAIL_BYTES, 0))
            tail = handle.read()
    except OSError:
        return None
    for line in reversed(
        tail.decode("utf-8", errors="replace").splitlines()
    ):  # lenient-decode: a log tail may start mid-character
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
    ran = sum(counts.get(kind, 0) for kind in _RAN_KINDS)
    if ran == 0:
        return "FAIL", "一个用例都没跑（no tests ran）"
    if counts.get("failed", 0) or counts.get("error", 0):
        return "FAIL", f"收尾行有失败或错误：{counts}"
    if counts.get("deselected", 0) and not group.deselect:
        return (
            "FAIL",
            f"有 {counts['deselected']} 个用例被 deselect，而这一组没有声明要剔除任何用例",
        )
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
        child = subprocess.Popen(  # noqa: S603 - argv is built from the group table
            list(argv),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        try:
            return child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
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
    started: str = ""
    finished: str = ""


@dataclass
class GateSummary:
    schema: str = SCHEMA
    commit: str = ""
    git_dirty: bool | None = None
    worktree: str = ""
    project_dir: str = ""
    manifest_sha256: str = ""
    groups_run: list[str] = field(default_factory=list)
    complete: bool = False
    verdict: str = "FAIL"
    results: dict[str, GroupResult] = field(default_factory=dict)


def _git(worktree: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603
            ["git", "-C", str(worktree), *args], capture_output=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (
        done.stdout.decode("utf-8", errors="replace").strip() if done.returncode == 0 else None
    )  # lenient-decode: git output


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
        status = _git(worktree, "status", "--porcelain", "--untracked-files=no")
        summary = GateSummary(
            commit=_git(worktree, "rev-parse", "HEAD") or "",
            git_dirty=None if status is None else bool(status),
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
            self._judge(result, group, log)
            summary.results[group.name] = result
            self._write(out_dir, summary)
        self._finalize(summary)
        self._write(out_dir, summary)
        return summary

    def judge_dir(self, out_dir: Path) -> GateSummary:
        """Read-only: recompute every verdict from the logs on disk (never regenerates anything)."""

        try:
            data = json.loads((out_dir / SUMMARY_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise GateRunError(f"读不了 {out_dir / SUMMARY_FILE}: {error}") from error
        groups = {g.name: g for g in GROUPS}
        summary = GateSummary(
            commit=str(data.get("commit", "")),
            git_dirty=data.get("git_dirty"),
            worktree=str(data.get("worktree", "")),
            project_dir=str(data.get("project_dir", "")),
            manifest_sha256=str(data.get("manifest_sha256", "")),
            groups_run=list(data.get("groups_run", [])),
        )
        for name, raw in dict(data.get("results", {})).items():
            result = GroupResult(
                name, list(raw.get("argv", [])), str(raw.get("cwd", "")), exit=raw.get("exit")
            )
            if name in groups:
                self._judge(result, groups[name], out_dir / f"{name}.txt")
            else:
                result.verdict, result.why = "FAIL", "记录里的组不在官方清单里"
            summary.results[name] = result
        self._finalize(summary)
        return summary

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
        clean = summary.git_dirty is False
        summary.verdict = (
            "PASS"
            if (summary.complete and all_pass and clean)
            else ("PARTIAL" if all_pass else "FAIL")
        )

    @staticmethod
    def _write(out_dir: Path, summary: GateSummary) -> None:
        text = json.dumps(asdict(summary), ensure_ascii=False, indent=2)
        tmp = out_dir / f"{SUMMARY_FILE}.tmp"
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, out_dir / SUMMARY_FILE)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
