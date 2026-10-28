"""ChangeMarkdownEditor 单元测试（M1-2）

验证变更单 Markdown 内容编辑器在三节结构（§10.1/§10.2/§10.3）下的行为。
"""

from __future__ import annotations

from auto_pm.change.constants import ChangeRequest
from auto_pm.change.generator import ChgGenerator
from auto_pm.change.markdown_editor import ChangeMarkdownEditor


class TestChangeMarkdownEditor:
    """变更单 Markdown 编辑器测试"""

    def _make_content(self) -> str:
        """生成带三节结构 §10 的变更单内容"""
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-030",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            urgency="normal",
            background="测试",
            necessity="测试",
        )
        return str(ChgGenerator().render(cr))

    def test_append_to_verification_table_v2(self) -> None:
        """测试三节结构下追加验证项到 §10.1 末尾（M1-2）

        验证项应追加到 §10.1 表格末尾（即 §10.2 标题之前），
        不应插入到 §10.2 跨领域联动验证或 §10.3 验证结论区域。
        """
        content = self._make_content()
        editor = ChangeMarkdownEditor()

        row = "| 1 | 功能测试 | 通过 | 功能正常 | 功能正常 | ☑通过 | 张三 | 2026-06-25 |"
        new_content = editor.append_to_verification_table(content, row)

        # 验证行已追加
        assert row in new_content

        # 验证行位于 §10.1 和 §10.2 之间（即在 §10.2 标题之前）
        pos_row = new_content.find(row)
        pos_10_2 = new_content.find("### 10.2")
        pos_10_3 = new_content.find("### 10.3")
        assert pos_row < pos_10_2 < pos_10_3

    def test_update_verification_conclusion_section_10_3(self) -> None:
        """测试更新 §10.3 验证结论（M1-2 新结构）

        三节结构下，验证结论位于 §10.3，应正确更新。
        """
        content = self._make_content()
        editor = ChangeMarkdownEditor()

        new_content = editor.update_verification_conclusion(content, "全部通过")

        # 验证结论已写入 §10.3 区域
        assert "| **验证结论** | 全部通过 |" in new_content

        # 验证写入位置在 §10.3 之后、§11 之前
        pos_10_3 = new_content.find("### 10.3")
        pos_conclusion = new_content.find("| **验证结论** | 全部通过 |")
        pos_11 = new_content.find("## 11.")
        assert pos_10_3 < pos_conclusion < pos_11

    def test_update_verification_conclusion_legacy_section_10_2(self) -> None:
        """测试向后兼容：旧结构 §10.2 验证结论（M1-2）

        旧变更单（§10.2 为验证结论，无 §10.3）应仍能正确更新。
        """
        # 构造旧结构内容（§10 只有 §10.1 和 §10.2 验证结论）
        legacy_content = """## 10. 变更验证

### 10.1 验证项清单

| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|------|--------|----------|
| | | | | | | | |

### 10.2 验证结论
| 结论 | □ 全部通过,可关闭 □ 部分不通过,需返工 □ 需补充验证 |
|------|-------------------------------------------------------|

## 11. 附录
"""
        editor = ChangeMarkdownEditor()
        new_content = editor.update_verification_conclusion(legacy_content, "全部通过")

        # 验证结论已写入 §10.2 区域（旧结构）
        assert "| **验证结论** | 全部通过 |" in new_content
