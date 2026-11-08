"""Pre-push self check (``gate precheck``): the three checks CI runs first, in one read-only command.

CI keeps failing on things a person could have seen in half a minute: a ruff finding, a mypy error on the Windows platform, a test
that the change broke.  ``precheck`` runs, in the worktree's project folder and with the same white-listed child environment as the
official gate (:func:`gate_run_service.child_environment`):

1. ``ruff check --no-cache auto_pm tests``;
2. ``mypy --platform win32 --no-incremental --cache-dir=/dev/null auto_pm tests``;
3. the pytest files that belong to the change (see :func:`related_tests`).

It is the quick check before a push, **not** the release gate: ``gate run`` stays the full pre-deploy gate.  It never writes the
ledger; its own arguments write nothing into the worktree (no caches: ``--no-cache``, ``--cache-dir=/dev/null``,
``-p no:cacheprovider``, ``PYTHONDONTWRITEBYTECODE``; junit goes to the log folder).  A test inside a full run that starts pytest in
the worktree again can still leave a git-ignored ``coverage/junit/test-results.xml``; ``git status`` and the index do not change.  The
step logs go to a temporary folder (or ``--out``).  A change outside the project folder (``AGENTS.md``, ``reviews/``, workflows) has no
step here: it is listed and the verdict is at best ``UNVERIFIED``.  A step whose tool is not installed is ``UNVERIFIED``, never a pass.
"""

from __future__ import annotations

import ast
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
FULL_TIMEOUT_SECONDS = 45 * 60  # the whole tests/ tree with -n 4 took about 12 minutes on the cloud container (audit of #634)
PARALLEL_FROM = 4  # this many test files or more (or the whole tree): run them with xdist
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
    outside_changes: list[str] = field(default_factory=list)  # changed files outside the project folder: no step of this check looks at them

    @property
    def verdict(self) -> str:
        verdicts = {step.verdict for step in self.steps}
        if "FAIL" in verdicts:
            return "FAIL"
        if self.outside_changes:
            return "UNVERIFIED"
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


def _dotted(relative: str) -> str:
    """``auto_pm/a/b.py`` -> ``auto_pm.a.b``; a package ``__init__`` names the package itself."""

    parts = Path(relative).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


_DOTTED_NAME = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")


def _imports_of(path: Path, relative: str) -> set[str] | None:
    """The module names a file may import (see :func:`_references_of`); ``None`` when it cannot be read or parsed."""

    found = _references_of(path, relative)
    return None if found is None else found[0]


def _references_of(path: Path, relative: str) -> tuple[set[str], set[str]] | None:
    """What a test file refers to: ``(module names, string constants)``, read with ``ast``.

    Module names: every import (multi-line and ``as`` forms, imports inside functions, relative imports); ``from a import b, c`` yields
    ``a``, ``a.b`` and ``a.c`` (``b`` may be a module or a name; both are candidates).  A string constant that looks like a dotted name
    (``monkeypatch.setattr("auto_pm.x.y.func", ...)``, ``importlib.import_module("auto_pm.x")``) counts as a reference to every dotted
    prefix of it.  Strings: every string constant, so a test that opens a file by its path or name can be matched to that file.
    ``None`` when the file cannot be read or parsed: the caller must then assume it may depend on anything.
    """

    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))  # bytes: ast copes with a UTF-8 BOM and the coding cookie
    except (OSError, SyntaxError, ValueError):
        return None
    package = _dotted(relative) if relative.endswith("__init__.py") else _dotted(relative).rpartition(".")[0]
    found: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
            if _DOTTED_NAME.match(node.value):
                parts = node.value.split(".")
                found.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")
                anchor = anchor[: len(anchor) - (node.level - 1)] if node.level > 1 else anchor
                base = ".".join(part for part in (*anchor, base) if part)
            if base:
                found.add(base)
            found.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names if alias.name != "*")
    return found, strings


