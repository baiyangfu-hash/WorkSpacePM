"""TD-071 technical debt (audit 77, 6): both entries that create a card hand their admission to the write transaction.

Each test lets "another process" open a colliding card between this entry's admission check and its card creation;
the entry must then refuse instead of creating a second card over the same files without the user's word.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from auto_pm.core.mission_service import MissionService
from click.testing import CliRunner

from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.cli.test_continuity import _create_args, _invoke, _repository
from tests.cli.test_pm_pending_cards import (
    COCKPIT,
    PROJECT,
    SECOND,
    _approve_args,
    _json,
    _planned,
    _run,
    _setup_planning,
)


def _race_once(monkeypatch: pytest.MonkeyPatch, other_process: Any) -> None:
    """Run ``other_process`` right after the first admission check returns, before that caller creates its card."""

    original = MissionService.admit
    fired: list[bool] = []

    def admit(self: MissionService, **kwargs: Any) -> Any:
        result = original(self, **kwargs)
        if not fired:
            fired.append(True)
            other_process()
        return result

    monkeypatch.setattr(MissionService, "admit", admit)


def test_continuity_mission_create_refuses_a_card_opened_after_its_check(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    store = ContinuityStore(tmp_path)
    _race_once(monkeypatch, lambda: _invoke(cli_runner, tmp_path, _create_args("MISSION-CLI-A")))

    raced = _invoke(cli_runner, tmp_path, _create_args("MISSION-CLI-B"))

    assert raced.exit_code != 0 and "准入检查之后项目里又开了新卡（MISSION-CLI-A）" in raced.output
    assert [item.mission_id for item in store.list_missions("SW-TEST-001")] == ["MISSION-CLI-A"]
    monkeypatch.undo()
    retried = _invoke(cli_runner, tmp_path, _create_args("MISSION-CLI-B"))
    assert retried.exit_code != 0 and "要改同一批文件" in retried.output


def test_pm_approve_refuses_a_card_opened_after_its_check(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_planning(tmp_path)
    first = _planned(cli_runner, tmp_path, COCKPIT)
    second = _planned(cli_runner, tmp_path, SECOND)
    _race_once(
        monkeypatch,
        lambda: _json(_run(cli_runner, tmp_path, *_approve_args(COCKPIT, first["plan_hash"]))),
    )

    raced = _run(cli_runner, tmp_path, *_approve_args(SECOND, second["plan_hash"]))

    assert raced.exit_code != 0 and "准入检查之后项目里又开了新卡" in raced.output
    assert len(ContinuityStore(tmp_path).list_missions(PROJECT)) == 1
    monkeypatch.undo()
    # The retry is checked against what is open now: the collision needs the user's word, which then admits it.
    retried = _run(cli_runner, tmp_path, *_approve_args(SECOND, second["plan_hash"]))
    assert retried.exit_code != 0 and "要改同一批文件" in retried.output
    released = _json(
        _run(
            cli_runner,
            tmp_path,
            *_approve_args(SECOND, second["plan_hash"], "--admission-release-ref", "user-confirmation:RACE-C-0001"),
        )
    )
    assert released["authorization_status"] == "AUTHORIZED"
    assert len(ContinuityStore(tmp_path).list_missions(PROJECT)) == 2
