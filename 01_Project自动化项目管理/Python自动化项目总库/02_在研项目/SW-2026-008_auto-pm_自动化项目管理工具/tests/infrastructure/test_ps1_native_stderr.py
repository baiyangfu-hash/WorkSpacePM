"""D-132: a PowerShell 5.1 script with ``$ErrorActionPreference = "Stop"`` must not let a native command's stderr end it.

Windows PowerShell 5.1 turns every stderr line of a native command (the launcher prints ``launcher: release verified…``)
into a terminating error under ``Stop``: the command has finished, but the script stops half way and returns -1.  The cure is
to call the native command under ``Continue`` and judge it by ``$LASTEXITCODE``.  This is a static check (no PowerShell runs
here); the real Windows run is done by the local thread.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]
STOP = re.compile(r'^\s*\$ErrorActionPreference\s*=\s*"Stop"', re.MULTILINE)
CONTINUE = re.compile(r'^\s*\$ErrorActionPreference\s*=\s*"Continue"', re.MULTILINE)
# ``& $python …`` / ``& $MMDC …``: a native command called through a variable (not a cmdlet)
NATIVE_CALL = re.compile(r"^\s*&\s+\$\w+", re.MULTILINE)
# Same defect, in files other AIs may not edit (``.trae/`` is Trae's, changed only on the user's word).  Listed so the check
# stays honest; an entry must be removed when its file is fixed (the second test below fails if one is stale).
KNOWN_UNFIXED = frozenset({".trae/bin/pm-as-trae.ps1", ".trae/bin/export-mermaid.ps1"})


def _tracked_scripts() -> list[str]:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("not run inside the workspace checkout")
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "*.ps1"],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return [name for name in out.split("\0") if name and "03_归档" not in name and "/archive/" not in name]


def _offends(text: str) -> bool:
    """Stop is set, a native command is called through a variable, and nothing ever switches to Continue."""

    return bool(STOP.search(text) and NATIVE_CALL.search(text) and not CONTINUE.search(text))


def test_pm_as_agent_runs_the_native_command_under_continue_and_returns_its_exit_code() -> None:
    path = REPO_ROOT / "00_Infrastructure" / "bin" / "pm-as-agent.ps1"
    if not path.is_file():
        pytest.skip("not run inside the workspace checkout")
    text = path.read_text(encoding="utf-8")
    call = NATIVE_CALL.search(text)
    assert call is not None
    before = text[: call.start()]
    assert CONTINUE.search(before), "the native call must run after $ErrorActionPreference is set to Continue"
    assert "$exitCode = $LASTEXITCODE" in text and "exit $exitCode" in text
    # Stop is put back for the rest of the script and when the call fails half way
    assert text.count("$ErrorActionPreference = $stopPreference") >= 2


def test_no_tracked_script_calls_a_native_command_under_stop_without_continue() -> None:
    offenders = {name for name in _tracked_scripts() if _offends((REPO_ROOT / name).read_text(encoding="utf-8-sig"))}
    assert offenders - KNOWN_UNFIXED == set(), f"原生命令的 stderr 会在 PowerShell 5.1 下让脚本中断: {sorted(offenders - KNOWN_UNFIXED)}"


def test_the_known_unfixed_list_has_no_stale_entry() -> None:
    offenders = {name for name in _tracked_scripts() if _offends((REPO_ROOT / name).read_text(encoding="utf-8-sig"))}
    assert KNOWN_UNFIXED <= offenders, f"已修好的文件要从 KNOWN_UNFIXED 里删掉: {sorted(KNOWN_UNFIXED - offenders)}"


def test_the_detector_tells_a_broken_script_from_a_fixed_one() -> None:
    broken = '$ErrorActionPreference = "Stop"\n& $python $entry @rest\n'
    fixed = '$ErrorActionPreference = "Stop"\n$ErrorActionPreference = "Continue"\n& $python $entry @rest\n'
    assert _offends(broken) and not _offends(fixed)
    assert not _offends('$ErrorActionPreference = "Stop"\nNew-Item x\n')
