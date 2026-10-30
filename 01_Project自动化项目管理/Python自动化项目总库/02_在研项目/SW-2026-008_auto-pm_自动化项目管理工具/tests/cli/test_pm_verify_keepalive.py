"""``pm verify`` runs about 15 minutes: the Run's lease must be kept alive meanwhile, and a lost renewal must be visible."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner
from pydantic import BaseModel

from auto_pm.ui.cli import pm_closure


class _Outcome(BaseModel):
    verified: bool = True


def _wire(monkeypatch: pytest.MonkeyPatch, events: list[str], *, keepalive_error: str) -> None:
    class _Store:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def list_runs(self, *_a: object, **_k: object) -> list[SimpleNamespace]:
            return [SimpleNamespace(run_id="RUN-1")]

        def get_lease(self, _run_id: str) -> SimpleNamespace:
            return SimpleNamespace(owner_id="agent-a")

    class _Facade:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def verify_for_acceptance_with_reason(self, _mission_id: str, *, lease_token: str) -> tuple[_Outcome, str]:
            events.append("verify")
            return _Outcome(), ""

    class _KeepAlive:
        def __init__(self, _execution: object, **kwargs: Any) -> None:
            events.append(f"init:{kwargs['run_id']}:{kwargs['owner_id']}:strict={kwargs['strict']}")
            self.error = keepalive_error

        def __enter__(self) -> _KeepAlive:
            events.append("enter")
            return self

        def __exit__(self, *_a: object) -> None:
            events.append("exit")

    monkeypatch.setattr(pm_closure, "_guarded_mission", lambda _ctx, _id: SimpleNamespace(root_work_id="W-1", mission_id="M-1"))
    monkeypatch.setattr(pm_closure, "ContinuityStore", _Store)
    monkeypatch.setattr(pm_closure, "PmFacadeService", _Facade)
    monkeypatch.setattr(pm_closure, "ContinuityExecutionService", lambda *_a, **_k: object())
    monkeypatch.setattr(pm_closure, "LeaseKeepAlive", _KeepAlive)
    monkeypatch.setattr(pm_closure.lease_wallet, "load", lambda *_a, **_k: "TOKEN")


def _verify(tmp_path: Path) -> Any:
    obj = SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path)
    return CliRunner().invoke(pm_closure.verify_pm, ["--mission-id", "M-1", "--lease-wallet"], obj=obj)


def test_verify_runs_inside_a_non_strict_keepalive_for_the_runs_holder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[str] = []
    _wire(monkeypatch, events, keepalive_error="")
    result = _verify(tmp_path)
    assert result.exit_code == 0, result.output
    assert events == ["init:RUN-1:agent-a:strict=False", "enter", "verify", "exit"]
    assert "lease_keepalive_warning" not in json.loads(result.output)


def test_a_lost_renewal_is_reported_in_the_verify_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[str] = []
    _wire(monkeypatch, events, keepalive_error="lease 已过期")
    result = _verify(tmp_path)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["lease_keepalive_warning"] == "lease 已过期"
