"""PLC-HMI 概念映射：SFB 库函数（技能文档↔代码契约漂移对账器（SHC-017）契约清单）

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

活动技能文档↔代码契约漂移对账器契约清单。

仅对仍处于活动状态的技能文档校验必要工程门禁。已弃用或隔离的技能不得
继续作为治理镜像源。本模块定义数据模型与活动契约清单，真源提取与文档校验
逻辑位于 checker_base.SkillContractDriftChecker。
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
        contract_id="C4",
        title="门禁口径",
        severity=Severity.WARNING,
        code_truths=(),
        literals=("ruff check", "mypy", "pytest --no-cov -q", "改动文件"),
        doc_relpaths=(".trae/skills/fullstack-engineer/SKILL.md",),
    ),
)
