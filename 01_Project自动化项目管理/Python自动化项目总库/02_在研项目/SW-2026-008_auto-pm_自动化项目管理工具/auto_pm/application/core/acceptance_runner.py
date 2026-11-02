"""Execute the approved acceptance commands, one by one, exactly as approved.

``pm plan --check "命令 => 退出码"`` used to only *store* the commands; the agent ran them itself and reported the
result, which is how a "done" could be claimed without the check ever passing.  :func:`run_acceptance_checks` is the
verifier's own execution: each command is split into an argument list (never passed to a shell), run from the given
directory (``pm verify`` passes the control root, where ``.venv`` and ``main.py`` live) with a UTF-8 environment and ``core.quotePath=false`` for Git, and its real exit code and output summary are
recorded.  A command that cannot start, times out, or exits with a code other than the approved one is a mismatch.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.acceptance_command import (
    WORKTREE_PLACEHOLDER,
    AcceptanceCommandError,
    command_problem,
    parse_command,
    with_git_quotepath,
)
from auto_pm.contracts.plan_checklist import AcceptanceCheck

__all__ = [
    "CONTROL_ROOT_ENV",
    "REPORT_DIRECTORY",
    "WORKSPACE_ENV",
    "AcceptanceScan",
    "AcceptanceScanFinding",
    "WORKTREE_ENV",
    "CheckRun",
    "execution_environment",
    "mismatch_lines",
    "refusal_reason",
    "worktree_environment",
    "run_acceptance_checks",
    "write_report",
]

#: Under the control root; ``.auto-pm`` is not tracked by Git.
REPORT_DIRECTORY = (".auto-pm", "reports", "acceptance")
#: Environment variable that tells an approved command where the Run's worktree is.
WORKTREE_ENV = "AUTO_PM_RUN_WORKTREE"
#: The cockpit's own switches: the project data to check (the worktree) and the ledger it reports to (the control root).
WORKSPACE_ENV = "AUTO_PM_WORKSPACE"
CONTROL_ROOT_ENV = "AUTO_PM_CONTROL_ROOT"
DEFAULT_TIMEOUT_SECONDS = 900
_TAIL_LINES = 20
_TAIL_CHARACTERS = 2000


@dataclass(frozen=True)
class CheckRun:
    """What really happened when one approved command was executed."""

    command: str
    argv: tuple[str, ...]
    argv_differs: bool
    expected_exit_code: int
    exit_code: int | None
    passed: bool
    seconds: float
    output_tail: str
    output_sha256: str
    output_bytes: int
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["argv"] = list(self.argv)
        return data


@dataclass(frozen=True)
class AcceptanceScanFinding:
    """One approved command (``index`` 1-based; 0 = the approval itself is unreadable) that ``pm verify`` would refuse."""

    mission_id: str
    index: int
    command: str
    reason: str


@dataclass(frozen=True)
class AcceptanceScan:
    """Result of the read-only ledger scan: how much was looked at and what would be refused."""

    missions_scanned: int
    commands_scanned: int
    findings: tuple[AcceptanceScanFinding, ...]
    #: Commands ``pm verify`` still runs but the plan stage would now refuse (Chinese text, ``$``, bare wildcards): the same
    #: text pasted into PowerShell is silently changed.  Listed only; they do not make the scan fail.
    fragile: tuple[AcceptanceScanFinding, ...] = ()


def worktree_environment(worktree: str | Path, control_root: str | Path) -> dict[str, str]:
    """What ties a command run from the control root to the Run's worktree.

    The command runs where ``.venv`` and ``main.py`` live, but it must judge the files the Run changed: cockpit commands
    (``main.py plc check <PID>``) read ``AUTO_PM_WORKSPACE`` as the project data and ``AUTO_PM_CONTROL_ROOT`` as the ledger,
    and scripts can read ``AUTO_PM_RUN_WORKTREE`` or take the path through the ``{worktree}`` placeholder.
    """

    return {
        WORKTREE_ENV: str(worktree),
        WORKSPACE_ENV: str(worktree),
        CONTROL_ROOT_ENV: str(control_root),
    }


def execution_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """A UTF-8 environment for the checks: Python in UTF-8 mode, Git told not to quote non-ASCII paths.

    Lease credentials are not handed to the checks.  Git is configured through ``GIT_CONFIG_*`` as well, so a Git call
    made *inside* a script (not only a top-level ``git`` command) also prints Chinese paths as they are.
    """

    env = {key: value for key, value in (os.environ if base is None else base).items() if "LEASE" not in key.upper()}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["NO_COLOR"] = "1"
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0
    env[f"GIT_CONFIG_KEY_{count}"] = "core.quotePath"
    env[f"GIT_CONFIG_VALUE_{count}"] = "false"
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    return env


def _decode(data: bytes) -> str:
    """UTF-8 first (the environment asks for it), then the Chinese Windows code page, then bytes as Latin-1."""

    for encoding in ("utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _tail(text: str) -> str:
    lines = text.strip().splitlines()[-_TAIL_LINES:]
    joined = "\n".join(lines)
    return joined[-_TAIL_CHARACTERS:]


def _resolve_executable(name: str, cwd: Path, env: Mapping[str, str]) -> str | None:
    if os.sep in name or (os.altsep and os.altsep in name):
        candidate = Path(name)
        path = candidate if candidate.is_absolute() else cwd / candidate
        return str(path) if path.exists() else None
    return shutil.which(name, path=env.get("PATH"))


def refusal_reason(command: str, *, cwd: str | Path, env: Mapping[str, str] | None = None) -> str:
    """Why ``pm verify`` would refuse to run ``command`` from ``cwd`` on this machine; empty when it would run.

    Read-only: nothing is executed.  The command is judged under both quoting rule sets (a plan approved on one platform
    may be verified on the other) and, with this platform's rules, its executable must exist where ``pm verify`` looks.
    """

    for windows in (os.name == "nt", os.name != "nt"):
        problem = command_problem(command, windows=windows)
        if problem:
            side = "本机引号规则" if windows == (os.name == "nt") else "另一平台的引号规则"
            return f"{side}下不能按原文执行：{problem}"
    argv = parse_command(command).argv
    environment = execution_environment() if env is None else dict(env)
    executable = argv[0]
    if _resolve_executable(executable, Path(cwd), environment) is None:
        return f"找不到命令 {executable}（在 {cwd} 下、按 PATH 查找）"
    return ""


def _failed(
    check: AcceptanceCheck, argv: tuple[str, ...], differs: bool, error: str, seconds: float = 0.0
) -> CheckRun:
    return CheckRun(
        command=check.command,
        argv=argv,
        argv_differs=differs,
        expected_exit_code=check.expected_exit_code,
        exit_code=None,
        passed=False,
        seconds=seconds,
        output_tail="",
        output_sha256="",
        output_bytes=0,
        error=error,
    )


def _run_one(
    check: AcceptanceCheck, *, cwd: Path, env: Mapping[str, str], timeout: int, windows: bool | None
) -> CheckRun:
    try:
        parsed = parse_command(check.command, windows=windows)
    except AcceptanceCommandError as error:
        return _failed(check, (), False, f"命令不能按原文执行：{error}")
    argv, differs = with_git_quotepath(parsed.argv)
    if any(WORKTREE_PLACEHOLDER in item for item in argv):
        worktree = env.get(WORKTREE_ENV, "")
        if not worktree:
            return _failed(check, argv, differs, f"命令里写了 {WORKTREE_PLACEHOLDER}，但这次验证没有工位路径可换")
        argv = tuple(item.replace(WORKTREE_PLACEHOLDER, worktree) for item in argv)
        differs = True
    executable = _resolve_executable(argv[0], cwd, env)
    if executable is None:
        return _failed(check, argv, differs, f"找不到命令 {argv[0]}（在 {cwd} 下、按 PATH 查找）")
    started = time.monotonic()
    try:
        done = subprocess.run(  # noqa: S603 - argument list, never a shell string
            [executable, *argv[1:]],
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failed(check, argv, differs, f"超过 {timeout} 秒没有结束，已终止", time.monotonic() - started)
    except OSError as error:
        return _failed(check, argv, differs, f"无法启动：{error}", time.monotonic() - started)
    seconds = time.monotonic() - started
    return CheckRun(
        command=check.command,
        argv=argv,
        argv_differs=differs,
        expected_exit_code=check.expected_exit_code,
        exit_code=done.returncode,
        passed=done.returncode == check.expected_exit_code,
        seconds=round(seconds, 3),
        output_tail=_tail(_decode(done.stdout)),
        output_sha256=hashlib.sha256(done.stdout).hexdigest(),
        output_bytes=len(done.stdout),
    )


def run_acceptance_checks(
    checks: Sequence[AcceptanceCheck],
    *,
    cwd: str | Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    env: Mapping[str, str] | None = None,
    extra_env: Mapping[str, str] | None = None,
    windows: bool | None = None,
) -> tuple[CheckRun, ...]:
    """Run every approved command in ``cwd`` (all of them, so one report shows every mismatch).

    ``extra_env`` is added on top of the execution environment -- ``pm verify`` uses it to tell a script where the Run's
    worktree is (``AUTO_PM_RUN_WORKTREE``) while the command itself runs from the control root.
    """

    root = Path(cwd)
    environment = execution_environment() if env is None else dict(env)
    if extra_env:
        environment.update(extra_env)
    if not root.is_dir():
        return tuple(_failed(check, (), False, f"执行目录不存在：{root}") for check in checks)
    return tuple(
        _run_one(check, cwd=root, env=environment, timeout=timeout, windows=windows) for check in checks
    )


def mismatch_lines(runs: Sequence[CheckRun]) -> tuple[str, ...]:
    """One readable line per failed command, for the refusal message."""

    lines: list[str] = []
    for index, run in enumerate(runs, start=1):
        if run.passed:
            continue
        if run.exit_code is None:
            lines.append(f"第 {index} 条验收命令 `{run.command}` 没有跑成：{run.error}")
            continue
        tail = " / ".join(run.output_tail.splitlines()[-3:])
        lines.append(
            f"第 {index} 条验收命令 `{run.command}` 期望退出码 {run.expected_exit_code}，实际 {run.exit_code}"
            + (f"：{tail}" if tail else "")
        )
    return tuple(lines)


def write_report(control_root: str | Path, run_id: str, runs: Sequence[CheckRun]) -> Path:
    """Persist what was executed; the file name carries the Run and the UTC second."""

    directory = Path(control_root).joinpath(*REPORT_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{run_id}-{stamp}.json"
    payload = {
        "schema_version": "acceptance-run.v1",
        "run_id": run_id,
        "executed_at": stamp,
        "all_passed": all(run.passed for run in runs),
        "checks": [run.as_dict() for run in runs],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
