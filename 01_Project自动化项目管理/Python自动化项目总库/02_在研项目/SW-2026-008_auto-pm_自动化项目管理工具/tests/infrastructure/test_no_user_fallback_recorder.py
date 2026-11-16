"""谁做的记账不许兜底写成 "user"（审计 ``audits/持有人字段记成user_只读核_20261115.md``）。

原来 5 处写成 ``caller_alias() or caller_agent().strip("?") or "user"`` 一类：认不出的 agent、忘了带标记的 agent 和用户本人
都被记成 user，事后看账会以为是用户本人干的。现在只有一个记录人函数 ``agent_worktree_service.recorder``：认得的 agent
记别名或名字，认不出记 ``unknown-agent``，没带标记记 ``no-agent-marker``（和 ``pm inbox`` 同一套词，``contracts.intake``）。

这里扫 ``auto_pm/`` 的源码：``… or "user"``、``… if … else "user"`` 这两种兜底一处都不许有（没有基线，现在就是 0），
同类写法结构上回不来。另核 ``recorder`` 本身的四种情况和 claim 写命令遇到认不出的调用方就拒。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core import agent_worktree_service as stations
from auto_pm.contracts.intake import NOTE_ACTOR_NO_MARKER, NOTE_ACTOR_UNKNOWN
from auto_pm.ui.cli.__main__ import cli

PACKAGE = Path(__file__).resolve().parents[2] / "auto_pm"
FALLBACK = "user"


def _is_fallback(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == FALLBACK


def user_fallbacks(source: str, filename: str = "<memory>") -> list[int]:
    """行号：``x or "user"``（"user" 是 or 的任一操作数）和 ``a if c else "user"``。"""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and any(_is_fallback(value) for value in node.values):
            lines.append(node.lineno)
        elif isinstance(node, ast.IfExp) and (_is_fallback(node.orelse) or _is_fallback(node.body)):
            lines.append(node.lineno)
    return lines


def test_no_user_fallback_anywhere_in_the_package() -> None:
    found = {
        str(path.relative_to(PACKAGE)): lines
        for path in sorted(PACKAGE.rglob("*.py"))
        if (lines := user_fallbacks(path.read_text(encoding="utf-8-sig"), str(path)))
    }
    assert found == {}, f"记录人兜底写成了 \"user\"，改用 agent_worktree_service.recorder()：{found}"


@pytest.mark.parametrize(
    "snippet",
    [
        'owner = explicit or caller_alias() or caller_agent().strip("?") or "user"',
        'record = {"caller": caller_alias() or caller_agent() or "user"}',
        "who = 'user' or name",
        'who = name if name else "user"',
    ],
)
def test_mutation_each_fallback_form_is_caught(snippet: str) -> None:
    assert user_fallbacks(snippet) == [1]


def test_the_word_alone_is_not_a_fallback() -> None:
    assert user_fallbacks('USER = "user"\nif actor == "user":\n    pass\n') == []


# ---- recorder() ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, NOTE_ACTOR_NO_MARKER),
        ({"AUTO_PM_AGENT": "nobody-on-the-roster"}, NOTE_ACTOR_UNKNOWN),
        ({"AUTO_PM_AGENT": "trae:cn", "CLAUDECODE": "1"}, NOTE_ACTOR_UNKNOWN),  # 标记互相矛盾
        ({"AUTO_PM_AGENT": "trae:cn"}, "trae"),  # 没有会话号：只用基名
        ({"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "a119dc00-0000-0000-0000-000000000000"}, "claude-a119dc"),
    ],
)
def test_recorder_never_writes_user(monkeypatch: pytest.MonkeyPatch, environ: dict[str, str], expected: str) -> None:
    for name in ("AUTO_PM_AGENT", "AUTO_PM_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    assert stations.recorder() == expected
    assert stations.recorder() != FALLBACK


# ---- claim 写命令：认不出的调用方一律拒 ------------------------------------------------------------------------

CLAIM_WRITES = [
    ("open", "999", "--paths", "x.py"),
    ("number", "--goal", "K6"),
    ("release", "999"),
    ("renew", "999"),
    ("add-paths", "999", "--paths", "x.py"),
    ("reclaim", "999", "--reason", "K6", "--approval-evidence-ref", "user-confirmation:2026-11-16T00:47:31Z"),
    ("note", "999", "--kind", "draft", "--to", "user", "--next", "无"),
]


@pytest.mark.parametrize("args", CLAIM_WRITES, ids=[args[0] for args in CLAIM_WRITES])
def test_claim_writes_refuse_a_caller_nobody_can_name(
    args: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--as`` 也救不了：工位命令早就这么拒（agent_worktree_service 里 ``caller == "?"``），占位和交接记录照办。"""
    monkeypatch.setenv("AUTO_PM_AGENT", "nobody-on-the-roster")
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.rglob("*"))
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "claim", *args, "--as", "someone"], catch_exceptions=False)
    assert result.exit_code == 1, result.output
    assert "认不出调用方" in result.output
    assert sorted(tmp_path.rglob("*")) == before


def test_claim_owner_defaults_to_the_recorder(monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.ui.cli import claim as claim_cli

    monkeypatch.setattr(claim_cli, "recorder", lambda: "claude-a119dc")
    assert claim_cli._owner("") == "claude-a119dc"
    assert claim_cli._owner(" trae-0a1b2c ") == "trae-0a1b2c"
