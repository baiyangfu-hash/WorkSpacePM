"""The holder-process probe of the reclaim interface observes real processes; it never reports a process it could not read as dead."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_pm.application.core.execution_recovery_status import (
    RecoveryVerdict,
    inspect_started_process,
)
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
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


# ---- a missing /proc/<pid> proves death only when this host's /proc can show every process (TD-074, review 505 a) -----------

LINUX_ONLY = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="procfs only exists on Linux")

MOUNTINFO_PLAIN = "29 22 0:25 / {mount} rw,nosuid,nodev,noexec,relatime - proc proc rw\n"


def _fake_proc(
    root: Path,
    *,
    own_pid: int = 4242,
    mountinfo: str | None = None,
    osrelease: str = "6.1.0-generic",
    has_init: bool = True,
    has_self: bool = True,
) -> Path:
    proc = root / "proc"
    (proc / "self").mkdir(parents=True)
    if has_self:
        (proc / "self" / "stat").write_text(f"{own_pid} (python) S 1 1 1 0 -1\n", encoding="utf-8")
    if has_init:
        (proc / "1").mkdir()
    (proc / "self" / "mountinfo").write_text(MOUNTINFO_PLAIN.format(mount=proc) if mountinfo is None else mountinfo, encoding="utf-8")
    (proc / "sys" / "kernel").mkdir(parents=True)
    (proc / "sys" / "kernel" / "osrelease").write_text(osrelease + "\n", encoding="utf-8")
    return proc


def test_a_plain_full_procfs_is_trusted(tmp_path: Path) -> None:
    assert process_probe.procfs_view_problem(_fake_proc(tmp_path), own_pid=4242) == ""


def test_a_missing_proc_is_not_trusted(tmp_path: Path) -> None:
    assert "读不到" in process_probe.procfs_view_problem(tmp_path / "no-such-proc", own_pid=4242)


def test_a_proc_of_another_pid_namespace_is_not_trusted(tmp_path: Path) -> None:
    """Our own pid is not what /proc/self reports: this /proc belongs to another namespace (a container's view)."""

    proc = _fake_proc(tmp_path, own_pid=1)
    assert "另一个进程号命名空间" in process_probe.procfs_view_problem(proc, own_pid=4242)


def test_a_proc_without_pid_1_is_not_trusted(tmp_path: Path) -> None:
    proc = _fake_proc(tmp_path, has_init=False)
    assert "1 号进程" in process_probe.procfs_view_problem(proc, own_pid=4242)


@pytest.mark.parametrize("option", ["hidepid=1", "hidepid=2", "hidepid=invisible", "hidepid=noaccess"])
def test_a_hidepid_mount_is_not_trusted(tmp_path: Path, option: str) -> None:
    proc = tmp_path / "proc"
    line = f"29 22 0:25 / {proc} rw,nosuid,nodev,noexec,relatime - proc proc rw,{option}\n"
    assert "hidepid" in process_probe.procfs_view_problem(_fake_proc(tmp_path, mountinfo=line), own_pid=4242)


def test_hidepid_in_the_per_mount_options_is_also_seen(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    line = f"29 22 0:25 / {proc} rw,hidepid=2,relatime - proc proc rw\n"
    assert "hidepid" in process_probe.procfs_view_problem(_fake_proc(tmp_path, mountinfo=line), own_pid=4242)


@pytest.mark.parametrize("option", ["hidepid=0", "hidepid=off"])
def test_hidepid_off_is_trusted(tmp_path: Path, option: str) -> None:
    proc = tmp_path / "proc"
    line = f"29 22 0:25 / {proc} rw,relatime - proc proc rw,{option}\n"
    assert process_probe.procfs_view_problem(_fake_proc(tmp_path, mountinfo=line), own_pid=4242) == ""


def test_hidepid_on_another_mount_does_not_matter(tmp_path: Path) -> None:
    line = f"30 22 0:26 / /somewhere/else rw - proc proc rw,hidepid=2\n29 22 0:25 / {tmp_path / 'proc'} rw - proc proc rw\n"
    assert process_probe.procfs_view_problem(_fake_proc(tmp_path, mountinfo=line), own_pid=4242) == ""


def test_an_unreadable_mount_table_is_not_trusted(tmp_path: Path) -> None:
    proc = _fake_proc(tmp_path)
    (proc / "self" / "mountinfo").unlink()
    assert "hidepid" in process_probe.procfs_view_problem(proc, own_pid=4242)


@pytest.mark.parametrize("release", ["5.15.90.1-microsoft-standard-WSL2", "4.4.0-19041-Microsoft"])
def test_wsl_is_not_trusted(tmp_path: Path, release: str) -> None:
    assert "WSL" in process_probe.procfs_view_problem(_fake_proc(tmp_path, osrelease=release), own_pid=4242)


@LINUX_ONLY
def test_a_missing_pid_is_not_reported_dead_when_the_table_cannot_be_trusted(
    child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    child.kill()
    child.wait(30)
    monkeypatch.setattr(process_probe, "_view_problem", lambda: "hidepid")

    assert process_probe.observe(child.pid) is None  # "could not observe": the contract turns this into UNKNOWN


@LINUX_ONLY
def test_a_missing_pid_is_dead_when_the_table_is_complete(child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    child.kill()
    child.wait(30)
    monkeypatch.setattr(process_probe, "_view_problem", lambda: "")

    observed = process_probe.observe(child.pid)
    assert observed is not None and observed.pid_exists is False


@LINUX_ONLY
def test_the_real_host_view_check_does_not_raise() -> None:
    assert isinstance(process_probe.procfs_view_problem(), str)  # whatever the verdict, the check itself never fails


@LINUX_ONLY
def test_an_untrusted_table_makes_recover_report_unknown_not_dead(
    child: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the judge that ``pm recover`` uses: a killed executor on a host that cannot prove absence is UNKNOWN."""

    evidence = ExecutionStartEvidence(process_id=child.pid, session_id="s", started_at=datetime.now(UTC))
    child.kill()
    child.wait(30)

    monkeypatch.setattr(process_probe, "_view_problem", lambda: "")
    assert inspect_started_process(evidence)[0].verdict is RecoveryVerdict.DEAD
    monkeypatch.setattr(process_probe, "_view_problem", lambda: "hidepid")
    assert inspect_started_process(evidence)[0].verdict is RecoveryVerdict.UNKNOWN


def test_a_procfs_file_that_is_not_valid_utf8_is_not_trusted(tmp_path: Path) -> None:
    proc = _fake_proc(tmp_path)
    (proc / "self" / "mountinfo").write_bytes(b"\xff\xfe not text\n")
    assert "hidepid" in process_probe.procfs_view_problem(proc, own_pid=4242)

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
    # the walk cannot read past the sandbox: neither the sandbox nor the per-command shell below it is recorded, both die with the command
    cut_off = _ancestry((9, "python.exe"), (8, "powershell.exe"), (7, "trae-sandbox.exe"), (6, ""))
    assert process_probe.holder_process_pid(9, cut_off) is None
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
    # a shell below an unreadable parent is not recorded (Codex on #80/#81): it may be the per-command shell of a host out of sight
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (8, "bash"))) is None
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (8, "bash"), (7, ""))) is None


def test_a_shell_whose_parent_shows_as_pid_1_outside_a_session_root_records_nothing() -> None:
    # Codex on #80/#81: in a container or sandbox the agent host is outside the visible PID space and the per-command shell shows PPID 1;
    # recording that shell made the lease PROVEN_DEAD as soon as the command exited, so a second agent could reclaim a live card
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (8, "bash"), (1, "tini"))) is None
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (8, "bash"), (1, "node"))) is None
    # positive control: a known session root as PID 1 still keeps the person's own shell
    assert process_probe.holder_process_pid(9, _ancestry((9, "python3"), (8, "bash"), (1, "systemd"))) == 8


@pytest.mark.skipif(not (sys.platform.startswith("linux") and Path("/bin/bash").exists()), reason="drives a real shell chain on Linux")
def test_on_a_real_process_chain_auto_records_the_agent_host_and_not_its_per_command_shell(tmp_path: Path) -> None:
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
        capture_output=True, text=True, encoding="utf-8", cwd=root, env={**os.environ, "PYTHONPATH": str(root)}, timeout=60, check=True,
    )
    lines = {(line.split("=", 1)[0] if "=" in line else "holder"): line.split("=", 1)[-1] for line in result.stdout.split()}
    assert lines["holder"] == lines["host"] != lines["shell"]


@pytest.mark.skipif(not (sys.platform.startswith("linux") and Path("/bin/bash").exists()), reason="drives a real shell chain on Linux")
def test_the_recorded_holder_is_still_alive_after_the_command_that_recorded_it_has_ended(tmp_path: Path) -> None:
    """The failure of 2026-10-19 / 2026-10-23: a single run looked right, but the recorded process died with its command.

    A resident stand-in host runs two commands, each in its own throwaway shell, like Trae CN.  The fingerprint taken in command 1 must
    still judge ALIVE after command 1's shell is gone, and command 2 must find the same host again: that is what a later reclaim sees.
    """

    host_image = tmp_path / "agent-host"  # a copy of bash under another name, so its image is neither a shell nor an interpreter
    host_image.write_bytes(Path("/bin/bash").read_bytes())
    host_image.chmod(0o755)
    root = Path(__file__).resolve().parents[2]
    probe = "from auto_pm.infrastructure import process_probe; print(process_probe.holder_process_pid())"
    # per command: a throwaway shell prints its own pid, then the holder the probe finds ("; true" keeps bash from exec'ing the last command)
    per_command = f"bash -c 'echo shell=$$; {sys.executable} -c \"{probe}\"; true'; echo done"
    host = subprocess.Popen(
        [str(host_image), "-c", f"echo host=$$; while read -r go; do {per_command}; done"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", cwd=root, env={**os.environ, "PYTHONPATH": str(root)},
    )
    stdin, stdout = host.stdin, host.stdout
    assert stdin is not None and stdout is not None

    def run_command() -> list[str]:
        stdin.write("go\n")
        stdin.flush()
        lines: list[str] = []
        while (line := stdout.readline().strip()) != "done":
            if not line:
                raise AssertionError(f"the stand-in host ended early; output so far: {lines}")
            lines.append(line)
        return lines

    try:
        first_pid_line = stdout.readline().strip()
        host_pid = int(first_pid_line.split("=", 1)[1])
        assert host_pid == host.pid

        first = run_command()
        shell_1, holder_1 = int(first[0].split("=", 1)[1]), int(first[1])
        assert holder_1 == host_pid != shell_1
        fingerprint = process_probe.fingerprint(holder_1)
        local_host = process_probe.local_host_id()
        if fingerprint is None or not local_host:
            pytest.skip("the process table of this host cannot be read")
        gone = process_probe.observe(shell_1)  # command 1's shell is gone
        assert gone is not None and gone.pid_exists is False

        # between the two commands: what a reclaim would judge right now
        assert judge_process(fingerprint, process_probe.observe(holder_1), local_host_id=local_host) is ProcessVerdict.ALIVE

        second = run_command()
        shell_2, holder_2 = int(second[0].split("=", 1)[1]), int(second[1])
        assert holder_2 == holder_1 and shell_2 != shell_1
        assert judge_process(fingerprint, process_probe.observe(holder_2), local_host_id=local_host) is ProcessVerdict.ALIVE
    finally:
        host.kill()
        host.wait(30)
