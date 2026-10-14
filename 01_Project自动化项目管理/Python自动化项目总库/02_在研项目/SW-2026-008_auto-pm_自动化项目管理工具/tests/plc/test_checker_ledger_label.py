"""TD-SW008-130: the static PLC check labels the change-ledger item with the specification glyph (台账), not the old one (台帐).

The label is what an operator reads and what scripts or tests assert on, so it must follow the specification and the template (whose file is named ``01_版本变更台账.md``).
The ledger is still *found* by either glyph in the file name; only the item label and the messages changed.
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.models.plc import CheckResult
from auto_pm.domain.plc.checker import PlcChecker

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
PID, NAME = "DJ-2026-903", "LEDGERLABEL"
LEDGER = "11_监控/01_变更管理/02_变更记录/01_版本变更台账.md"
OLD_GLYPH, NEW_GLYPH = "台帐", "台账"


def _generate(workspace: Path) -> Path:
    destination = workspace / PID
    TemplateService(str(TEMPLATES_DIR)).copy_template("plc-standard-project", str(destination), {"project_id": PID, "project_name": NAME})
    return destination


def _check(workspace: Path, project: Path) -> CheckResult:
    result: CheckResult = PlcChecker(workspace_root=str(workspace)).check_project(str(project))
    return result


def test_the_ledger_item_passes_under_the_specification_label(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    items = {i.item: i for i in _check(tmp_path, project).items}
    assert "版本变更台账" in items and items["版本变更台账"].status == "pass"
    assert "版本变更台帐" not in items


def test_a_missing_ledger_fails_under_the_specification_label_and_names_the_specification_file(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    (project / LEDGER).unlink()
    failed = [i for i in _check(tmp_path, project).items if i.status == "fail"]
    assert [i.item for i in failed] == ["版本变更台账"]
    assert "01_版本变更台账.md" in failed[0].message and OLD_GLYPH not in failed[0].message


def test_no_item_label_or_message_of_a_generated_project_uses_the_old_glyph(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    for item in _check(tmp_path, project).items:
        assert OLD_GLYPH not in item.item and OLD_GLYPH not in item.message, (item.item, item.message)
    assert any(NEW_GLYPH in i.item for i in _check(tmp_path, project).items)


def test_a_ledger_file_named_with_the_old_glyph_is_still_found(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    ledger = project / LEDGER
    ledger.rename(ledger.with_name("01_版本变更台帐.md"))
    items = {i.item: i for i in _check(tmp_path, project).items}
    assert items["版本变更台账"].status == "pass"
