"""PLC-HMI 概念映射：SFB 库函数（变更单解析器（Markdown 解析为结构化数据））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变更单 Markdown 解析器"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, cast

from auto_pm.change.constants import (
    ALL_STATUSES,
    BUSINESS_NATURES,
    DOMAINS,
    IMPACT_SCOPES,
    REQUIRED_SUBSECTIONS,
    ChangeRequest,
    ChangeSummary,
)
from auto_pm.models import ImpactAnalysis
from auto_pm.models.enums import BusinessNature, ChangeStatus, Domain, ImpactScope
from auto_pm.utils.file_utils import get_mtime, read_file

log = logging.getLogger(__name__)


class ChgParser:
    """变更单 Markdown 解析器"""

    def parse(self, file_path: str) -> ChangeRequest:
        """解析变更单文件，返回 ChangeRequest"""
        content = read_file(file_path)
        if not content:
            log.warning("变更单文件为空或读取失败: %s", file_path)
            return ChangeRequest()

        cr = ChangeRequest(
            file_path=file_path,
            file_mtime=get_mtime(file_path),
        )

        # 解析开头的 YAML frontmatter（如 id: ..., project_id: ...）
        frontmatter = self._parse_frontmatter(content)
        if frontmatter.get("project_id"):
            cr.project_id = frontmatter["project_id"]
        if frontmatter.get("id"):
            cr.change_number = frontmatter["id"]

        # 从文件路径提取 domain
        cr.domain = cast(Domain, self._extract_domain_from_path(file_path))
        # 从文件名提取 change_number（若文件名符合规范，优先级高于 frontmatter）
        extracted_num = self._extract_change_number(file_path)
        if extracted_num:
            cr.change_number = extracted_num

        # 按章节拆分
        sections = self._split_sections(content)
        log.debug("变更单章节拆分: %s → %s", os.path.basename(file_path), list(sections.keys()))

        # 解析 §3 变更基本信息
        if "3" in sections:
            self._parse_change_info(sections["3"], cr)
        else:
            log.warning("变更单缺少§3变更基本信息章节: %s", cr.change_number)

        # 解析 §4 变更原因
        if "4" in sections:
            self._parse_change_reason(sections["4"], cr)

        # 解析 §6 变更影响分析
        if "6" in sections:
            self._parse_impact_analysis(sections["6"], cr)

        # 状态确定：优先从 §3.4 "变更状态" 字段读取（流转时写入），回退到 §8 推断
        explicit_status = self._read_explicit_status(sections.get("3", ""))
        if explicit_status:
            cr.status = cast(ChangeStatus, explicit_status)
            log.debug("状态来源: §3.4 变更状态字段 → %s", explicit_status)
        else:
            # 回退：从 §8 审批章节推断
            if "8" in sections:
                cr.status = cast(ChangeStatus, self._infer_status_from_approval(sections["8"]))
            elif "7" in sections:
                cr.status = cast(ChangeStatus, self._infer_status_from_approval(sections["7"]))

            # 从 §9/§10 进一步推断
            if "9" in sections and cr.status in ("approved",):
                if self._has_implementation_records(sections["9"]):
                    cr.status = "implementing"
            if "10" in sections and cr.status == "implementing":
                if self._all_verification_passed(sections["10"]):
                    cr.status = "completed"
            log.debug("状态来源: §8推断 → %s", cr.status)

        # 如果 change_number 未从文件提取到，尝试从内容提取
        if not cr.change_number:
            cr.change_number = self._extract_change_number_from_content(content)
        if not cr.change_number and frontmatter.get("id"):
            cr.change_number = frontmatter["id"]

        # 如果 project_id 未从 §3 提取到，从正文提取或回退到 frontmatter
        if not cr.project_id:
            cr.project_id = self._extract_project_id_from_content(content)
        if not cr.project_id and frontmatter.get("project_id"):
            cr.project_id = frontmatter["project_id"]

        # 填充章节内容标志（门禁校验用）
        self._fill_section_flags(cr, sections)

        # M3.5-6: 保存原始章节文本供 CLI show 命令渲染 §6/§8/§9/§10
        cr.sections = sections

        # 规范结构校验：检查必填字段和合法枚举值
        violations = self._validate_spec_compliance(cr, sections)
        if violations:
            for v in violations:
                proj_prefix = f"{cr.project_id} | " if cr.project_id else ""
                log.warning("规范校验违规 [%s%s]: %s", proj_prefix, cr.change_number, v)

        log.info("解析变更单完成: %s, domain=%s, nature=%s, status=%s",
                 cr.change_number, cr.domain, cr.business_nature, cr.status)
        return cr

    def to_summary(self, cr: ChangeRequest) -> ChangeSummary:
        """将 ChangeRequest 转换为轻量级 ChangeSummary"""
        title = cr.background[:50] + "..." if len(cr.background) > 50 else cr.background
        return ChangeSummary(
            change_number=cr.change_number,
            project_id=cr.project_id,
            domain=cr.domain,
            business_nature=cr.business_nature,
            impact_scope=cr.impact_scope,
            status=cr.status,
            applicant=cr.applicant,
            apply_date=cr.apply_date,
            title=title,
            urgency=cr.urgency,
        )

    def to_impact_analysis(self, cr: ChangeRequest) -> ImpactAnalysis:
        """将 ChangeRequest 的 §6 影响分析字段转换为 ImpactAnalysis 持久化模型（M2-4 T58）

        提取 ChangeRequest 中已解析的 §6.1/§6.2/§6.3 字段，构造 ImpactAnalysis 模型。
        供 ChangeService.create_change_request / update_change_request 调用以持久化影响分析。

        Args:
            cr: 已解析的 ChangeRequest

        Returns:
            ImpactAnalysis 持久化模型（updated_at 自动填充当前时间）
        """
        from datetime import datetime

        return ImpactAnalysis(
            project_id=cr.project_id,
            change_number=cr.change_number,
            risk_level=cr.risk_level,
            mitigation=cr.mitigation,
            constraint_impacts=cr.constraint_impacts,
            domain_impacts=cr.domain_impacts,
            propagation_chain=cr.propagation_chain,
            related_changes=cr.related_changes,
            updated_at=datetime.now().isoformat(),
        )

    # ---- 内部方法 ----

    def _split_sections(self, content: str) -> dict[str, str]:
        """按 ## N. 标题 拆分章节"""
        sections: dict[str, str] = {}
        pattern = re.compile(r"^##\s+(\d+)\s*[.、：:]", re.MULTILINE)
        matches = list(pattern.finditer(content))

        for i, match in enumerate(matches):
            section_key = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            sections[section_key] = content[start:end]

        return sections

    def _parse_table(self, text: str) -> dict[str, str]:
        """解析 Markdown 表格为 {字段名: 值} 字典"""
        result: dict[str, str] = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 2:
                key = re.sub(r"\*\*", "", cells[0]).strip()
                value = re.sub(r"\*\*", "", cells[1]).strip()
                if key:
                    result[key] = value
        return result

    def _parse_change_info(self, text: str, cr: ChangeRequest) -> None:
        """解析 §3 变更基本信息（多级子表格式）"""
        # §3.0 编号与项目
        s30 = self._find_subsection(text, "3.0")
        if s30:
            table = self._parse_table(s30)
            if table.get("变更编号"):
                cr.change_number = table["变更编号"].strip().strip("`")
            if table.get("项目名称"):
                cr.project_name = table["项目名称"].strip().strip("`")
            raw_pid = table.get("项目编号")
            if raw_pid and raw_pid.strip().strip("`"):
                cr.project_id = raw_pid.strip().strip("`")

        # §3.1 技术领域
        s31 = self._find_subsection(text, "3.1")
        if s31:
            cr.domain = cast(Domain, self._extract_selected_option(s31) or cr.domain)

        # §3.2 业务性质
        s32 = self._find_subsection(text, "3.2")
        if s32:
            cr.business_nature = cast(BusinessNature, self._extract_selected_option(s32) or cr.business_nature)

        # §3.3 影响范围
        s33 = self._find_subsection(text, "3.3")
        if s33:
            cr.impact_scope = cast(list[ImpactScope], self._extract_selected_options(s33))

        # §3.4 申请信息
        s34 = self._find_subsection(text, "3.4")
        if s34:
            table = self._parse_table(s34)
            cr.applicant = table.get("变更申请人", cr.applicant)
            cr.apply_date = table.get("申请日期", cr.apply_date)
            cr.planned_date = table.get("预计实施日期", cr.planned_date)
            # 紧急程度 - 检查 ☑ 标记的位置
            urgency_raw = table.get("紧急程度", "")
            if "☑非常紧急" in urgency_raw or "☑ 非常紧急" in urgency_raw:
                cr.urgency = "critical"
            elif "☑紧急" in urgency_raw or "☑ 紧急" in urgency_raw:
                cr.urgency = "urgent"
            elif "☑一般" in urgency_raw or "☑ 一般" in urgency_raw:
                cr.urgency = "normal"
            elif "非常紧急" in urgency_raw and "☑" in urgency_raw.split("非常紧急")[0][-5:]:
                cr.urgency = "critical"
            elif "紧急" in urgency_raw and "☑" in urgency_raw.split("紧急")[0][-5:]:
                cr.urgency = "urgent"
            else:
                cr.urgency = "normal"

    def _parse_change_reason(self, text: str, cr: ChangeRequest) -> None:
        """解析 §4 变更原因（文本段落格式）"""
        cr.background = self._extract_text_block(text, "变更背景")
        cr.necessity = self._extract_text_block(text, "变更必要性")
        cr.references = self._extract_text_block(text, "参考依据")

    def _find_subsection(self, text: str, subsection_num: str) -> str | None:
        """查找子章节（如 ### 3.0 编号与项目）"""
        pattern = re.compile(
            rf"###\s*{re.escape(subsection_num)}\s*[.、：:]*(.*?)(?=\n###|\n##|\Z)",
            re.DOTALL,
        )
        match = pattern.search(text)
        if match:
            return match.group(0)
        return None

    def _extract_selected_option(self, text: str) -> str:
        """从选择表格中提取 ☑ 选中的选项代码

        例: ☑ **DOCU** 工程文档 → DOCU
        """
        for line in text.split("\n"):
            if "☑" in line:
                # 提取 **CODE** 格式
                match = re.search(r"☑\s*\*\*(\w+)\*\*", line)
                if match:
                    return match.group(1)
        return ""

    def _extract_selected_options(self, text: str) -> list[str]:
        """从多选表格中提取所有 ☑ 选中的选项代码"""
        options: list[str] = []
        for line in text.split("\n"):
            if "☑" in line:
                match = re.search(r"☑\s*\*\*(\w+)\*\*", line)
                if match:
                    options.append(match.group(1))
        return options

    def _extract_text_block(self, text: str, label: str) -> str:
        """提取文本块（如 **变更背景**：后面的内容）"""
        pattern = re.compile(
            rf"\*\*{re.escape(label)}\*\*[：:]\s*(.*?)(?=\n\*\*|\n##|\n###|\Z)",
            re.DOTALL,
        )
        match = pattern.search(text)
        if match:
            content = match.group(1).strip()
            # 清理列表编号
            content = re.sub(r"^\d+\.\s*", "- ", content, flags=re.MULTILINE)
            return content
        return "待补充"

    def _infer_status_from_approval(self, text: str) -> str:
        """从审批章节推断状态

        推断优先级（PM-042 V2.3.0 §5.2 状态机）：
        1. ☑ 驳回/拒绝 → rejected
        2. ☑ 有条件通过 → conditionally_approved
        3. ☑ 通过 → approved
        4. 有审批记录 → under_review
        5. 有审批章节无记录 → submitted
        6. 无审批信息 → draft

        注意: archived 状态无法从审批章节推断（归档是验收后操作），
        需依赖 §3.4 变更状态字段显式读取。
        """
        # 检查审批结论中的 ☑ 标记（按优先级：驳回 > 有条件通过 > 通过）
        if "☑ 驳回" in text or "☑驳回" in text:
            log.debug("状态推断: 审批结论☑驳回 → rejected")
            return "rejected"
        if "☑ 拒绝" in text or "☑拒绝" in text:
            log.debug("状态推断: 审批结论☑拒绝 → rejected")
            return "rejected"
        if "☑ 有条件通过" in text or "☑有条件通过" in text:
            log.debug("状态推断: 审批结论☑有条件通过 → conditionally_approved")
            return "conditionally_approved"
        if "☑ 通过" in text or "☑通过" in text:
            log.debug("状态推断: 审批结论☑通过 → approved")
            return "approved"
        # 检查审批流程中是否有已审批记录（有审批人+审批意见+日期）
        approval_rows = 0
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", line):
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 4 and cells[0] not in ("审批环节", "结论"):
                    if cells[2] and cells[3]:  # 有审批意见和日期
                        approval_rows += 1
        if approval_rows > 0:
            # 有审批记录但无明确结论 → 检查是否包含"同意"
            if "同意" in text:
                log.debug("状态推断: 有审批记录+同意 → approved")
                return "approved"
            log.debug("状态推断: 有审批记录无结论 → under_review")
            return "under_review"
        # 有审批章节但无记录
        if "审批" in text:
            log.debug("状态推断: 有审批章节无记录 → submitted")
            return "submitted"
        log.debug("状态推断: 无审批信息 → draft")
        return "draft"

    def _has_implementation_records(self, text: str) -> bool:
        """检查 §9 是否有实施记录"""
        # 查找表格中的数据行（排除表头和分隔行）
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", line):
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 2 and cells[0] not in ("实施日期", "序号"):
                    return True
        return False

    def _all_verification_passed(self, text: str) -> bool:
        """检查 §10 验证是否全部通过"""
        # 查找验证结论
        if "全部通过" in text:
            return True
        # 检查验证项表格中是否所有状态都是"通过"
        pass_count = 0
        total_count = 0
        for line in text.split("\n"):
            if "☑通过" in line or "✓通过" in line or "通过" in line:
                pass_count += 1
                total_count += 1
            elif line.startswith("|") and "状态" not in line and "验证项" not in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 6:
                    total_count += 1
        return total_count > 0 and pass_count == total_count

    def _extract_domain_from_path(self, file_path: str) -> str:
        """从文件路径提取领域

        例: .../CHG-DOCU/CHG-DOCU-2026-001.md → DOCU
        """
        parts = file_path.replace("\\", "/").split("/")
        for part in parts:
            if part.startswith("CHG-") and part != os.path.basename(file_path).replace(".md", ""):
                # 目录名如 CHG-DOCU
                domain = part.replace("CHG-", "")
                if domain:
                    return domain
        return ""

    def _extract_change_number(self, file_path: str) -> str:
        """从文件名提取变更编号

        例: CHG-DOCU-2026-001.md → CHG-DOCU-2026-001
        """
        basename = os.path.splitext(os.path.basename(file_path))[0]
        if re.match(r"CHG-[A-Z]+-\d{4}-\d{3}", basename):
            return basename
        return ""

    def _extract_change_number_from_content(self, content: str) -> str:
        """从内容中提取变更编号"""
        match = re.search(r"CHG-[A-Z]+-\d{4}-\d{3}", content)
        return match.group(0) if match else ""

    def _parse_frontmatter(self, content: str) -> dict[str, str]:
        """解析开头的 YAML frontmatter (--- ... ---)"""
        match = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", content, re.DOTALL)
        if not match:
            return {}
        result: dict[str, str] = {}
        for line in match.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip()] = val.strip().strip("'\"`")
        return result

    def _extract_project_id_from_content(self, content: str) -> str:
        """从内容中提取项目编号（从§3.0编号与项目表格或正文提取，兼容反引号与加粗标记）"""
        match = re.search(r"项目编号\*{0,2}[|：:]\s*[`]?([A-Z]+-\d{4}-\d{3})[`]?", content)
        return match.group(1) if match else ""

    def _read_explicit_status(self, section3_text: str) -> str:
        """从 §3.4 申请信息表中读取"变更状态"字段

        流转时写入此字段，解析时优先读取，确保状态持久化。
        返回空字符串表示无显式状态（回退到§8推断）。
        """
        match = re.search(r"\|\s*变更状态\s*\|\s*(\S+)\s*\|", section3_text)
        if match:
            status = match.group(1).strip()
            if status in ALL_STATUSES:
                return status
            log.debug("§3.4 变更状态值 '%s' 不在合法状态集中，忽略", status)
        return ""

    def _parse_impact_analysis(self, text: str, cr: ChangeRequest) -> None:
        """解析 §6 变更影响分析（三个子表）"""
        # §6.1 项目约束影响
        s61 = self._find_subsection(text, "6.1")
        if s61:
            cr.constraint_impacts = self._parse_constraint_impacts(s61)
            # M1-1: 解析 §6.1 下方的风险等级和缓解措施
            cr.risk_level = self._parse_risk_level(s61)
            cr.mitigation = self._parse_mitigation(s61)

        # §6.2 技术领域影响
        s62 = self._find_subsection(text, "6.2")
        if s62:
            cr.domain_impacts = self._parse_domain_impacts(s62)

        # §6.3 变更传播链
        s63 = self._find_subsection(text, "6.3")
        if s63:
            cr.propagation_chain = self._extract_propagation_chain(s63)
            cr.related_changes = self._extract_related_changes(s63)

        # 判断 §6 是否有实质内容
        has_constraint = bool(cr.constraint_impacts)
        has_domain = any(
            info.get("affected") for info in cr.domain_impacts.values()
        )
        has_propagation = bool(cr.related_changes)
        cr.has_section_6 = has_constraint or has_domain or has_propagation

    def _parse_risk_level(self, text: str) -> str:
        """解析 §6.1 风险等级（M1-1: PMBOK 风险评估）

        从 **风险等级** 标记行中提取 ☑ 对应的等级。
        返回: none/low/medium/high，空字符串表示未评估。

        格式示例:
            **风险等级**（PMBOK风险评估）：□无 ☑低 □中 □高 → low
            **风险等级**（PMBOK风险评估）：☑无 □低 □中 □高 → none
        """
        # 定位 **风险等级** 标记行
        pattern = re.compile(
            r"\*\*风险等级\*\*[^：:]*[：:]\s*(.*?)(?:\n\n|\n\*\*|\n###|\Z)",
            re.DOTALL,
        )
        match = pattern.search(text)
        if not match:
            return ""
        risk_text = match.group(1).strip()

        # 提取 ☑ 标记对应的等级
        level_map = {"无": "none", "低": "low", "中": "medium", "高": "high"}
        for cn, code in level_map.items():
            if f"☑{cn}" in risk_text or f"☑ {cn}" in risk_text:
                return code
        return ""

    def _parse_mitigation(self, text: str) -> str:
        """解析 §6.1 缓解措施（M1-1: 风险应对策略）

        从 **缓解措施** 标记后提取文本块。
        返回: 缓解措施文本，空字符串表示未填写。

        格式示例:
            **缓解措施**（风险应对策略）：
            增加单元测试覆盖率，进行代码评审
        """
        # 定位 **缓解措施** 标记后的文本块
        pattern = re.compile(
            r"\*\*缓解措施\*\*[^：:]*[：:]\s*\n(.*?)(?:\n\n###|\n###|\n##|\Z)",
            re.DOTALL,
        )
        match = pattern.search(text)
        if not match:
            return ""
        content = match.group(1).strip()
        # 过滤模板占位符
        if content == "（待填写）" or not content:
            return ""
        return content

    def _parse_constraint_impacts(self, text: str) -> dict[str, str]:
        """解析 §6.1 项目约束影响表

        提取每个维度的影响程度（无/低/中/高），通过 ☑ 标记判断。
        返回: {维度名称: 影响程度}
        """
        impacts: dict[str, str] = {}
        # 维度名称映射（表格中可能出现的格式 → 标准名称）
        dimension_names = ["范围", "进度", "成本", "质量", "风险"]

        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            # 检查是否包含维度关键词
            for dim in dimension_names:
                if dim in line:
                    # 提取影响程度：查找 ☑ 标记对应的无/低/中/高
                    level = self._extract_impact_level(line)
                    if level:
                        impacts[dim] = level
                    break
        return impacts

    def _extract_impact_level(self, line: str) -> str:
        """从表格行中提取影响程度

        格式示例: | **范围(Scope)** | □无 □低 ☑中 □高 |  |  |
        返回: "无"/"低"/"中"/"高"，无匹配则返回空字符串
        """
        levels = ["无", "低", "中", "高"]
        for level in levels:
            # 匹配 ☑紧接程度 或 ☑ 紧接程度
            if f"☑{level}" in line or f"☑ {level}" in line:
                return level
        return ""

    def _parse_domain_impacts(self, text: str) -> dict[str, dict[str, Any]]:
        """解析 §6.2 技术领域影响表

        提取每个领域的受影响状态、影响内容和关联变更单号。
        返回: {领域代码: {affected: bool, content: str, related_chg: str}}
        """
        impacts: dict[str, dict[str, Any]] = {}

        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            # 检查是否包含领域代码
            domain_match = re.search(r"\*\*(\w+)\*\*", line)
            if not domain_match:
                continue
            domain_code = domain_match.group(1)

            # 判断是否受影响（☑是）
            affected = "☑是" in line or "☑ 是" in line

            # 提取单元格内容
            cells = [c.strip() for c in line.split("|") if c.strip()]
            content = cells[2] if len(cells) > 2 else ""
            related_chg = ""
            # 提取关联变更单号（CHG-xxx 格式）
            for cell in cells:
                chg_match = re.search(r"(CHG-[A-Z]+-\d{4}-\d{3})", cell)
                if chg_match:
                    related_chg = chg_match.group(1)
                    break

            impacts[domain_code] = {
                "affected": affected,
                "content": content,
                "related_chg": related_chg,
            }
        return impacts

    def _extract_propagation_chain(self, text: str) -> str:
        """提取 §6.3 变更传播链路径描述

        §6.3 包含两个代码块：
        1. 传播路径示例（包含"原始领域变更"/"领域A"等占位文字）
        2. 本次变更传播链（用户填写）

        遍历所有代码块，跳过示例路径，返回第一个非示例代码块的内容。
        """
        code_blocks: list[str] = re.findall(r"```\s*\n(.*?)\n```", text, re.DOTALL)
        for raw_block in code_blocks:
            chain_text = raw_block.strip()
            # 跳过示例路径
            if "原始领域变更" not in chain_text and "领域A" not in chain_text:
                return chain_text
        return ""

    def _extract_related_changes(self, text: str) -> list[str]:
        """提取 §6.3 关联变更单清单中的变更单编号"""
        changes: list[str] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            # 在表格行中查找 CHG-xxx 格式的变更单号
            matches = re.findall(r"CHG-[A-Z]+-\d{4}-\d{3}", line)
            for m in matches:
                if m not in changes and not m.endswith("______"):
                    changes.append(m)
        return changes

    def _fill_section_flags(self, cr: ChangeRequest, sections: dict[str, str]) -> None:
        """填充章节内容标志（门禁校验用）

        检查各章节是否有实质内容（非空、非模板占位符）
        """
        # §4 变更原因：background 非空且非"待补充"
        cr.has_section_4 = bool(cr.background and cr.background != "待补充")

        # §7 实施计划：有至少一条数据行（表格中非表头/分隔符的行）
        if "7" in sections:
            cr.has_section_7 = self._has_table_data_rows(sections["7"])
        else:
            cr.has_section_7 = False

        # §8.1 审批记录：有至少一条审批数据行
        if "8" in sections:
            cr.has_section_8_approval = self._has_approval_records(sections["8"])
        else:
            cr.has_section_8_approval = False

        # §9 实施记录：有至少一条数据行
        if "9" in sections:
            cr.has_section_9 = self._has_table_data_rows(sections["9"])
        else:
            cr.has_section_9 = False

        # §10.1 验证项：有至少一条数据行
        # §10.2 验证结论
        if "10" in sections:
            cr.has_section_10_verify = self._has_verification_records(sections["10"])
            cr.section_10_conclusion = self._extract_verification_conclusion(sections["10"])
        else:
            cr.has_section_10_verify = False
            cr.section_10_conclusion = ""

    def _has_table_data_rows(self, text: str) -> bool:
        """检查章节中是否有表格数据行（排除表头和分隔符行）"""
        lines = text.strip().split("\n")
        data_rows = 0
        for line in lines:
            line = line.strip()
            if line.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", line):
                # 排除标题行（包含 # 序号 等表头关键词）
                if re.match(r"^\|\s*#\s*\|", line):
                    continue
                # 排除空数据行（所有单元格都是空白或-）
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if any(c and c != "-" for c in cells):
                    data_rows += 1
        return data_rows > 0

    def _has_approval_records(self, text: str) -> bool:
        """检查 §8 中是否有审批记录"""
        # 在 §8.1 审批流程表格中找数据行
        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", line):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                # 审批记录至少有一个非空单元格（排除表头行）
                if any(c for c in cells) and not re.match(r"^\|\s*审批环节\s*\|", line):
                    return True
        return False

    def _has_verification_records(self, text: str) -> bool:
        """检查 §10.1 中是否有验证项"""
        return self._has_table_data_rows(text)

    def _extract_verification_conclusion(self, text: str) -> str:
        """提取验证结论（M1-2: 适配 §10.3 三节结构，兼容旧 §10.2）

        定位策略（按优先级）：
        1. 新结构 §10.3 验证结论区域
        2. 旧结构 §10.2 验证结论区域（向后兼容）

        匹配三种行格式（按优先级）：
        1. _update_verification_conclusion 写入格式: | **验证结论** | 全部通过 |
        2. 原始模板格式: | 结论 | ☑全部通过 □ ... |
        3. 原始模板格式: | 结论 | □ 全部通过,可关闭 ... |
        """
        # 优先提取 §10.3 区域文本，回退到 §10.2（向后兼容）
        section_text = self._extract_conclusion_section_text(text)

        # 格式1: _update_verification_conclusion 写入的 **验证结论** | 值 | 格式（精确匹配）
        match = re.search(
            r"\|[^|\n]*\*+\s*验证结论\s*\*+\s*\|\s*([^|\n]+)\s*\|",
            section_text,
        )
        if match:
            conclusion = match.group(1).strip()
            if conclusion:
                return conclusion

        # 格式2: 原始模板含 ☑ 标记（仅在结论区域内）
        match = re.search(r"\|[^|\n]*结论[^|\n]*\|[^|\n]*☑\s*(\S+?)(?:\s*[,，□\|\n]|$)", section_text)
        if match:
            return match.group(1).strip()

        # 格式3: 兜底，如果结论行明确写了"全部通过"，提取它
        conclusion_match = re.search(
            r"\|[^|\n]*结论[^|\n]*\|\s*[^|\n]*全部通过[^|\n]*\s*\|",
            section_text,
        )
        if conclusion_match:
            return "全部通过"

        return ""

    def _extract_conclusion_section_text(self, text: str) -> str:
        """提取验证结论章节文本（M1-2）

        优先匹配 §10.3，回退到 §10.2（向后兼容旧变更单）。
        返回结论章节的正文文本（不含节标题），用于在其中查找结论行。
        """
        # 优先匹配 §10.3（新结构）
        sec_10_3_match = re.search(
            r"###\s*§?\s*10\.3\b(.*?)(?:###\s|##\s11\b|\Z)",
            text,
            re.DOTALL,
        )
        if sec_10_3_match:
            return sec_10_3_match.group(1)

        # 回退到 §10.2（旧结构）
        sec_10_2_match = re.search(
            r"###\s*§?\s*10\.2\b(.*?)(?:###\s|##\s11\b|\Z)",
            text,
            re.DOTALL,
        )
        if sec_10_2_match:
            return sec_10_2_match.group(1)

        # 兜底：返回整个 §10 文本
        return text

    def _parse_cross_domain_verification(self, text: str) -> list[dict[str, str]]:
        """解析 §10.2 跨领域联动验证（M1-2）

        解析 §10.2 表格中的传播环节验证记录。

        表格结构（对齐 040 模板 V2.1.0）：
        | 传播环节 | 关联变更单 | 该环节验证 | 验证人 | 验证日期 |

        返回: [{propagation: str, related_chg: str, result: str, verifier: str, date: str}]
        """
        # 定位 §10.2 区域
        sec_10_2_match = re.search(
            r"###\s*§?\s*10\.2\b(.*?)(?:###\s|##\s11\b|\Z)",
            text,
            re.DOTALL,
        )
        if not sec_10_2_match:
            return []

        section_text = sec_10_2_match.group(1)
        records: list[dict[str, str]] = []

        for line in section_text.split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            # 排除表头行
            if "传播环节" in line and "关联变更单" in line:
                continue

            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) < 5:
                continue
            # 排除模板占位行（CHG-xxx 占位符）
            if "CHG-xxx" in cells[1] or "CHG-yyy" in cells[1]:
                continue

            # 解析验证结果：☑通过 / ☑不通过
            result = ""
            if "☑通过" in cells[2] or "☑ 通过" in cells[2]:
                result = "通过"
            elif "☑不通过" in cells[2] or "☑ 不通过" in cells[2]:
                result = "不通过"

            records.append({
                "propagation": cells[0],
                "related_chg": cells[1],
                "result": result,
                "verifier": cells[3],
                "date": cells[4],
            })

        return records

    def _validate_spec_compliance(self, cr: ChangeRequest, sections: dict[str, str]) -> list[str]:
        """校验变更单是否符合 CHG-040 规范

        返回违规列表，空列表表示合规。
        不抛异常，仅记录警告，让解析继续完成。
        """
        violations: list[str] = []

        # 1. 必须有 §3 变更基本信息
        if "3" not in sections:
            violations.append("缺少 §3 变更基本信息章节")
        else:
            # §3 必须包含 3.0~3.4 子章节
            s3_text = sections["3"]
            for sub in REQUIRED_SUBSECTIONS:
                if not re.search(rf"###\s*{re.escape(sub)}", s3_text):
                    violations.append(f"§3 缺少子章节 §{sub}")

        # 2. 必须有 §4 变更原因
        if "4" not in sections:
            violations.append("缺少 §4 变更原因章节")

        # 3. 必须有 §8 变更审批
        if "8" not in sections:
            violations.append("缺少 §8 变更审批章节")

        # 4. 枚举值校验
        if cr.domain and cr.domain not in DOMAINS:
            violations.append(f"领域 '{cr.domain}' 不在规范允许值 {list(DOMAINS.keys())} 中")
        if cr.business_nature and cr.business_nature not in BUSINESS_NATURES:
            violations.append(f"业务性质 '{cr.business_nature}' 不在规范允许值 {list(BUSINESS_NATURES.keys())} 中")
        for scope in cr.impact_scope:
            if scope and scope not in IMPACT_SCOPES:
                violations.append(f"影响范围 '{scope}' 不在规范允许值 {list(IMPACT_SCOPES.keys())} 中")

        # 5. 必填字段校验
        if not cr.change_number:
            violations.append("变更编号为空")
        if not cr.project_id:
            violations.append("项目编号为空")

        return violations
