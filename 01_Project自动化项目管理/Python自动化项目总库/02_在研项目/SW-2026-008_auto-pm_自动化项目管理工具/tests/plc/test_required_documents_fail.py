"""TD-SW008-129 (user ruling B7): a deleted interface document, an unreadable OB1 and a deleted variable definition
document are failures of ``plc check``; none of them is skipped or only warned about."""

from __future__ import annotations

import shutil
from pathlib import Path

from auto_pm.domain.plc.checker import PlcChecker
from auto_pm.domain.plc.models import CheckResult

from .test_checker import (
    full_project,  # noqa: F401  (pytest fixture: a standard project where every check passes)
)
from .test_doc_consistency import VAR_DOC
from .test_doc_consistency_checker import make, run

VAR_ITEM = "变量定义文档存在性"


def _failing(result: CheckResult) -> dict[str, str]:
    return {item.item: item.message for item in result.items if item.status == "fail"}


def _check(workspace: Path) -> CheckResult:
    project = workspace / "DJ-2026-FULL_完整项目"
    return PlcChecker(str(workspace)).check_project(str(project))


def test_the_complete_project_fails_nothing(full_project: Path) -> None:  # noqa: F811
    assert _failing(_check(full_project)) == {}


def test_a_deleted_interface_document_fails_the_check(full_project: Path) -> None:  # noqa: F811
    (full_project / "DJ-2026-FULL_完整项目" / "PRD" / "接口文档_INT.md").unlink()

    failing = _failing(_check(full_project))

    assert any("接口文档_INT.md" in name and "缺少" in message for name, message in failing.items()), failing


def test_an_unreadable_ob1_fails_the_check(full_project: Path) -> None:  # noqa: F811
    main = full_project / "DJ-2026-FULL_完整项目" / "02_PLC程序" / "PLC_ST" / "00_主程序"
    main.mkdir(parents=True)
    (main / "OB1.scl").write_text("@@@ !!! garbage (((\n", encoding="utf-8")

    failing = _failing(_check(full_project))

    assert "SCL 代码规范" in failing and "OB1.scl" in failing["SCL 代码规范"], failing


def test_a_deleted_variable_definition_document_fails_the_check(tmp_path: Path) -> None:
    result = run(make(tmp_path, var=None))

    failing = _failing(result)

    assert VAR_ITEM in failing, failing
    assert "PLC变量定义文档_VAR.md" in failing[VAR_ITEM] and "plc docs sync" in failing[VAR_ITEM]
    assert result.fail_count >= 1


def test_the_same_project_with_its_variable_definition_document_does_not_fail_on_it(tmp_path: Path) -> None:
    assert VAR_ITEM not in _failing(run(make(tmp_path)))


def test_a_project_with_no_data_blocks_or_structures_needs_no_variable_definition_document(tmp_path: Path) -> None:
    project = make(tmp_path, var=None)
    # Keep the function block alone: nothing is left for a variable definition file to document.
    (project / "02_PLC程序" / "PLC_ST" / "01_泵" / "ST_PumpCfg.scl").unlink()
    (project / "02_PLC程序" / "PLC_ST" / "00_全局数据" / "GlobalVars.db").unlink()

    assert VAR_ITEM not in _failing(run(project))


def test_a_missing_interface_document_of_one_block_still_only_warns(tmp_path: Path) -> None:
    # B7 is about the three files above; the per-block drafts made by ``plc docs sync`` stay warnings.
    result = run(make(tmp_path, ifc=None))

    assert VAR_ITEM not in _failing(result)
    assert any(
        item.status == "warn" and item.item.startswith("文档一致性") and "缺文档" in item.message
        for item in result.items
    )


def test_restoring_the_deleted_variable_definition_document_clears_the_failure(tmp_path: Path) -> None:
    project = make(tmp_path, var=VAR_DOC)
    document = next(project.rglob("PLC变量定义文档_VAR.md"))
    backup = tmp_path / "VAR.bak"
    shutil.move(str(document), str(backup))
    assert VAR_ITEM in _failing(run(project))

    shutil.move(str(backup), str(document))

    assert VAR_ITEM not in _failing(run(project))
