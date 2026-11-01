"""The holder-process probe of the reclaim interface observes real processes; it never reports a process it could not read as dead."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
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
