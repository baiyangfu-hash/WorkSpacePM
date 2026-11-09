"""D-141 (part 3): ``pm retire`` stays registered in the interlock matrix as a control-root-only write (D-134)."""

from __future__ import annotations

from auto_pm.contracts.interlock_matrix import COMMANDS


def test_pm_retire_needs_the_control_root_and_is_guarded_against_mutating_elsewhere() -> None:
    spec = COMMANDS["pm retire"]

    assert "workspace=control_root" in spec.needs
    assert "G-MUTATION-ROOT" in spec.guards
