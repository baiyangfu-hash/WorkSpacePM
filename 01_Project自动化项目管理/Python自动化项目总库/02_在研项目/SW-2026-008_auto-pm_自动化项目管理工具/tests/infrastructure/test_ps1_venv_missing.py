"""D-150: the PowerShell wrappers say "no .venv" in plain words (exit 3) instead of dying on CommandNotFoundException.

Without ``.venv\\Scripts\\python.exe`` the call ``& $python …`` throws a CommandNotFoundException in Windows PowerShell 5.1 that
says nothing about the real cause.  Each wrapper must test the interpreter path first, print the setup hint and exit with the
fixed code 3, before it touches ``AUTO_PM_AGENT`` (so there is nothing to restore).  Static check: no PowerShell runs here; the
real Windows run (both invocation styles) is done by the local thread.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

REPO_ROOT = Path(__file__).resolve().parents[6]
WRAPPERS = ["00_Infrastructure/bin/pm-as-agent.ps1", ".trae/bin/pm-as-trae.ps1"]
NATIVE_VENV_CALL = re.compile(r"^\s*&\s+\$python\b", re.MULTILINE)


def _read(script: str) -> str:
    path = REPO_ROOT / script
    if not path.is_file():
        pytest.skip("not run inside the workspace checkout")
    return path.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("script", WRAPPERS)
def test_the_wrapper_checks_the_interpreter_before_it_sets_the_agent_marker_or_calls_it(script: str) -> None:
    text = _read(script)
    # the guard fires when the interpreter is NOT there: a flipped condition (no ``-not``) would refuse every working setup
    assert "if (-not (Test-Path -LiteralPath $python)) {" in text
    guard = text.index("Test-Path -LiteralPath $python")
    assert guard < text.index("$env:AUTO_PM_AGENT =")  # nothing to put back when the guard fires
    assert guard < NATIVE_VENV_CALL.search(text).start()  # type: ignore[union-attr]
    block = text[guard : text.index("}", text.index("return", guard))]
    assert "找不到 .venv，先跑 setup_env.bat" in block
    assert "exit 3" in block
    assert "[Console]::Error.WriteLine" in block  # plain text on the real stderr, not an error record


@pytest.mark.parametrize("script", WRAPPERS)
def test_the_hint_does_not_glue_a_full_width_character_to_the_variable_name(script: str) -> None:
    """``"$python）"`` is parsed by PowerShell as part of the name; only ``${python}`` is safe in this sentence."""

    hint = next(line for line in _read(script).splitlines() if "找不到 .venv" in line)
    assert "${python}" in hint and "$python）" not in hint and "$python：" not in hint


@pytest.mark.parametrize("script", WRAPPERS)
def test_a_dot_sourced_wrapper_returns_instead_of_closing_the_callers_terminal(script: str) -> None:
    text = _read(script)
    block = text[text.index("Test-Path -LiteralPath $python") :]
    block = block[: block.index("}\n", block.index("return")) + 1] if "}\n" in block else block
    assert "if ($MyInvocation.InvocationName -ne '.') { exit 3 }" in block
    assert re.search(r"^\s*return\s*$", block, re.MULTILINE)


@pytest.mark.parametrize("script", WRAPPERS)
def test_the_bom_stays_because_windows_powershell_5_1_reads_the_chinese_text_as_cp936_without_it(script: str) -> None:
    assert (REPO_ROOT / script).read_bytes().startswith(b"\xef\xbb\xbf")


def test_every_tracked_script_that_calls_the_venv_interpreter_directly_checks_it_first() -> None:
    """The sweep behind D-150: today exactly the two wrappers call ``& $python``; a new one must come with the same guard."""

    if not (REPO_ROOT / ".git").exists():
        pytest.skip("not run inside the workspace checkout")
    names = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "*.ps1"], capture_output=True, check=True, text=True, encoding="utf-8"
    ).stdout.split("\0")
    callers = []
    for name in names:
        if not name or "03_归档" in name or "/archive/" in name:
            continue
        text = (REPO_ROOT / name).read_text(encoding="utf-8-sig")
        if ".venv" in text and NATIVE_VENV_CALL.search(text):
            callers.append(name)
            assert "Test-Path -LiteralPath $python" in text, f"{name} 直接调用 .venv python 却没有先检查它存在"
            assert text.index("Test-Path -LiteralPath $python") < NATIVE_VENV_CALL.search(text).start()  # type: ignore[union-attr]
    assert sorted(callers) == sorted(WRAPPERS)
