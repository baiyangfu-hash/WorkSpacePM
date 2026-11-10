"""Is this interpreter fit to run the official gate? (D-196)

2026-11-09: the full gate was started with the system Python.  It has no xdist, so every group died at once with
``unrecognized arguments: -n`` and the summary said FAIL with an empty reason column.  The gate now looks at its own
interpreter *before* it starts a single group and refuses, with the command to use instead, when it is not fit.

Everything here is read-only: one probe subprocess, nothing written.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: import names the test children need.  The first four are what a gate group loads before its first test runs.
REQUIRED_MODULES: tuple[str, ...] = ("pytest", "xdist", "pytest_qt", "PySide6", "jinja2")
PROBE_TIMEOUT_SECONDS = 60
UNFIT_HEADLINE = "环境不合格，未开跑"

_PROBE_CODE = (
    "import importlib.util, json, sys\n"
    "mods = json.loads(sys.argv[1])\n"
    "missing = [m for m in mods if importlib.util.find_spec(m) is None]\n"
    "print(json.dumps({'version': list(sys.version_info[:3]), 'venv': sys.prefix != sys.base_prefix, 'missing': missing}))\n"
)

#: Log lines that mean "the test run could not even start" rather than "a test failed".
ENV_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"unrecognized arguments:.*(?:-n\b|--numprocesses|--dist)"),
    re.compile(
        r"No module named ['\"]?(?:xdist|pytest_qt|pytestqt|PySide6|jinja2|pytest_cov|pytest_asyncio)"
    ),
    re.compile(r"ImportError while loading conftest"),
    re.compile(r"ModuleNotFoundError: No module named"),
    re.compile(r"Fatal Python error"),
)


@dataclass(frozen=True)
class EnvReport:
    version: tuple[int, ...] = ()
    in_venv: bool = False
    missing: tuple[str, ...] = ()
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def fit(self) -> bool:
        return not self.error and not self.missing


Prober = Callable[[Sequence[str], int], "subprocess.CompletedProcess[bytes]"]


def _run_probe(argv: Sequence[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 - argv is the interpreter under test plus a fixed one-liner
        list(argv), capture_output=True, check=False, timeout=timeout, stdin=subprocess.DEVNULL
    )


def probe_interpreter(python: str, *, prober: Prober = _run_probe) -> EnvReport:
    argv = [python, "-I", "-c", _PROBE_CODE, json.dumps(list(REQUIRED_MODULES))]
    try:
        done = prober(argv, PROBE_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        return EnvReport(error=f"解释器 {python} 起不来或探测超时：{error}")
    if done.returncode != 0:
        tail = (
            done.stderr.decode("utf-8", errors="replace").strip().splitlines()
        )  # lenient-decode: diagnostic text only
        return EnvReport(
            error=f"解释器 {python} 运行探测脚本失败（退出码 {done.returncode}）：{tail[-1] if tail else '无输出'}"
        )
    try:
        data = json.loads(
            done.stdout.decode("utf-8", errors="replace")
        )  # lenient-decode: a JSON parse follows
        return EnvReport(
            version=tuple(int(n) for n in data["version"]),
            in_venv=bool(data["venv"]),
            missing=tuple(str(m) for m in data["missing"]),
        )
    except (ValueError, KeyError, TypeError):
        return EnvReport(error=f"解释器 {python} 的探测输出读不懂：{done.stdout[:80]!r}")


def venv_command_hint(worktree: Path) -> str:
    """The interpreter to use instead: the control root's ``.venv`` if it exists, else how to build it."""

    for parent in (worktree, *worktree.parents):
        for relative in (".venv/Scripts/python.exe", ".venv/bin/python"):
            candidate = parent / relative
            if candidate.is_file():
                return f"{candidate} -B main.py gate run …"
    return (
        "先在仓库根建环境：sh 00_Infrastructure/auto_pm/environment/setup_env.sh（Windows 用 setup_env.ps1），"
        "再用 .venv 里的 python 启动：<仓库根>/.venv/Scripts/python.exe -B main.py gate run …"
    )


def preflight_problems(
    python: str, worktree: Path, *, prober: Prober = _run_probe
) -> tuple[list[str], list[str]]:
    """``(refusals, warnings)``.  Any refusal means the gate must not start."""

    report = probe_interpreter(python, prober=prober)
    refusals: list[str] = []
    warnings: list[str] = []
    if report.error:
        refusals.append(report.error)
    elif report.missing:
        refusals.append(f"解释器 {python} 缺少测试要用的包：{'、'.join(report.missing)}")
    if not report.error and not report.in_venv:
        warnings.append(
            f"当前解释器 {python} 不在虚拟环境里（像是系统 Python），门禁应该用控制根的 .venv"
        )
    if refusals or warnings:
        hint = f"正确的启动方式：{venv_command_hint(worktree)}"
        (refusals or warnings).append(hint)
    return refusals, warnings


def looks_like_environment_error(log_text: str) -> str:
    """The matching log line when the group died of its environment rather than of a failing test, else ``""``."""

    for line in log_text.splitlines():
        for pattern in ENV_ERROR_PATTERNS:
            if pattern.search(line):
                return line.strip()[:200]
    return ""


def current_interpreter() -> str:
    return sys.executable
