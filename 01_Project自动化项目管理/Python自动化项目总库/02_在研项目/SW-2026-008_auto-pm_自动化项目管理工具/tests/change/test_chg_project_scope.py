"""Mission 收口写证据与实施回填只在本项目里找变更单（M3-CHGSCOPE）

变更单按项目编号，不同项目可以有同号的 ``CHG-SCPT-2026-002``；以前收口写证据要求它在整个工作空间
里只有一份，D08 第 1 道（SW-2026-010）的 Mission 因此停在 ACCEPTED。现在给了项目编号就只在该项目
``04_监控``/``11_监控`` 下的 ``01_变更管理/01_变更单`` 里找（不含 ``archive``），那里仍必须恰好一份。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.domain.change.substance_injector import SubstanceInjectionError, SubstanceInjector
from tests.change.test_substance_control import _closure_evidence, _write_closure_chg

CHG = "CHG-SCPT-2026-002"


def _project(ws: Path, name: str, monitor: str = "04_监控") -> Path:
    root = ws / name
    root.mkdir(parents=True)
    (root / f"PM_SESSION_{name.split('_')[0]}.md").write_text("# PM_SESSION\n", encoding="utf-8")
    return root / monitor / "01_变更管理" / "01_变更单"


def _write(chg_dir: Path) -> Path:
    written = _write_closure_chg(chg_dir, CHG)  # writes <dir>/changes/<CHG>.md
    target = chg_dir / "CHG-SCPT" / f"{CHG}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    written.replace(target)
    written.parent.rmdir()
    return target


def _inject(ws: Path, project_id: str | None) -> Path:
    return SubstanceInjector.inject_closure_evidence(
        ws,
        change_number=CHG,
        target_path=f"change://{CHG}",
        evidence=_closure_evidence(CHG),
        project_id=project_id,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> dict[str, Path]:
    a = _write(_project(tmp_path, "SW-2026-010_验证套件"))
    b = _write(_project(tmp_path, "SW-2026-009_英语学习助手"))
    c = _write(_project(tmp_path / "0100_PLC", "DJ-2026-011_验证", monitor="11_监控"))
    stale = _write(
        tmp_path
        / ".auto-pm"
        / "worktrees"
        / "old"
        / "SW-2026-010_验证套件"
        / "04_监控"
        / "01_变更管理"
        / "01_变更单"
    )
    return {"root": tmp_path, "a": a, "b": b, "c": c, "stale": stale}


def test_the_same_number_in_other_projects_does_not_block_the_closure(
    workspace: dict[str, Path],
) -> None:
    before = {k: workspace[k].read_bytes() for k in ("b", "c", "stale")}
    written = _inject(workspace["root"], "SW-2026-010")
    assert written == workspace["a"].resolve()
    assert "PM-CLOSURE-EVIDENCE" in workspace["a"].read_text(encoding="utf-8")
    assert {k: workspace[k].read_bytes() for k in before} == before


def test_a_project_with_the_old_monitor_layout_is_found(workspace: dict[str, Path]) -> None:
    assert _inject(workspace["root"], "DJ-2026-011") == workspace["c"].resolve()


def test_without_a_project_the_old_workspace_wide_uniqueness_still_refuses(
    workspace: dict[str, Path],
) -> None:
    with pytest.raises(SubstanceInjectionError, match="唯一存在"):
        _inject(workspace["root"], None)


def test_an_archived_copy_in_the_same_project_is_ignored(workspace: dict[str, Path]) -> None:
    archive = workspace["a"].parent / "archive" / f"{CHG}.md"
    archive.parent.mkdir()
    archive.write_bytes(workspace["a"].read_bytes())
    assert _inject(workspace["root"], "SW-2026-010") == workspace["a"].resolve()
    assert "PM-CLOSURE-EVIDENCE" not in archive.read_text(encoding="utf-8")


def test_two_live_copies_inside_the_project_are_still_refused(workspace: dict[str, Path]) -> None:
    second = workspace["a"].parent.parent / "CHG-OTHER" / f"{CHG}.md"
    second.parent.mkdir()
    second.write_bytes(workspace["a"].read_bytes())
    untouched = workspace["a"].read_bytes()
    with pytest.raises(SubstanceInjectionError, match="项目 SW-2026-010 的变更单目录内唯一存在"):
        _inject(workspace["root"], "SW-2026-010")
    assert workspace["a"].read_bytes() == untouched


def test_the_change_missing_in_its_project_is_refused_even_if_another_project_has_it(
    workspace: dict[str, Path],
) -> None:
    workspace["a"].unlink()
    with pytest.raises(SubstanceInjectionError, match="实际匹配数: 0"):
        _inject(workspace["root"], "SW-2026-010")


def test_implementation_backfill_writes_into_the_change_of_its_own_project(
    workspace: dict[str, Path],
) -> None:
    before = {k: workspace[k].read_bytes() for k in ("a", "c", "stale")}
    written = SubstanceInjector.inject(
        workspace_root=workspace["root"],
        change_number=CHG,
        substance={"implementation_tasks": [], "verification_records": []},
        changed_files=["src/x.py"],
        executor_id="tester",
        project_id="SW-2026-009",
    )
    assert Path(written).resolve() == workspace["b"].resolve()
    assert {k: workspace[k].read_bytes() for k in before} == before


def test_the_closure_service_passes_the_project_of_its_work(tmp_path: Path) -> None:
    """收口服务按 Work 的项目（subject_project_id）定位变更单，别的项目的同号变更单不挡它。"""
    from typing import cast

    from auto_pm.application.core.pm_closure_service import PmClosureService
    from auto_pm.infrastructure.continuity_store import ContinuityStore
    from tests.change.test_substance_control import _ClosureStore, _prepared_closure_payload

    change_id = "CHG-SCPT-2026-280"
    own = _project(tmp_path, "SW-TEST-001_计算器")
    other = _project(tmp_path, "SW-TEST-002_其他")
    for chg_dir in (own, other):
        written = _write_closure_chg(chg_dir, change_id)
        target = chg_dir / "CHG-SCPT" / f"{change_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        written.replace(target)
        written.parent.rmdir()
    untouched = (other / "CHG-SCPT" / f"{change_id}.md").read_bytes()
    payload = _prepared_closure_payload(change_id)
    service = PmClosureService(tmp_path, store=cast(ContinuityStore, _ClosureStore(payload)))

    updated = service.inject_prepared_change_substance(str(payload["closure"]["closure_id"]))

    assert updated == (own / "CHG-SCPT" / f"{change_id}.md").resolve()
    assert (other / "CHG-SCPT" / f"{change_id}.md").read_bytes() == untouched
