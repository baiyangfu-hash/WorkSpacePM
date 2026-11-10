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

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

REPO_ROOT = Path(__file__).resolve().parents[6]
STOP = re.compile(r'^\s*\$ErrorActionPreference\s*=\s*"Stop"', re.MULTILINE)
CONTINUE = re.compile(r'^\s*\$ErrorActionPreference\s*=\s*"Continue"', re.MULTILINE)
# ``& $python …`` / ``& $MMDC …``: a native command called through a variable (not a cmdlet)
NATIVE_CALL = re.compile(r"^\s*&\s+\$\w+", re.MULTILINE)
# An entry may be added here only with a defect number (D-142 fixed the last two).
KNOWN_UNFIXED: frozenset[str] = frozenset()


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
    """Stop is set and a native command is called through a variable before anything switched to Continue."""

    call = NATIVE_CALL.search(text)
    if not (STOP.search(text) and call):
        return False
    return CONTINUE.search(text[: call.start()]) is None


@pytest.mark.parametrize("script", ["00_Infrastructure/bin/pm-as-agent.ps1", ".trae/bin/pm-as-trae.ps1"])
def test_the_wrapper_runs_the_native_command_under_continue_and_returns_its_exit_code(script: str) -> None:
    path = REPO_ROOT / script
    if not path.is_file():
        pytest.skip("not run inside the workspace checkout")
    text = path.read_text(encoding="utf-8-sig")
    call = NATIVE_CALL.search(text)
    assert call is not None
    before = text[: call.start()]
    assert CONTINUE.search(before), "the native call must run after $ErrorActionPreference is set to Continue"
    assert "$exitCode = $LASTEXITCODE" in text and "exit $exitCode" in text
    # A caller that collects our stderr with ``2>&1`` / ``2> file`` makes PowerShell 5.1 wrap each native stderr line in a
    # NativeCommandError record and stop the caller: the script merges the native stderr into the pipe itself, turns the
    # error records back into plain text and writes them to the real stderr, so no error record ever leaves the script.
    call_line = text[call.start() : text.index("\n", call.start())]
    assert "2>&1" in call_line and "ForEach-Object" in call_line
    assert "System.Management.Automation.ErrorRecord" in text and "[Console]::Error.WriteLine" in text
    # the exit code is read right after the pipeline, before anything else can overwrite it
    after_call = text[call.start() :]
    assert after_call.index("$exitCode = $LASTEXITCODE") < after_call.index("$ErrorActionPreference = $stopPreference")
    # Stop is put back for the rest of the script and when the call fails half way
    assert text.count("$ErrorActionPreference = $stopPreference") >= 2


def test_no_tracked_script_calls_a_native_command_under_stop_without_continue() -> None:
    offenders = {name for name in _tracked_scripts() if _offends((REPO_ROOT / name).read_text(encoding="utf-8-sig"))}
    assert offenders - KNOWN_UNFIXED == set(), f"原生命令的 stderr 会在 PowerShell 5.1 下让脚本中断: {sorted(offenders - KNOWN_UNFIXED)}"


def test_the_known_unfixed_list_has_no_stale_entry() -> None:
    offenders = {name for name in _tracked_scripts() if _offends((REPO_ROOT / name).read_text(encoding="utf-8-sig"))}
    assert KNOWN_UNFIXED <= offenders, f"已修好的文件要从 KNOWN_UNFIXED 里删掉: {sorted(KNOWN_UNFIXED - offenders)}"


BOM = b"\xef\xbb\xbf"
# Windows PowerShell 5.1 reads a script without a BOM in the machine's ANSI code page (cp936 on a Chinese PC): the bytes of a
# Chinese comment or string then swallow the characters after them and whole statements disappear.  Scripts with non-ASCII
# text therefore need a UTF-8 BOM (D-136 fixed the last twelve).  An entry may be added here only with a defect number.
KNOWN_NO_BOM: frozenset[str] = frozenset()


def _non_ascii_without_bom() -> set[str]:
    found = set()
    for name in _tracked_scripts():
        data = (REPO_ROOT / name).read_bytes()
        if not data.startswith(BOM) and any(byte > 127 for byte in data):
            found.add(name)
    return found


def test_pm_as_agent_starts_with_a_utf8_bom() -> None:
    path = REPO_ROOT / "00_Infrastructure" / "bin" / "pm-as-agent.ps1"
    if not path.is_file():
        pytest.skip("not run inside the workspace checkout")
    assert path.read_bytes().startswith(BOM), "没有 BOM：PowerShell 5.1 会按 cp936 读，中文注释会吞掉后面的语句"


def test_no_other_live_script_with_non_ascii_text_lacks_a_bom() -> None:
    assert _non_ascii_without_bom() - KNOWN_NO_BOM == set()


def test_the_known_no_bom_list_has_no_stale_entry() -> None:
    assert KNOWN_NO_BOM <= _non_ascii_without_bom()


def test_the_detector_tells_a_broken_script_from_a_fixed_one() -> None:
    broken = '$ErrorActionPreference = "Stop"\n& $python $entry @rest\n'
    fixed = '$ErrorActionPreference = "Stop"\n$ErrorActionPreference = "Continue"\n& $python $entry @rest\n'
    assert _offends(broken) and not _offends(fixed)
    assert not _offends('$ErrorActionPreference = "Stop"\nNew-Item x\n')


def test_export_mermaid_forwards_mmdc_under_continue() -> None:
    path = REPO_ROOT / ".trae" / "bin" / "export-mermaid.ps1"
    if not path.is_file():
        pytest.skip("not run inside the workspace checkout")
    text = path.read_text(encoding="utf-8-sig")
    call = NATIVE_CALL.search(text)
    assert call is not None and CONTINUE.search(text[: call.start()])
    assert "$ErrorActionPreference = $stopPreference" in text[call.start() :]


def test_the_detector_wants_continue_before_the_call_not_just_somewhere() -> None:
    late = '$ErrorActionPreference = "Stop"\n& $python $entry\n$ErrorActionPreference = "Continue"\n'
    assert _offends(late)
