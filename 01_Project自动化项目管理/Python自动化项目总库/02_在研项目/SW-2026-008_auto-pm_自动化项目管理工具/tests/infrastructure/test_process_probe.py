"""The holder-process probe of the reclaim interface observes real processes; it never reports a process it could not read as dead."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator

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
