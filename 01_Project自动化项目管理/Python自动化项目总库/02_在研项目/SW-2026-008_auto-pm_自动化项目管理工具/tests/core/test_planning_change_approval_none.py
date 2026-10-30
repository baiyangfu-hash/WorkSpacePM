"""If the ledger gives back no CHG after a status step, approval must refuse cleanly, not crash on ``None.status``."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest

from auto_pm import api as cockpit_api
from auto_pm.application.core import pm_facade_service as facade_module
from auto_pm.ui.cli import pm as pm_cli

CARD = SimpleNamespace(change_id="CHG-X-2026-001", subject_project_id="P-1", plan_hash="H")


class _Changes:
    """A ledger whose status step returns nothing (the real service's return type allows it)."""

    def __init__(self, *_a: object, **_k: object) -> None: ...

    def get_change_request(self, change_id: str, project_id: str) -> SimpleNamespace:
        return SimpleNamespace(change_number=change_id, status="draft")

    def transition_status(self, *_a: object, **_k: object) -> None:
        return None


def test_the_facade_refuses_when_the_status_step_returns_no_change(monkeypatch: pytest.MonkeyPatch) -> None:
    service = object.__new__(facade_module.PmFacadeService)
    service._changes = _Changes()  # type: ignore[assignment]
    with pytest.raises(facade_module.PmFacadeError, match="不可批准"):
        service._approve_planning_change(CARD, "user")  # type: ignore[arg-type]


def test_the_sdk_refuses_when_the_status_step_returns_no_change(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cockpit_api, "ChangeService", _Changes)
    client = object.__new__(cockpit_api.CockpitClient)
    client._root = tmp_path  # type: ignore[attr-defined]
    with pytest.raises(cockpit_api.CockpitApiError, match="不可批准"):
        client._approve_change(CARD, "user")  # type: ignore[arg-type]


def test_the_cli_refuses_when_the_status_step_returns_no_change(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pm_cli, "ChangeService", _Changes)
    root: Any = SimpleNamespace(obj=SimpleNamespace(control_root=tmp_path))
    ctx: Any = SimpleNamespace(find_root=lambda: root)
    with pytest.raises(click.ClickException, match="不可批准"):
        pm_cli._approve_planning_change(ctx, CARD, "user")  # type: ignore[arg-type]
