"""PLC-HMI 概念映射：SFB 库函数（Markdown 编辑器（变更单 Frontmatter 编辑））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变更单 Markdown 内容编辑器（M3-Iter2 从 ChangeService 拆分）

负责变更单 .md 文件的内容级编辑：
- 审批/实施/验证表格追加行
- 状态字段更新
- 验证结论更新
- 字段值更新（背景/必要性/参考依据/预计日期/紧急程度）

ChangeService 通过组合方式使用本模块，保持向后兼容。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from auto_pm.change.constants import URGENCY_LEVELS

log = logging.getLogger(__name__)


class ChangeMarkdownEditor:
    """变更单 Markdown 内容编辑器

    所有方法都是纯函数式操作：输入 .md 内容字符串，返回修改后的字符串。
    不涉及文件 I/O，便于单测和复用。
    """

    def append_to_approval_table(self, content: str, row: str) -> str:
        """在审批流程表格末尾追加一行"""
        # 查找 §8.1 审批流程
        pattern = re.compile(
            r"(###\s*8\.1.*?\|.*?\|.*?\|.*?\|.*?\|.*?\|\n)((?:\|[\s\-:|]+\|\n)?(?:\|.*\|\n)*)",
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            return content[:match.end()] + row + content[match.end():]
        # 兜底：在 §8 章节末尾追加
        return content + "\n" + row

    def append_to_implementation_table(self, content: str, row: str) -> str:
        """在实施记录表格末尾追加一行"""
        pattern = re.compile(
            r"(##\s*9\..*?\|.*?\|.*?\|.*?\|.*?\|.*?\|.*?\|\n)((?:\|[\s\-:|]+\|\n)?(?:\|.*\|\n)*)",
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            return content[:match.end()] + row + content[match.end():]
        return content + "\n" + row

    def append_to_verification_table(self, content: str, row: str) -> str:
        """在验证表格 (§10.1) 末尾追加一行

        M1-2: §10 改为三节结构后，§10.2 为跨领域联动验证。
        验证项仍追加到 §10.1 末尾（即 §10.2 标题之前）。
        """
        # 定位 §10.1 起始位置
        sec_10_1 = re.search(r"^###\s*10\.1", content, re.MULTILINE)
        if not sec_10_1:
            return content + "\n" + row

        # 定位 §10.2 节标题，在其前插入
        remainder = content[sec_10_1.end():]
        next_section = re.search(r"^###\s*10\.2", remainder, re.MULTILINE)
        if next_section:
            insert_pos = sec_10_1.end() + next_section.start()
            return content[:insert_pos].rstrip() + "\n" + row + content[insert_pos:]

        # 无 §10.2：在 §10.1 区域末尾追加
        return content + "\n" + row

    def update_status_field(self, content: str, new_status: str) -> str:
        """更新 §3.4 申请信息表中的"变更状态"字段

        如果已有"变更状态"行，替换值；如果没有，在紧急程度行后追加。
        """
        # 替换已有的变更状态行
        pattern = re.compile(r"(\|\s*变更状态\s*\|\s*)\S+(\s*\|)")
        if pattern.search(content):
            return pattern.sub(r"\g<1>" + new_status + r"\2", content)
        # 没有变更状态行，在紧急程度行后追加
        urgency_pattern = re.compile(r"(\|\s*紧急程度\s*\|.*?\|)\n")
        match = urgency_pattern.search(content)
        if match:
            return content[:match.end()] + f"| 变更状态 | {new_status} |\n" + content[match.end():]
        # 兜底：在 §3.4 末尾追加
        return content + f"\n| 变更状态 | {new_status} |\n"

    def update_verification_conclusion(self, content: str, conclusion: str) -> str:
        """更新验证结论为指定值（M1-2: 适配 §10.3 三节结构，兼容旧 §10.2）

        定位策略（按优先级）：
        1. 新结构 §10.3 验证结论（M1-2 后生成器默认输出）
        2. 旧结构 §10.2 验证结论（向后兼容已存在的变更单）

        兼容三种行格式：
        1. 原始模板格式: | 结论 | □ 全部通过,可关闭 □ 部分不通过,需返工 □ 需补充验证 |
        2. 已写入格式:    | **验证结论** | 全部通过 |
        3. § 符号变体:    ### §10.3 或 ### 10.3
        """
        # 先扫描判断结构：优先 §10.3，无 §10.3 时回退到 §10.2
        has_section_10_3 = bool(re.search(r"^###\s*§?\s*10\.3\b", content, re.MULTILINE))
        if has_section_10_3:
            target_pattern = re.compile(r"^###\s*§?\s*10\.3\b")
        else:
            target_pattern = re.compile(r"^###\s*§?\s*10\.2\b")

        lines = content.splitlines()
        in_conclusion_section = False
        found_conclusion_line = False
        result = []
        for line in lines:
            stripped = line.strip()
            # 匹配目标结论节标题
            if not in_conclusion_section and target_pattern.match(stripped):
                in_conclusion_section = True
                result.append(line)
                continue
            # 遇到下一个 ### 节标题，退出当前结论节
            if in_conclusion_section and re.match(r"^###\s", stripped):
                in_conclusion_section = False

            if in_conclusion_section and not found_conclusion_line:
                # 格式A: 模板原始格式 | 结论 | □ ... |
                if re.match(r"^\|\s*结论\s*\|", stripped):
                    result.append(f"| **验证结论** | {conclusion} |")
                    found_conclusion_line = True
                    continue
                # 格式B: 已写入的 **验证结论** 格式
                if "**验证结论**" in stripped:
                    result.append(f"| **验证结论** | {conclusion} |")
                    found_conclusion_line = True
                    continue

            result.append(line)

        # 如果进入了结论节但没找到结论行，在节标题后插入
        if not found_conclusion_line:
            for i, r in enumerate(result):
                if target_pattern.match(r.strip()):
                    result.insert(i + 1, f"| **验证结论** | {conclusion} |")
                    break

        return "\n".join(result)

    def update_field(self, content: str, field: str, value: Any) -> str:
        """根据字段名分发到对应的章节更新逻辑

        Args:
            content: .md 文件原始内容
            field: 字段名（background/necessity/references/planned_date/urgency
                   /risk_level/mitigation/propagation_chain/constraint_impacts/domain_impacts）
            value: 新值（str 或 dict）

        Returns:
            更新后的 .md 内容（未匹配到则原样返回）
        """
        # §4/§3.4 基本字段
        if field in ("background", "necessity", "references"):
            label_map = {
                "background": "变更背景",
                "necessity": "变更必要性",
                "references": "参考依据",
            }
            return self._update_text_block(content, label_map[field], value)
        if field == "planned_date":
            return self._update_table_field(content, "预计实施日期", value)
        if field == "urgency":
            return self._update_table_field(
                content, "紧急程度", self.render_urgency_value(value)
            )
        # §6 影响分析字段（M3-1 新增）
        if field == "risk_level":
            return self.update_risk_level(content, value)
        if field == "mitigation":
            return self.update_mitigation(content, value)
        if field == "propagation_chain":
            return self.update_propagation_chain(content, value)
        if field == "constraint_impacts":
            return self.update_constraint_impacts(content, value)
        if field == "domain_impacts":
            return self.update_domain_impacts(content, value)
        return content

    def _update_text_block(self, content: str, label: str, value: str) -> str:
        """更新 §4 中的文本块（**变更背景**：xxx）

        保留 ``**label**：`` 标记行，仅替换后续段落内容，
        直到遇到下一个 ``**...**`` 标记或 ``##`` 章节标题。
        """
        pattern = re.compile(
            rf"(\*\*{re.escape(label)}\*\*[：:]\s*\n)(.*?)(?=\n\*\*|\n##|\Z)",
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            # 使用函数替换避免 value 中的反斜杠被当作反向引用
            return pattern.sub(lambda m: m.group(1) + value + "\n", content, count=1)
        log.warning("更新文本块: 未找到标签 '%s'，跳过", label)
        return content

    def _update_table_field(self, content: str, field_name: str, value: str) -> str:
        """更新 §3.4 表格中的字段值（| 字段名 | 值 |）

        仅替换值单元格，保留字段名和表格结构。
        """
        pattern = re.compile(
            rf"(\|\s*{re.escape(field_name)}\s*\|\s*)[^|]*(\s*\|)"
        )
        match = pattern.search(content)
        if match:
            return pattern.sub(
                lambda m: m.group(1) + value + m.group(2), content, count=1
            )
        log.warning("更新表格字段: 未找到字段 '%s'，跳过", field_name)
        return content

    @staticmethod
    def render_urgency_value(urgency: str) -> str:
        """渲染紧急程度为 ☑/□ 格式（与 ChgGenerator._render_urgency 对齐）"""
        parts = []
        for code, label in URGENCY_LEVELS.items():
            mark = "☑" if code == urgency else "□"
            parts.append(f"{mark}{label}")
        return " ".join(parts)

    # ── §6 影响分析字段更新（M3-1 新增） ──────────────────

    def update_risk_level(self, content: str, risk_level: str) -> str:
        """更新 §6.1 风险等级行的 ☑ 标记

        匹配格式: **风险等级**（PMBOK风险评估）：□无 □低 □中 □高

        Args:
            risk_level: none/low/medium/high，空字符串保留原样
        """
        new_value = self._render_risk_level_value(risk_level)
        pattern = re.compile(r"(\*\*风险等级\*\*[^：:]*[：:])\s*[^|\n]+")
        if pattern.search(content):
            return pattern.sub(lambda m: m.group(1) + " " + new_value, content)
        log.warning("更新风险等级: 未找到 **风险等级** 标记行，跳过")
        return content

    def update_mitigation(self, content: str, mitigation: str) -> str:
        """更新 §6.1 缓解措施文本块

        匹配格式:
            **缓解措施**（风险应对策略）：
            （待填写）
        """
        pattern = re.compile(
            r"(\*\*缓解措施\*\*[^：:]*[：:]\s*\n)(.*?)(?=\n\n###|\n###|\n##|\Z)",
            re.DOTALL,
        )
        if pattern.search(content):
            return pattern.sub(
                lambda m: m.group(1) + mitigation + "\n", content, count=1
            )
        log.warning("更新缓解措施: 未找到 **缓解措施** 标记，跳过")
        return content

    def update_propagation_chain(self, content: str, chain: str) -> str:
        """更新 §6.3 本次变更传播链代码块

        匹配格式:
            **本次变更传播链:**
            ```
            [___________] → [___________]
            ```
        """
        pattern = re.compile(
            r"(\*\*本次变更传播链:\*\*\s*\n```\s*\n)(.*?)(\n```)",
            re.DOTALL,
        )
        if pattern.search(content):
            return pattern.sub(
                lambda m: m.group(1) + chain + m.group(3), content, count=1
            )
        log.warning("更新传播链: 未找到 **本次变更传播链:** 代码块，跳过")
        return content

    def update_constraint_impacts(
        self, content: str, impacts: dict[str, str]
    ) -> str:
        """更新 §6.1 项目约束影响表格中每个维度的影响程度

        逐行扫描表格，匹配包含 **{维度}** 的行，替换影响程度列的 ☑ 标记。

        Args:
            impacts: {维度名称: 影响程度(无/低/中/高)}
        """
        lines = content.splitlines()
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|"):
                for dim, level in impacts.items():
                    if f"**{dim}" in stripped:
                        cells = [c.strip() for c in line.split("|")]
                        # cells[0] 为空（行首 |），cells[-1] 为空（行尾 |）
                        if len(cells) >= 4:
                            # cells[1] = 维度列, cells[2] = 影响程度列
                            cells[2] = self._render_impact_level(level)
                            line = "|" + "|".join(cells[1:-1]) + "|"
                        break
            result.append(line)
        return "\n".join(result)

    def update_domain_impacts(
        self, content: str, impacts: dict[str, dict[str, Any]]
    ) -> str:
        """更新 §6.2 技术领域影响表格中每个领域的是否受影响和影响内容

        逐行扫描表格，匹配包含 **{领域代码}** 的行，替换：
        - 领域列的 ☑/□ 标记（行首）
        - 是否受影响列（☑是 □否 / □是 ☑否）
        - 具体影响内容列

        Args:
            impacts: {领域代码: {affected: bool, content: str, related_chg: str}}
        """
        lines = content.splitlines()
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|"):
                for domain_code, info in impacts.items():
                    if f"**{domain_code}**" in stripped:
                        cells = [c.strip() for c in line.split("|")]
                        if len(cells) >= 6:
                            affected = bool(info.get("affected", False))
                            # cells[1] = 领域列（更新行首 ☑/□）
                            cells[1] = re.sub(
                                r"^[□☑]\s*",
                                "☑ " if affected else "□ ",
                                cells[1],
                            )
                            # cells[2] = 是否受影响列
                            cells[2] = "☑是 □否" if affected else "□是 ☑否"
                            # cells[3] = 具体影响内容列
                            cells[3] = info.get("content", "") or ""
                            line = "|" + "|".join(cells[1:-1]) + "|"
                        break
            result.append(line)
        return "\n".join(result)

    @staticmethod
    def _render_risk_level_value(risk_level: str) -> str:
        """渲染风险等级为 ☑/□ 格式（与 ChgGenerator._render_risk_level 对齐）"""
        levels = [("none", "无"), ("low", "低"), ("medium", "中"), ("high", "高")]
        parts = []
        for code, label in levels:
            mark = "☑" if code == risk_level else "□"
            parts.append(f"{mark}{label}")
        return " ".join(parts)

    @staticmethod
    def _render_impact_level(level: str) -> str:
        """渲染影响程度为 ☑/□ 格式"""
        levels = ["无", "低", "中", "高"]
        parts = []
        for lvl in levels:
            mark = "☑" if lvl == level else "□"
            parts.append(f"{mark}{lvl}")
        return " ".join(parts)
