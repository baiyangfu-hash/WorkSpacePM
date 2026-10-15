"""修复器补 PRD 目录的位置（M3-PRDLAYOUT 第 2 张）：PLC 项目补到 ``00_程序方案/``，根 ``PRD/`` 不再新建；已有根 ``PRD/`` 的老项目仍补到原处。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.domain.plc.repairer import PlcRepairer


def _project(tmp_path: Path, *, with_plc_st: bool, root_prd: bool = False) -> Path:
    project = tmp_path / "DJ-2026-888_测试机"
    project.mkdir()
    (project / ".plc.json").write_text(
        json.dumps({"name": "DJ-2026-888", "version": "V1.0.0", "description": "x", "type": "standard", "libraries": []}), encoding="utf-8"
    )
    (project / "PM_SESSION_DJ-2026-888.md").write_text("# PM_SESSION_DJ-2026-888" + chr(10), encoding="utf-8")
    if with_plc_st:
        (project / "02_PLC程序" / "PLC_ST").mkdir(parents=True)
    if root_prd:
        (project / "PRD").mkdir()
    return project


def test_a_plc_project_without_any_prd_directory_gets_the_program_scheme_directory(tmp_path: Path) -> None:
    project = _project(tmp_path, with_plc_st=True)
    result = PlcRepairer(str(tmp_path)).repair_project(str(project))
    assert any(a.item == "PRD 目录" and a.status == "fixed" and "00_程序方案" in a.action for a in result.actions)
    assert (project / "02_PLC程序" / "PLC_ST" / "00_程序方案").is_dir()
    assert not (project / "PRD").exists()


def test_the_prd_documents_are_then_created_in_the_program_scheme_directory(tmp_path: Path) -> None:
    project = _project(tmp_path, with_plc_st=True)
    repairer = PlcRepairer(str(tmp_path))
    repairer.repair_project(str(project))
    repairer.repair_project(str(project))
    scheme = project / "02_PLC程序" / "PLC_ST" / "00_程序方案"
    assert (scheme / "接口文档_INT.md").is_file()
    assert not (project / "PRD").exists()


def test_a_dry_run_creates_nothing(tmp_path: Path) -> None:
    project = _project(tmp_path, with_plc_st=True)
    PlcRepairer(str(tmp_path)).repair_project(str(project), dry_run=True)
    assert not (project / "02_PLC程序" / "PLC_ST" / "00_程序方案").exists()
    assert not (project / "PRD").exists()


def test_a_project_without_the_plc_source_tree_keeps_the_root_prd_directory(tmp_path: Path) -> None:
    project = _project(tmp_path, with_plc_st=False)
    PlcRepairer(str(tmp_path)).repair_project(str(project))
    assert (project / "PRD").is_dir()


def test_an_old_project_that_already_has_a_root_prd_directory_keeps_its_documents_there(tmp_path: Path) -> None:
    project = _project(tmp_path, with_plc_st=True, root_prd=True)
    PlcRepairer(str(tmp_path)).repair_project(str(project))
    assert (project / "PRD" / "接口文档_INT.md").is_file()
    assert not (project / "02_PLC程序" / "PLC_ST" / "00_程序方案").exists()
