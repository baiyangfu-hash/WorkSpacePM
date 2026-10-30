"""A template PLC project's ledger carries the「变更单索引」table, and ``--fix`` heals a ledger without it (D09 onboarding N3)."""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.ledger_reconciler import LedgerReconciler
from auto_pm.domain.change.ledger_updater import LedgerUpdater

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
PID = "DJ-2026-901"
LEDGER = Path("11_监控", "01_变更管理", "02_变更记录", "01_版本变更台账.md")


def _generate(workspace: Path) -> Path:
    project = workspace / "0100_PLC自动化" / PID
    TemplateService(str(TEMPLATES_DIR)).copy_template(
        "plc-standard-project", str(project), {"project_id": PID, "project_name": "TESTMACHINE"}
    )
    return project


def _create_change(workspace: Path) -> str:
    change = ChangeService(str(workspace)).create_change_request(
        project_id=PID,
        domain="PLC",
        business_nature="DEF",
        impact_scope=["LOCAL"],
        applicant="fubai",
        background="双手启动窗口",
        necessity="安全",
    )
    return str(change.change_number)


def _without_index_table(ledger: Path) -> str:
    """The ledger as the template wrote it before this fix (DJ-2026-009 still has this shape)."""
    text = ledger.read_text(encoding="utf-8")
    old = text[: text.index("---\n\n## 3. 变更单索引")]
    ledger.write_text(old, encoding="utf-8")
    return old


def test_a_change_created_in_a_template_project_lands_in_its_ledger(tmp_path: Path) -> None:
    project = _generate(tmp_path)

    change_number = _create_change(tmp_path)

    ledger = (project / LEDGER).read_text(encoding="utf-8")
    assert f"[→ {change_number}]" in ledger
    assert LedgerReconciler().reconcile(str(project)).is_clean


def test_reconcile_fix_adds_the_missing_index_table_and_the_row(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    ledger = project / LEDGER
    old = _without_index_table(ledger)
    change_number = _create_change(tmp_path)
    assert change_number not in ledger.read_text(encoding="utf-8")  # update() still never invents a table
    reconciler = LedgerReconciler()
    assert reconciler.reconcile(str(project)).missing_in_ledger == [change_number]

    reconciler.auto_fix(str(project))

    healed = ledger.read_text(encoding="utf-8")
    assert healed.startswith(old)  # the existing ledger text is kept as it was
    assert "## 变更单索引" in healed and f"[→ {change_number}]" in healed
    assert reconciler.reconcile(str(project)).is_clean


def test_ensure_index_table_is_a_no_op_when_the_table_exists(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    ledger = project / LEDGER
    before = ledger.read_bytes()

    assert LedgerUpdater().ensure_index_table(str(ledger)) is False
    assert ledger.read_bytes() == before

    _without_index_table(ledger)
    assert LedgerUpdater().ensure_index_table(str(ledger)) is True
    once = ledger.read_bytes()
    assert LedgerUpdater().ensure_index_table(str(ledger)) is False
    assert ledger.read_bytes() == once


def test_a_heading_that_only_mentions_the_index_does_not_count_as_a_table(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text("# 台账\n\n## 变更单索引\n\n见附件\n", encoding="utf-8")

    assert LedgerUpdater().ensure_index_table(str(ledger)) is True
    LedgerUpdater().update(str(ledger), "CHG-PLC-2026-001", "测试")

    assert "[→ CHG-PLC-2026-001]" in ledger.read_text(encoding="utf-8")