def _touches(imports: set[str], module: str, is_package: bool) -> bool:
    """Does a file with these imports load ``module``?  Importing ``a.b.c`` loads package ``a.b`` first, so a change to a package
    ``__init__`` reaches every importer of anything below it."""

    return module in imports or (is_package and any(name.startswith(module + ".") for name in imports))


_SOURCE_TREE_WORDS = ("auto_pm", "scripts", "tests")
_WALKERS = frozenset({"rglob", "glob", "walk", "scandir"})


def _scans_the_tree(path: Path) -> bool:
    """A guard test: it walks a source folder (``rglob``/``glob``/``os.walk``/``scandir`` call) and names ``auto_pm``, ``scripts`` or ``tests``.

    Such a test does not import the module a change touches, it reads every file, so any Python file written wrongly turns it red.
    Unreadable or unparsable counts as a guard (run more).
    """

    try:
        raw = path.read_bytes()
        tree = ast.parse(raw, filename=str(path))
    except (OSError, SyntaxError, ValueError):
        return True
    text = raw.decode("utf-8", errors="ignore")  # lenient-decode: only looks for three words
    if not any(word in text for word in _SOURCE_TREE_WORDS):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if name in _WALKERS:
                return True
    return False


def related_tests(project: Path, project_relative_changes: Sequence[str]) -> tuple[list[str], str]:
    """The test files that belong to a change, as paths relative to ``project``; and a note when the set is "everything".

    Principle (audit 1 of #634): when the choice is not certain, run more, never report PASS on tests that did not run.

    * a changed ``test_*.py`` is itself related;
    * a changed Python module (``auto_pm``, ``scripts`` ...) is related to every test file that imports it, **directly or through
      the helper modules and conftest files under ``tests/``** (parsed with ``ast``);
    * a changed ``conftest.py`` is related to every test file under its folder; ``tests/conftest.py`` / ``pyproject.toml`` /
      ``requirements.txt`` mean everything;
    * a changed file that is neither Python nor documentation (``.qml``, ``.jinja``, ``.yaml`` ...) and a test file that cannot be parsed
      mean everything, because nothing says which tests read it;
    * documentation (``.md`` / ``.rst``) relates to nothing;
    * **any changed Python file also pulls in every guard test** (audit 2 of #634): a test file that calls ``rglob``/``glob``/``os.walk``/
      ``scandir`` (found with ``ast``, no hand-kept list) and mentions ``auto_pm``, ``scripts`` or ``tests`` in its text.  These read the
      whole source tree (no unexplained ``errors="replace"``, subprocess encodings and timeouts, layer imports ...) and never import the
      changed module, so the import graph cannot select them.  The criterion is deliberately wide (about 84 of 440 files; 22 of them
      ``rglob("*.py")`` the tree); a test that walks the tree by other means (``iterdir`` recursion, ``git ls-files``) is not recognised.

    A string constant counts too: a dotted name (``monkeypatch.setattr("auto_pm.x.y", ...)``, ``import_module``) refers to the module and its
    packages, and a path or file name (``"main.py"``) refers to the file (audit 2 self-check: 18 tests reach a module only that way).

    Indirect dependence through ``auto_pm`` modules (A imports B, a test imports A) is **not** followed: that would make nearly every
    change relate to nearly every test.  It is the one known blind spot (CI and ``gate run`` stay the full check).
    """

    changes = [path for path in project_relative_changes if path and not path.endswith((".md", ".rst"))]
    if any(path in EVERYTHING_FILES for path in changes):
        return ["tests"], "改到了 conftest/pyproject/requirements：相关测试 = 全部 tests（并行跑，会比较慢）"
    others = [path for path in changes if not path.endswith(".py")]
    if others:
        return ["tests"], f"改到了非 Python 文件（{others[0]} 等 {len(others)} 个），没有可靠的办法知道哪些测试读它：相关测试 = 全部 tests"
    # a deleted or renamed module stays in the list (D-128): the tests that import its old name now fail with ImportError, and mypy's
    # ignore_missing_imports hides that, so only a test run shows it
    python = list(changes)
    test_files = sorted(p.relative_to(project).as_posix() for p in (project / "tests").rglob("*.py")) if (project / "tests").is_dir() else []
    imports: dict[str, set[str]] = {}
    strings: dict[str, set[str]] = {}
    for relative in test_files:
        parsed = _references_of(project / relative, relative)
        if parsed is None:
            return ["tests"], f"{relative} 读不出/解析不了，没法判断依赖：相关测试 = 全部 tests"
        imports[relative], strings[relative] = parsed
    by_dotted = {_dotted(relative): relative for relative in test_files}
    conftests = [relative for relative in test_files if Path(relative).name == "conftest.py"]

    def conftests_above(relative: str) -> list[str]:
        folder = Path(relative).parent
        return [c for c in conftests if folder == Path(c).parent or Path(c).parent in folder.parents]

    related: set[str] = set()
    changed_modules: list[tuple[str, bool]] = []  # (dotted name, is a package __init__)
    for path in python:
        name = Path(path).name
        if name == "conftest.py":
            folder = Path(path).parent
            related.update(t for t in test_files if Path(t).name.startswith("test_") and (folder in Path(t).parents or folder == Path(t).parent))
        if path.startswith("tests/") and name.startswith("test_") and (project / path).is_file():
            related.add(path)
        if path.endswith(".py") and not (path.startswith("tests/") and name.startswith("test_")):
            changed_modules.append((_dotted(path), name == "__init__.py"))
    # dependency edges inside tests/: a test depends on the tests-modules it imports and on the conftest files above it
    depends: dict[str, set[str]] = {}
    for relative, names in imports.items():
        targets = {by_dotted[name] for name in names if name in by_dotted}
        targets.update(conftests_above(relative))
        depends[relative] = targets - {relative}
    direct = {
        relative
        for relative, names in imports.items()
        if any(_touches(names, module, is_package) for module, is_package in changed_modules)
    }
    # a test that names a changed file in a string (opens "main.py" or "auto_pm/x/y.py" by path) depends on it without importing it
    named = [path for path in python if Path(path).name not in {"__init__.py", "conftest.py"} and not Path(path).name.startswith("test_")]
    direct.update(
        relative
        for relative, texts in strings.items()
        if any(
            path in text or text == Path(path).name or text.endswith("/" + Path(path).name)
            for path in named
            for text in texts
        )
    )
    changed = set(direct)
    grew = True
    while grew:
        grew = False
        for relative, targets in depends.items():
            if relative not in changed and targets & changed:
                changed.add(relative)
                grew = True
    related.update(t for t in changed if Path(t).name.startswith("test_"))
    guards = sorted(t for t in test_files if Path(t).name.startswith("test_") and _scans_the_tree(project / t))
    if changes:
        related.update(guards)
        return sorted(related), f"含 {len(guards)} 个扫整棵源码树的守卫类测试（任何 Python 改动都会带上）"
    return sorted(related), ""


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
        outside = [path for path in changed if not path.startswith(prefix)]
        report = PrecheckReport(base=base, changed=changed, related_tests=tests, scope_note=note, outside_changes=outside)
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
            # the project's addopts write coverage/junit/test-results.xml into the worktree and --no-cov does not stop that: point it at the logs
            junit = f"--junitxml={logs / 'pytest-junit.xml'}"
            pytest_argv = [python, "-B", "-m", "pytest", *tests, "-p", "no:cacheprovider", "--no-cov", "-q", junit]
            if (len(tests) >= PARALLEL_FROM or tests == ["tests"]) and jobs > 1:
                pytest_argv += ["-n", str(jobs), "--dist", "loadfile"]
            plan.append(("pytest", pytest_argv))
        for name, argv in plan:
            log = logs / f"{name}.txt"
            code: int | None
            try:
                limit = max(timeout_seconds, FULL_TIMEOUT_SECONDS) if tests == ["tests"] and name == "pytest" else timeout_seconds
                code = self._runner(argv, project, env, log, limit)
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
