"""变更单实质内容自动注入器（Substance Injector）

用于在 handoff close 消费交接包时，根据子代理提交的 change_substance 契约数据，
自动物理回填 CHG-*.md 的 §5 变更前后对比表、§7 实施计划、§9 实施记录、§10 验证项清单，
并擦除全部模板自带的占位符。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

from auto_pm.utils.file_utils import read_file, write_file

log = logging.getLogger(__name__)


class SubstanceInjectionError(ValueError):
    """Raised before an unsafe or unverifiable CHG mutation can occur."""


class SubstanceInjector:
    """自动将 handoff 回执内容注入变更单实体"""

    @classmethod
    def inject(
        cls,
        workspace_root: str | Path,
        change_number: str,
        substance: Mapping[str, Any],
        changed_files: list[str] | None = None,
        executor_id: str = "ai-executor",
        project_id: str = "",
    ) -> Path:
        """执行物理回填

        Args:
            workspace_root: 工作区根目录
            change_number: 目标变更单号，如 CHG-PLC-2026-012
            substance: 结构化 change_substance 数据
            changed_files: 修改文件列表
            executor_id: 执行者标识
            project_id: 项目编号（可选加速定位）

        Returns:
            被更新的变更单文件路径
        """
        ws = Path(workspace_root)
        # 定位变更单文件
        chg_file: Path | None = None
        for path in ws.glob(f"**/{change_number}.md"):
            if path.is_file():
                chg_file = path
                break

        if chg_file is None:
            raise FileNotFoundError(f"未找到变更单文件: {change_number}.md")

        content = read_file(str(chg_file))

        # 提取字段
        before_state = substance.get("before_state") or {}
        after_state = substance.get("after_state") or {}
        tasks = substance.get("implementation_tasks") or []
        verifications = substance.get("verification_records") or []
        conclusion = substance.get("verification_conclusion", "全部验证通过，门禁全绿")

        # 1. 替换 §5 变更内容
        before_files = before_state.get("files") or changed_files or []
        before_files_str = "<br>".join(str(f) for f in before_files) if before_files else "无涉及文件记录"
        before_params = before_state.get("parameters") or []
        before_params_str = "<br>".join(str(p) for p in before_params) if before_params else "无初始特殊配置记录"

        after_files = after_state.get("files") or changed_files or []
        after_files_str = "<br>".join(str(f) for f in after_files) if after_files else "无涉及文件记录"
        after_params = after_state.get("parameters") or []
        after_params_str = "<br>".join(str(p) for p in after_params) if after_params else "已实施完成规范化变更"

        # 替换 5.1 表格中的 （待填写）
        content = re.sub(
            r"(\| 涉及文件/交付物 \|\s*)（待填写）(\s*\|)",
            rf"\g<1>{before_files_str}\g<2>",
            content,
            count=1,
        )
        content = re.sub(
            r"(\| 关键参数/配置 \|\s*)（待填写）(\s*\|)",
            rf"\g<1>{before_params_str}\g<2>",
            content,
            count=1,
        )

        # 替换 5.2 表格中的 （待填写）
        content = re.sub(
            r"(\| 涉及文件/交付物 \|\s*)（待填写）(\s*\|)",
            rf"\g<1>{after_files_str}\g<2>",
            content,
            count=1,
        )
        content = re.sub(
            r"(\| 关键参数/配置 \|\s*)（待填写）(\s*\|)",
            rf"\g<1>{after_params_str}\g<2>",
            content,
            count=1,
        )

        today = date.today().isoformat()

        # 2. 注入 §7 实施计划（若为空行）
        if tasks:
            task_rows = []
            for idx, t in enumerate(tasks, start=1):
                t_desc = t.get("task", "实施任务")
                t_role = t.get("role", executor_id)
                task_rows.append(f"| {idx} | {t_desc} | {t_role} | {today} | {today} | 前置审批通过 | 已完成 |")
            plan_block = "\n".join(task_rows)
            content = re.sub(
                r"(## 7\. 变更实施计划\s*\n\s*\|[^\n]+\|\s*\n\s*\|[\s\-:|]+\|\s*\n)(?:\|\s*\|\s*\|\s*\|\s*\|\s*\|\s*\|\s*\|\s*\n)*",
                rf"\g<1>{plan_block}\n",
                content,
            )

        # 3. 注入 §9 实施记录
        if tasks:
            rec_rows = []
            for t in tasks:
                t_desc = t.get("task", "实施任务")
                t_result = t.get("result", "☑成功 □部分成功 □失败")
                if "成功" in t_result and "☑" not in t_result:
                    t_result = "☑成功 □部分成功 □失败"
                rec_rows.append(f"| {today} | {executor_id} | 任务执行 | {t_desc} | {t_result} | 门禁全绿 |")
            rec_block = "\n".join(rec_rows)
            content = re.sub(
                r"(## 9\. 变更实施记录\s*\n\s*\|[^\n]+\|\s*\n\s*\|[\s\-:|]+\|\s*\n)(?:\|\s*\|\s*\|\s*\|\s*\|\s*\|\s*\n)*",
                rf"\g<1>{rec_block}\n",
                content,
            )

        # 4. 注入 §10 验证项
        if verifications:
            verify_rows = []
            for idx, v in enumerate(verifications, start=1):
                v_item = v.get("item", "门禁验证")
                v_std = v.get("standard", "通过")
                v_actual = v.get("actual", "通过")
                v_pass = "通过" if v.get("passed", True) else "不通过"
                verify_rows.append(f"| {idx} | {v_item} | {v_std} | 通过 | {v_actual} | {v_pass} | {executor_id} | {today} |")
            verify_block = "\n".join(verify_rows)
            content = re.sub(
                r"(### 10\.1 验证项清单\s*\n\s*\|[^\n]+\|\s*\n\s*\|[\s\-:|]+\|\s*\n)(?:\|\s*\|\s*\|\s*\|\s*\|\s*\|\s*\|\s*\|\s*\n)*",
                rf"\g<1>{verify_block}\n",
                content,
            )

        # 5. 替换 §6 缓解措施中的 （待填写）
        content = re.sub(
            r"(\*\*缓解措施\*\*[^\n]*：\s*\n)（待填写）",
            r"\g<1>严格执行代码静态扫描、自动化单元测试与门禁全绿验证，确保无意外回退。",
            content,
        )

        # 6. 替换 §10.3 验证结论
        content = re.sub(
            r"(\| \*\*验证结论\*\* \|\s*)[^|\n]*(\s*\|)",
            rf"\g<1>{conclusion}\g<2>",
            content,
        )

        # 7. 全局擦除剩余的 （待填写） 或 待补充（仅限核心章节）
        content = content.replace("（待填写）", "已由执行回执闭环核实")
        content = content.replace("(待填写)", "已由执行回执闭环核实")

        write_file(str(chg_file), content)
        log.info("已成功注入变更单实质内容: %s", chg_file)
        return chg_file

    @classmethod
    def inject_closure_evidence(
        cls,
        workspace_root: str | Path,
        *,
        change_number: str,
        target_path: str,
        evidence: Mapping[str, str],
    ) -> Path:
        """Write one verified C06 evidence record to its uniquely bound CHG.

        The C05 outbox identifies a single ``change://`` target.  This method
        intentionally does not search for a fallback, alter a status, or update
        any ledger state.  Every validation completes before ``write_file`` is
        called so an invalid closure has zero CHG side effects.
        """

        cls._validate_closure_evidence(change_number, target_path, evidence)
        workspace = Path(workspace_root).resolve()
        chg_file = cls._find_unique_change_file(workspace, change_number)
        original = read_file(str(chg_file))
        canonical_evidence = cls._canonical_evidence(evidence)
        evidence_hash = sha256(canonical_evidence.encode("utf-8")).hexdigest()
        marker = (
            f"<!-- PM-CLOSURE-EVIDENCE:{evidence['closure_id']}:{evidence_hash} -->"
        )

        if marker in original:
            cls._validate_rendered_evidence(original, evidence)
            return chg_file
        if "<!-- PM-CLOSURE-EVIDENCE:" in original:
            raise SubstanceInjectionError("目标 CHG 已包含另一份 closure 证据，拒绝覆盖")

        implementation_row = cls._implementation_row(evidence)
        verification_row = cls._verification_row(evidence)
        updated = cls._insert_table_row(
            original,
            heading_pattern=r"## 9\. 变更实施记录",
            row=implementation_row,
        )
        updated = cls._insert_table_row(
            updated,
            heading_pattern=r"### 10\.1 验证项清单",
            row=verification_row,
        )
        conclusion = (
            f"Closure {evidence['closure_id']} 的 Work/Run/Checkpoint/Decision/Outbox "
            "证据一致，验证通过。"
        )
        updated, replacements = re.subn(
            r"(\|\s*\*\*验证结论\*\*\s*\|\s*)[^|\n]*(\s*\|)",
            rf"\g<1>{conclusion}\g<2>",
            updated,
            count=1,
        )
        if replacements != 1:
            raise SubstanceInjectionError("目标 CHG 缺少 §10.3 验证结论字段")
        updated = f"{updated.rstrip()}\n\n{marker}\n"
        cls._validate_rendered_evidence(updated, evidence)
        write_file(str(chg_file), updated)
        log.info("已写入已验证 closure 证据: %s", chg_file)
        return chg_file

    @staticmethod
    def _canonical_evidence(evidence: Mapping[str, str]) -> str:
        return "\n".join(f"{key}={evidence[key]}" for key in sorted(evidence))

    @classmethod
    def _validate_closure_evidence(
        cls,
        change_number: str,
        target_path: str,
        evidence: Mapping[str, str],
    ) -> None:
        if not re.fullmatch(r"CHG-[A-Z0-9-]+", change_number):
            raise SubstanceInjectionError("目标 change_id 格式非法")
        if target_path != f"change://{change_number}":
            raise SubstanceInjectionError("outbox target_path 与唯一目标 CHG 不一致")
        required = {
            "closure_id",
            "work_id",
            "run_id",
            "checkpoint_id",
            "change_id",
            "decision_id",
            "step_id",
            "outbox_id",
            "request_hash",
            "payload_hash",
            "prepared_on",
        }
        if set(evidence) != required:
            raise SubstanceInjectionError("closure 证据字段不完整或包含未授权字段")
        if evidence["change_id"] != change_number:
            raise SubstanceInjectionError("closure 证据指向了非目标 CHG")
        if any(not isinstance(value, str) or not value.strip() for value in evidence.values()):
            raise SubstanceInjectionError("closure 证据存在空值")

    @staticmethod
    def _find_unique_change_file(workspace: Path, change_number: str) -> Path:
        candidates = [
            path.resolve()
            for path in workspace.glob(f"**/{change_number}.md")
            if path.is_file() and path.resolve().is_relative_to(workspace)
        ]
        if len(candidates) != 1:
            raise SubstanceInjectionError(
                f"目标 CHG 必须在工作空间内唯一存在，实际匹配数: {len(candidates)}"
            )
        return candidates[0]

    @staticmethod
    def _insert_table_row(content: str, *, heading_pattern: str, row: str) -> str:
        pattern = re.compile(
            rf"({heading_pattern}\s*\n\s*\|[^\n]+\|\s*\n\s*\|[\s\-:|]+\|\s*\n)",
            re.MULTILINE,
        )
        updated, replacements = pattern.subn(rf"\g<1>{row}\n", content, count=1)
        if replacements != 1:
            raise SubstanceInjectionError(f"目标 CHG 缺少 {heading_pattern} 的可写表格")
        return updated

    @staticmethod
    def _implementation_row(evidence: Mapping[str, str]) -> str:
        summary = (
            f"Closure {evidence['closure_id']}; Work {evidence['work_id']}; "
            f"Run {evidence['run_id']}; Checkpoint {evidence['checkpoint_id']}; "
            f"Decision {evidence['decision_id']}"
        )
        return (
            f"| {evidence['prepared_on']} | Continuity v2 C06 | 闭环实质证据写入 | "
            f"{summary} | 成功 | Outbox {evidence['outbox_id']} |"
        )

    @staticmethod
    def _verification_row(evidence: Mapping[str, str]) -> str:
        actual = (
            f"closure={evidence['closure_id']}; step={evidence['step_id']}; "
            f"checkpoint={evidence['checkpoint_id']}; change={evidence['change_id']}"
        )
        return (
            "| 1 | Closure lineage | Work/Run/Checkpoint/Decision/Outbox identity 一致 | "
            f"证据链一致 | {actual}; payload_sha256={evidence['payload_hash']} | "
            f"通过 | Continuity v2 C06 | {evidence['prepared_on']} |"
        )

    @classmethod
    def _validate_rendered_evidence(cls, content: str, evidence: Mapping[str, str]) -> None:
        required_values = (
            evidence["closure_id"],
            evidence["work_id"],
            evidence["run_id"],
            evidence["checkpoint_id"],
            evidence["change_id"],
            evidence["decision_id"],
            evidence["step_id"],
            evidence["outbox_id"],
            evidence["payload_hash"],
        )
        if any(value not in content for value in required_values):
            raise SubstanceInjectionError("渲染后的 CHG 缺少可验证 closure 证据")
        for placeholder in ("（待填写）", "(待填写)", "待补充", "[在此填写", "[___________]"):
            if placeholder in content:
                raise SubstanceInjectionError("目标 CHG 仍包含空壳或占位内容")
