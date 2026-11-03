"""Long regressions are not run by ``pm verify``; it accepts the record of a ``main.py long-run`` that ran them (11-03 memory P1, PR-C).

Why: a regression of 40-60 minutes run directly in an agent's terminal made the laptop's commit charge climb until the machine was nearly
dead, and ``pm verify`` itself runs each approved command in the foreground with a 900 second timeout, so such a regression cannot finish
there anyway.  The program cannot see (or stop) what an agent types in its own terminal; the one place it can insist is the evidence.

A *long* regression is a pytest command that collects more than ``LONG_CASES`` test cases, or one whose size cannot be determined (unknown
counts as long: the only cost of a wrong guess is one extra ``long-run``).  The duration cannot be known before it runs, so the case count
is the rule.  For such a command ``pm verify`` looks for a ``long-run.v1`` status file under ``.auto-pm/long-run/`` that says, all at once:

- the very same command (argument list), finished (DONE/FAILED, not STOPPED) with the approved exit code;
- run detached, with the memory guard, and the guard really sampled (``guard.json``);
- it ran in the control root (where the acceptance commands run) and judged this Run's worktree, which was committed (``git_dirty`` false) and is at the same ``git_head`` as the worktree is now, still clean;
- it ended after the Run was created, and the log file still has the recorded SHA-256;
- the log ends with a pytest summary line that ran every collected case and deselected none (a ``-k`` or ``PYTEST_ADDOPTS`` that picks a
  few cases is not the regression);
- the guard's number of samples and its times fit the job's duration, and the worker recorded which ``PYTEST_*`` variables it removed.

Anything else is refused, and the refusal prints the exact ``long-run start`` command to type.  What this cannot do: a status file is plain
JSON, **not a cryptographic proof**; whoever can write the control root can still write one by hand.  It raises the price of "I ran it, trust
me" from nothing to a forgery, and the user's own acceptance remains the last gate.  A root of trust (the ledger's hash chain, or evidence
issued by CI) is recorded as a P2 debt.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.acceptance_runner import CheckRun, run_acceptance_checks
from auto_pm.contracts.acceptance_command import (
    WORKTREE_PLACEHOLDER,
    AcceptanceCommandError,
    parse_command,
)
from auto_pm.contracts.plan_checklist import AcceptanceCheck
from auto_pm.infrastructure.executable_lookup import find_on_path
from auto_pm.infrastructure.long_run_core import LongRunError, LongRunMissingError, read_json_file

__all__ = ["LONG_CASES", "LongVerdict", "classify", "find_evidence", "run_checks", "start_command"]

#: A pytest command that collects more cases than this is a long regression.
LONG_CASES = 100
COLLECT_TIMEOUT_SECONDS = 180
SCHEMA = "long-run.v1"
RUN_ROOT = (".auto-pm", "long-run")
_COLLECTED = re.compile(r"(?:(\d+)/)?(\d+) tests? collected")
_PER_FILE = re.compile(r"^\S.*: (\d+)$")
#: The runner keeps the last 20 lines of output; a per-file listing that long may be cut, so it is not summed.
_TAIL_LINES = 20
_VERBOSITY = frozenset({"-q", "-qq", "-qqq", "--quiet", "-v", "-vv", "-vvv", "--verbose"})
_NAME_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
#: "1843 passed, 4 skipped, 2 deselected in 93.28s (0:01:33)": the line pytest prints last.
_SUMMARY_TOKEN = re.compile(r"(\d+) (passed|failed|skipped|deselected|xfailed|xpassed|errors?|warnings?|rerun)\b")
_SUMMARY_TIMING = re.compile(r"\bin \d+(?:\.\d+)?s\b")
_RAN_KINDS = ("passed", "failed", "skipped", "xfailed", "xpassed", "error")
LOG_TAIL_BYTES = 64 * 1024
#: The guard samples every 20 seconds by default; ``spec.json`` records the interval a run was started with.  It is self-reported, so a value below
#: ``MIN_POLL_SECONDS`` (or a missing / unreadable one) counts as the default: a forger cannot widen the allowed sample count by writing a tiny interval.
SAMPLE_SECONDS = 20
MIN_POLL_SECONDS = 0.1
MIN_SAMPLE_SECONDS = 120  # at least one sample per two minutes of the job
CLOCK_SLACK_SECONDS = 30
AFTER_END_SLACK_SECONDS = 120  # a job that ended before the guard even started is still sampled once, a little after the end
NOT_PROOF = "（long-run 记录是纯文件，不是密码学证明；能写控制根的人就能伪造，用户验收是最后一道）"


@dataclass(frozen=True)
class LongVerdict:
    """Whether a command is a long regression, and why (``cases`` is None when it could not be counted)."""

    long: bool
    reason: str
    cases: int | None = None


def _is_pytest(argv: Sequence[str]) -> bool:
    names = [Path(item.replace("\\", "/")).name.lower() for item in argv[:3]]
    return any(name in {"pytest", "pytest.exe", "py.test"} for name in names) or any(
        argv[i] == "-m" and argv[i + 1] == "pytest" for i in range(min(len(argv) - 1, 4))
    )


def _count(tail: str) -> int | None:
    found = _COLLECTED.findall(tail)
    if found:
        selected, total = found[-1]
        return int(selected or total)
    if "no tests collected" in tail:
        return 0
    lines = [line for line in tail.splitlines() if line.strip()]
    matches = [_PER_FILE.match(line) for line in lines]
    if lines and len(lines) < _TAIL_LINES and all(matches):  # ``-qq`` prints "file: N" and no total
        return sum(int(match.group(1)) for match in matches if match is not None)
    return None


def classify(
    check: AcceptanceCheck,
    *,
    cwd: str | Path,
    extra_env: Mapping[str, str],
    collect: Callable[..., tuple[CheckRun, ...]] = run_acceptance_checks,
) -> LongVerdict:
    """Decide whether ``check`` is a long regression.  Only a pytest command can be; it is counted with ``--collect-only`` (seconds, runs no test)."""

    try:
        argv = parse_command(check.command).argv
    except AcceptanceCommandError:
        return LongVerdict(False, "命令不能按原文执行，交给普通验收去报错")
    if not _is_pytest(argv):
        return LongVerdict(False, "不是 pytest 命令")
    if "--collect-only" in argv or "--co" in argv:
        return LongVerdict(False, "只收集不执行")
    # The same command with the verbosity flags replaced by one ``-q``: that prints the node ids and a "N tests collected" total.
    words = [item for item in argv if item not in _VERBOSITY] + ["--collect-only", "-q"]
    probe = AcceptanceCheck(command=subprocess.list2cmdline(words) if os.name == "nt" else shlex.join(words), expected_exit_code=0)
    (run,) = collect((probe,), cwd=cwd, extra_env=extra_env, timeout=COLLECT_TIMEOUT_SECONDS)
    # exit 0: collected; exit 5: nothing to collect (the real run would exit 5 too); anything else (usage error, collection error) is not a count
    cases = _count(run.output_tail) if run.exit_code in (0, 5) else None
    if cases is None:
        return LongVerdict(True, "数不出用例数，按长回归处理", None)
    if cases > LONG_CASES:
        return LongVerdict(True, f"收集到 {cases} 个用例，超过 {LONG_CASES}", cases)
    return LongVerdict(False, f"收集到 {cases} 个用例，不超过 {LONG_CASES}", cases)


def _git(worktree: str | Path, *args: str) -> str | None:
    git = find_on_path("git")
    if git is None:
        return None
    done = subprocess.run([git, "-C", str(worktree), *args], capture_output=True, check=False, timeout=60)  # noqa: S603
    if done.returncode != 0:
        return None
    try:
        return done.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None


def _same_path(left: str, right: str | Path) -> bool:
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def _parse_time(text: object) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def _read(path: Path) -> tuple[dict[str, object] | None, str]:
    """(the file's JSON object, "") — (None, "") when the file does not exist — (None, why) when it exists but cannot be read (after retries).

    "Absent" and "unreadable" are different findings: only the first may be treated as "no record"; the second is named in the refusal.
    """

    try:
        return read_json_file(path), ""
    except LongRunMissingError:
        return None, ""
    except LongRunError as error:
        return None, str(error)


def _pytest_summary(log_path: Path) -> dict[str, int] | None:
    """Counts of the last pytest summary line in the log (``error``/``warning`` singular), or None when the log has no such line."""

    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(handle.tell() - LOG_TAIL_BYTES, 0))
            tail = handle.read()
    except OSError:
        return None
    for line in reversed(tail.decode("latin-1").splitlines()):  # latin-1 never fails; the summary line is ASCII
        tokens = _SUMMARY_TOKEN.findall(line)
        if tokens and _SUMMARY_TIMING.search(line):
            counts: dict[str, int] = {}
            for number, kind in tokens:
                key = kind.rstrip("s") if kind in {"errors", "warnings"} else kind
                counts[key] = counts.get(key, 0) + int(number)
            return counts
    return None


def _log_problem(log_path: Path, cases: int | None) -> str:
    counts = _pytest_summary(log_path)
    if counts is None:
        return "日志里找不到 pytest 收尾行（形如 '1843 passed, 4 skipped in 93.28s'），这不是一次跑完的 pytest 输出"
    if counts.get("deselected", 0):
        return f"pytest 收尾行显示 {counts['deselected']} 个用例被 deselect（-k、-m 或 PYTEST_ADDOPTS 只选了一部分），这不是整套回归"
    ran = sum(counts.get(kind, 0) for kind in _RAN_KINDS)
    if cases is not None and ran != cases:
        return f"pytest 收尾行共 {ran} 个用例，而收集阶段数出 {cases} 个；没有跑全或跑的不是同一批"
    return ""


def _poll_seconds(task_dir: Path) -> tuple[float, str]:
    """(the guard interval the run was started with (``spec.json``), "") — a missing file, a value below the floor or a non-number is the
    default; a ``spec.json`` that exists but cannot be read is a refusal reason, not a silent default."""

    spec, unreadable = _read(task_dir / "spec.json")
    if unreadable:
        return float(SAMPLE_SECONDS), unreadable
    value = spec.get("guard_poll_seconds") if spec else None
    if isinstance(value, bool) or not isinstance(value, int | float) or not value >= MIN_POLL_SECONDS:
        return float(SAMPLE_SECONDS), ""
    return float(value), ""


def _guard_problem(guard: dict[str, object] | None, status: dict[str, object], poll_seconds: float = float(SAMPLE_SECONDS)) -> str:
    """The guard's sample count and times must fit the job's start and end.

    ``guard.json`` keeps only the first and the last sample time, no per-sample times, so the median of neighbouring intervals cannot be checked;
    the count is bounded above by ``duration / poll`` and below by one sample per ``MIN_SAMPLE_SECONDS``.
    """

    samples = guard.get("samples") if guard else None
    if guard is None or not isinstance(samples, int) or samples < 1:
        return "内存守卫没有采样记录（guard.json 缺失或为空）"
    started, ended = _parse_time(status.get("started_at")), _parse_time(status.get("ended_at"))
    guard_start, guard_last = _parse_time(guard.get("started_at")), _parse_time(guard.get("last_sample_at"))
    if started is None or ended is None or guard_start is None or guard_last is None:
        return "守卫或任务的起止时间读不出，无法核对守卫是否真的看着这个任务"
    seconds = max((ended - started).total_seconds(), 0.0)
    if (
        guard_start.timestamp() < started.timestamp() - CLOCK_SLACK_SECONDS
        or guard_last < guard_start
        or guard_last.timestamp() < started.timestamp() - CLOCK_SLACK_SECONDS
        or guard_start.timestamp() > ended.timestamp() + AFTER_END_SLACK_SECONDS
        or guard_last.timestamp() > ended.timestamp() + AFTER_END_SLACK_SECONDS
    ):
        return "守卫的时间不在任务的启动和结束之间，它看的不是这次运行"
    if samples < max(1, int(seconds // MIN_SAMPLE_SECONDS)) or samples > int(seconds // poll_seconds) + 6:
        return f"守卫采样 {samples} 次，与任务时长 {seconds:.0f} 秒对不上（每 {poll_seconds:g} 秒一次）"
    return ""


def _problem(
    status: dict[str, object],
    task_dir: Path,
    *,
    expected_exit_code: int,
    cwd: str | Path,
    worktree: str | Path,
    head: str | None,
    dirty: bool | None,
    run_started: datetime | None,
    cases: int | None,
) -> str:
    """Why this record (same command) is not acceptable evidence; empty when it is."""

    if status.get("state") not in {"DONE", "FAILED"}:
        return f"还没有正常结束（状态 {status.get('state')}；被停止的不算）"
    if status.get("exit_code") != expected_exit_code:
        return f"退出码是 {status.get('exit_code')}，批准的是 {expected_exit_code}"
    if status.get("detached") is not True or status.get("mem_guard") is not True:
        return "不是脱离终端并带内存守卫跑的"
    ran_in = status.get("cwd")
    if not isinstance(ran_in, str) or not _same_path(ran_in, cwd):
        return f"它在 {ran_in} 下运行，验收命令是在控制根 {cwd} 下运行的（相对路径和 .venv 的含义不同）"
    recorded = status.get("worktree")
    if not isinstance(recorded, str) or not _same_path(recorded, worktree):
        return f"它判的不是这个 Run 的工作树（记录的是 {recorded}）"
    if status.get("git_dirty") is not False:
        return "启动时工作树有未提交的改动（或读不出），结果不对应任何提交；先提交再跑"
    if not head or status.get("git_head") != head:
        return f"跑的时候工作树在 {str(status.get('git_head'))[:12]}，现在是 {str(head)[:12] or '读不出'}；代码变了，要重跑"
    if dirty is not False:
        return "工作树现在有未提交的改动（或读不出），上次的结果不再对应现在的代码；先提交再重跑"
    ended = _parse_time(status.get("ended_at"))
    if run_started is None or ended is None or ended <= run_started:
        return "结束时间不在本 Run 创建之后（或时间读不出）"
    guard, guard_unreadable = _read(task_dir / "guard.json")
    if guard_unreadable:
        return f"内存守卫的 guard.json 在，但读不了（读失败不等于没有记录）：{guard_unreadable}"
    poll, spec_unreadable = _poll_seconds(task_dir)
    if spec_unreadable:
        return f"spec.json 在，但读不了（读失败不等于没有记录）：{spec_unreadable}"
    guard_problem = _guard_problem(guard, status, poll)
    if guard_problem:
        return guard_problem
    if not isinstance(status.get("env_stripped"), list):
        return "记录里没有 env_stripped（工作进程是否剔除了 PYTEST_ADDOPTS 等变量无法确认；用当前版本的 long-run 重跑）"
    log = status.get("log")
    log_path = Path(log) if isinstance(log, str) else task_dir / "run.log"
    if _sha256(log_path) != status.get("log_sha256"):
        return "日志文件与记录的 SHA-256 对不上（被改过或丢了）"
    return _log_problem(log_path, cases)


def find_evidence(
    control_root: str | Path,
    argv: Sequence[str],
    expected_exit_code: int,
    *,
    worktree: str | Path,
    run_started: str,
    cases: int | None = None,
) -> tuple[dict[str, object] | None, str]:
    """(the acceptable ``long-run`` status for this command, "") or (None, why the closest record was refused / that there is none)."""

    base = Path(control_root).joinpath(*RUN_ROOT)
    head = _git(worktree, "rev-parse", "HEAD")
    status_text = _git(worktree, "status", "--porcelain", "--untracked-files=no")
    dirty = None if status_text is None else bool(status_text)
    started = _parse_time(run_started)
    closest = ""
    for task_dir in sorted(base.iterdir(), reverse=True) if base.is_dir() else []:
        status, unreadable = _read(task_dir / "status.json")
        if unreadable:  # cannot tell whether it is this command's record: name it instead of passing it over as "no record"
            closest = closest or f"记录 {task_dir.name} 的 status.json 在，但读不了（读失败不等于没有记录）：{unreadable}"
            continue
        if not status or status.get("schema_version") != SCHEMA or status.get("command") != list(argv):
            continue
        problem = _problem(
            status, task_dir, expected_exit_code=expected_exit_code, cwd=control_root, worktree=worktree, head=head, dirty=dirty, run_started=started, cases=cases
        )
        if not problem:
            return status, ""
        closest = closest or f"最近一条同命令的记录 {task_dir.name} 不能用：{problem}"
    return None, closest or "没有找到同一条命令的 long-run 记录"


def start_command(argv: Sequence[str], *, control_root: str | Path, worktree: str | Path, name: str) -> str:
    """The exact command to type (from the control root) to run ``argv`` as acceptable evidence."""

    windows = os.name == "nt"
    interpreter = r".venv\Scripts\python.exe" if windows else ".venv/bin/python"
    quote = subprocess.list2cmdline if windows else shlex.join
    head = quote([interpreter, "-B", "main.py", "long-run", "start", "--name", name, "--cwd", str(control_root), "--worktree", str(worktree), "--"])
    return f"{head} {quote(list(argv))}"


def _evidence_run(check: AcceptanceCheck, argv: tuple[str, ...], status: dict[str, object]) -> CheckRun:
    started, ended = _parse_time(status.get("started_at")), _parse_time(status.get("ended_at"))
    seconds = round((ended - started).total_seconds(), 3) if started and ended else 0.0
    exit_code = status.get("exit_code")
    peak = status.get("peak_committed_gib")
    note = (
        f"long-run 记录 {status.get('name')}：HEAD {str(status.get('git_head'))[:12]}，退出码 {exit_code}，"
        f"峰值已提交 {peak if peak is not None else '未知'} GiB，日志 SHA-256 {str(status.get('log_sha256'))[:16]}{NOT_PROOF}"
    )
    log_bytes = status.get("log_bytes")
    return CheckRun(
        command=check.command,
        argv=argv,
        argv_differs=False,
        expected_exit_code=check.expected_exit_code,
        exit_code=exit_code if isinstance(exit_code, int) else None,
        passed=True,
        seconds=seconds,
        output_tail=note,
        output_sha256=str(status.get("log_sha256") or ""),
        output_bytes=log_bytes if isinstance(log_bytes, int) else 0,
    )


def _refused(check: AcceptanceCheck, argv: tuple[str, ...], message: str) -> CheckRun:
    return CheckRun(
        command=check.command,
        argv=argv,
        argv_differs=False,
        expected_exit_code=check.expected_exit_code,
        exit_code=None,
        passed=False,
        seconds=0.0,
        output_tail="",
        output_sha256="",
        output_bytes=0,
        error=message,
    )


def run_checks(
    checks: Sequence[AcceptanceCheck],
    *,
    cwd: str | Path,
    extra_env: Mapping[str, str],
    worktree: str | Path,
    run_id: str,
    run_started: str,
    run_one: Callable[..., tuple[CheckRun, ...]] = run_acceptance_checks,
) -> tuple[CheckRun, ...]:
    """Like ``run_acceptance_checks`` (same order, every check reported), but a long regression is judged by its ``long-run`` record, not run."""

    results: list[CheckRun] = []
    for index, check in enumerate(checks, start=1):
        verdict = classify(check, cwd=cwd, extra_env=extra_env, collect=run_one)
        if not verdict.long:
            results.extend(run_one((check,), cwd=cwd, extra_env=extra_env))
            continue
        argv = tuple(item.replace(WORKTREE_PLACEHOLDER, str(worktree)) for item in parse_command(check.command).argv)
        status, why = find_evidence(cwd, argv, check.expected_exit_code, worktree=worktree, run_started=run_started, cases=verdict.cases)
        if status is not None:
            results.append(_evidence_run(check, argv, status))
            continue
        name = _NAME_SAFE.sub("-", f"verify-{run_id}-{index}-{datetime.now(UTC):%m%d%H%M}")[:64].strip("-.")
        results.append(
            _refused(
                check,
                argv,
                f"这是长回归（{verdict.reason}），pm verify 不在前台跑它，也不认你在终端里自己跑的结果；"
                f"{why}。{NOT_PROOF}请在控制根执行下面这条（脱离终端、带内存守卫，跑完留下记录），结束后再 pm verify：{start_command(argv, control_root=cwd, worktree=worktree, name=name)}",
            )
        )
    return tuple(results)
