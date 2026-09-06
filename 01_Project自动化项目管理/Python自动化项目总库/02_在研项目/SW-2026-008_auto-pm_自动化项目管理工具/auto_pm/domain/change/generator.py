"""PLC-HMI 概念映射：SFB 库函数（变更单生成器（从模板创建新变更单））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变更单 Markdown 文件生成器"""

from __future__ import annotations

import datetime
import logging
from typing import cast

from auto_pm.change.constants import (
    BUSINESS_NATURE_DESCRIPTIONS,
    BUSINESS_NATURES,
    DOMAIN_DESCRIPTIONS,
    DOMAINS,
    IMPACT_SCOPE_DESCRIPTIONS,
    IMPACT_SCOPES,
    URGENCY_LEVELS,
    ChangeRequest,
)
from auto_pm.utils.file_utils import write_file

log = logging.getLogger(__name__)


class ChgGenerator:
    """变更单 Markdown 文件生成器"""

    def render(self, cr: ChangeRequest) -> str:
        """渲染变更单 Markdown 内容"""
        log.info("渲染变更单: %s, domain=%s, nature=%s",
                 cr.change_number, cr.domain, cr.business_nature)
        today = datetime.date.today().isoformat()

        # 影响范围选择行
        scope_lines = self._render_scope_options(cast(list[str], cr.impact_scope))
        # 领域选择行
        domain_lines = self._render_domain_options(cr.domain)
        # 业务性质选择行
        nature_lines = self._render_nature_options(cr.business_nature)
        # 紧急程度
        urgency_lines = self._render_urgency(cr.urgency)
        # M1-1: 风险等级（PMBOK 风险评估）
        risk_level_lines = self._render_risk_level(cr.risk_level)
        # M1-1: 缓解措施
        mitigation_text = cr.mitigation if cr.mitigation else "（待填写）"

        content = f"""# 变更单

## 1. 文档基础信息

**文档标题**：变更单
**文档版本**：V2.1.0
**编制日期**：{today}
**编制人**：{cr.applicant}
**审核人**：

## 2. 版本变更记录

| 版本号 | 变更内容 | 变更人 | 变更日期 | 详细说明 |
|--------|----------|--------|----------|----------|
| V1.0.0 | 初始版本 | {cr.applicant} | {today} | 变更单创建 |

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | {cr.change_number} |
| 项目名称 | {cr.project_name} |
| 项目编号 | {cr.project_id} |

### 3.1 技术领域（必选）
{domain_lines}

### 3.2 业务性质（必选）
{nature_lines}

### 3.3 影响范围（可多选）
{scope_lines}

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | {cr.applicant} |
| 申请日期 | {cr.apply_date} |
| 预计实施日期 | {cr.planned_date} |
| 紧急程度 | {urgency_lines} |
| 变更状态 | {cr.status} |

## 4. 变更原因

**变更背景**：
{cr.background}

**变更必要性**：
{cr.necessity}

**参考依据**：
{cr.references}

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

### 6.1 项目约束影响（PMBOK五大约束）

| 约束维度 | 影响程度 | 影响描述 | 应对措施 |
|---------|:--------:|----------|----------|
| **范围(Scope)** | □无 □低 □中 □高 |  |  |
| **进度(Schedule)** | □无 □低 □中 □高 | 延迟___天 |  |
| **成本(Cost)** | □无 □低 □中 □高 | 增加___元 |  |
| **质量(Quality)** | □无 □低 □中 □高 |  |  |
| **风险(Risk)** | □无 □低 □中 □高 |  |  |

**风险等级**（PMBOK风险评估）：{risk_level_lines}

**缓解措施**（风险应对策略）：
{mitigation_text}

### 6.2 技术领域影响（跨领域变更必填！）

| 受影响领域 | 是否受影响 | 具体影响内容 | 涉及交付物 | 关联变更单号 |
|-----------|:---------:|-------------|-----------|-------------|
| □ **ELEC**  电气设计 | □是 □否 |  |  | CHG-______ |
| □ **MECH**  机械结构 | □是 □否 |  |  | CHG-______ |
| □ **PLC**   PLC程序 | □是 □否 |  |  | CHG-______ |
| □ **HMI**   HMI程序 | □是 □否 |  |  | CHG-______ |
| □ **SCPT** Python脚本 | □是 □否 |  |  | CHG-______ |
| □ **DOCU** 工程文档 | □是 □否 |  |  | CHG-______ |
| □ **SAFE** 安全功能 | □是 □否 |  |  | CHG-______ |

### 6.3 变更传播链（跨领域变更必填！）

**传播路径示例:**
```
[原始领域变更] → [领域A被影响] → [领域B被联动] → [领域C需同步]
```

**本次变更传播链:**
```
[___________] → [___________] → [___________]
     ↓               ↓               ↓
  (领域)          (领域)           (领域)
```

**关联变更单清单:**
| 关联单号 | 关联领域 | 关联原因 | 状态 |
|----------|----------|----------|:----:|
| CHG-______ |  |  | □待发起 □已发起 □已完成 |
| CHG-______ |  |  | □待发起 □已发起 □已完成 |

> **注**: 如果本变更不涉及其他领域,可填写"无跨领域影响"并跳过§6.2和§6.3

## 7. 变更实施计划

| 序号 | 任务描述 | 负责人(角色) | 开始日期 | 完成日期 | 前置依赖 | 备注 |
|------|----------|-------------|----------|----------|----------|------|
| | | | | | | |

## 8. 变更审批

### 8.1 审批流程（按影响范围分级）

| 审批环节 | 审批人 | 审批意见 | 审批日期 | 签字/电子签章 |
|----------|--------|----------|----------|---------------|
| | | | | |

### 8.2 审批结论
| 结论 | □ 通过 □ 有条件通过(附条件) □ 驳回(附原因) □ 拒绝(附原因) |
|------|----------------------------------------------------------|

## 9. 变更实施记录

| 实施日期 | 实施人 | 实施任务 | 实施内容摘要 | 实施结果 | 备注 |
|----------|--------|----------|-------------|----------|------|
| | | | | | |

## 10. 变更验证

### 10.1 验证项清单

| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|------|--------|----------|
| | | | | | | | |

### 10.2 跨领域联动验证（如有传播链）

| 传播环节 | 关联变更单 | 该环节验证 | 验证人 | 验证日期 |
|----------|-----------|:---------:|--------|----------|
| [原始]→[领域A] | CHG-xxx | □通过 □不通过 |  |  |
| [领域A]→[领域B] | CHG-yyy | □通过 □不通过 |  |  |

### 10.3 验证结论
| 结论 | □ 全部通过,可关闭 □ 部分不通过,需返工 □ 需补充验证 |
|------|-------------------------------------------------------|

## 11. 版本详细变更说明

<a name="v100"></a>
### V1.0.0 版本详细变更
1. 变更单创建
2. 初始版本，记录变更基本信息、原因、内容、影响分析

[↑ 返回版本变更记录](#L13)

## 12. 附录

### 12.1 填写指南

#### 如何选择技术领域?
- 主要改哪个专业的交付物,就选哪个领域
- 如果同时涉及多个专业,选**最主要**的那个作为主领域,其他在§6.2中标注

#### 如何判断影响范围?
- **LOCAL**: 改一个变量/一行代码/一个接线端子
- **MODULE**: 改一个FB/一条输送线/一台设备
- **SYSTEM**: 改全局变量/联锁逻辑/通讯接口
- **CROSS**: 改了电气,PLC和HMI都要跟着改
- **SAFE**: 动了急停回路/安全继电器/SIL相关

### 12.2 参考资料
| 资料名称 | 版本 | 来源 |
|----------|------|------|
| 通用变更单模板 | V2.1.0 | 00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/ |
| 变更管理流程规范 | V2.2.0 | 本仓库/04_监控和控制/01_变更管理/ |
| 项目管理知识体系指南(PMBOK) | - | PMI |

---

**文档版本**：V2.1.0
**编制日期**：{today}
**编制人**：{cr.applicant}
**审核人**：
"""
        return content

    def save(self, cr: ChangeRequest, file_path: str) -> str:
        """保存变更单到文件，返回文件路径"""
        content = self.render(cr)
        write_file(file_path, content)
        log.info("变更单已保存: %s → %s", cr.change_number, file_path)
        return file_path

    # ---- 内部方法 ----

    def _render_domain_options(self, selected: str) -> str:
        """渲染领域选择表格"""
        lines = ["| 领域 | 选择 | 说明 |", "|------|------|------|"]
        for code, name in DOMAINS.items():
            desc = DOMAIN_DESCRIPTIONS.get(code, "")
            check = "**选中**" if code == selected else "-"
            mark = "☑" if code == selected else "□"
            lines.append(f"| {mark} **{code}** {name} | {check} | {desc} |")
        return "\n".join(lines)

    def _render_nature_options(self, selected: str) -> str:
        """渲染业务性质选择表格"""
        lines = ["| 性质 | 选择 | 典型场景 |", "|------|------|----------|"]
        for code, name in BUSINESS_NATURES.items():
            desc = BUSINESS_NATURE_DESCRIPTIONS.get(code, "")
            check = "**选中**" if code == selected else "-"
            mark = "☑" if code == selected else "□"
            lines.append(f"| {mark} **{code}** {name} | {check} | {desc} |")
        return "\n".join(lines)

    def _render_scope_options(self, selected_scopes: list[str]) -> str:
        """渲染影响范围选择表格"""
        lines = ["| 范围 | 选择 | 审批要求 |", "|------|------|----------|"]
        for code, name in IMPACT_SCOPES.items():
            desc = IMPACT_SCOPE_DESCRIPTIONS.get(code, "")
            is_selected = code in selected_scopes
            check = "**选中**" if is_selected else "-"
            mark = "☑" if is_selected else "□"
            lines.append(f"| {mark} **{code}** {name} | {check} | {desc} |")
        return "\n".join(lines)

    def _render_urgency(self, urgency: str) -> str:
        """渲染紧急程度"""
        parts = []
        for code, label in URGENCY_LEVELS.items():
            mark = "☑" if code == urgency else "□"
            parts.append(f"{mark}{label}")
        return " ".join(parts)

    def _render_risk_level(self, risk_level: str) -> str:
        """渲染风险等级（M1-1: PMBOK 风险评估）

        Args:
            risk_level: none/low/medium/high，空字符串表示未评估

        Returns:
            ☑/□ 格式的风险等级选项字符串
        """
        levels = [("none", "无"), ("low", "低"), ("medium", "中"), ("high", "高")]
        parts = []
        for code, label in levels:
            mark = "☑" if code == risk_level else "□"
            parts.append(f"{mark}{label}")
        return " ".join(parts)
