"""总控屏全流程测试是发版前必过的闸：正式门禁（``main.py gate run`` 的分组）必收它们，并且它们不能悄悄跳过。

像联锁回路里的“断线检测”：总控屏全流程（主线和“出事了”两份）本来就在 ``tests/core`` 里，正式门禁的 core 组会跑到。
可门禁按组判，一组里跳过 40 个以内都算过（``gate_run_service.MAX_SKIPPED``）：这两份测试要是被分组漏掉、被 ``--ignore`` 掉、
被谁加了跳过标记，或者门禁那台机器的虚拟环境里少了 PySide6、pytest-qt（文件头的 ``importorskip`` 会让整份测试跳过），
门禁照样是绿的，总控屏坏了也发得出去。本文件把这几条断线各接一个检测，任何一条断了就红。

只读门禁的分组表和这两份测试的源码，不改门禁代码、不改那两份测试。
"""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path

import pytest

from auto_pm.application.core import gate_run_service as gate

PROJECT_DIR = Path(__file__).resolve().parents[2]

# 发版前必过的总控屏测试（相对驾驶舱项目目录）。新加一份总控屏端到端测试，就加到这里。
BOARD_FLOW_FILES = (
    "tests/core/test_cockpit_board_full_flow.py",
    "tests/core/test_cockpit_board_incident_flow.py",
)
# 这两份测试的文件头只许用 importorskip 跳过这两样；门禁那台机器上必须装着（见最后一条测试）。
# 缺 PySide6 时 tests/conftest.py 的 pytest_configure 整个进程就起不来（门禁那组直接红）；缺 pytest-qt 却只会让这两份整份跳过，
# 其余照跑、门禁照绿（2026-11-16 云端改坏试验实测），所以最后一条主要守的是 pytest-qt。
QT_STACK = ("PySide6", "pytestqt")


def _covers(prefix: str, path: str) -> bool:
    """``prefix``（一个 pytest 目标或 --ignore 路径）是不是把 ``path`` 这个文件包进去了。"""

    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _groups_running(path: str) -> list[str]:
    taken = []
    for group in gate.GROUPS:
        if not any(_covers(target, path) for target in group.targets):
            continue
        if any(_covers(ignored, path) for ignored in group.ignore):
            continue
        taken.append(group.name)
    return taken


@pytest.mark.parametrize("path", BOARD_FLOW_FILES)
def test_the_official_gate_runs_each_board_flow_file_in_exactly_one_group(path: str) -> None:
    assert (PROJECT_DIR / path).is_file(), f"{path} 不见了：发版前必过的总控屏测试被删或改名，要先改这里并说明理由"
    taken = _groups_running(path)
    assert len(taken) == 1, f"正式门禁应当正好有 1 组跑 {path}，实际 {taken}（gate_run_service.GROUPS 的 targets/ignore 改过）"
    deselected = [d for group in gate.GROUPS for d in group.deselect if d.split("::")[0] == path]
    assert not deselected, f"正式门禁把 {path} 里的用例剔除了：{deselected}"


SKIP_WORDS = ("skip", "skipif", "importorskip", "xfail")


