"""批处理守护：仓库里所有 .bat/.cmd 不许再出现两类“括号块”写法错误。

1. 括号块里读 %errorlevel%（TD-SW008-150）：cmd 解析整个括号块时就把 %errorlevel%
   展开成进块前的旧值，块里命令失败也判断不到。改用 `命令 || ( ... )` 或 `if errorlevel 1`。
2. 括号块里的 echo 文字带没转义的右括号（TD-SW008-181，PR #51 修过 setup_env.bat 的 `(.venv)`）：
   cmd 把它当成块结束，后面报“此时不应有 ...”并中止。要写成 ^) 或改用全角括号。

只读，不执行批处理；Linux 上也能跑。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
ERRORLEVEL_VAR = re.compile(r"%errorlevel%", re.IGNORECASE)
COMMENT = re.compile(r"^\s*(?:@?rem(?:\s|$)|::)", re.IGNORECASE)
ECHO = re.compile(r"^\s*@?echo(?:[\s.]|$)", re.IGNORECASE)


def _tracked_scripts() -> list[Path]:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "*.bat", "*.cmd"],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [WORKSPACE_ROOT / p for p in out.split("\0") if p]


def _parens(line: str) -> tuple[int, int]:
    """数一行里引号外的左、右括号（^ 转义的不算）。"""
    opened = closed = 0
    in_quote = False
    escaped = False
    for ch in line:
        if escaped:
            escaped = False
            continue
        if ch == "^" and not in_quote:
            escaped = True
        elif ch == '"':
            in_quote = not in_quote
        elif not in_quote and ch == "(":
            opened += 1
        elif not in_quote and ch == ")":
            closed += 1
    return opened, closed


def check_batch(text: str) -> list[str]:
    """返回问题清单（“第 N 行：原因”），空表示没问题。"""
    problems: list[str] = []
    depth = 0
    for no, line in enumerate(text.splitlines(), start=1):
        if COMMENT.match(line):
            continue
        if ECHO.match(line):
            # 块外的 echo 文字里的括号不影响结构；块内 echo 的左括号不算开块，但没转义的右括号会提前结束块
            if depth > 0 and _parens(line)[1] > 0:
                problems.append(f"第 {no} 行：括号块里的 echo 带没转义的右括号，会提前结束块（写成 ^) 或用全角括号）")
            continue
        if depth > 0 and ERRORLEVEL_VAR.search(line):
            problems.append(f"第 {no} 行：括号块里读 %errorlevel%，解析时就展开成旧值（改用 || 或 if errorlevel 1）")
        opened, closed = _parens(line)
        depth = max(depth + opened - closed, 0)
    return problems


SCRIPTS = _tracked_scripts()


def test_found_the_known_scripts() -> None:
    names = {p.name for p in SCRIPTS}
    assert "setup_env.bat" in names
    assert "双击启动驾驶舱.bat" in names


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.relative_to(WORKSPACE_ROOT).as_posix())
def test_no_block_pitfalls(script: Path) -> None:
    text = script.read_bytes().decode("utf-8", errors="replace")
    assert check_batch(text) == []


# ---- 反例：检查本身要能抓到两类错误（防止检查失灵还报绿） ----

OLD_TD150 = """\
if not exist ".venv" (
    python -m venv .venv
    if %errorlevel% neq 0 (
        exit /b 1
    )
)
"""

OLD_TD181 = """\
if not exist ".venv" (
    echo 已有的 .venv (.venv) 不是 3.12
)
"""


def test_catches_errorlevel_in_block() -> None:
    assert len(check_batch(OLD_TD150)) == 1


def test_catches_errorlevel_case_and_nesting() -> None:
    text = 'for %%f in (*.txt) do (\r\n  if exist "%%f" (\r\n    type "%%f"\r\n    set rc=%ErrorLevel%\r\n  )\r\n)\r\n'
    assert len(check_batch(text)) == 1


def test_catches_unescaped_paren_in_block_echo() -> None:
    assert len(check_batch(OLD_TD181)) == 1


def test_allows_the_safe_forms() -> None:
    text = (
        "python -c \"import sys\" >nul 2>&1\n"
        "if %errorlevel% neq 0 (\n"
        "    echo 块外判断、块里转义 ^(.venv^) 都可以\n"
        "    exit /b 1\n"
        ")\n"
        "echo 块外的 echo (随便写)\n"
        "if not exist \".venv\" (\n"
        "    python -m venv .venv || (\n"
        "        echo 失败\n"
        "    )\n"
        "    rem 注释里写 %errorlevel% 不算\n"
        "    if errorlevel 1 exit /b 1\n"
        ")\n"
    )
    assert check_batch(text) == []
