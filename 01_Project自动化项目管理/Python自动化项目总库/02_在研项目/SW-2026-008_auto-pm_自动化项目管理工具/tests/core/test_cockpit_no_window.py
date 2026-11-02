"""总控屏后台子进程不弹黑窗口（用户 2026-11-01 S3 试用：点“重新读取”弹出好几个窗口又自动关掉）。

Windows 上界面从没有控制台的 pythonw 启动时，每条后台命令（git、main.py pm …）不带 CREATE_NO_WINDOW 都会各弹一个黑窗口。
这里两层防：每个入口真的把标志传给运行器；再用源码扫描拦住以后新加的后台调用漏掉它（open_console 是故意给用户看的新窗口，不在此列）。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, tool_actions  # noqa: E402

FLAG = 0x08000000  # CREATE_NO_WINDOW


class Spy:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.kwargs = kwargs
        return subprocess.CompletedProcess(command, 0, "{}", "")


def _entries(tmp_path: Path) -> list[tuple[str, Callable[[Spy], Any]]]:
    return [
        ("probe_online", lambda spy: actions.probe_online(tmp_path, runner=spy)),
        ("run_check", lambda spy: actions.run_check(tmp_path, tmp_path, "DJ-1", "plc_check", runner=spy)),
        ("run_cli", lambda spy: actions.run_cli(tmp_path, "读", ("pm", "pending"), runner=spy)),
        ("run_tool", lambda spy: tool_actions.run_tool(tmp_path, "change_list", {"pid": "DJ-1"}, runner=spy)),
    ]



def test_every_background_entry_passes_the_no_window_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions, "no_window_flag", lambda: FLAG)
    for name, call in _entries(tmp_path):
        spy = Spy()
        call(spy)
        assert spy.kwargs.get("creationflags") == FLAG, name


def test_without_the_flag_nothing_extra_is_passed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """非 Windows：no_window_flag 为 0，不传 creationflags（POSIX 上传非 0 会报错）。"""
    monkeypatch.setattr(actions, "no_window_flag", lambda: 0)
    for name, call in _entries(tmp_path):
        spy = Spy()
        call(spy)
        assert "creationflags" not in spy.kwargs, name


def _calls(path: Path) -> list[ast.Call]:
    return [node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8", errors="replace"))) if isinstance(node, ast.Call)]  # lenient-decode: 只扫源码结构


def _is_quiet(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg is None and isinstance(keyword.value, ast.Call) and getattr(keyword.value.func, "id", "") == "quiet":
            return True
        if keyword.arg == "creationflags":
            return True
    return False


def test_every_background_runner_call_in_the_cockpit_board_asks_for_no_window() -> None:
    """cockpit_board 里凡是 ``runner(...)`` 调用都要带 ``**quiet()``；``opener(...)`` 是故意开新窗口，不管；
    也不允许有人直接调 ``subprocess.run/Popen/check_output``（整个包里只有 actions / tool_actions 经运行器起进程）。"""
    missing, direct = [], []
    for path in sorted((SCRIPTS / "cockpit_board").rglob("*.py")):
        for call in _calls(path):
            func = call.func
            if isinstance(func, ast.Name) and func.id == "runner" and not _is_quiet(call):
                missing.append(f"{path.name}:{call.lineno}")
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "subprocess" \
                    and func.attr in {"run", "check_output", "check_call", "call"} and path.name != "actions.py":
                direct.append(f"{path.name}:{call.lineno}")
    assert missing == [], f"这些后台调用没带 **quiet()：{missing}"
    assert direct == [], f"不要在运行器之外直接起子进程：{direct}"


def test_the_dashboard_git_probe_hides_its_window() -> None:
    bad = [f"pm_dashboard.py:{c.lineno}" for c in _calls(SCRIPTS / "pm_dashboard.py")
           if isinstance(c.func, ast.Attribute) and c.func.attr in {"run", "Popen"} and getattr(c.func.value, "id", "") == "subprocess"
           and not _is_quiet(c)]
    assert bad == []


def test_online_probe_never_waits_for_a_password_or_pops_a_login_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """后台联网探测（每次刷新都跑）没登录时不能停下来问密码，也不能让凭据管理器弹窗。"""
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")  # 用户环境里即使开着，探测也要关掉
    monkeypatch.setenv("GCM_INTERACTIVE", "always")
    spy = Spy()
    actions.probe_online(tmp_path, runner=spy)
    assert spy.kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0" and spy.kwargs["env"]["GCM_INTERACTIVE"] == "never"
    assert spy.kwargs["env"]["PATH"] == os.environ["PATH"]  # 其余环境照旧，git 找得到自己
    assert os.environ["GIT_TERMINAL_PROMPT"] == "1"  # 不改本进程的环境
