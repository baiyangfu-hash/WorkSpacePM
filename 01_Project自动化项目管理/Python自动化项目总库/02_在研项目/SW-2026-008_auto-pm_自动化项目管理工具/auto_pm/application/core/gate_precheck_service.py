"""Pre-push self check (``gate precheck``): the three checks CI runs first, in one read-only command.

CI keeps failing on things a person could have seen in half a minute: a ruff finding, a mypy error on the Windows platform, a test
that the change broke.  ``precheck`` runs, in the worktree's project folder and with the same white-listed child environment as the
official gate (:func:`gate_run_service.child_environment`):

1. ``ruff check --no-cache auto_pm tests``;
2. ``mypy --platform win32 --no-incremental --cache-dir=/dev/null auto_pm tests``;
3. the pytest files that belong to the change (see :func:`related_tests`).

It is the quick check before a push, **not** the release gate: ``gate run`` stays the full pre-deploy gate.  It never writes the
ledger or the worktree (no caches: ``--no-cache``, ``--cache-dir=/dev/null``, ``-p no:cacheprovider``, ``PYTHONDONTWRITEBYTECODE``);
the step logs go to a temporary folder (or ``--out``).  A step whose tool is not installed is ``UNVERIFIED``, never a pass.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from auto_pm.application.core.gate_run_service import (
    GateRunError,
    Runner,
    _git,
    child_environment,
    default_runner,
    project_dir_in,
    pytest_counts,
)

DEFAULT_BASE = "origin/main"
STEP_TIMEOUT_SECONDS = 20 * 60
PARALLEL_FROM = 4  # more test files than this: run them with xdist
# A change to one of these can break any test: the related set is everything (slow, said out loud in the report).
EVERYTHING_FILES = frozenset({"tests/conftest.py", "pyproject.toml", "requirements.txt"})
_NO_MODULE = re.compile(r"No module named")


@dataclass
class StepResult:
    name: str
    verdict: str  # PASS | FAIL | UNVERIFIED | SKIPPED
    exit: int | None = None
    why: str = ""
    argv: list[str] = field(default_factory=list)
    log: str = ""


@dataclass
class PrecheckReport:
    base: str
    changed: list[str]
    related_tests: list[str]
    scope_note: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        verdicts = {step.verdict for step in self.steps}
        if "FAIL" in verdicts:
            return "FAIL"
        return "PASS" if verdicts <= {"PASS", "SKIPPED"} and "PASS" in verdicts else "UNVERIFIED"


def changed_files(worktree: Path, base: str) -> list[str]:
    """Repo-relative paths changed against the merge base with ``base`` (committed, staged, unstaged and untracked)."""

    merge_base = _git(worktree, "merge-base", base, "HEAD")
    if not merge_base:
        raise GateRunError(f"算不出 {base} 与当前提交的共同祖先（先 git fetch origin main？）")
    # -z: paths come back raw and NUL-separated; without it git quotes non-ASCII names ("\\350\\...") and nothing would match
    tracked = _git(worktree, "diff", "--name-only", "-z", "--no-renames", merge_base)
    untracked = _git(worktree, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked is None or untracked is None:
        raise GateRunError("git 读不出改动文件清单（索引损坏？）")
    return sorted({name for name in (tracked + "\0" + untracked).split("\0") if name.strip()})


def _module_names(relative: str) -> tuple[str, str]:
    """``auto_pm/a/b.py`` -> (``auto_pm.a.b``, ``auto_pm.a``); a package ``__init__`` names the package itself."""

    parts = Path(relative).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    dotted = ".".join(parts)
    return dotted, ".".join(parts[:-1])


def related_tests(project: Path, project_relative_changes: Sequence[str]) -> tuple[list[str], str]:
    """The test files that belong to a change, as paths relative to ``project``; and a note when the set is "everything".

    * a changed ``tests/**/test_*.py`` file is itself related;
    * a changed ``auto_pm/**/*.py`` module is related to every test file that imports it (``import auto_pm.a.b``,
      ``from auto_pm.a import b``, ``from auto_pm.a.b import x``) or is named ``test_<module>*.py``;
    * a change to ``tests/conftest.py`` / ``pyproject.toml`` / ``requirements.txt`` means every test is related.
    """

    changes = [path for path in project_relative_changes if path.endswith((".py", ".toml", ".txt"))]
    if any(path in EVERYTHING_FILES for path in changes):
        return ["tests"], "改到了 conftest/pyproject/requirements：相关测试 = 全部 tests（会比较慢）"
    found: set[str] = set()
    modules = [path for path in changes if path.startswith("auto_pm/") and path.endswith(".py")]
    for path in changes:
        if path.startswith("tests/") and Path(path).name.startswith("test_") and (project / path).is_file():
            found.add(path)
    if modules:
        patterns = []
        for module in modules:
            dotted, package = _module_names(module)
            leaf = dotted.rsplit(".", 1)[-1]
            patterns.append(
                (
                    re.compile(
                        rf"(?m)^\s*(?:import\s+{re.escape(dotted)}\b|from\s+{re.escape(dotted)}(?:\.\w+)*\s+import\b"
                        rf"|from\s+{re.escape(package)}\s+import\s+[^\n#]*\b{re.escape(leaf)}\b)"
                    ),
                    leaf,
                )
            )
        for test in sorted((project / "tests").rglob("test_*.py")):
            relative = test.relative_to(project).as_posix()
            if relative in found:
                continue
            text = test.read_text(encoding="utf-8", errors="replace")  # lenient-decode: only searched for import lines
            if any(regex.search(text) or test.name.startswith(f"test_{leaf}") for regex, leaf in patterns):
                found.add(relative)
    return sorted(found), ""


def _step_verdict(name: str, exit_code: int | None, log: Path) -> tuple[str, str]:
    tail = log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.is_file() else ""  # lenient-decode: tool output tail
    if exit_code == 0:
        return "PASS", ""
    if exit_code is None:
        return "FAIL", "没有退出码"
    if exit_code == 124:
        return "FAIL", "超时被杀掉"
    if _NO_MODULE.search(tail) and name != "pytest":
        return "UNVERIFIED", f"本环境没装 {name}（No module named）；用 setup_env.sh 建的 .venv 里的 python 来跑"
    return "FAIL", ""


class PrecheckService:
    def __init__(self, *, runner: Runner = default_runner, python: str = sys.executable) -> None:
        self._runner = runner
        self._python = python

    def run(
        self,
        worktree: Path,
        *,
        base: str = DEFAULT_BASE,
        out_dir: Path | None = None,
        jobs: int = 4,
        timeout_seconds: int = STEP_TIMEOUT_SECONDS,
    ) -> PrecheckReport:
        worktree = worktree.resolve()
        project = project_dir_in(worktree)
        if not (project / "tests").is_dir():
            raise GateRunError(f"{project} 里没有 tests/，无法自检（D-105：工作目录必须含 tests/）")
        changed = changed_files(worktree, base)
        top = _git(worktree, "rev-parse", "--show-toplevel")
        prefix = project.resolve().relative_to(Path(top).resolve()).as_posix() + "/" if top else ""
        inside = [path[len(prefix) :] for path in changed if path.startswith(prefix)]
        tests, note = related_tests(project, inside)
        report = PrecheckReport(base=base, changed=changed, related_tests=tests, scope_note=note)
        logs = out_dir or Path(tempfile.mkdtemp(prefix="gate-precheck-"))
        logs.mkdir(parents=True, exist_ok=True)
        env = child_environment()
        python = self._python
        plan: list[tuple[str, list[str]]] = [
            ("ruff", [python, "-B", "-m", "ruff", "check", "--no-cache", "auto_pm", "tests"]),
            (
                "mypy",
                [python, "-B", "-m", "mypy", "--platform", "win32", "--no-incremental", "--cache-dir=/dev/null", "auto_pm", "tests"],
            ),
        ]
        if tests:
            pytest_argv = [python, "-B", "-m", "pytest", *tests, "-p", "no:cacheprovider", "--no-cov", "-q"]
            if len(tests) >= PARALLEL_FROM and jobs > 1:
                pytest_argv += ["-n", str(jobs), "--dist", "loadfile"]
            plan.append(("pytest", pytest_argv))
        for name, argv in plan:
            log = logs / f"{name}.txt"
            code: int | None
            try:
                code = self._runner(argv, project, env, log, timeout_seconds)
            except (OSError, subprocess.SubprocessError) as error:
                log.write_text(f"[precheck] could not start: {error}\n", encoding="utf-8")
                code = None
            verdict, why = _step_verdict(name, code, log)
            if name == "pytest" and verdict == "PASS":
                counts = pytest_counts(log)
                if counts is None or counts.get("passed", 0) == 0:
                    verdict, why = "FAIL", "pytest 退出码 0 但没有 passed 收尾行（没有跑到任何用例）"
            report.steps.append(StepResult(name, verdict, code, why, argv, str(log)))
        if not tests:
            code_changed = any(path.endswith(".py") for path in inside)
            report.steps.append(
                StepResult(
                    "pytest",
                    "UNVERIFIED" if code_changed else "SKIPPED",
                    None,
                    "改了 Python 文件但没找到引用它们的测试文件：这些改动没有被任何测试检验到"
                    if code_changed
                    else "没有改 Python 文件，没有要跑的测试",
                )
            )
        return report
