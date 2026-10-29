"""变更单完成前的文档同步检查（SHC-011/SHC-014）只读本项目、只作提示（M3-DOCSYNC）

PM_SESSION 已于 2026-10-10 退役。以前这项检查在整个工作空间里递归找 ``PM_SESSION_<项目编号>*.md``
（会命中 ``.auto-pm/worktrees`` 里的旧副本），检查不过就禁止变更单流转到 completed；
D08 第 1 道（SW-2026-010）因此停在“验收中”。现在：
- 只读变更单所在项目根目录下的 ``PM_SESSION_<项目编号>.md``，项目根下没有就跳过；
- 检查结果写进验证结论作为提示，不再阻止完成。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.spec.core.checker_base import HealthChecker
from tests.change.test_acceptance_flow import _build_chg_with_implementation

PID = "TEST-2026-001"
CHG = "CHG-DOCU-2026-001"


def _project(tmp_path: Path, monitor: str = "04_监控", pm_session: bool = True) -> Path:
    project = tmp_path / PID
    chg_dir = project / monitor / "01_变更管理" / "01_变更单" / "CHG-DOCU"
    chg_dir.mkdir(parents=True)
    if pm_session:
        (project / f"PM_SESSION_{PID}.md").write_text("# PM_SESSION\n", encoding="utf-8")
    (chg_dir / f"{CHG}.md").write_text(_build_chg_with_implementation(), encoding="utf-8")
    ledger_dir = project / monitor / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "01_版本变更台帐.md").write_text(
        "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n",
        encoding="utf-8",
    )
    return chg_dir / f"{CHG}.md"


def _to_accepting(svc: ChangeService) -> None:
    svc.transition_status(CHG, "pending_acceptance", approver="张三", project_id=PID)
    svc.transition_status(CHG, "accepting", approver="李四", project_id=PID)


@pytest.mark.parametrize("monitor", ["04_监控", "11_监控"])
def test_project_root_is_the_folder_above_the_monitor_folder(tmp_path: Path, monitor: str) -> None:
    chg_file = _project(tmp_path, monitor=monitor)
    assert ChangeService._project_root_of(str(chg_file)) == (tmp_path / PID).resolve()


def test_project_root_is_none_outside_a_monitor_folder(tmp_path: Path) -> None:
    loose = tmp_path / "loose" / f"{CHG}.md"
    loose.parent.mkdir(parents=True)
    loose.write_text("x", encoding="utf-8")
    assert ChangeService._project_root_of(str(loose)) is None


def test_a_stale_copy_elsewhere_is_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """项目根下没有 PM_SESSION 时跳过；工作空间别处（如 .auto-pm/worktrees）的旧副本不再被读到。"""
    chg_file = _project(tmp_path, pm_session=False)
    stale = tmp_path / ".auto-pm" / "worktrees" / "old" / PID
    stale.mkdir(parents=True)
    (stale / f"PM_SESSION_{PID}.md").write_text("# 旧副本\n", encoding="utf-8")
    (stale / ".copier-answers.yml").write_text(f"project_id: {PID}\n", encoding="utf-8")

    def _must_not_run(*_args: object, **_kwargs: object) -> list[object]:
        raise AssertionError(
            "the doc-sync checkers ran although the project root has no PM_SESSION"
        )

    monkeypatch.setattr(HealthChecker, "run_by_id", _must_not_run)
    assert ChangeService(str(tmp_path))._check_doc_sync(PID, str(chg_file)) == []


def test_the_check_reads_the_project_of_the_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chg_file = _project(tmp_path)
    seen: list[Path] = []

    def _record(
        self: HealthChecker, check_id: str, registry: object, scanner: object
    ) -> list[object]:
        seen.append(Path(scanner.project_root))  # type: ignore[attr-defined]
        return []

    monkeypatch.setattr(HealthChecker, "run_by_id", _record)
    assert ChangeService(str(tmp_path))._check_doc_sync(PID, str(chg_file)) == []
    assert seen and all(p.resolve() == (tmp_path / PID).resolve() for p in seen)


def test_doc_sync_findings_do_not_block_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SHC-011/SHC-014 报错时变更单照样能完成，提示写进验证结论。"""
    chg_file = _project(tmp_path)
    finding = "[SHC-014] PM_SESSION §4 缺少必需文档索引: dsn, int, tec"
    calls: list[tuple[str | None, str | None]] = []

    def _findings(
        self: ChangeService, project_id: str | None, change_file: str | None = None
    ) -> list[str]:
        calls.append((project_id, change_file))
        return [finding]

    monkeypatch.setattr(ChangeService, "_check_doc_sync", _findings)
    svc = ChangeService(str(tmp_path))
    _to_accepting(svc)
    cr = svc.transition_status(
        CHG, "completed", approver="李四", verification_conclusion="全部通过", project_id=PID
    )
    assert cr is not None and cr.status == "completed"
    assert calls and calls[-1][0] == PID and Path(str(calls[-1][1])).resolve() == chg_file.resolve()
    text = chg_file.read_text(encoding="utf-8")
    assert "[文档同步提示，不阻止完成]" in text and finding in text


def test_a_clean_check_leaves_the_conclusion_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chg_file = _project(tmp_path)
    monkeypatch.setattr(
        ChangeService, "_check_doc_sync", lambda self, project_id, change_file=None: []
    )
    svc = ChangeService(str(tmp_path))
    _to_accepting(svc)
    cr = svc.transition_status(
        CHG, "completed", approver="李四", verification_conclusion="全部通过", project_id=PID
    )
    assert cr is not None and cr.status == "completed"
    assert "文档同步提示" not in chg_file.read_text(encoding="utf-8")
