"""PLC-HMI 概念映射：SFB 库函数（门禁检查器（变更状态/审批流校验））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变更单状态流转门禁检查器（M3-Iter2 从 ChangeService 拆分）

负责 PM-042 V2.2.0/V2.3.0 §5.3 定义的状态流转门禁条件校验。

ChangeService 通过组合方式使用本模块，保持向后兼容。
"""

from __future__ import annotations

import logging

from auto_pm.change.constants import (
    ChangeRequest,
    TransitionGuardError,
)

log = logging.getLogger(__name__)


class TransitionGuardChecker:
    """变更单状态流转门禁检查器

    读取变更单当前内容，校验是否满足目标状态的前置条件。
    不满足则抛 TransitionGuardError，列出所有未满足的条件。

    门禁规则完整清单见 PM-042 规范第四章。
    completed 状态的门禁校验已提升至 transition_status 方法中
    （参数级前置拦截），此处不再重复。
    """

    def check(
        self,
        cr: ChangeRequest,
        target_status: str,
        approver: str,
        comment: str,
    ) -> None:
        """检查流转门禁条件

        Args:
            cr: 当前变更单对象（已解析）
            target_status: 目标状态
            approver: 审批人
            comment: 审批意见/返工原因

        Raises:
            TransitionGuardError: 门禁条件未满足
        """
        violations: list[str] = []

        if target_status == "submitted":
            # [第四章] draft → submitted: 提交变更
            # 门禁: §3全部填写 + §4非空
            if not cr.domain:
                violations.append("§3.1 技术领域未填写")
            if not cr.business_nature:
                violations.append("§3.2 业务性质未填写")
            if not cr.impact_scope:
                violations.append("§3.3 影响范围未填写")
            if not cr.applicant or cr.applicant == "待补充":
                violations.append("§3.4 变更申请人未填写")
            if not cr.has_section_4:
                violations.append("§4 变更原因未填写")

        elif target_status == "approved":
            # [第四章] under_review → approved: 批准通过
            # 门禁: §8.1有审批记录 + 审批人非空
            if not cr.has_section_8_approval and not approver:
                violations.append("§8.1 无审批记录，且未提供审批人")
            if not approver:
                violations.append("审批人(approver)不能为空")

        elif target_status == "conditionally_approved":
            # [第四章] under_review → conditionally_approved: 有条件批准
            # 门禁: 同approved + comment非空
            if not cr.has_section_8_approval and not approver:
                violations.append("§8.1 无审批记录，且未提供审批人")
            if not approver:
                violations.append("审批人(approver)不能为空")
            if not comment:
                violations.append("有条件通过必须附条件说明(comment)")

        elif target_status == "rejected":
            # [第四章] under_review → rejected: 驳回
            # 门禁: 审批人+comment非空
            if not approver:
                violations.append("审批人(approver)不能为空")
            if not comment:
                violations.append("驳回必须附原因(comment)")

        elif target_status == "implementing":
            # [第四章] 两条路径进入 implementing:
            #   路径A: approved/conditionally_approved → implementing（首次实施）
            #     门禁: §7 实施计划至少一条任务
            #   路径B: accepting → implementing（验证不通过，返工重做）
            #     门禁: 无额外门禁（第四章 路径B）
            if cr.status in ("approved", "conditionally_approved"):
                if not cr.has_section_7:
                    violations.append("§7 实施计划未填写（至少一条任务）")
                # C-10: conditionally_approved → implementing 需确认条件已满足
                if cr.status == "conditionally_approved" and not comment:
                    violations.append("有条件批准进入实施必须附条件确认说明(comment)")
            # 路径B（返工）：不施加额外门禁，允许验证不通过时返回重做

        elif target_status == "archived":
            # [PM-042 V2.3.0 §5.2] completed → archived: 归档
            # 门禁: 当前状态必须为 completed
            if cr.status != "completed":
                violations.append(f"仅 'completed' 状态可归档，当前状态为 '{cr.status}'")

        elif target_status == "draft":
            # [PM-042 V2.3.0 §5.2] rejected → draft: 重新起草
            # 门禁: 必须附修改原因
            if cr.status == "rejected" and not comment:
                violations.append("驳回后重新起草必须附修改原因(comment)")

        elif target_status == "pending_acceptance":
            # [第四章] implementing → pending_acceptance: 提交验收
            # 门禁: §9 实施记录至少一条
            if not cr.has_section_9:
                violations.append("§9 实施记录未填写（至少一条实施记录）")

        elif target_status == "accepting":
            # pending_acceptance → accepting: 无额外门禁（PM-042 V2.2.0 第四章）
            pass

        # completed 的门禁已提升至 transition_status 方法中作为参数级前置校验，
        # 不在此处重复检查，避免与参数级校验逻辑冲突。

        # 深度实质内容门禁（杜绝空壳变更单 Phantom Ticket）
        from auto_pm.domain.change.substance_checker import SubstanceChecker
        substance_violations = SubstanceChecker.check_substance(cr, target_status=target_status)
        if substance_violations:
            violations.extend(substance_violations)

        if violations:
            msg = (
                f"变更单 {cr.change_number} 不满足 '{target_status}' 的门禁条件:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
            log.error("门禁校验失败: %s", msg)
            raise TransitionGuardError(msg)
