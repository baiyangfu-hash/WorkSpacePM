"""Keep the scoped source-guard manifest and non-guard tree-walker allowlist synchronized."""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.gate_precheck_service import (
    SOURCE_GUARDS_MANIFEST,
    _guard_scope_matches,
    _load_source_guards_manifest,
    _scans_the_tree,
)

PROJECT = Path(__file__).resolve().parents[2]
TESTS = PROJECT / "tests"
MANIFEST = PROJECT / SOURCE_GUARDS_MANIFEST

# 仅保留真正只遍历临时夹具目录或业务构建数据的测试（6 项）；
# 全部 34 项全局/子树源码静态守卫均按真实扫描作用域保留在 source_guards_manifest.txt 中，不按大小删减。
NON_SOURCE_GUARD_ALLOWLIST: frozenset[str] = frozenset(
    {
        "tests/cli/test_workflow_compat.py",
        "tests/constraint/test_loader.py",
        "tests/core/test_cockpit_api.py",
        "tests/core/test_plc_gate_baseline.py",
        "tests/tools/test_gate_progress.py",
        "tests/utils/test_file_utils.py",
    }
)


def test_manifest_and_allowlist_entries_exist_and_stay_disjoint() -> None:
    assert MANIFEST.is_file()
    entries = _load_source_guards_manifest(MANIFEST)
    assert len(entries) >= 34

    manifest_tests: list[str] = []
    for scope_spec, rel in entries:
        for scope in scope_spec.split(","):
            assert scope == "*" or scope.endswith("/") or scope.startswith("*.") or "/" in scope or "." in scope, (
                scope_spec
            )
        assert (PROJECT / rel).is_file(), f"清单中守卫文件不存在: {rel}"
        assert _scans_the_tree(PROJECT / rel) is True, f"清单条目不再满足 _scans_the_tree: {rel}"
        manifest_tests.append(rel)

    assert len(manifest_tests) == len(set(manifest_tests)), "source_guards_manifest.txt 存在重复测试路径"
    manifest_set = set(manifest_tests)
    assert manifest_set.isdisjoint(NON_SOURCE_GUARD_ALLOWLIST)

    for rel in sorted(NON_SOURCE_GUARD_ALLOWLIST):
        assert (PROJECT / rel).is_file(), f"白名单文件不存在: {rel}"
        assert _scans_the_tree(PROJECT / rel) is True, (
            f"{rel} 已不再触发 _scans_the_tree，请从 NON_SOURCE_GUARD_ALLOWLIST 移除"
        )


def test_every_tree_scanning_test_is_registered_in_manifest_or_allowlist() -> None:
    manifest_set = {rel for _, rel in _load_source_guards_manifest(MANIFEST)}
    known = manifest_set | NON_SOURCE_GUARD_ALLOWLIST
    live_matches = {
        path.relative_to(PROJECT).as_posix()
        for path in sorted(TESTS.rglob("test_*.py"))
        if _scans_the_tree(path)
    }
    unregistered = sorted(live_matches - known)
    assert unregistered == [], (
        "发现未登记的新增树遍历测试（请登记进 source_guards_manifest.txt 并标明作用域，"
        f"或确认仅扫夹具后再纳入 allowlist）：{unregistered}"
    )


def test_manifest_scopes_exclude_gui_and_board_tests_on_script_and_test_changes() -> None:
    entries = _load_source_guards_manifest(MANIFEST)
    pilot_matched = {
        rel
        for scope, rel in entries
        if _guard_scope_matches(
            scope,
            ["scripts/command_catalog.py", "tests/infrastructure/test_command_catalog.py"],
        )
    }
    expected_pilot_guards = {
        "tests/change/test_change_number_width.py",
        "tests/infrastructure/test_subprocess_text_encoding.py",
        "tests/contract/test_registry_fields_one_source.py",
        "tests/core/test_agent_registry.py",
        "tests/infrastructure/test_no_new_short_layer_imports.py",
        "tests/infrastructure/test_run_control_root_guard_ratchet.py",
        "tests/infrastructure/test_external_reads_marked.py",
        "tests/infrastructure/test_memory_preflight.py",
        "tests/infrastructure/test_source_guards_manifest.py",
        "tests/test_fixture_health.py",
    }
    assert expected_pilot_guards <= pilot_matched
    excluded_on_pilot = {
        "tests/infrastructure/test_cockpit_board_static_guards.py",
        "tests/core/test_cockpit_board_release_page.py",
        "tests/core/test_cockpit_board_runner.py",
        "tests/core/test_cockpit_board_shell.py",
        "tests/core/test_cockpit_board_tools.py",
        "tests/core/test_cockpit_no_window.py",
        "tests/test_layer_import_direction.py",
        "tests/cli/test_caller_path.py",
        "tests/contract/test_interlock_matrix.py",
    }
    assert excluded_on_pilot.isdisjoint(pilot_matched)
    assert pilot_matched.isdisjoint(NON_SOURCE_GUARD_ALLOWLIST)

    manifest_set = {rel for _, rel in entries}
    assert {"tests/core/test_cockpit_board.py", "tests/core/test_pm_dashboard_gui.py"}.isdisjoint(
        manifest_set
    )

    board_matched = {rel for scope, rel in entries if _guard_scope_matches(scope, ["scripts/cockpit_board/app.py"])}
    assert {
        "tests/infrastructure/test_cockpit_board_static_guards.py",
        "tests/core/test_cockpit_board_release_page.py",
        "tests/core/test_cockpit_board_runner.py",
        "tests/core/test_cockpit_board_shell.py",
        "tests/core/test_cockpit_board_tools.py",
        "tests/core/test_cockpit_no_window.py",
    } <= board_matched
    assert "tests/core/test_cockpit_board.py" not in board_matched
    assert "tests/core/test_pm_dashboard_gui.py" not in board_matched

    pm_dash_matched = {rel for scope, rel in entries if _guard_scope_matches(scope, ["scripts/pm_dashboard.py"])}
    assert "tests/core/test_cockpit_no_window.py" in pm_dash_matched

    gui_entry_matched = {rel for scope, rel in entries if _guard_scope_matches(scope, ["scripts/pm_dashboard_gui.py"])}
    assert "tests/infrastructure/test_cockpit_board_static_guards.py" in gui_entry_matched
    assert "tests/core/test_pm_dashboard_gui.py" not in gui_entry_matched
    assert "tests/core/test_cockpit_board.py" not in gui_entry_matched

    cli_matched = {rel for scope, rel in entries if _guard_scope_matches(scope, ["auto_pm/ui/cli/pm.py"])}
    assert {"tests/cli/test_caller_path.py", "tests/contract/test_interlock_matrix.py"} <= cli_matched
