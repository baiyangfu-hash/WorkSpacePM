"""Tests for L1/L2/L3 gate tier classification and fail-closed invariants."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.gate_tier_policy import (
    ALL_GATE_GROUPS,
    L1_VERIFIED_PILOT_PATHS,
    classify_gate_tier,
)

REPO_PROJECT = Path(__file__).resolve().parents[2]


def test_docs_only_change_is_l1_without_groups() -> None:
    decision = classify_gate_tier(["02_规划/notes.md", "README.md"], project=REPO_PROJECT)
    assert decision.tier == "L1"
    assert decision.m2_tier == "docs"
    assert decision.full_forced is False
    assert decision.require_plugin is False
    assert decision.recommended_groups == ()
    assert set(decision.to_dict()) >= {
        "tier",
        "m2_tier",
        "recommended_groups",
        "require_plugin",
        "full_forced",
        "reasons",
        "rules_sha256",
    }


def test_verified_pilot_script_and_test_change_is_l1() -> None:
    assert "scripts/command_catalog.py" in L1_VERIFIED_PILOT_PATHS
    assert "tests/infrastructure/test_command_catalog.py" in L1_VERIFIED_PILOT_PATHS
    decision = classify_gate_tier(
        ["scripts/command_catalog.py", "tests/infrastructure/test_command_catalog.py"],
        project=REPO_PROJECT,
    )
    assert decision.tier == "L1"
    assert decision.m2_tier == "product"
    assert decision.full_forced is False
    assert decision.require_plugin is False
    assert decision.recommended_groups == ("infrastructure", "rest")
    assert set(decision.recommended_groups) <= set(ALL_GATE_GROUPS)


@pytest.mark.parametrize(
    ("paths", "expected_group"),
    [
        (["auto_pm/application/mod_0.py"], "application"),
        (["scripts/other_tool.py"], "rest"),
        (["tests/cli/test_other.py"], "cli"),
        ([f"auto_pm/application/mod_{i}.py" for i in range(4)], "application"),
        (["scripts/cockpit_board/app.py"], "core"),
        (["scripts/pm_dashboard_gui.py"], "core"),
        (["tests/cli/conftest.py"], "cli"),
        (["tests/core/test_pm_dashboard_gui.py"], "core"),
        ([f"tests/cli/test_case_{i}.py" for i in range(7)], "cli"),
    ],
)
def test_unverified_board_sub_conftest_gui_or_many_tests_escalate_to_l2(
    paths: list[str], expected_group: str
) -> None:
    decision = classify_gate_tier(paths, project=REPO_PROJECT)
    assert decision.tier == "L2"
    assert decision.full_forced is False
    assert decision.require_plugin is False
    assert expected_group in decision.recommended_groups
    assert set(decision.recommended_groups) <= set(ALL_GATE_GROUPS)


@pytest.mark.parametrize(
    "path",
    [
        "auto_pm/contracts/models.py",
        "auto_pm/infrastructure/git_hook_enforcer.py",
        "auto_pm/infrastructure/change_status_guard.py",
        "auto_pm/domain/change/change_service.py",
        "auto_pm/domain/change/status_journal.py",
        "auto_pm/domain/change/guard_checker.py",
        "auto_pm/ui/cli/change.py",
        "scripts/pm_merge.py",
        "scripts/pm_release.py",
        "scripts/long_gate.py",
        "auto_pm/application/core/gate_precheck_service.py",
        "auto_pm/application/core/release_deploy_check.py",
        "auto_pm/domain/plc/model.py",
        "auto_pm/ui/qml/Main.qml",
        "tests/plc/test_ladder.py",
        "tests/qml/test_panel.py",
        "tests/tools/sw008_ci/source_guards_manifest.txt",
        "tests/conftest.py",
        "pyproject.toml",
        "requirements.txt",
        "config/settings.json",
        "unknown_top/new_script.py",
    ],
)
def test_core_protected_plc_qml_global_non_py_and_unknown_paths_force_l3(path: str) -> None:
    decision = classify_gate_tier([path], project=REPO_PROJECT)
    assert decision.tier == "L3"
    assert decision.full_forced is True
    assert decision.require_plugin is True
    assert decision.recommended_groups == ALL_GATE_GROUPS


def test_outside_changes_and_extra_protected_patterns_force_l3() -> None:
    outside_dec = classify_gate_tier(
        ["scripts/command_catalog.py"],
        project=REPO_PROJECT,
        outside_changes=["AGENTS.md"],
    )
    assert outside_dec.tier == "L3"
    assert outside_dec.full_forced is True

    extra_dec = classify_gate_tier(
        ["scripts/custom_tool.py"],
        project=REPO_PROJECT,
        extra_protected_patterns=["scripts/custom_*.py"],
    )
    assert extra_dec.tier == "L3"
    assert extra_dec.full_forced is True


@pytest.mark.parametrize(
    "bad_paths",
    [
        [],
        [""],
        ["../escape.py"],
        ["/etc/passwd"],
        ["C:/Windows/win.ini"],
        ["auto_pm\x00/a.py"],
    ],
)
def test_empty_and_invalid_paths_fail_closed_to_l3(bad_paths: list[str]) -> None:
    decision = classify_gate_tier(bad_paths, project=REPO_PROJECT)
    assert decision.tier == "L3"
    assert decision.full_forced is True
    assert decision.require_plugin is True
    assert decision.recommended_groups == ALL_GATE_GROUPS


def test_missing_or_corrupted_rules_file_fails_closed_to_l3(tmp_path: Path) -> None:
    missing = classify_gate_tier(["scripts/command_catalog.py"], rules_path=tmp_path / "missing.json")
    assert missing.tier == "L3" and missing.full_forced is True

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")
    corrupt = classify_gate_tier(["scripts/command_catalog.py"], rules_path=bad_json)
    assert corrupt.tier == "L3" and corrupt.full_forced is True

    bad_schema = tmp_path / "schema.json"
    bad_schema.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    wrong = classify_gate_tier(["scripts/command_catalog.py"], rules_path=bad_schema)
    assert wrong.tier == "L3" and wrong.full_forced is True
