"""D-141 (part 3): ``pm retire`` stays registered in the interlock matrix as a control-root-only write (D-134)."""

from __future__ import annotations

from auto_pm.contracts.interlock_matrix import COMMANDS


def test_pm_retire_needs_the_control_root_and_is_guarded_against_mutating_elsewhere() -> None:
    spec = COMMANDS["pm retire"]

    assert "workspace=control_root" in spec.needs
    assert "G-MUTATION-ROOT" in spec.guards


def test_pm_retire_with_mission_id_still_only_obeys_the_user() -> None:
    """CHG-SCPT-2026-647: --mission-id extends the same command; it stays control-root-only and on the user's word."""

    spec = COMMANDS["pm retire"]

    assert "operator=user" in spec.needs
    assert "G-AGENT-APPROVAL" in spec.guards
    assert "pm retire --mission-id" not in COMMANDS  # no new command: the same entry and guards cover the new option
