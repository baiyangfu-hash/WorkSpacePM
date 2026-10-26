"""提交钩子输出含 emoji，在 GBK 终端上不能因编码报错（TD-SW008-015）"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from auto_pm.cli import git_hook as git_hook_module
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def _gbk_stream() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="gbk", errors="strict", write_through=True)


def test_emoji_print_crashes_on_a_strict_gbk_stream_without_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    """前提：没有修复时，GBK 严格流上 print 钩子提示确实抛错（保证下面的用例是真测试）。"""
    monkeypatch.setattr(sys, "stdout", _gbk_stream())
    with pytest.raises(UnicodeEncodeError):
        print("❌ [auto-pm ledger gate] 台账对账不一致")


def test_make_stdio_encoding_safe_lets_the_hook_prints_through(monkeypatch: pytest.MonkeyPatch) -> None:
    out, err = _gbk_stream(), _gbk_stream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    git_hook_module.make_stdio_encoding_safe()
    print("❌ [auto-pm ledger gate] 台账对账不一致")
    print("⚠️ [auto-pm pre-commit] 无关提示", file=sys.stderr)
    assert "台账对账不一致".encode("gbk") in out.buffer.getvalue()
    assert b"?" in out.buffer.getvalue()  # emoji 换成 ?，汉字原样


def test_utf8_streams_are_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True)
    monkeypatch.setattr(sys, "stdout", out)
    git_hook_module.make_stdio_encoding_safe()
    print("❌ 台账")
    assert out.buffer.getvalue().decode("utf-8").rstrip("\r\n") == "❌ 台账"


def test_streams_without_reconfigure_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", object())
    monkeypatch.setattr(sys, "stderr", object())
    git_hook_module.make_stdio_encoding_safe()  # 不抛


@pytest.mark.parametrize("sub", [["pre-commit"], ["release-gate"]])
def test_every_git_hook_command_runs_the_stdio_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sub: list[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(git_hook_module, "make_stdio_encoding_safe", lambda: calls.append("guard"))
    monkeypatch.setattr(git_hook_module, "enforce_pre_commit", lambda *a, **k: 0)
    monkeypatch.setattr(git_hook_module, "enforce_release_ledger_gate", lambda *a, **k: 0)
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "git-hook", *sub])
    assert result.exit_code == 0, result.output
    assert calls == ["guard"]
