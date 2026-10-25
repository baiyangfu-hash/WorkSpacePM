"""LocalCodexExecutor 解析命令名：带路径的名字原样使用，不再经 PATH 解析（审计 145 的存活变异）。

Linux 上 ``shutil.which`` 对带路径的名字会原样返回或返回 None，结果与“没有守卫”无法区分；
所以这里直接监视 ``which`` 是否被调用：守卫被删掉，带路径的名字会走到 ``which``，用例变红。
"""

from __future__ import annotations

import os

import pytest

from auto_pm.infrastructure.local_executor import LocalCodexExecutor


@pytest.fixture
def which_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_which(command: str, *args: object, **kwargs: object) -> str | None:
        calls.append(command)
        return "/resolved/by/path/" + command

    monkeypatch.setattr("shutil.which", fake_which)
    return calls


def test_command_with_a_path_is_used_as_given_and_never_resolved(which_calls: list[str]) -> None:
    for command in (os.path.join("opt", "codex"), os.sep + os.path.join("opt", "codex")):
        executor = LocalCodexExecutor(command_prefix=(command, "exec"))
        assert executor._command_prefix == (command, "exec")  # noqa: SLF001
    assert which_calls == []


def test_bare_command_name_is_resolved_through_path(which_calls: list[str]) -> None:
    executor = LocalCodexExecutor(command_prefix=("codex", "exec"))
    assert which_calls == ["codex"]
    assert executor._command_prefix == ("/resolved/by/path/codex", "exec")  # noqa: SLF001


def test_unknown_bare_name_is_left_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda *_args, **_kwargs: None)
    assert LocalCodexExecutor(command_prefix=("codex",))._command_prefix == ("codex",)  # noqa: SLF001
