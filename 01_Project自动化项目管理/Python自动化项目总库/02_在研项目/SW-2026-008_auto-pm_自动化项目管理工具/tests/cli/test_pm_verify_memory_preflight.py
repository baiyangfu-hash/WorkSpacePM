"""``pm verify`` asks the memory preflight first: a hot machine is refused before the ledger, the wallet or any test is touched."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from auto_pm.infrastructure import memory_preflight as mp
from auto_pm.ui.cli import pm_closure

GIB = mp.GIB


def _invoke(*args: str) -> object:
    # obj=None: anything that touches the app context before the preflight would fail with AttributeError, not the refusal
    return CliRunner().invoke(pm_closure.verify_pm, ["--mission-id", "M-1", "--lease-wallet", *args], obj=None)


def test_verify_is_refused_on_a_hot_machine_before_anything_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mp, "read_commit", lambda: mp.CommitSnapshot(40 * GIB, 64 * GIB, 32 * GIB, 2 * GIB))
    monkeypatch.setattr(mp, "all_processes", lambda: (mp.ProcessUse(7, "pytest.exe", 12 * GIB),))

    result = _invoke()

    assert result.exit_code == 1  # type: ignore[attr-defined]
    output = result.output  # type: ignore[attr-defined]
    assert "拒绝启动" in output and "40.0 GiB" in output and "pytest.exe（PID 7）12.0 GiB" in output
    assert "long-run start" in output
    assert "Traceback" not in output and "AttributeError" not in output


def test_verify_goes_on_when_the_machine_has_room(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mp, "read_commit", lambda: mp.CommitSnapshot(5 * GIB, 64 * GIB, 32 * GIB))

    result = _invoke()

    assert "拒绝启动" not in result.output  # type: ignore[attr-defined]  # it fails later, on the missing app context: past the preflight
