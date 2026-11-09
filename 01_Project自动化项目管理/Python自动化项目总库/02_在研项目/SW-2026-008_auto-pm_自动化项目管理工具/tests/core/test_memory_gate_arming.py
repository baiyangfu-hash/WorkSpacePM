"""D-174: the deploy is armed for the memory gate only until it starts moving the release pointers; the door's disarm is silent and exact."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import memory_gate_arming as door
from auto_pm.application.core import release_ops as ops
from auto_pm.application.core import release_wiring as rw
from auto_pm.infrastructure import memory_preflight as mp


@pytest.fixture(autouse=True)
def _the_real_arm_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """tests/conftest.py blanks ``arm_dir`` so no test arms the real control root; here every call passes an explicit ``start`` inside tmp_path, so use the genuine one."""

    spec = importlib.util.spec_from_file_location("memory_preflight_genuine", mp.__file__)
    assert spec is not None and spec.loader is not None
    genuine = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, genuine)  # dataclasses looks the module up by name while it executes
    spec.loader.exec_module(genuine)
    monkeypatch.setattr(mp, "arm_dir", genuine.arm_dir)


def _control_root(tmp_path: Path) -> Path:
    (tmp_path / ".auto-pm").mkdir()
    return tmp_path


def test_disarm_removes_the_record_the_real_arm_wrote_and_leaves_other_processes_alone(tmp_path: Path) -> None:
    root = _control_root(tmp_path)
    record = mp.arm("deploy-gate", start=root)
    assert record is not None and record.is_file()
    other = record.parent / "1.json"
    other.write_text("{}", encoding="ascii")

    door.disarm_this_process(root)

    assert not record.exists() and record == record.parent / f"{os.getpid()}.json", "the door and arm() must agree on the file name"
    assert other.is_file(), "only this process's own record is removed"


def test_disarm_is_silent_when_nothing_is_armed_or_there_is_no_arm_folder(tmp_path: Path) -> None:
    door.disarm_this_process(_control_root(tmp_path))  # armed nowhere: nothing to remove
    door.disarm_this_process(tmp_path / "no" / "such" / "place")  # no .auto-pm on the way: nothing to do, nothing raised


def test_a_switch_disarms_before_it_touches_the_pointers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(rw, "disarm_this_process", lambda: order.append("disarm"))

    def fake_switch(root: Path, new: str, old: str, backup: Path, identity: Any) -> dict[str, Any]:
        order.append("switch")
        return {"active": new}

    monkeypatch.setattr(ops, "switch", fake_switch)
    container = ops.container_of(tmp_path)
    container.mkdir(parents=True)
    (container / "active_release.json").write_text('{"release_id": "1.3.3-1234567"}', encoding="utf-8")
    adapter = rw.ReleaseOpsAdapter(tmp_path, tmp_path, "a" * 40, "1.3.3-abcdef0", lambda root: {})

    result = adapter.switch(tmp_path / "backup")

    assert order == ["disarm", "switch"] and result == {"active": "1.3.3-abcdef0"}


def test_a_failing_disarm_record_removal_never_stops_the_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _control_root(tmp_path)
    record = mp.arm("deploy-gate", start=root)
    assert record is not None
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(PermissionError("locked")))

    door.disarm_this_process(root)  # the deploy goes on: the record is merely still there

    assert record.exists()
