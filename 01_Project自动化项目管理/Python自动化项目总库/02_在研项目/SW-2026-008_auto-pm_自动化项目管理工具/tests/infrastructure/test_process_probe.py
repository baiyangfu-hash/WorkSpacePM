"""The holder-process probe of the reclaim interface observes real processes; it never reports a process it could not read as dead."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from auto_pm.contracts.lease_reclaim import ProcessVerdict, judge_process
from auto_pm.infrastructure import process_probe

SUPPORTED = sys.platform == "win32" or sys.platform.startswith("linux")
pytestmark = pytest.mark.skipif(not SUPPORTED, reason="the probe observes Windows and Linux only")


@pytest.fixture
def child() -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    yield process
    if process.poll() is None:
        process.kill()
    process.wait(30)


def test_the_host_identity_is_stable_and_hashed() -> None:
    first, second = process_probe.local_host_id(), process_probe.local_host_id()
    assert first == second
    if first:
        assert first.startswith("host:") and len(first) == len("host:") + 32


def test_a_running_process_is_alive_and_a_killed_one_is_proven_dead(child: subprocess.Popen[bytes]) -> None:
    host = process_probe.local_host_id()
    fingerprint = process_probe.fingerprint(child.pid)
    if not host or fingerprint is None:
        pytest.skip("the process table of this host cannot be read")

    assert fingerprint.pid == child.pid and fingerprint.start_time.isdigit()
    alive = judge_process(fingerprint, process_probe.observe(child.pid), local_host_id=host)
    assert alive in (ProcessVerdict.ALIVE, ProcessVerdict.UNKNOWN)  # never PROVEN_DEAD while it runs

    child.kill()
    child.wait(30)
    assert judge_process(fingerprint, process_probe.observe(child.pid), local_host_id=host) is ProcessVerdict.PROVEN_DEAD


def test_a_fingerprint_from_another_host_is_unknown(child: subprocess.Popen[bytes]) -> None:
    fingerprint = process_probe.fingerprint(child.pid)
    if fingerprint is None:
        pytest.skip("the process table of this host cannot be read")
    child.kill()
    child.wait(30)
    assert judge_process(fingerprint, process_probe.observe(child.pid), local_host_id="host:another-machine") is ProcessVerdict.UNKNOWN


def test_this_process_is_observed_with_a_start_time() -> None:
    observed = process_probe.observe(os.getpid())
    assert observed is not None and observed.pid_exists and observed.start_time is not None


@pytest.mark.parametrize("pid", [0, -1])
def test_an_invalid_pid_cannot_be_observed(pid: int) -> None:
    assert process_probe.observe(pid) is None
    assert process_probe.fingerprint(pid) is None


def test_the_holder_behind_a_call_is_never_a_python_interpreter_of_the_launcher_chain() -> None:
    pid = process_probe.holder_process_pid()
    if pid is None:
        return  # an ancestry made only of interpreters (or unreadable) records nothing: a later reclaim sees UNKNOWN, never DEAD
    assert pid != os.getpid()
    observed = process_probe.observe(pid)
    assert observed is not None and observed.pid_exists


def _ancestry(*chain: tuple[int, str]) -> Callable[[int], tuple[int, str] | None]:
    """A fake process table: ``chain`` lists (pid, image) from the CLI process upwards; the first entry is the CLI itself."""

    parents = {pid: chain[index + 1] for index, (pid, _image) in enumerate(chain[:-1])}
    return lambda pid: parents.get(pid)


# M3 drill 2026-10-19: Trae CN runs each command in a fresh PowerShell that exits with it; recording that shell made every reclaim PROVEN_DEAD
TRAE_CN = _ancestry(
    (900, "python.exe"), (800, "python.exe"), (700, "powershell.exe"), (600, "trae cn.exe"), (500, "explorer.exe")
)


def test_an_agent_host_that_runs_each_command_in_a_fresh_shell_is_the_holder_not_the_shell() -> None:
    assert process_probe.holder_process_pid(900, TRAE_CN) == 600


# Trae CN on the user's laptop, 2026-10-23 (PR #53 audit 98 §5, probe A): the pids and images as observed; trae-sandbox.exe (42116) was
# gone as soon as A finished, so recording it made reclaim PROVEN_DEAD again; agent-tool-host.exe hangs off the resident utility process
TRAE_CN_SANDBOXED = _ancestry(
    (43680, "python.exe"),
    (16152, "powershell.exe"),
    (42116, "trae-sandbox.exe"),
    (17968, "agent-tool-host.exe"),
    (31476, "trae cn.exe"),
    (17036, "trae cn.exe"),
    (4000, "explorer.exe"),
)


def test_a_per_command_sandbox_is_skipped_and_the_resident_tool_host_is_the_holder() -> None:
    assert process_probe.holder_process_pid(43680, TRAE_CN_SANDBOXED) == 17968


def test_a_sandbox_is_never_the_fallback_holder_even_when_the_walk_stops_above_it() -> None:
    # the walk cannot read past the sandbox: the shell below it is the best candidate, never the sandbox that dies with the command
    cut_off = _ancestry((9, "python.exe"), (8, "powershell.exe"), (7, "trae-sandbox.exe"), (6, ""))
    assert process_probe.holder_process_pid(9, cut_off) == 8
    reaches_root = _ancestry((9, "python.exe"), (8, "powershell.exe"), (7, "trae-sandbox.exe"), (5, "explorer.exe"))
    assert process_probe.holder_process_pid(9, reaches_root) == 8


def test_nested_shells_and_versioned_interpreters_are_all_skipped() -> None:
    claude_code = _ancestry(
        (90, "python3.12"), (80, "python3"), (70, "bash"), (60, "timeout"), (50, "bash"), (40, "claude"), (1, "systemd")
    )
    assert process_probe.holder_process_pid(90, claude_code) == 40
    codex = _ancestry((9, "python.exe"), (8, "cmd.exe"), (7, "pwsh.exe"), (6, "codex.exe"))
    assert process_probe.holder_process_pid(9, codex) == 6


def test_a_person_typing_in_a_terminal_keeps_the_shell_they_keep_open() -> None:
    windows = _ancestry((9, "python.exe"), (8, "python.exe"), (7, "powershell.exe"), (6, "windowsterminal.exe"), (5, "explorer.exe"))
    assert process_probe.holder_process_pid(9, windows) == 7
    linux = _ancestry((9, "python3"), (8, "bash"), (7, "zsh"), (6, "sshd"))
    assert process_probe.holder_process_pid(9, linux) == 7  # the login shell nearest the session root, not the subshell


def test_an_unreadable_or_interpreter_only_ancestry_records_nothing_rather_than_a_dying_process() -> None:
    assert process_probe.holder_process_pid(9, _ancestry((9, "python.exe"), (8, "python.exe"))) is None
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (1, "systemd"))) is None
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (8, ""))) is None
    # started without any shell (double-click in Explorer, a scheduled task under svchost): the session root is never recorded, because
    # explorer.exe or svchost.exe outlive every agent and a lease held by them could never be reclaimed (cloud audit of ee0268fa)
    assert process_probe.holder_process_pid(9, _ancestry((9, "python.exe"), (8, "python.exe"), (5, "explorer.exe"))) is None
    assert process_probe.holder_process_pid(9, _ancestry((9, "pythonw.exe"), (4, "svchost.exe"))) is None
    assert process_probe.holder_process_pid(9, _ancestry((9, "python.exe"), (7, "trae-sandbox.exe"), (4, "services.exe"))) is None
    # the shell already seen is still the best long-lived candidate when the walk cannot read further
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (8, "bash"))) == 8


def test_on_a_real_process_chain_auto_records_the_agent_host_and_not_its_per_command_shell(tmp_path: Path) -> None:
    if not sys.platform.startswith("linux") or not Path("/bin/bash").exists():
        pytest.skip("drives a real shell chain on Linux")
    # a stand-in agent host: a copy of bash under another name, so its image is neither a shell nor an interpreter
    host = tmp_path / "agent-host"
    host.write_bytes(Path("/bin/bash").read_bytes())
    host.chmod(0o755)
    root = Path(__file__).resolve().parents[2]
    probe = "from auto_pm.infrastructure import process_probe; print(process_probe.holder_process_pid())"
    # the host prints its own pid, then runs the command in a throwaway shell, as Trae CN does (each "; true" keeps bash from exec'ing the last command in its own place)
    command = f"echo host=$$; bash -c '{sys.executable} -c \"{probe}\"; echo shell=$$; true'; true"
    result = subprocess.run(
        [str(host), "-c", command],
        capture_output=True, text=True, cwd=root, env={**os.environ, "PYTHONPATH": str(root)}, timeout=60, check=True,
    )
    lines = dict(line.split("=", 1) if "=" in line else ("holder", line) for line in result.stdout.split())
    assert lines["holder"] == lines["host"] != lines["shell"]