def _skip_problems(path: str) -> list[str]:
    """源码里所有能让用例跳过或不算数的写法（文件头那两句 importorskip 除外）。

    * ``skip``、``skipif``、``importorskip`` 不管怎么写（点号、别名、``getattr``）都算；
    * ``xfail`` 只许写成调用，并且带 ``strict=True`` 和 ``raises=``，不许带 ``run=``（不带括号的 ``@pytest.mark.xfail`` 什么都吞）；
    * 模块级 ``pytestmark`` 里出现上面任何一样都算（整份文件一起变）；
    * ``from pytest import skip`` 一类的导入都算（别名调用就看不出来了）。
    """

    tree = ast.parse((PROJECT_DIR / path).read_text(encoding="utf-8", errors="replace"), filename=path)
    allowed: set[int] = set()
    for node in tree.body:  # 只认文件头一句一句的 pytest.importorskip("PySide6") / ("pytestqt")
        call = node.value if isinstance(node, ast.Expr) else None
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "importorskip"
            and len(call.args) == 1
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value in QT_STACK
        ):
            allowed.add(id(call.func))
    calls = {id(c.func): c for c in ast.walk(tree) if isinstance(c, ast.Call)}
    problems = []
    for found in ast.walk(tree):
        name = found.attr if isinstance(found, ast.Attribute) else found.id if isinstance(found, ast.Name) else ""
        if name in ("skip", "skipif", "importorskip") and id(found) not in allowed:
            problems.append(f"第 {found.lineno} 行 {ast.unparse(found)}")
        elif name == "xfail":
            call = calls.get(id(found))
            if call is None:
                problems.append(f"第 {found.lineno} 行 {ast.unparse(found)} 没写成调用（不带 strict、raises，什么错都吞）")
                continue
            keywords = {k.arg: k.value for k in call.keywords}
            strict = keywords.get("strict")
            if not (isinstance(strict, ast.Constant) and strict.value is True):
                problems.append(f"第 {found.lineno} 行 xfail 没写 strict=True（修好了不会自己变红）")
            if "raises" not in keywords:
                problems.append(f"第 {found.lineno} 行 xfail 没写 raises=（别的错也会被当成已知缺陷吞掉）")
            if "run" in keywords:
                problems.append(f"第 {found.lineno} 行 xfail 写了 run=（run=False 用例根本不跑）")
        if isinstance(found, ast.ImportFrom) and (found.module or "").split(".")[0] in ("pytest", "_pytest"):
            hits = [a.name for a in found.names if a.name in (*SKIP_WORDS, "mark", "*")]
            if hits:
                problems.append(f"第 {found.lineno} 行 from {found.module} import {hits}（换个名字调用就看不出来）")
        if isinstance(found, ast.Call) and isinstance(found.func, ast.Name) and found.func.id == "getattr":
            texts = [a.value for a in found.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if any(t in SKIP_WORDS for t in texts):
                problems.append(f"第 {found.lineno} 行 {ast.unparse(found)}")
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign | ast.AugAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            problems.append(f"第 {node.lineno} 行模块级 pytestmark（整份文件一起被标记）：{ast.unparse(node)[:120]}")
    return problems


@pytest.mark.parametrize("path", BOARD_FLOW_FILES)
def test_a_board_flow_file_cannot_skip_quietly(path: str) -> None:
    problems = _skip_problems(path)
    assert not problems, f"{path} 里有能让发版闸悄悄放行的写法：{problems}"


@pytest.mark.parametrize("path", BOARD_FLOW_FILES)
def test_a_board_flow_file_has_tests_that_must_pass(path: str) -> None:
    """全是 xfail 的文件，门禁里一个 passed 都不出；每份至少一条除了 parametrize 不带任何标记的用例。"""

    tree = ast.parse((PROJECT_DIR / path).read_text(encoding="utf-8", errors="replace"), filename=path)
    tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    # 只带 parametrize 的才算必过：别的标记（包括先赋给一个名字再拿来装饰的 xfail）都不算
    must_pass = [n.name for n in tests if all(ast.unparse(d).startswith("pytest.mark.parametrize(") for d in n.decorator_list)]
    assert must_pass, f"{path} 里没有一条必须通过的用例：{[n.name for n in tests]}"


def _under_a_gate() -> str:
    """在正式门禁里（门禁给每组设 ``PROGRESS_ENV``）或 GitHub 的检查里跑，返回是哪一个；本机手跑返回空。"""

    if os.environ.get(gate.PROGRESS_ENV):
        return f"正式门禁（{gate.PROGRESS_ENV} 已设）"
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "GitHub 检查（GITHUB_ACTIONS=true）"
    return ""


def test_the_gate_has_the_qt_stack_so_the_board_flow_runs_instead_of_skipping() -> None:
    missing = []
    for name in QT_STACK:
        try:
            importlib.import_module(name)
        except ImportError as error:
            missing.append(f"{name}：{error}")
    where = _under_a_gate()
    if missing and not where:
        pytest.skip(f"本机手跑，没装 {missing}；正式门禁和 GitHub 检查里这一条会红")
    assert not missing, f"{where}的虚拟环境里缺 {missing}：总控屏全流程测试会整份跳过，发版闸形同虚设"
