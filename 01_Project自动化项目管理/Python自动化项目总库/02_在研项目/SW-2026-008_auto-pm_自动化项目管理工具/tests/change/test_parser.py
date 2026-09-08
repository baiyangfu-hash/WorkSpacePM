"""ChgParser 单元测试"""

from __future__ import annotations

import os

import pytest
from auto_pm.change.parser import ChgParser
from auto_pm.utils.file_utils import write_file


class TestChgParser:
    """变更单解析器测试"""

    def test_parse_sample(self, sample_chg_content: str, tmp_dir: str) -> None:
        """测试解析样例变更单"""
        # 模拟 CHG-DOCU 目录结构
        chg_dir = os.path.join(tmp_dir, "CHG-DOCU")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-001.md")
        write_file(file_path, sample_chg_content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        assert cr.change_number == "CHG-PLC-2026-001"
        assert cr.project_id == "TEST-2026-001"
        assert cr.project_name == "TEST-2026-001 测试项目"
        assert cr.domain == "DOCU"  # 从路径提取
        assert cr.business_nature == "DEF"
        assert "LOCAL" in cr.impact_scope
        assert "MODULE" in cr.impact_scope
        assert cr.applicant == "张三"
        assert cr.apply_date == "2026-01-15"
        assert cr.planned_date == "2026-01-20"
        assert cr.urgency == "normal"
        assert cr.background != "待补充"
        assert cr.status == "approved"  # 有审批且通过

    def test_parse_real_file(self, chg_file: str) -> None:
        """测试解析真实变更单 CHG-DOCU-2026-001"""
        if not os.path.isfile(chg_file):
            pytest.skip("真实变更单文件不存在")

        parser = ChgParser()
        cr = parser.parse(chg_file)

        assert cr.change_number == "CHG-DOCU-2026-001"
        assert cr.domain == "DOCU"
        assert cr.business_nature == "DEF"
        assert "MODULE" in cr.impact_scope
        # 状态可能是 approved/completed/closed（取决于实施记录和验证）
        assert cr.status in ("approved", "implementing", "completed", "closed")

    def test_status_inference_draft(self, tmp_dir: str) -> None:
        """测试状态推断：无审批 → draft"""
        content = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-099 |

## 4. 变更原因

**变更背景**：
测试草稿
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-099.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        assert cr.status == "draft"

    def test_status_inference_approved(self, tmp_dir: str) -> None:
        """测试状态推断：审批通过 → approved"""
        content = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-100 |

## 8. 变更审批

### 8.2 审批结论
| 结论 | ☑ 通过 |
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-100.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        assert cr.status == "approved"

    def test_status_inference_rejected(self, tmp_dir: str) -> None:
        """测试状态推断：审批驳回 → rejected"""
        content = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-101 |

## 8. 变更审批

### 8.2 审批结论
| 结论 | □ 通过 ☑ 驳回(附原因) |
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-101.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        assert cr.status == "rejected"

    def test_to_summary(self, sample_chg_content: str, tmp_dir: str) -> None:
        """测试转换为 ChangeSummary"""
        chg_dir = os.path.join(tmp_dir, "CHG-DOCU")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-001.md")
        write_file(file_path, sample_chg_content)

        parser = ChgParser()
        cr = parser.parse(file_path)
        summary = parser.to_summary(cr)

        assert summary.change_number == cr.change_number
        assert summary.domain == cr.domain
        assert summary.status == cr.status
        assert len(summary.title) <= 53  # 50 + "..."

    def test_domain_extraction_from_path(self) -> None:
        """测试从路径提取领域"""
        parser = ChgParser()
        assert parser._extract_domain_from_path("/path/CHG-DOCU/CHG-DOCU-2026-001.md") == "DOCU"
        assert parser._extract_domain_from_path("/path/CHG-PLC/CHG-PLC-2026-001.md") == "PLC"

    def test_change_number_extraction(self) -> None:
        """测试变更编号提取"""
        parser = ChgParser()
        assert parser._extract_change_number("/path/CHG-DOCU-2026-001.md") == "CHG-DOCU-2026-001"
        assert parser._extract_change_number("/path/other.md") == ""

    def test_urgency_parsing(self, tmp_dir: str) -> None:
        """测试紧急程度解析"""
        content = """# 变更单

## 3. 变更基本信息

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-01-15 |
| 预计实施日期 | 2026-01-20 |
| 紧急程度 | □一般 ☑紧急 □非常紧急 |

## 8. 变更审批

### 8.2 审批结论
| 结论 | ☑ 通过 |
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-200.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        assert cr.urgency == "urgent"

    def test_parse_risk_level_mitigation(self, tmp_dir: str) -> None:
        """测试解析 §6.1 风险等级和缓解措施（M1-1）

        验证 PMBOK 风险评估字段能被正确解析。
        """
        content = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-300 |
| 项目名称 | 测试项目 |
| 项目编号 | TEST-2026-001 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-01-15 |

## 4. 变更原因

**变更背景**：
测试风险等级解析

**变更必要性**：
验证 M1-1 字段

## 6. 变更影响分析

### 6.1 项目约束影响（PMBOK五大约束）

| 约束维度 | 影响程度 | 影响描述 | 应对措施 |
|---------|:--------:|----------|----------|
| **范围(Scope)** | □无 □低 ☑中 □高 | 影响多个模块 | 分阶段实施 |
| **进度(Schedule)** | □无 □低 □中 □高 |  |  |
| **成本(Cost)** | □无 □低 □中 □高 |  |  |
| **质量(Quality)** | □无 □低 □中 □高 |  |  |
| **风险(Risk)** | □无 □低 ☑中 □高 |  |  |

**风险等级**（PMBOK风险评估）：□无 □低 ☑中 □高

**缓解措施**（风险应对策略）：
增加单元测试覆盖率，进行代码评审，分阶段上线

### 6.2 技术领域影响（跨领域变更必填！）

| 受影响领域 | 是否受影响 | 具体影响内容 | 涉及交付物 | 关联变更单号 |
|-----------|:---------:|-------------|-----------|-------------|
| □ **PLC**   PLC程序 | □是 □否 |  |  | CHG-______ |

## 8. 变更审批

### 8.2 审批结论
| 结论 | ☑ 通过 |
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-300.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        # M1-1: 验证风险等级解析
        assert cr.risk_level == "medium"
        # M1-1: 验证缓解措施解析
        assert cr.mitigation == "增加单元测试覆盖率，进行代码评审，分阶段上线"
        # M1-1: 验证 §6.1 约束影响仍然正常解析
        assert "范围" in cr.constraint_impacts
        assert cr.constraint_impacts["范围"] == "中"

    def test_parse_risk_level_none(self, tmp_dir: str) -> None:
        """测试解析 §6.1 风险等级为空的情况（M1-1）

        未设置风险等级时返回空字符串。
        """
        content = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-301 |

## 4. 变更原因

**变更背景**：
测试无风险等级

## 6. 变更影响分析

### 6.1 项目约束影响（PMBOK五大约束）

| 约束维度 | 影响程度 | 影响描述 | 应对措施 |
|---------|:--------:|----------|----------|
| **范围(Scope)** | □无 □低 □中 □高 |  |  |

**风险等级**（PMBOK风险评估）：□无 □低 □中 □高

**缓解措施**（风险应对策略）：
（待填写）

## 8. 变更审批

### 8.2 审批结论
| 结论 | ☑ 通过 |
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-301.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        # M1-1: 未选中任何风险等级 → 空字符串
        assert cr.risk_level == ""
        # M1-1: 缓解措施为模板占位符 → 空字符串
        assert cr.mitigation == ""

    def test_to_impact_analysis(self, tmp_dir: str) -> None:
        """M2-4 T59: to_impact_analysis 将 §6 字段转换为 ImpactAnalysis 持久化模型"""
        content = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-001 |
| 项目名称 | 测试项目 |
| 项目编号 | SW-2026-001 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-06-25 |
| 预计实施日期 | 2026-07-01 |
| 紧急程度 | ☑一般 |
| 变更状态 | draft |

## 4. 变更原因

**变更背景**：
测试影响分析持久化

## 6. 变更影响分析

### 6.1 项目约束影响（PMBOK五大约束）

| 约束维度 | 影响程度 | 影响描述 | 应对措施 |
|---------|:--------:|----------|----------|
| **范围(Scope)** | □无 □低 ☑中 □高 | 新增模块 | 分阶段实施 |
| **进度(Schedule)** | □无 ☑低 □中 □高 | 延迟3天 | 加班追赶 |

**风险等级**（PMBOK风险评估）：□无 □低 ☑中 □高

**缓解措施**（风险应对策略）：
增加单元测试覆盖率，进行代码评审

### 6.2 技术领域影响

| 领域 | 是否受影响 | 影响内容 | 关联变更单 |
|------|:--------:|----------|-----------|
| **PLC** | ☑是 | 修改FB_TON定时器 | CHG-PLC-2026-002 |
| **HMI** | ☑是 | 更新变量映射 | |

### 6.3 变更传播链

```
SCPT -> PLC -> HMI
```

| 关联变更单 | 传播方向 |
|-----------|---------|
| CHG-PLC-2026-002 | SCPT → PLC |
| CHG-HMI-2026-001 | PLC → HMI |

## 8. 变更审批

### 8.2 审批结论
| 结论 | ☑ 通过 |
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-001.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        # 验证解析结果（前提条件）
        assert cr.change_number == "CHG-PLC-2026-001"
        assert cr.risk_level == "medium"
        assert cr.mitigation == "增加单元测试覆盖率，进行代码评审"
        assert "范围" in cr.constraint_impacts
        assert cr.constraint_impacts["范围"] == "中"
        assert "PLC" in cr.domain_impacts
        assert cr.domain_impacts["PLC"]["affected"] is True
        assert cr.propagation_chain == "SCPT -> PLC -> HMI"
        assert "CHG-PLC-2026-002" in cr.related_changes

        # M2-4 T59: 调用 to_impact_analysis 转换为持久化模型
        analysis = parser.to_impact_analysis(cr)

        # 验证字段映射
        assert analysis.change_number == "CHG-PLC-2026-001"
        assert analysis.risk_level == "medium"
        assert analysis.mitigation == "增加单元测试覆盖率，进行代码评审"
        assert analysis.constraint_impacts == {"范围": "中", "进度": "低"}
        assert analysis.domain_impacts["PLC"]["affected"] is True
        assert analysis.domain_impacts["PLC"]["related_chg"] == "CHG-PLC-2026-002"
        assert analysis.domain_impacts["HMI"]["affected"] is True
        assert analysis.propagation_chain == "SCPT -> PLC -> HMI"
        assert "CHG-PLC-2026-002" in analysis.related_changes
        assert "CHG-HMI-2026-001" in analysis.related_changes
        # updated_at 应自动填充
        assert analysis.updated_at != ""

    def test_to_impact_analysis_empty_fields(self, tmp_dir: str) -> None:
        """M2-4 T59: to_impact_analysis 处理空影响分析字段"""
        content = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-002 |
| 项目名称 | 测试项目 |
| 项目编号 | SW-2026-001 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-06-25 |
| 预计实施日期 | 2026-07-01 |
| 紧急程度 | ☑一般 |
| 变更状态 | draft |

## 4. 变更原因

**变更背景**：
测试空影响分析

## 6. 变更影响分析

### 6.1 项目约束影响（PMBOK五大约束）

| 约束维度 | 影响程度 | 影响描述 | 应对措施 |
|---------|:--------:|----------|----------|
| **范围(Scope)** | □无 □低 □中 □高 |  |  |

**风险等级**（PMBOK风险评估）：□无 □低 □中 □高

**缓解措施**（风险应对策略）：
（待填写）

## 8. 变更审批

### 8.2 审批结论
| 结论 | ☑ 通过 |
"""
        chg_dir = os.path.join(tmp_dir, "CHG-PLC")
        os.makedirs(chg_dir, exist_ok=True)
        file_path = os.path.join(chg_dir, "CHG-PLC-2026-002.md")
        write_file(file_path, content)

        parser = ChgParser()
        cr = parser.parse(file_path)

        # 验证空字段
        assert cr.risk_level == ""
        assert cr.mitigation == ""
        assert cr.constraint_impacts == {}

        # M2-4 T59: 转换为持久化模型
        analysis = parser.to_impact_analysis(cr)

        assert analysis.change_number == "CHG-PLC-2026-002"
        assert analysis.risk_level == ""
        assert analysis.mitigation == ""
        assert analysis.constraint_impacts == {}
        assert analysis.domain_impacts == {}
        assert analysis.propagation_chain == ""
        assert analysis.related_changes == []
        assert analysis.updated_at != ""
