"""单元测试：变更单实质内容防御门禁与自动注入引擎（Substance Control & Injection）"""

from pathlib import Path

import pytest
from auto_pm.change.constants import ChangeRequest, TransitionGuardError

from auto_pm.domain.change.guard_checker import TransitionGuardChecker
from auto_pm.domain.change.substance_checker import SubstanceChecker
from auto_pm.domain.change.substance_injector import SubstanceInjector


def test_substance_checker_catches_placeholders() -> None:
    """测试 SubstanceChecker 能够准确识别未填写的模板占位符"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-999",
        project_id="DJ-2026-005",
        status="completed",
        has_section_7=True,
        has_section_9=True,
        has_section_10_verify=True,
        section_10_conclusion="全部通过",
    )
    # 模拟包含占位符的章节
    cr.sections = {
        "5": "### 5.1 变更前\n| 涉及文件 | （待填写） |\n### 5.2 变更后\n| 涉及文件 | （待填写） |",
        "7": "| 1 | 任务 | 负责人 | 2026-09-03 | 2026-09-03 | - | 已完成 |",
        "9": "| 2026-09-03 | fubai | 实施 | 内容 | 成功 | - |",
        "10": "| 1 | 测试 | 标准 | 预期 | 实际 | 通过 | fubai | 2026-09-03 |\n| **验证结论** | 全部通过 |",
    }
    violations = SubstanceChecker.check_substance(cr)
    assert any("包含未替换占位符: '（待填写）'" in v for v in violations)


def test_substance_checker_passes_on_full_substance() -> None:
    """测试 SubstanceChecker 在变更单实质内容完整时全绿通过"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-999",
        project_id="DJ-2026-005",
        status="completed",
        has_section_7=True,
        has_section_9=True,
        has_section_10_verify=True,
        section_10_conclusion="全部验证通过，门禁全绿",
    )
    cr.sections = {
        "5": "### 5.1 变更前\n| 涉及文件 | FB_2001.scl |\n### 5.2 变更后\n| 涉及文件 | FB_2001.scl (增加2009报警) |",
        "7": "| 1 | 编写SCL | plc-engineer | 2026-09-03 | 2026-09-03 | - | 已完成 |",
        "9": "| 2026-09-03 | plc-engineer | 实施 | 完成常量挂接 | 成功 | - |",
        "10": "| 1 | plc check | 51 PASS | 51 PASS | 51 PASS | 通过 | plc-engineer | 2026-09-03 |\n| **验证结论** | 全部验证通过，门禁全绿 |",
    }
    violations = SubstanceChecker.check_substance(cr)
    assert violations == []


def test_transition_guard_blocks_empty_substance() -> None:
    """测试状态流转守卫在遇到空壳单据时抛出 TransitionGuardError 阻断"""
    guard = TransitionGuardChecker()
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-999",
        project_id="DJ-2026-005",
        status="implementing",
        has_section_7=True,
        has_section_9=False,
        has_section_10_verify=False,
        section_10_conclusion="",
    )
    cr.sections = {
        "5": "### 5.1 变更前\n| 涉及文件 | （待填写） |\n### 5.2 变更后\n| 涉及文件 | （待填写） |",
    }
    with pytest.raises(TransitionGuardError) as exc_info:
        guard.check(cr, target_status="completed", approver="fubai", comment="")
    assert "包含未替换占位符" in str(exc_info.value)


def test_substance_injector_replaces_placeholders(tmp_path: Path) -> None:
    """测试 SubstanceInjector 物理回填与占位符擦除逻辑"""
    chg_dir = tmp_path / "01_变更单" / "CHG-PLC"
    chg_dir.mkdir(parents=True)
    chg_file = chg_dir / "CHG-PLC-2026-888.md"

    initial_content = """# CHG-PLC-2026-888

## 5. 变更内容

### 5.1 变更前（当前状态）
| 项目 | 当前值/描述 |
|------|-----------|
| 涉及文件/交付物 | （待填写） |
| 关键参数/配置 | （待填写） |

### 5.2 变更后（目标状态）
| 项目 | 目标值/描述 |
|------|-----------|
| 涉及文件/交付物 | （待填写） |
| 关键参数/配置 | （待填写） |

## 6. 变更影响分析
**缓解措施**（风险应对策略）：
（待填写）

## 7. 变更实施计划
| 序号 | 任务描述 | 负责人(角色) | 开始日期 | 完成日期 | 前置依赖 | 备注 |
|------|----------|-------------|----------|----------|----------|------|
| | | | | | | |

## 9. 变更实施记录
| 实施日期 | 实施人 | 实施任务 | 实施内容摘要 | 实施结果 | 备注 |
|----------|--------|----------|-------------|----------|------|
| | | | | | |

## 10. 变更验证
### 10.1 验证项清单
| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|------|--------|----------|
| | | | | | | | |

### 10.3 验证结论
| **验证结论** | （待填写） |
"""
    chg_file.write_text(initial_content, encoding="utf-8")

    substance = {
        "before_state": {
            "files": ["FB_Test.scl"],
            "parameters": ["初始参数未设置"],
        },
        "after_state": {
            "files": ["FB_Test.scl"],
            "parameters": ["已配置看门狗超时"],
        },
        "implementation_tasks": [
            {"task": "编写看门狗逻辑", "result": "成功"}
        ],
        "verification_records": [
            {"item": "门禁自检", "standard": "通过", "actual": "51 PASS", "passed": True}
        ],
        "verification_conclusion": "全部验证通过，门禁全绿",
    }

    updated_file = SubstanceInjector.inject(
        workspace_root=tmp_path,
        change_number="CHG-PLC-2026-888",
        substance=substance,
        changed_files=["FB_Test.scl"],
        executor_id="plc-electrical-engineer",
    )

    result_text = updated_file.read_text(encoding="utf-8")
    assert "（待填写）" not in result_text
    assert "FB_Test.scl" in result_text
    assert "已配置看门狗超时" in result_text
    assert "编写看门狗逻辑" in result_text
    assert "全部验证通过，门禁全绿" in result_text
