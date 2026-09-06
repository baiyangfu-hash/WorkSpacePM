"""单元测试：跨领域关联变更单穿透门禁（Cross Domain Associated Change Gate）"""

from pathlib import Path

from auto_pm.change.constants import ChangeRequest

from auto_pm.domain.change.substance_checker import SubstanceChecker


def test_cross_domain_pass_when_marked_self():
    """测试跨领域标记为本单或无时放行"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-001",
        project_id="DJ-2026-005",
        status="completed",
        has_section_7=True,
        has_section_9=True,
        has_section_10_verify=True,
        section_10_conclusion="通过",
    )
    cr.sections = {
        "5": "### 5.1 变更前\n| 涉及文件 | a.scl |\n### 5.2 变更后\n| 涉及文件 | a.scl |",
        "6": """### 6.2 技术领域影响
| 受影响领域 | 是否受影响 | 具体影响内容 | 涉及交付物 | 关联变更单号 |
|---|:---:|---|---|---|
| ☑ **PLC** | ☑是 □否 | 报警逻辑 | a.scl | 本单 |
| □ **HMI** | □是 ☑否 | 无 | 无 | 无 |
""",
    }
    violations = SubstanceChecker.check_cross_domain_links(cr)
    assert violations == []


def test_cross_domain_fails_on_missing_ticket(tmp_path: Path):
    """测试跨领域声明了关联单号但物理文件不存在时拦截"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-001",
        project_id="DJ-2026-005",
        status="completed",
    )
    cr.sections = {
        "6": """### 6.2 技术领域影响
| 受影响领域 | 是否受影响 | 具体影响内容 | 涉及交付物 | 关联变更单号 |
|---|:---:|---|---|---|
| ☑ **HMI** | ☑是 □否 | 画面改动 | view.qml | CHG-HMI-2026-999 |
""",
    }
    violations = SubstanceChecker.check_cross_domain_links(cr, workspace_root=tmp_path)
    assert any("关联变更单在工作空间中不存在: 'CHG-HMI-2026-999'" in v for v in violations)


def test_cross_domain_passes_when_ticket_exists(tmp_path: Path):
    """测试跨领域声明的关联单号物理存在时放行"""
    hmi_dir = tmp_path / "01_变更单" / "CHG-HMI"
    hmi_dir.mkdir(parents=True)
    (hmi_dir / "CHG-HMI-2026-001.md").write_text("# CHG-HMI-2026-001", encoding="utf-8")

    cr = ChangeRequest(
        change_number="CHG-PLC-2026-001",
        project_id="DJ-2026-005",
        status="completed",
    )
    cr.sections = {
        "6": """### 6.2 技术领域影响
| 受影响领域 | 是否受影响 | 具体影响内容 | 涉及交付物 | 关联变更单号 |
|---|:---:|---|---|---|
| ☑ **HMI** | ☑是 □否 | 画面改动 | view.qml | CHG-HMI-2026-001 |
""",
    }
    violations = SubstanceChecker.check_cross_domain_links(cr, workspace_root=tmp_path)
    assert violations == []


def test_cross_domain_fails_on_empty_associated_id():
    """测试勾选了受影响但未指定单号（如留下横杠或占位符）时拦截"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-001",
        project_id="DJ-2026-005",
        status="completed",
    )
    cr.sections = {
        "6": """### 6.2 技术领域影响
| 受影响领域 | 是否受影响 | 具体影响内容 | 涉及交付物 | 关联变更单号 |
|---|:---:|---|---|---|
| ☑ **HMI** | ☑是 □否 | 画面改动 | view.qml | 未填 |
""",
    }
    violations = SubstanceChecker.check_cross_domain_links(cr)
    assert any("已勾选跨领域影响但未指定有效关联变更单号" in v for v in violations)
