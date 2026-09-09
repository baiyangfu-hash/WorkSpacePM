"""ChgGenerator 单元测试"""

from __future__ import annotations

import os
import re

from auto_pm.change.constants import ChangeRequest
from auto_pm.change.document_contract import CLOSURE_REQUIRED_SECTIONS
from auto_pm.change.generator import ChgGenerator


class TestChgGenerator:
    """变更单生成器测试"""

    def test_render_basic(self) -> None:
        """测试基本渲染"""
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-001",
            project_id="TEST-2026-001",
            project_name="测试项目",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL", "MODULE"],
            applicant="张三",
            apply_date="2026-01-15",
            planned_date="2026-01-20",
            urgency="normal",
            background="测试变更背景",
            necessity="测试变更必要性",
            references="测试参考依据",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        assert "CHG-PLC-2026-001" in content
        assert "TEST-2026-001" in content
        assert "张三" in content
        assert "测试变更背景" in content
        assert "☑ **PLC**" in content
        assert "☑ **DEF**" in content
        assert "☑ **LOCAL**" in content
        assert "☑ **MODULE**" in content

    def test_render_satisfies_shared_document_contract(self) -> None:
        """生成器输出必须覆盖关闭门禁消费的全部章节契约。"""
        content = ChgGenerator().render(
            ChangeRequest(
                change_number="CHG-PLC-2026-001",
                project_id="TEST-2026-001",
                project_name="测试项目",
                domain="PLC",
                business_nature="DEF",
                impact_scope=["LOCAL"],
                applicant="张三",
                apply_date="2026-01-15",
                planned_date="2026-01-20",
                urgency="normal",
                background="测试变更背景",
                necessity="测试变更必要性",
                references="测试参考依据",
            )
        )

        assert all(
            re.search(section.heading_pattern(), content, re.MULTILINE)
            for section in CLOSURE_REQUIRED_SECTIONS
        )

    def test_render_local_change_has_no_cross_domain_placeholders(self) -> None:
        """LOCAL 单域变更使用明确的不适用语义，而不是关闭占位符。"""
        content = ChgGenerator().render(
            ChangeRequest(
                change_number="CHG-PLC-2026-011",
                project_id="TEST-2026-001",
                project_name="测试项目",
                domain="PLC",
                business_nature="DEF",
                impact_scope=["LOCAL"],
                applicant="张三",
                apply_date="2026-01-15",
                planned_date="2026-01-20",
                urgency="normal",
                background="测试变更背景",
                necessity="测试变更必要性",
                references="测试参考依据",
            )
        )

        assert "无跨领域影响（LOCAL 单域变更）" in content
        assert "CHG-______" not in content
        assert "[___________]" not in content

    def test_render_urgency_critical(self) -> None:
        """测试紧急程度渲染"""
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-002",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="EMRG",
            impact_scope=["SAFE"],
            applicant="李四",
            urgency="critical",
            background="紧急变更",
            necessity="必须立即处理",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        assert "☑非常紧急" in content
        assert "☑ **EMRG**" in content
        assert "☑ **SAFE**" in content

    def test_save(self, tmp_dir: str) -> None:
        """测试保存文件"""
        cr = ChangeRequest(
            change_number="CHG-DOCU-2026-001",
            project_id="TEST-2026-001",
            domain="DOCU",
            business_nature="OPT",
            impact_scope=["LOCAL"],
            applicant="王五",
            urgency="normal",
            background="优化文档",
            necessity="提升可读性",
        )

        gen = ChgGenerator()
        file_path = os.path.join(tmp_dir, "CHG-DOCU", "CHG-DOCU-2026-001.md")
        result = gen.save(cr, file_path)

        assert os.path.isfile(result)
        with open(result, encoding="utf-8") as f:
            content = f.read()
        assert "CHG-DOCU-2026-001" in content

    def test_render_contains_all_sections(self) -> None:
        """测试渲染结果包含所有章节"""
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-003",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            urgency="normal",
            background="测试",
            necessity="测试",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        # 检查所有章节标题
        assert "## 1. 文档基础信息" in content
        assert "## 2. 版本变更记录" in content
        assert "## 3. 变更基本信息" in content
        assert "### 3.0 编号与项目" in content
        assert "### 3.1 技术领域" in content
        assert "### 3.2 业务性质" in content
        assert "### 3.3 影响范围" in content
        assert "### 3.4 申请信息" in content
        assert "## 4. 变更原因" in content
        assert "## 5. 变更内容" in content
        assert "## 8. 变更审批" in content
        assert "## 9. 变更实施记录" in content
        assert "## 10. 变更验证" in content

    def test_section_6_1_fields(self) -> None:
        """测试 §6.1 风险等级和缓解措施字段渲染（M1-1）

        验证 PMBOK 风险评估字段在 §6.1 表格下方正确渲染。
        """
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-010",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            urgency="normal",
            background="测试",
            necessity="测试",
            risk_level="medium",
            mitigation="增加单元测试覆盖率，进行代码评审",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        # 风险等级字段存在且选中 medium
        assert "**风险等级**" in content
        assert "☑中" in content
        assert "□无" in content
        assert "□低" in content
        assert "□高" in content

        # 缓解措施字段存在且内容正确
        assert "**缓解措施**" in content
        assert "增加单元测试覆盖率，进行代码评审" in content

    def test_section_6_1_fields_default(self) -> None:
        """测试 §6.1 风险等级和缓解措施默认值（M1-1）

        未设置 risk_level/mitigation 时渲染为未选中/待填写。
        """
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-011",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            urgency="normal",
            background="测试",
            necessity="测试",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        # 风险等级全部未选中
        assert "**风险等级**" in content
        assert "□无" in content
        assert "□低" in content
        assert "□中" in content
        assert "□高" in content
        assert "☑" not in content.split("**风险等级**")[1].split("\n")[0]

        # 缓解措施为待填写
        assert "**缓解措施**" in content
        assert "（待填写）" in content

    def test_section_10_three_subsections(self) -> None:
        """测试 §10 三节结构渲染（M1-2）

        验证生成器输出对齐 040 模板 V2.1.0：
        - §10.1 验证项清单
        - §10.2 跨领域联动验证（如有传播链）
        - §10.3 验证结论
        """
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-020",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            urgency="normal",
            background="测试",
            necessity="测试",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        # §10 主标题存在
        assert "## 10. 变更验证" in content

        # §10.1 验证项清单
        assert "### 10.1 验证项清单" in content
        assert "| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |" in content

        # §10.2 跨领域联动验证（M1-2 新增）
        assert "### 10.2 跨领域联动验证" in content
        assert "| 传播环节 | 关联变更单 | 该环节验证 | 验证人 | 验证日期 |" in content

        # §10.3 验证结论（原 §10.2 改名）
        assert "### 10.3 验证结论" in content
        assert "□ 全部通过,可关闭" in content
        assert "□ 部分不通过,需返工" in content
        assert "□ 需补充验证" in content

        # 验证章节顺序：§10.1 在 §10.2 之前，§10.2 在 §10.3 之前
        pos_10_1 = content.find("### 10.1")
        pos_10_2 = content.find("### 10.2")
        pos_10_3 = content.find("### 10.3")
        assert pos_10_1 < pos_10_2 < pos_10_3

    def test_section_11_12_structure(self) -> None:
        """测试 §11 版本详细变更说明 + §12 附录结构（M1-3）

        验证生成器输出对齐 040 模板 V2.1.0：
        - §11 版本详细变更说明（含 V1.0.0 详细变更）
        - §12 附录（含填写指南和参考资料）
        """
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-021",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            urgency="normal",
            background="测试",
            necessity="测试",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        # §11 版本详细变更说明（M1-3: 原 §11 附录改为版本详细变更说明）
        assert "## 11. 版本详细变更说明" in content
        assert "### V1.0.0 版本详细变更" in content
        assert "变更单创建" in content

        # §12 附录（M1-3: 新增 §12）
        assert "## 12. 附录" in content
        assert "### 12.1 填写指南" in content
        assert "### 12.2 参考资料" in content

        # 验证章节顺序：§11 在 §12 之前
        pos_11 = content.find("## 11.")
        pos_12 = content.find("## 12.")
        assert pos_11 < pos_12

    def test_document_version_aligned_with_template(self) -> None:
        """测试文档版本号对齐 040 模板 V2.1.0（M1-4）

        §1 文档基础信息和文档末尾的"文档版本"应为 V2.1.0，
        表示变更单基于 V2.1.0 模板生成。
        §2 版本变更记录中的 V1.0.0 是变更单本身的版本，不变。
        """
        cr = ChangeRequest(
            change_number="CHG-PLC-2026-022",
            project_id="TEST-2026-001",
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            urgency="normal",
            background="测试",
            necessity="测试",
        )

        gen = ChgGenerator()
        content = gen.render(cr)

        # §1 文档基础信息中的文档版本为 V2.1.0
        assert "**文档版本**：V2.1.0" in content

        # 文档末尾的文档版本为 V2.1.0
        # 统计 V2.1.0 出现次数（§1 + 文档末尾 = 2 次）
        assert content.count("**文档版本**：V2.1.0") == 2

        # §2 版本变更记录中仍有 V1.0.0（变更单本身的初始版本）
        assert "| V1.0.0 | 初始版本 |" in content
