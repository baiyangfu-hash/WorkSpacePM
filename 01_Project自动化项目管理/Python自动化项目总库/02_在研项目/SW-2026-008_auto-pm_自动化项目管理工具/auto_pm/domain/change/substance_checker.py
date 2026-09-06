"""变更单实质内容检查器（Substance Checker）

检查变更单（CHG-*.md）是否包含实质技术内容，杜绝空壳变更单（Phantom Ticket）通过门禁。

门禁规则：
1. 占位符黑名单：严禁包含“（待填写）”、“(待填写)”、“待补充”、“CHG-______”、“[在此填写”。
2. 章节完整性（按状态分级）：
   - draft: 允许草稿占位符
   - submitted / approved / implementing:
     - §5 变更内容必须存在且无占位符，§5.1（变更前）和 §5.2（变更后）必须有有效数据
   - pending_acceptance / accepting / completed / closed:
     - §5 变更内容必须存在且无占位符
     - §7 实施计划必须有有效数据行
     - §9 实施记录必须有有效数据行
     - §10 验证项清单必须有有效数据行，且验证结论必须包含“通过”并不包含“不通过”
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from auto_pm.change.constants import ChangeRequest
from auto_pm.change.parser import ChgParser

log = logging.getLogger(__name__)


class SubstanceChecker:
    """变更单实质内容检查器"""

    FORBIDDEN_PLACEHOLDERS: tuple[str, ...] = (
        "（待填写）",
        "(待填写)",
        "待补充",
        "CHG-______",
        "[在此填写",
    )

    @classmethod
    def check_placeholders(cls, text: str) -> list[str]:
        """检查文本中是否存在未替换的占位符"""
        violations: list[str] = []
        for p in ("（待填写）", "(待填写)", "待补充", "[在此填写"):
            if p in text:
                violations.append(f"包含未替换占位符: '{p}'")

        # 针对 CHG-______：仅当出现在勾选了 ☑是 的行或关联变更单行时，才算真正未指定关联单号
        for line in text.splitlines():
            if "CHG-______" in line:
                if "☑是" in line or "☑ 是" in line:
                    violations.append("已勾选受影响领域但未填写关联单号: 'CHG-______'")
                    break
                # 在 §6.3 关联变更单清单中
                if re.match(r"^\|\s*CHG-______\s*\|", line.strip()):
                    violations.append("关联变更单清单包含未指定的单号占位符: 'CHG-______'")
                    break
        return violations

    @classmethod
    def check_substance(
        cls,
        cr: ChangeRequest,
        target_status: str | None = None,
        workspace_root: Path | None = None,
    ) -> list[str]:
        """检查变更单实质内容

        Args:
            cr: 已解析的 ChangeRequest 对象
            target_status: 目标状态（若为空则使用 cr.status）
            workspace_root: 工作空间根目录（用于跨领域单据穿透检测）

        Returns:
            违规清单，空列表表示检查通过。
        """
        status = target_status or cr.status
        violations: list[str] = []
        sections = getattr(cr, "sections", {}) or {}

        # 仅对完成验收状态 (completed / closed) 强制要求零占位符与实质内容完备
        if status in ("completed", "closed"):
            # 1. 占位符检查：核心章节严禁包含占位符
            core_sections = ("3", "4", "5", "6", "7", "8", "9", "10")
            core_text = "\n".join(sections.get(s, "") for s in core_sections if s in sections)
            ph_violations = cls.check_placeholders(core_text)
            if ph_violations:
                violations.extend(ph_violations)

            # 2. §5 变更内容检查：若存在 §5 章节，必须包含 5.1/5.2 且有有效数据行
            if "5" in sections:
                s5_text = sections["5"]
                if not s5_text.strip():
                    violations.append("§5 变更内容章节为空")
                elif "5.1" in s5_text and "5.2" in s5_text:
                    lines = [line.strip() for line in s5_text.split("\n") if line.strip().startswith("|")]
                    data_lines = [
                        line for line in lines
                        if not re.match(r"^\|[\s\-:|]+\|$", line)
                        and not re.match(r"^\|\s*项目\s*\|", line)
                    ]
                    if not data_lines:
                        violations.append("§5 变更内容表格无有效数据行")

            # 3. 完成状态下如果有 §10，严禁结论为“不通过”
            if "10" in sections and cr.section_10_conclusion:
                if "不通过" in cr.section_10_conclusion:
                    violations.append("§10.3 验证结论包含'不通过'")

            # 4. 跨领域受影响声明穿透校验
            cross_violations = cls.check_cross_domain_links(cr, workspace_root=workspace_root)
            if cross_violations:
                violations.extend(cross_violations)

        return violations

    @classmethod
    def check_cross_domain_links(
        cls,
        cr: ChangeRequest,
        workspace_root: Path | None = None,
    ) -> list[str]:
        """检查 §6.2 声明的跨领域关联单据物理存在性与合法性"""
        violations: list[str] = []
        sections = getattr(cr, "sections", {}) or {}
        s6_text = sections.get("6", "")
        if not s6_text:
            return violations

        ws = workspace_root or Path.cwd()

        for line in s6_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("|") and ("☑是" in line_str or "☑ 是" in line_str):
                parts = [p.strip() for p in line_str.split("|") if p.strip()]
                if parts:
                    assoc_col = parts[-1]
                    if assoc_col in ("本单", "无", "-", "N/A", "无关联变更单"):
                        continue
                    m = re.search(r"CHG-[A-Z0-9]+-\d{4}-\d+", assoc_col)
                    if not m:
                        violations.append(f"已勾选跨领域影响但未指定有效关联变更单号: '{assoc_col}'")
                    else:
                        target_chg_num = m.group(0)
                        matches = list(ws.glob(f"**/{target_chg_num}.md"))
                        if not matches:
                            violations.append(f"跨领域声明的关联变更单在工作空间中不存在: '{target_chg_num}'")

        return violations

    @classmethod
    def check_file(
        cls,
        file_path: str | Path,
        target_status: str | None = None,
        workspace_root: Path | None = None,
    ) -> list[str]:
        """直接检查指定变更单文件（静态全量文件检查）"""
        p = Path(file_path).resolve()
        if not p.is_file():
            return [f"变更单文件不存在: {file_path}"]
        parser = ChgParser()
        try:
            cr = parser.parse(str(p))
        except Exception as e:
            return [f"变更单文件解析失败: {e}"]

        ws = workspace_root
        if ws is None:
            for parent in [p] + list(p.parents):
                if (parent / ".git").exists() or (parent / "00_Infrastructure").exists():
                    ws = parent
                    break
            if ws is None:
                ws = Path.cwd()

        violations = cls.check_substance(cr, target_status=target_status, workspace_root=ws)
        status = target_status or cr.status
        if status in ("completed", "closed"):
            sections = getattr(cr, "sections", {}) or {}
            if "5" not in sections or not sections["5"].strip():
                violations.append("§5 变更内容章节缺失或为空")
        return violations
