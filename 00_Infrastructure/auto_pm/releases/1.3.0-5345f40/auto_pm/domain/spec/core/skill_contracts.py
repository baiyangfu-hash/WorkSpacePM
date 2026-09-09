"""PLC-HMI 概念映射：SFB 库函数（技能文档↔代码契约漂移对账器（SHC-017）契约清单）

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

技能文档↔代码契约漂移对账器契约清单（CHG-SCPT-2026-167）。

以「代码为唯一真源」动态提取关键常量，校验技能文档（<workspace>/.trae/skills/**）
是否仍包含这些值。本模块仅定义数据模型（CodeTruth / SkillContract）与契约清单
（C1~C4），真源提取与文档校验逻辑位于 checker_base.SkillContractDriftChecker。
"""

from __future__ import annotations

from dataclasses import dataclass

from .checker_base import Severity


@dataclass(frozen=True)
class CodeTruth:
    """代码真源提取指令。

    kind ∈ {"value", "keys"}：
    - value：取标量值并转 str 作为真源值；
    - keys：取 dict 的 keys 逐项转 str 作为真源值集合。
    """

    module: str
    attribute: str
    kind: str


@dataclass(frozen=True)
class SkillContract:
    """技能文档↔代码契约：某份技能文档应包含的一组真源值。"""

    contract_id: str
    title: str
    severity: Severity
    code_truths: tuple[CodeTruth, ...]
    literals: tuple[str, ...]
    doc_relpaths: tuple[str, ...]


SKILL_CONTRACTS: tuple[SkillContract, ...] = (
    SkillContract(
        contract_id="C1",
        title="PM_SESSION 阈值与归档路径",
        severity=Severity.ERROR,
        code_truths=(
            CodeTruth(
                module="auto_pm.application.core.pm_session_service",
                attribute="MAX_FILE_SIZE_KB",
                kind="value",
            ),
            CodeTruth(
                module="auto_pm.application.core.pm_session_service",
                attribute="MAX_FILE_LINES",
                kind="value",
            ),
            CodeTruth(
                module="auto_pm.application.core.pm_session_service",
                attribute="ARCHIVE_DIR_NAME",
                kind="value",
            ),
            CodeTruth(
                module="auto_pm.application.core.paths",
                attribute="PG_CLOSING_DIR",
                kind="value",
            ),
        ),
        literals=(),
        doc_relpaths=(".trae/skills/pm-workflow/refs/pm_session_guide.md",),
    ),
    SkillContract(
        contract_id="C2",
        title="变更状态机 12 态",
        severity=Severity.ERROR,
        code_truths=(
            CodeTruth(
                module="auto_pm.domain.change.constants",
                attribute="STATUS_FLOW",
                kind="keys",
            ),
        ),
        literals=(),
        doc_relpaths=(".trae/skills/pm-workflow/refs/process_gates.md",),
    ),
    SkillContract(
        contract_id="C3",
        title="变更编号格式",
        severity=Severity.ERROR,
        code_truths=(),
        literals=("CHG-{DOMAIN}-{YYYY}-{XXX}",),
        doc_relpaths=(".trae/skills/pm-workflow/refs/handoff_schema.md",),
    ),
    SkillContract(
        contract_id="C4",
        title="门禁口径",
        severity=Severity.WARNING,
        code_truths=(),
        literals=("ruff check", "mypy", "pytest --no-cov -q", "改动文件"),
        doc_relpaths=(
            ".trae/skills/fullstack-engineer/SKILL.md",
            ".trae/skills/pm-workflow/refs/process_gates.md",
        ),
    ),
)
