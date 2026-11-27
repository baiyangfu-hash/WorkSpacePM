"""Pre-push self check (``gate precheck``): the three checks CI runs first, in one read-only command.

CI keeps failing on things a person could have seen in half a minute: a ruff finding, a mypy error on the Windows platform, a test
that the change broke.  ``precheck`` runs, in the worktree's project folder and with the same white-listed child environment as the
official gate (:func:`gate_run_service.child_environment`):

1. ``ruff check --no-cache auto_pm tests``;
2. ``mypy --platform win32 --no-incremental --cache-dir=<os.devnull> auto_pm tests``;
3. the pytest files that belong to the change (see :func:`related_tests`).

It is the quick check before a push, **not** the release gate: ``gate run`` stays the full pre-deploy gate.  It never writes the
ledger; its own arguments write nothing into the worktree (no caches: ``--no-cache``, ``--cache-dir=<os.devnull>``,
``-p no:cacheprovider``, ``PYTHONDONTWRITEBYTECODE``; junit goes to the log folder).  A test inside a full run that starts pytest in
the worktree again can still leave a git-ignored ``coverage/junit/test-results.xml``; ``git status`` and the index do not change.  The
step logs go to a temporary folder (or ``--out``).  A change outside the project folder (``AGENTS.md``, ``reviews/``, workflows) has no
step here: it is listed and the verdict is at best ``UNVERIFIED``.  A step whose tool is not installed is ``UNVERIFIED``, never a pass.
"""

from __future__ import annotations

import ast
import json
import os
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
from auto_pm.application.core.gate_tier_policy import (
    classify_gate_tier,
    is_l1_inside_record_path,
    is_l1_outside_record_path,
)

DEFAULT_BASE = "origin/main"
STEP_TIMEOUT_SECONDS = 20 * 60
FULL_TIMEOUT_SECONDS = 120 * 60  # Windows local parallel runs need headroom beyond the old 45-minute cloud estimate (CHG-SCPT-2026-722)
PARALLEL_FROM = 4  # this many test files or more (or the whole tree): run them with xdist
# A change to one of these can break any test: the related set is everything (slow, said out loud in the report).
EVERYTHING_FILES = frozenset({"tests/conftest.py", "pyproject.toml", "requirements.txt"})
# Local handoff exchange files (PM-056 Track B, card 318) are data records validated by test_pm_handoff.py, not full-suite triggers.
_HANDOFF_EXCHANGE_PREFIXES = ("04_监控/交接交换区/", "11_监控/交接交换区/")
_HANDOFF_TEST = "tests/infrastructure/test_pm_handoff.py"
SOURCE_GUARDS_MANIFEST = Path("tests") / "tools" / "sw008_ci" / "source_guards_manifest.txt"
_NO_MODULE = re.compile(r"No module named")


def _load_source_guards_manifest(manifest_path: Path) -> list[tuple[str, str]]:
    """Parse scoped source-guard test rules cleanly (UTF-8 strict)."""
    text = manifest_path.read_bytes().decode("utf-8")
    entries: list[tuple[str, str]] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"第 {line_no} 行缺少冒号分隔符：{stripped!r}")
        scope_raw, test_raw = stripped.split(":", 1)
        scope_spec = scope_raw.strip()
        test_rel = test_raw.strip()
        sub_scopes = [part.strip() for part in scope_spec.split(",") if part.strip()]
        if not scope_spec or not test_rel or "\\" in test_rel or test_rel.startswith("/") or not sub_scopes:
            raise ValueError(f"第 {line_no} 行规则非法：{stripped!r}")
        for scope in sub_scopes:
            if (
                scope != "*"
                and not scope.endswith("/")
                and not scope.startswith("*.")
                and "/" not in scope
                and "." not in scope
            ):
                raise ValueError(f"第 {line_no} 行作用域格式不支持：{scope!r}")
        entries.append((",".join(sub_scopes), test_rel))
    return entries


def _guard_scope_matches(scope_spec: str, changes: Sequence[str]) -> bool:
    for raw_scope in scope_spec.split(","):
        scope = raw_scope.strip()
        if not scope:
            continue
        if scope == "*":
            if changes:
                return True
            continue
        folded_scope = scope.casefold()
        if folded_scope.startswith("*."):
            ext = folded_scope[1:]
            if any(path.casefold().endswith(ext) for path in changes):
                return True
            continue
        if folded_scope.endswith("/"):
            if any(path.casefold().startswith(folded_scope) for path in changes):
                return True
            continue
        if any(path.casefold() == folded_scope for path in changes):
            return True
    return False


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
    full_gate_required: bool = False
    outside_changes: list[str] = field(default_factory=list)  # changed files outside the project folder: no step of this check looks at them
    tier: str = "L3"
    recommended_groups: list[str] = field(default_factory=list)
    require_plugin: bool = False
    tier_reasons: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        verdicts = {step.verdict for step in self.steps}
        if "FAIL" in verdicts:
            return "FAIL"
        if self.outside_changes or self.full_gate_required:
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
_OS_WALKERS = frozenset({"walk", "scandir"})
_GLOB_WALKERS = frozenset({"glob", "iglob"})
_NON_PY_PATTERN_SUFFIXES = (
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".log",
    ".scl",
    ".qml",
    ".html",
    ".css",
    ".js",
    ".xml",
    ".csv",
    ".png",
    ".svg",
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".sqlite",
    ".lock",
    ".bak",
    ".tmp",
    ".jsonl",
    ".jinja",
    ".j2",
    ".rst",
    ".ini",
    ".cfg",
    ".sh",
    ".bat",
    ".ps1",
    ".zip",
    ".tar",
    ".gz",
)


