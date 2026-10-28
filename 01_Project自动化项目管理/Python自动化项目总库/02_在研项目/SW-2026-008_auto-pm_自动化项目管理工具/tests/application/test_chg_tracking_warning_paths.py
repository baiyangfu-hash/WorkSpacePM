"""TD-SW008-213: every exit of ``ledger reconcile`` (diff, ``--fix``, orphans) and ``change verify --ledger-check`` shows the commit-tracking warning and keeps its own exit code."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner, Result

from auto_pm.domain.change.ledger_reconciler import ReconcileDiff
from tests.application.test_chg_tracking_service import CHG, _commit, _repo, _write

pytestmark = pytest.mark.usefixtures("identity_guard_off")

_UNTRACKED_LINE = "未入库: 04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-002.md"
_MISSING = ReconcileDiff(missing_in_ledger=["CHG-SCPT-2026-002"])
_ORPHAN = ReconcileDiff(orphan_in_ledger=["CHG-SCPT-2026-777"])


class _Fixture:
    """A repository with one committed and one uncommitted change request, plus scripted reconcile results."""

    def __init__(self, tmp_path: Path, diffs: list[ReconcileDiff], *, project_found: bool = True, commit: bool = True) -> None:
        self.root = _repo(tmp_path)
        self.project = self.root / "SW-1"
        _write(self.project, CHG)
        if commit:
            _commit(self.root)
        _write(self.project, "CHG-SCPT-2026-002.md")
        self.diffs = list(diffs)
        self.fix_calls = 0
        self.project_found = project_found

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import auto_pm.application.core.project_service as project_module
        import auto_pm.domain.change.ledger_reconciler as reconciler_module
        from auto_pm.ui.cli import ledger

        fixture = self

        class FakeProjects:
            def __init__(self, _root: Path) -> None: ...

            def find_project_path(self, _pid: str) -> str | None:
                return str(fixture.project) if fixture.project_found else None

        class FakeReconciler:
            def reconcile(self, _path: str) -> ReconcileDiff:
                return fixture.diffs.pop(0) if len(fixture.diffs) > 1 else fixture.diffs[0]

            def auto_fix(self, _path: str, _diff: ReconcileDiff) -> None:
                fixture.fix_calls += 1

        for module in (ledger, project_module):
            monkeypatch.setattr(module, "ProjectService", FakeProjects)
        for module in (ledger, reconciler_module):
            monkeypatch.setattr(module, "LedgerReconciler", FakeReconciler)

    def run_reconcile(self, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
        from auto_pm.ui.cli import ledger

        self.install(monkeypatch)
        return CliRunner().invoke(ledger.ledger_group, ["reconcile", "SW-1", *args], obj=SimpleNamespace(workspace_root=self.root))

    def run_verify(self, monkeypatch: pytest.MonkeyPatch, *args: str) -> Result:
        from auto_pm.ui.cli.change import change_group

        self.install(monkeypatch)
        return CliRunner().invoke(change_group, ["verify", "SW-1", *args], obj=SimpleNamespace(workspace_root=self.root))


def test_reconcile_with_differences_exits_2_and_still_shows_the_warning_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _Fixture(tmp_path, [_MISSING]).run_reconcile(monkeypatch)

    assert result.exit_code == 2, result.output
    assert result.output.index("检测到差异") < result.output.index("提交跟踪警告")
    assert _UNTRACKED_LINE in result.output


def test_reconcile_fix_that_cleans_up_exits_0_and_shows_the_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _Fixture(tmp_path, [_MISSING, ReconcileDiff()])

    result = fixture.run_reconcile(monkeypatch, "--fix")

    assert result.exit_code == 0, result.output
    assert fixture.fix_calls == 1
    assert result.output.index("对账完成，无差异") < result.output.index("提交跟踪警告")
    assert _UNTRACKED_LINE in result.output


def test_reconcile_fix_left_with_orphans_exits_2_and_shows_the_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _Fixture(tmp_path, [_ORPHAN, _ORPHAN])

    result = fixture.run_reconcile(monkeypatch, "--fix")

    assert result.exit_code == 2, result.output
    assert fixture.fix_calls == 1
    assert result.output.index("仅有孤儿记录") < result.output.index("提交跟踪警告")
    assert _UNTRACKED_LINE in result.output


def test_reconcile_fix_that_cannot_repair_everything_exits_2_and_shows_the_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _Fixture(tmp_path, [_MISSING, _MISSING]).run_reconcile(monkeypatch, "--fix")

    assert result.exit_code == 2, result.output
    assert result.output.index("修复后仍有差异") < result.output.index("提交跟踪警告")


def test_reconcile_for_an_unknown_project_exits_1_without_a_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _Fixture(tmp_path, [ReconcileDiff()], project_found=False).run_reconcile(monkeypatch)

    assert result.exit_code == 1
    assert "提交跟踪" not in result.output


def test_reconcile_in_a_folder_without_commits_says_the_check_was_skipped_and_keeps_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _Fixture(tmp_path, [_MISSING], commit=False).run_reconcile(monkeypatch)

    assert result.exit_code == 2
    assert "提交跟踪检查未执行" in result.output
    assert "提交跟踪警告" not in result.output


def test_verify_ledger_check_passes_with_exit_0_and_shows_the_warning_after_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _Fixture(tmp_path, [ReconcileDiff()]).run_verify(monkeypatch, "--ledger-check")

    assert result.exit_code == 0, result.output
    assert result.output.index("门禁通过") < result.output.index("提交跟踪警告")
    assert _UNTRACKED_LINE in result.output


def test_verify_ledger_check_fails_with_exit_2_and_still_shows_the_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _Fixture(tmp_path, [_MISSING]).run_verify(monkeypatch, "--ledger-check")

    assert result.exit_code == 2, result.output
    assert result.output.index("门禁失败") < result.output.index("提交跟踪警告")
    assert _UNTRACKED_LINE in result.output


def test_verify_lists_everything_with_verbose_and_ten_without(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _Fixture(tmp_path, [ReconcileDiff()])
    for number in range(3, 15):
        _write(fixture.project, f"CHG-SCPT-2026-{number:03d}.md")

    short = fixture.run_verify(monkeypatch, "--ledger-check").output
    full = fixture.run_verify(monkeypatch, "--ledger-check", "--verbose").output

    assert short.count("未入库: ") == 10 and "另有 3 个未入库" in short
    assert full.count("未入库: ") == 13 and "另有" not in full


def test_verify_without_ledger_check_exits_1_and_does_not_look_at_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _Fixture(tmp_path, [ReconcileDiff()]).run_verify(monkeypatch)

    assert result.exit_code == 1
    assert "提交跟踪" not in result.output


def test_reconcile_clean_without_fix_exits_0_and_shows_the_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _Fixture(tmp_path, [ReconcileDiff()])

    result = fixture.run_reconcile(monkeypatch)

    assert result.exit_code == 0, result.output
    assert fixture.fix_calls == 0
    assert result.output.index("对账无差异") < result.output.index("提交跟踪警告")
    assert _UNTRACKED_LINE in result.output


def test_reconcile_lists_everything_with_verbose_and_ten_without(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _Fixture(tmp_path, [ReconcileDiff()])
    for number in range(3, 15):
        _write(fixture.project, f"CHG-SCPT-2026-{number:03d}.md")

    short = fixture.run_reconcile(monkeypatch)
    full = fixture.run_reconcile(monkeypatch, "--verbose")

    assert short.exit_code == 0 and full.exit_code == 0
    assert short.output.count("未入库: ") == 10 and "另有 3 个未入库" in short.output
    assert full.output.count("未入库: ") == 13 and "另有" not in full.output
