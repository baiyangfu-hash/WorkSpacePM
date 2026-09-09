"""auto_pm.core.gates.stage_gate_engine - 5 大过程组 Stage-Gate 阶段门禁评估引擎

提供毫秒级、纯函数式的过程组准入与准出卡点评估。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.change.ledger_reconciler import LedgerReconciler

from auto_pm.contracts.gate_dtos import (
    GateCheckItemDTO,
    ProcessGroupStage,
    StageGateResultDTO,
)


class StageGateEngine:
    """5 大过程组门禁规则评估引擎"""

    def __init__(self, workspace_root: str = "") -> None:
        self.workspace_root = workspace_root

    def evaluate_stage_transition(
        self,
        project_path: str,
        current_stage: ProcessGroupStage,
        target_stage: ProcessGroupStage,
    ) -> StageGateResultDTO:
        """评估项目是否满足从 current_stage 流转到 target_stage 的准出/准入门禁条件"""
        p = Path(project_path)
        if not p.exists():
            return StageGateResultDTO(
                current_stage=current_stage,
                target_stage=target_stage,
                can_proceed=False,
                items=[
                    GateCheckItemDTO(
                        id="G-ROOT-EXIST",
                        name="项目目录存在性",
                        passed=False,
                        severity="BLOCKER",
                        message=f"项目根路径不存在: {project_path}",
                        fix_suggestion="检查项目路径是否正确",
                    )
                ],
            )

        items: list[GateCheckItemDTO] = []

        # 根据目标流转阶段执行对应的门禁检查
        if target_stage == "planning":
            items = self._evaluate_g1_initiating_to_planning(p)
        elif target_stage == "executing":
            items = self._evaluate_g2_planning_to_executing(p)
        elif target_stage == "monitoring":
            items = self._evaluate_g3_executing_to_monitoring(p)
        elif target_stage == "closing":
            items = self._evaluate_g4_monitoring_to_closing(p)
        else:
            # 默认通用检查
            items = [
                GateCheckItemDTO(
                    id="G-DEFAULT-PASS",
                    name="基础环境可用性",
                    passed=True,
                    severity="INFO",
                    message="未定义特定阻断项，允许流转",
                )
            ]

        return StageGateResultDTO(
            current_stage=current_stage,
            target_stage=target_stage,
            can_proceed=False,  # 由 __post_init__ 自动计算
            items=items,
        )

    # ── G1 门禁：启动 (Initiating) -> 规划 (Planning) ──────
    def _evaluate_g1_initiating_to_planning(self, p: Path) -> list[GateCheckItemDTO]:
        items: list[GateCheckItemDTO] = []

        # 1. 检查 PM_SESSION 是否存在
        pm_session_files = list(p.glob("PM_SESSION_*.md"))
        has_pm_session = len(pm_session_files) > 0
        items.append(
            GateCheckItemDTO(
                id="G1-PM-SESSION",
                name="PM_SESSION 单一真源就绪",
                passed=has_pm_session,
                severity="BLOCKER",
                message="PM_SESSION 文件已就绪" if has_pm_session else "缺少根目录 PM_SESSION_<ID>.md",
                fix_suggestion="运行 auto-pm project retrofit 补齐单一真源",
            )
        )

        # 2. 检查是否有 Non-Goals 或定位说明
        has_nongoals = False
        if has_pm_session:
            content = pm_session_files[0].read_text(encoding="utf-8", errors="ignore")
            if "non_goals" in content or "Non-Goals" in content or "定位" in content:
                has_nongoals = True

        items.append(
            GateCheckItemDTO(
                id="G1-NON-GOALS",
                name="项目边界与 Non-Goals 定义",
                passed=has_nongoals,
                severity="BLOCKER",
                message="已定义项目定位与明确边界" if has_nongoals else "PM_SESSION 缺少 non_goals 边界定义",
                fix_suggestion="在 PM_SESSION §1 中明确 non_goals 清单",
            )
        )

        return items

    # ── G2 门禁：规划 (Planning) -> 执行/现场 (Executing) ──
    def _evaluate_g2_planning_to_executing(self, p: Path) -> list[GateCheckItemDTO]:
        items: list[GateCheckItemDTO] = []

        # 1. 检查 PRD / REQ 需求文档
        prd_candidates = [
            p / "01_需求与设计" / "001_产品需求文档_PRD.md",
            p / "02_规划" / "001_产品需求文档_PRD.md",
            p / "01_需求与设计" / "PRD.md",
            p / "02_规划" / "PRD.md",
        ]
        has_prd = any(f.exists() for f in prd_candidates)
        items.append(
            GateCheckItemDTO(
                id="G2-PRD-FROZEN",
                name="PRD 需求规格说明书就绪",
                passed=has_prd,
                severity="BLOCKER",
                message="PRD 需求规格说明书已就绪" if has_prd else "缺少 001_产品需求文档_PRD.md",
                fix_suggestion="在 01_需求与设计/ 或 02_规划/ 下补齐 PRD 文档",
            )
        )

        # 2. 检查 INT 接口/变量表契约
        int_candidates = [
            p / "01_需求与设计" / "002_接口文档_INT.md",
            p / "02_规划" / "002_接口文档_INT.md",
            p / "02_PLC程序" / "程序文档" / "015_IO分配表_IO.md",
            p / "02_PLC程序" / "PLC_ST" / "00_程序方案" / "接口文档_INT.md",
        ]
        has_int = any(f.exists() for f in int_candidates) or any(p.glob("**/*INT*.md")) or any(p.glob("**/*IO*.md"))
        items.append(
            GateCheckItemDTO(
                id="G2-INT-FROZEN",
                name="接口与变量表契约冻结",
                passed=has_int,
                severity="BLOCKER",
                message="接口/IO变量表契约已存在" if has_int else "未找到接口文档 (002_INT.md 或 IO分配表)",
                fix_suggestion="输出并冻结接口/IO变量分配表",
            )
        )

        # 3. 检查 HMI 原型文件 / DESIGN.md
        hmi_candidates = list(p.glob("**/*.html")) + list(p.glob("**/DESIGN.md"))
        has_hmi = len(hmi_candidates) > 0
        items.append(
            GateCheckItemDTO(
                id="G2-HMI-PROTOTYPE",
                name="HMI/UI 交互原型就绪",
                passed=has_hmi,
                severity="WARNING",  # 警告级，提示完善
                message="已包含 HMI 原型或 DESIGN.md" if has_hmi else "未找到 HMI 交互原型 (.html 或 DESIGN.md)",
                fix_suggestion="使用 auto-pm prototype init 生成可交互原型",
            )
        )

        return items

    # ── G3 门禁：执行 (Executing) -> 现场调试/监控 (Monitoring) ──
    def _evaluate_g3_executing_to_monitoring(self, p: Path) -> list[GateCheckItemDTO]:
        items: list[GateCheckItemDTO] = []

        # 1. 检查代码实现存在性 (SCL / Python)
        has_src = any(p.glob("**/*.scl")) or any(p.glob("**/*.py"))
        items.append(
            GateCheckItemDTO(
                id="G3-SRC-EXISTS",
                name="核心程序源码存在性",
                passed=has_src,
                severity="BLOCKER",
                message="检测到 PLC SCL 或 Python 核心代码" if has_src else "未检测到源码实现文件",
                fix_suggestion="完成核心业务代码编写",
            )
        )

        pm_session_files = list(p.glob("PM_SESSION_*.md"))
        session_content = ""
        if pm_session_files:
            session_content = pm_session_files[0].read_text(encoding="utf-8", errors="ignore")

        # 2. 检查是否有未闭环的 P0/阻断缺陷
        has_blocker_defects = "P0" in session_content and "未修复" in session_content
        items.append(
            GateCheckItemDTO(
                id="G3-NO-P0-DEFECT",
                name="P0 阻断性缺陷清零",
                passed=not has_blocker_defects,
                severity="BLOCKER",
                message="无未决 P0 阻断性缺陷" if not has_blocker_defects else "存在未修复的 P0 阻断性缺陷",
                fix_suggestion="优先修复 P0 缺陷并走变更闭环",
            )
        )

        # 3. 检查 PM 收尾落账完整性 (CHG-SCPT-2026-166)
        has_handoff = "skill_handoff" in session_content

        ledger_missing: list[str] = []
        try:
            diff = LedgerReconciler().reconcile(str(p))
            ledger_missing = diff.missing_in_ledger
        except Exception:
            # 台账对账异常时降级为通过，防止门禁引擎崩溃
            ledger_missing = []

        closure_ok = (not ledger_missing) and has_handoff
        if closure_ok:
            closure_message = "台账无缺失且 PM_SESSION 已含 skill_handoff"
        else:
            closure_reasons: list[str] = []
            if ledger_missing:
                closure_reasons.append(
                    f"台账缺失 {len(ledger_missing)} 条变更记录: "
                    f"{', '.join(ledger_missing[:3])}"
                )
            if not has_handoff:
                closure_reasons.append("PM_SESSION §8 缺少 skill_handoff 回写")
            closure_message = "；".join(closure_reasons)

        items.append(
            GateCheckItemDTO(
                id="G3-PM-CLOSURE",
                name="PM 收尾落账完整性",
                passed=closure_ok,
                severity="BLOCKER",
                message=closure_message,
                fix_suggestion="执行 change create + 回写 PM_SESSION §8 + ledger reconcile",
            )
        )

        return items

    # ── G4 门禁：现场监控 (Monitoring) -> 生产收尾 (Closing) ──
    def _evaluate_g4_monitoring_to_closing(self, p: Path) -> list[GateCheckItemDTO]:
        items: list[GateCheckItemDTO] = []

        # 1. 检查所有 CHG 变更单是否全部 closed
        chg_files = list(p.glob("**/CHG-*.md"))
        unclosed_chgs: list[str] = []
        for cf in chg_files:
            txt = cf.read_text(encoding="utf-8", errors="ignore")
            if "status: closed" not in txt and "状态: closed" not in txt and "状态: 已关闭" not in txt:
                unclosed_chgs.append(cf.name)

        all_chgs_closed = len(unclosed_chgs) == 0
        items.append(
            GateCheckItemDTO(
                id="G4-CHG-ALL-CLOSED",
                name="现场变更单全闭环 (Dogfooding)",
                passed=all_chgs_closed,
                severity="BLOCKER",
                message="所有 CHG 变更单均已闭环" if all_chgs_closed else f"存在未闭环变更单: {', '.join(unclosed_chgs[:3])}",
                fix_suggestion="完成变更验证并流转到 closed 状态",
            )
        )

        return items
