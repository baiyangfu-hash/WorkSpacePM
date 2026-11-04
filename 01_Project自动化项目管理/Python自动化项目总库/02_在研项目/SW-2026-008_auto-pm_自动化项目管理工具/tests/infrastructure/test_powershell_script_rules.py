"""Every PowerShell script in the project must parse in Windows PowerShell 5.1 (11-04: the memory gate installer failed to parse on the user's PC)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".auto-pm"}

# PowerShell treats the curly single/double quotes as quote characters. A curly quote inside a
# double-quoted string,
# e.g. 选“以管理员身份运行”, ends the string early and 5.1 reports UnexpectedToken. The file
# encoding is not involved: the installer had a UTF-8 BOM and still failed.
_QUOTE_LOOKALIKES = re.compile(
    "[\\u2018-\\u201f]"
)  # U+2018..U+201F, written as escapes so the file itself stays plain
_UTF8_BOM = b"\xef\xbb\xbf"

_PARSE_SCRIPT = (
    "$e=$null;$t=$null;"
    "[void][System.Management.Automation.Language.Parser]::ParseFile($env:PS_PARSE_PATH,[ref]$t,[ref]$e);"
    "if($e){$e|ForEach-Object{'{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message};exit 1};"
    "exit 0"
)


def powershell_scripts() -> list[Path]:
    found: list[Path] = []
    for directory, names, files in os.walk(ROOT):
        names[:] = [name for name in names if name not in _SKIP_DIRS]
        found.extend(
            Path(directory) / name for name in files if name.lower().endswith((".ps1", ".psm1"))
        )
    return sorted(found)


def quote_lookalike_lines(text: str) -> list[int]:
    """1-based line numbers holding a curly single/double quote."""
    return [
        number for number, line in enumerate(text.splitlines(), 1) if _QUOTE_LOOKALIKES.search(line)
    ]


def needs_bom(raw: bytes) -> bool:
    """Windows PowerShell 5.1 reads a BOM-less file as the ANSI code page, so any non-ASCII byte needs the BOM."""
    return not raw.startswith(_UTF8_BOM) and any(byte > 127 for byte in raw)


SCRIPTS = powershell_scripts()


def test_the_project_has_powershell_scripts_to_check() -> None:
    assert any(path.name == "install_memory_gate.ps1" for path in SCRIPTS), (
        "the scan no longer finds the installer"
    )


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.name)
def test_no_curly_quotes(path: Path) -> None:
    lines = quote_lookalike_lines(path.read_bytes().decode("utf-8", errors="replace"))
    assert not lines, (
        f"{path.name} lines {lines}: curly quotes end a PowerShell string; use ASCII quotes or 「」"
    )


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.name)
def test_non_ascii_script_has_a_utf8_bom(path: Path) -> None:
    assert not needs_bom(path.read_bytes()), (
        f"{path.name} has non-ASCII text but no UTF-8 BOM; Windows PowerShell 5.1 would read it as ANSI"
    )


def test_rules_catch_the_11_04_failure() -> None:
    broken = 'throw "请用管理员 PowerShell 运行本脚本（选“以管理员身份运行”）。"\r\n'
    assert quote_lookalike_lines("a\n" + broken) == [2]
    assert quote_lookalike_lines('throw "请用管理员运行（选「以管理员身份运行」）。"\n') == []
    assert needs_bom(broken.encode("utf-8"))
    assert not needs_bom(_UTF8_BOM + broken.encode("utf-8"))
    assert not needs_bom(b'Write-Host "ascii only"\r\n')


def _windows_powershell() -> str | None:
    """Windows PowerShell 5.1 (powershell.exe), not PowerShell 7 (pwsh): the user's PC runs 5.1."""
    return shutil.which("powershell") if sys.platform == "win32" else None


@pytest.mark.skipif(
    _windows_powershell() is None, reason="Windows PowerShell 5.1 only exists on Windows"
)
@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.name)
def test_script_parses_in_windows_powershell(path: Path) -> None:
    executable = _windows_powershell()
    assert executable is not None
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", _PARSE_SCRIPT],
        env={**os.environ, "PS_PARSE_PATH": str(path)},
        capture_output=True,
        timeout=120,
        check=False,
    )
    detail = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert result.returncode == 0, (
        f"{path.name} does not parse in Windows PowerShell 5.1:\n{detail}"
    )