def _call_arg(node: ast.Call, keyword: str) -> ast.expr | None:
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def _pattern_scans_python(arg: ast.expr | None) -> bool:
    """Whether a ``glob``/``rglob`` pattern argument can match Python source files (fail-closed on unknown dynamic expressions)."""

    if arg is None:
        return True
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        pat = arg.value.strip().lower()
        if pat.endswith(".py"):
            return True
        if any(pat.endswith(ext) for ext in _NON_PY_PATTERN_SUFFIXES):
            return False
        if pat in ("*", "**", "**/*"):
            return False
        return ".py" in pat and not pat.endswith(".pyc")
    if isinstance(arg, ast.JoinedStr):
        tail = arg.values[-1] if arg.values else None
        if isinstance(tail, ast.Constant) and isinstance(tail.value, str):
            low = tail.value.strip().lower()
            if low.endswith(".py"):
                return True
            if any(low.endswith(ext) for ext in _NON_PY_PATTERN_SUFFIXES):
                return False
        literals = [v.value.lower() for v in arg.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        if any(lit.endswith(".py") for lit in literals):
            return True
        if any(any(lit.endswith(ext) for ext in _NON_PY_PATTERN_SUFFIXES) for lit in literals):
            return False
        return True
    return True


def _scans_the_tree(path: Path) -> bool:
    """A guard test: it walks a source folder for Python files and names ``auto_pm``, ``scripts`` or ``tests``.

    Recognised walkers:
    * ``os.walk`` / ``os.scandir`` (including module/symbol aliases, excluding ``ast.walk`` or unrelated local ``walk()``);
    * ``.rglob(...)`` / ``.glob(...)`` / ``glob.glob(...)`` / ``glob.iglob(...)`` whose pattern can match ``.py`` source files
      (excluding explicit non-Python data globs such as ``*.json``, ``*.md``, ``*.scl``, ``*.qml``, ``*.pyc``).

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
    os_mods: set[str] = set()
    os_funcs: set[str] = set()
    glob_mods: set[str] = set()
    glob_funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name == "os":
                    os_mods.add(local)
                elif alias.name == "glob":
                    glob_mods.add(local)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    if alias.name == "*":
                        os_funcs.update(_OS_WALKERS)
                    elif alias.name in _OS_WALKERS:
                        os_funcs.add(alias.asname or alias.name)
            elif node.module == "glob":
                for alias in node.names:
                    if alias.name == "*":
                        glob_funcs.update(_GLOB_WALKERS)
                    elif alias.name in _GLOB_WALKERS:
                        glob_funcs.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr in _OS_WALKERS and isinstance(func.value, ast.Name) and func.value.id in os_mods:
                return True
            if func.attr in _GLOB_WALKERS and isinstance(func.value, ast.Name) and func.value.id in glob_mods:
                if _pattern_scans_python(_call_arg(node, "pathname")):
                    return True
            elif func.attr in ("rglob", "glob"):
                if _pattern_scans_python(_call_arg(node, "pattern")):
                    return True
        elif isinstance(func, ast.Name):
            if func.id in os_funcs:
                return True
            if func.id in glob_funcs and _pattern_scans_python(_call_arg(node, "pathname")):
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
    * **any changed Python file also pulls in every guard test** (audit 2 of #634, refined by CHG-SCPT-2026-722): a test file that walks
      the source tree via ``os.walk``/``os.scandir`` or Python-matching ``rglob``/``glob`` (found with ``ast``, no hand-kept list) and
      mentions ``auto_pm``, ``scripts`` or ``tests`` in its text.  These read the whole source tree (no unexplained ``errors="replace"``,
      subprocess encodings and timeouts, layer imports ...) and never import the changed module, so the import graph cannot select them.
      Non-filesystem ``ast.walk`` calls and non-Python data globs (``*.json``, ``*.md``, ``*.scl``, ``*.qml``, ``*.pyc``) are excluded so
      unrelated E2E/PLC/QML tests are not pulled in on every edit; a test that walks the tree by other means (``iterdir`` recursion,
      ``git ls-files``) is not recognised.

    A string constant counts too: a dotted name (``monkeypatch.setattr("auto_pm.x.y", ...)``, ``import_module``) refers to the module and its
    packages, and a path or file name (``"main.py"``) refers to the file (audit 2 self-check: 18 tests reach a module only that way).

    Indirect dependence through ``auto_pm`` modules (A imports B, a test imports A) is **not** followed: that would make nearly every
    change relate to nearly every test.  It is the one known blind spot (CI and ``gate run`` stay the full check).
    """

    changes = [path for path in project_relative_changes if path and not path.endswith((".md", ".rst"))]
    if any(path in EVERYTHING_FILES for path in changes):
        return ["tests"], "改到了 conftest/pyproject/requirements：相关测试 = 全部 tests（并行跑，会比较慢）"
    handoff_changes = [
        path for path in changes if path.startswith(_HANDOFF_EXCHANGE_PREFIXES) and path.endswith((".json", ".jsonl"))
    ]
    handoff_set = set(handoff_changes)
    others = [path for path in changes if path not in handoff_set and not path.endswith(".py")]
    if others:
        return ["tests"], f"改到了非 Python 文件（{others[0]} 等 {len(others)} 个），没有可靠的办法知道哪些测试读它：相关测试 = 全部 tests"
    # a deleted or renamed module stays in the list (D-128): the tests that import its old name now fail with ImportError, and mypy's
    # ignore_missing_imports hides that, so only a test run shows it
    python = [path for path in changes if path not in handoff_set]
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
    if handoff_changes and (project / _HANDOFF_TEST).is_file():
        related.add(_HANDOFF_TEST)
    if python:
        manifest_path = project / SOURCE_GUARDS_MANIFEST
        if manifest_path.is_file():
            try:
                manifest_entries = _load_source_guards_manifest(manifest_path)
            except (OSError, ValueError) as exc:
                return ["tests"], f"守卫清单 {SOURCE_GUARDS_MANIFEST.as_posix()} 无效（{exc}）：相关测试 = 全部 tests"
            test_file_set = set(test_files)
            guards = sorted(
                {
                    test_rel
                    for scope, test_rel in manifest_entries
                    if test_rel in test_file_set and _guard_scope_matches(scope, changes)
                }
            )
            related.update(guards)
            note = f"按作用域守卫清单命中 {len(guards)} 个守卫类测试" if guards else ""
            return sorted(related), note
        guards = sorted(t for t in test_files if Path(t).name.startswith("test_") and _scans_the_tree(project / t))
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
    last = next((line.strip() for line in reversed(tail.splitlines()) if line.strip()), "")
    if _NO_MODULE.search(tail) and name == "pytest":
        return "FAIL", f"环境错误（pytest 或它的插件没装，测试没能开始）：{_missing_module_line(tail)}；用 setup_env.sh 建的 .venv 里的 python 来跑"
    # D-196: a FAIL always says why; an empty reason is what made the 11-09 gate summary unreadable.
    return "FAIL", f"退出码 {exit_code}" + (f"；日志最后一行：{last[:160]}" if last else "；日志是空的")


def _missing_module_line(tail: str) -> str:
    return next((line.strip()[:160] for line in tail.splitlines() if _NO_MODULE.search(line)), "No module named")


def _validate_record_files(
    worktree: Path,
    project: Path,
    outside_records: Sequence[str],
    inside_records: Sequence[str],
    log_path: Path,
) -> StepResult:
    """Validate whitelisted JSON/JSONL record files strictly (UTF-8 + schema) for L1 local closeout."""
    checked = 0
    errors: list[str] = []
    lines: list[str] = []

    targets: list[tuple[str, Path]] = [
        *((rel, worktree / rel) for rel in outside_records),
        *((rel, project / rel) for rel in inside_records),
    ]
    for rel, path in targets:
        checked += 1
        if not path.is_file():
            errors.append(f"{rel}: 文件不存在或被删除")
            lines.append(f"FAIL {rel}: missing")
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{rel}: UTF-8 读取失败（{exc}）")
            lines.append(f"FAIL {rel}: utf8 error {exc}")
            continue

        name = path.name.lower()
        if name.endswith(".jsonl"):
            for line_no, raw_line in enumerate(text.splitlines(), start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    parsed = json.loads(stripped)
                except ValueError as exc:
                    errors.append(f"{rel}:{line_no} JSONL 语法错误（{exc}）")
                    lines.append(f"FAIL {rel}:{line_no}: {exc}")
                    break
                if not isinstance(parsed, dict):
                    errors.append(f"{rel}:{line_no} 必须是 JSON 对象")
                    lines.append(f"FAIL {rel}:{line_no}: not an object")
                    break
            else:
                lines.append(f"PASS {rel}")
        else:
            try:
                parsed = json.loads(text)
            except ValueError as exc:
                errors.append(f"{rel}: JSON 语法错误（{exc}）")
                lines.append(f"FAIL {rel}: {exc}")
                continue
            if not isinstance(parsed, dict):
                errors.append(f"{rel}: 顶层必须是 JSON 对象")
                lines.append(f"FAIL {rel}: not an object")
                continue
            if name in ("active_release.json", "previous_release.json"):
                rel_id = parsed.get("release_id")
                if not isinstance(rel_id, str) or not rel_id.strip():
                    errors.append(f"{rel}: 缺少非空字符串字段 release_id")
                    lines.append(f"FAIL {rel}: missing release_id")
                    continue
            elif name == "deployment_manifest.json":
                if not isinstance(parsed.get("releases"), dict):
                    errors.append(f"{rel}: 缺少对象字段 releases")
                    lines.append(f"FAIL {rel}: missing releases")
                    continue
            lines.append(f"PASS {rel}")

    log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    if errors:
        return StepResult("records", "FAIL", 1, "；".join(errors[:5]), [], str(log_path))
    return StepResult("records", "PASS", 0, f"校验 {checked} 个记录类文件通过", [], str(log_path))


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
        defer_full: bool = False,
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
        raw_outside = [path for path in changed if not path.startswith(prefix)]
        outside_records = [path for path in raw_outside if is_l1_outside_record_path(path)]
        outside = [path for path in raw_outside if not is_l1_outside_record_path(path)]
        inside_records = [path for path in inside if is_l1_inside_record_path(path)]
        report = PrecheckReport(base=base, changed=changed, related_tests=tests, scope_note=note, outside_changes=outside)
        if not changed:
            report.tier = "L1"
            report.recommended_groups = []
            report.require_plugin = False
            report.tier_reasons = ["工作树相对基线无改动文件"]
        else:
            decision = classify_gate_tier(inside, project=project, outside_changes=raw_outside)
            report.tier = decision.tier
            report.recommended_groups = list(decision.recommended_groups)
            report.require_plugin = decision.require_plugin
            report.tier_reasons = list(decision.reasons)
        logs = out_dir or Path(tempfile.mkdtemp(prefix="gate-precheck-"))
        logs.mkdir(parents=True, exist_ok=True)
        if outside_records or inside_records:
            report.steps.append(
                _validate_record_files(worktree, project, outside_records, inside_records, logs / "records.txt")
            )
        env = child_environment()
        python = self._python
        changed_scripts = sorted(
            path for path in inside if path.startswith("scripts/") and path.endswith(".py") and (project / path).is_file()
        )
        plan: list[tuple[str, list[str]]] = [
            ("ruff", [python, "-B", "-m", "ruff", "check", "--no-cache", "auto_pm", "tests", *changed_scripts]),
            (
                "mypy",
                [python, "-B", "-m", "mypy", "--platform", "win32", "--no-incremental", "--no-sqlite-cache", f"--cache-dir={os.devnull}", "auto_pm", "tests"],
            ),
        ]
        report.full_gate_required = defer_full and bool(changed) and (report.tier != "L1" or tests == ["tests"])
        if report.full_gate_required:
            report.steps.append(StepResult("pytest", "SKIPPED", None, "交给托管全量门禁", [], ""))
        elif tests:
            # the project's addopts write coverage/junit/test-results.xml into the worktree and --no-cov does not stop that: point it at the logs
            junit = f"--junitxml={logs / 'pytest-junit.xml'}"
            pytest_argv = [python, "-B", "-m", "pytest", *tests, "-p", "no:cacheprovider", "--no-cov", "-q", junit]
            if tests == ["tests"]:
                execution_record = logs / "gate_execution.json"
                execution_record.write_text(
                    json.dumps(
                        {
                            "schema": "gate-execution.v1",
                            "kind": "gate-precheck",
                            "project": str(project.resolve()),
                            "worktree": str(worktree),
                            "commit": _git(worktree, "rev-parse", "HEAD"),
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                pytest_argv.append(f"--gate-execution={execution_record}")
            effective_jobs = min(jobs, 2) if (defer_full and report.tier == "L1") else jobs
            if (len(tests) >= PARALLEL_FROM or tests == ["tests"]) and effective_jobs > 1:
                pytest_argv += ["-n", str(effective_jobs), "--dist", "loadfile"]
            plan.append(("pytest", pytest_argv))
        for name, argv in plan:
            log = logs / f"{name}.txt"
            code: int | None
            try:
                limit = (
                    max(timeout_seconds, FULL_TIMEOUT_SECONDS)
                    if (tests == ["tests"] or len(tests) >= PARALLEL_FROM) and name == "pytest"
                    else timeout_seconds
                )
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
