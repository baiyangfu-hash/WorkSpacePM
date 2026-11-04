"""TD-SW008-267 ratchet: the "a Run never works in the control root" rule cannot be switched off by accident or bypassed by a new path.

Two ways the rule could silently rot, each pinned here:

1. **Tests turning it off.**  ``tests/conftest.py`` switches the guard off for the whole session (hundreds of throw-away
   repositories use their own root as the station) and ``control_root_guard_on`` switches it back on.  Any other test file that
   patches the guard, or asks for ``control_root_guard_on`` without being on the list below, goes red.  A new file that needs the
   real rule is added to ``FILES_THAT_MAY_USE_THE_REAL_GUARD`` on purpose, in review.
2. **A new write path for Runs.**  Every place in ``auto_pm`` that creates a Run row (``create_run``) must call the guard first and
   raise on it.  A second path that skips it fails here, naming the function.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "auto_pm"
TESTS = ROOT / "tests"
THIS_FILE = Path(__file__).resolve()
GUARD = "_worktree_is_the_control_root"
OPT_IN_FIXTURE = "control_root_guard_on"
# The same opt-in in its apply-later form (a scene is built with the rule off, then the test calls the switch).
OPT_IN_FIXTURES = frozenset({OPT_IN_FIXTURE, "control_root_guard_switch"})
# Test files (relative to tests/) allowed to run with the real guard on.  Add a file here only on purpose, in review.
FILES_THAT_MAY_USE_THE_REAL_GUARD = frozenset(
    {
        "core/test_run_start_control_root_guard.py",
        "cli/test_continuity_recovery_run.py",
        # CHG-SCPT-2026-476: the exit drills walk the recovery chain with the production control-root rule on.
        "e2e/test_exit_drill.py",
    }
)
# The one module that implements ``create_run`` itself (it is the storage layer; the service in front of it owns the rule).
STORE_MODULE = PACKAGE / "infrastructure" / "continuity_store.py"
PATCHING_CALLS = frozenset({"setattr", "setitem", "delattr", "patch", "object", "multiple", "dict"})


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_bytes(), filename=str(path))  # bytes: some files start with a BOM


def _mentions(node: ast.AST, name: str) -> bool:
    """True when *name* appears under *node* as an identifier, attribute or (part of a) string constant."""

    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == name:
            return True
        if isinstance(child, ast.Attribute) and child.attr == name:
            return True
        if isinstance(child, ast.Constant) and isinstance(child.value, str) and name in child.value:
            return True
    return False


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def patches_the_guard(tree: ast.AST) -> list[int]:
    """Line numbers of calls like ``monkeypatch.setattr(..., GUARD, ...)`` / ``mock.patch("...GUARD")`` in *tree*."""

    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _call_name(node) in PATCHING_CALLS
        and _mentions(node, GUARD)
    ]


def asks_for_the_real_guard(tree: ast.AST) -> bool:
    """True when the module requests the opt-in fixture (parameter name or ``usefixtures("…")`` string)."""

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if any(arg.arg in OPT_IN_FIXTURES for arg in all_args):
                return True
        if isinstance(node, ast.Constant) and node.value in OPT_IN_FIXTURES:
            return True
    return False


def _calls_to(node: ast.AST, name: str) -> list[ast.Call]:
    return [c for c in ast.walk(node) if isinstance(c, ast.Call) and _call_name(c) == name]


def _guards_by_raising(function: ast.AST, before_line: int) -> bool:
    """True when *function* has ``if <…GUARD(…)…>: raise …`` that starts before *before_line*."""

    for node in ast.walk(function):
        if not isinstance(node, ast.If) or node.lineno >= before_line:
            continue
        if _calls_to(node.test, GUARD) and any(
            isinstance(inner, ast.Raise) for stmt in node.body for inner in ast.walk(stmt)
        ):
            return True
    return False


def unguarded_run_writers(tree: ast.Module, label: str) -> list[str]:
    """Functions in *tree* that call ``create_run`` without first raising on the guard (``label`` names the file)."""

    problems: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in _calls_to(function, "create_run"):
            if not _guards_by_raising(function, call.lineno):
                problems.append(f"{label}:{call.lineno} {function.name}")
    return problems


def run_writer_functions(tree: ast.Module) -> list[str]:
    return [
        function.name
        for function in ast.walk(tree)
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _calls_to(function, "create_run")
    ]


def test_only_conftest_and_the_listed_files_touch_the_guard() -> None:
    patchers: list[str] = []
    askers: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        if path.resolve() == THIS_FILE or path.name == "conftest.py" and path.parent == TESTS:
            continue
        tree = _parse(path)
        relative = path.relative_to(TESTS).as_posix()
        patchers.extend(f"tests/{relative}:{line}" for line in patches_the_guard(tree))
        if asks_for_the_real_guard(tree) and relative not in FILES_THAT_MAY_USE_THE_REAL_GUARD:
            askers.append(f"tests/{relative}")
    assert not patchers, f"这些测试在改守卫函数 {GUARD}（只有 tests/conftest.py 可以）：{patchers}"
    assert not askers, (
        f"这些测试用了 {OPT_IN_FIXTURE} 但不在名单 FILES_THAT_MAY_USE_THE_REAL_GUARD 里：{askers}"
    )


def test_the_listed_files_exist_and_really_use_the_real_guard() -> None:
    """A stale name on the list would let a differently named file in unnoticed."""

    for relative in FILES_THAT_MAY_USE_THE_REAL_GUARD:
        path = TESTS / relative
        assert path.is_file(), f"名单里的 {relative} 不存在，请同步名单"
        assert asks_for_the_real_guard(_parse(path)), (
            f"名单里的 {relative} 没有用 {OPT_IN_FIXTURE}，请从名单删掉"
        )


def test_the_ratchet_sees_a_patched_guard_and_an_unlisted_opt_in() -> None:
    """Self-check: the scanners do flag what they are written to flag."""

    patched = ast.parse(
        f'def test_x(monkeypatch):\n    monkeypatch.setattr(mod, "{GUARD}", lambda a, b: False)\n'
    )
    assert patches_the_guard(patched) == [2]
    string_target = ast.parse(
        f'def test_x(monkeypatch):\n    monkeypatch.setattr("auto_pm.application.core.x.{GUARD}", None)\n'
    )
    assert patches_the_guard(string_target) == [2]
    mock_patch = ast.parse(
        f'def test_x():\n    with mock.patch.object(mod, "{GUARD}"):\n        pass\n'
    )
    assert patches_the_guard(mock_patch)
    assert not patches_the_guard(
        ast.parse(f"def test_x():\n    assert mod.{GUARD}(a, b) is True\n")
    )
    assert asks_for_the_real_guard(ast.parse(f"def test_x({OPT_IN_FIXTURE}):\n    pass\n"))
    assert asks_for_the_real_guard(
        ast.parse(f'pytestmark = pytest.mark.usefixtures("{OPT_IN_FIXTURE}")\n')
    )
    assert asks_for_the_real_guard(ast.parse("def test_x(control_root_guard_switch):\n    pass\n"))
    assert not asks_for_the_real_guard(ast.parse("def test_x(tmp_path):\n    pass\n"))


def test_every_service_that_creates_a_run_raises_on_the_guard_first() -> None:
    writers: list[str] = []
    problems: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == STORE_MODULE.resolve():
            continue
        tree = _parse(path)
        relative = path.relative_to(ROOT).as_posix()
        writers.extend(f"{relative}::{name}" for name in run_writer_functions(tree))
        problems.extend(unguarded_run_writers(tree, relative))
    assert writers, (
        "没有找到任何调用 create_run 的服务方法：棘轮已经看不到东西了，请核对它的扫描范围"
    )
    assert not problems, (
        f"这些方法创建 Run 前没有先检查守卫 {GUARD}（并在命中时 raise）：{problems}"
    )


def test_the_writer_scanner_flags_a_second_path_without_the_guard() -> None:
    guarded = ast.parse(
        f"def start(self):\n    if {GUARD}(a, b):\n        raise ValueError('x')\n    self._store.create_run(v)\n"
    )
    assert unguarded_run_writers(guarded, "f.py") == []
    unguarded = ast.parse("def sneak(self):\n    self._store.create_run(v)\n")
    assert unguarded_run_writers(unguarded, "f.py") == ["f.py:2 sneak"]
    guard_after = ast.parse(
        f"def late(self):\n    self._store.create_run(v)\n    if {GUARD}(a, b):\n        raise ValueError('x')\n"
    )
    assert unguarded_run_writers(guard_after, "f.py") == ["f.py:2 late"]
    no_raise = ast.parse(
        f"def soft(self):\n    if {GUARD}(a, b):\n        print('x')\n    self._store.create_run(v)\n"
    )
    assert unguarded_run_writers(no_raise, "f.py") == ["f.py:4 soft"]
