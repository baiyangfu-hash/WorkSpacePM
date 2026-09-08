"""验收流程端到端测试（M4-Iter4）

测试 PM-042 V2.2.0 §5.2 定义的完整验收流程：
    implementing → pending_acceptance → accepting → completed
                                                 ↘ implementing（返工）

测试内容：
- 完整验收流程（成功路径）
- 返工路径（accepting → implementing → pending_acceptance → accepting → completed）
- 各阶段门禁校验
- 状态流转合法性校验
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import (
    SpecViolationError,
    TransitionGuardError,
    validate_status_transition,
)

# ── 测试用变更单内容 ────────────────────────────────────


def _build_chg_with_implementation() -> str:
    """构建包含 §7 实施计划和 §9 实施记录的变更单（状态：implementing）"""
    return """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-DOCU-2026-001 |
| 项目名称 | TEST-2026-001 测试项目 |
| 项目编号 | TEST-2026-001 |

### 3.1 技术领域（必选）
| 领域 | 选择 | 说明 |
|------|------|------|
| ☑ **DOCU** 工程文档 | **选中** | 设计说明书 |

### 3.2 业务性质（必选）
| 性质 | 选择 | 典型场景 |
|------|------|----------|
| ☑ **DEF** 缺陷修复 | **选中** | Bug修复 |

### 3.3 影响范围（可多选）
| 范围 | 选择 | 审批要求 |
|------|------|----------|
| ☑ **MODULE** 模块级变更 | **选中** | 项目负责人审批 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-01-15 |
| 预计实施日期 | 2026-01-20 |
| 紧急程度 | ☑一般 □紧急 □非常紧急 |

### 3.5 变更状态
| 字段 | 内容 |
|------|------|
| 变更状态 | implementing |

## 4. 变更原因

**变更背景**：
测试变更背景描述

**变更必要性**：
测试变更必要性描述

## 7. 实施计划

| # | 任务描述 | 负责人 | 预计工时 | 计划开始 | 计划完成 | 依赖任务 |
|---|----------|--------|----------|----------|----------|----------|
| 1 | 修改文档章节 | 张三 | 4h | 2026-01-20 | 2026-01-20 | - |

## 8. 变更审批

### 8.1 审批流程（按影响范围分级）

| 审批环节 | 审批人 | 审批意见 | 审批日期 | 签字/电子签章 |
|----------|--------|----------|----------|---------------|
| **初审** | 李四 | 同意 | 2026-01-16 | 李四 |

### 8.2 审批结论
| 结论 | ☑ 通过 □ 有条件通过 □ 驳回 □ 拒绝 |

## 9. 实施记录

| 日期 | 实施人 | 变更内容 | 实施结果 | 状态 | 备注 |
|------|--------|----------|----------|------|------|
| 2026-01-20 | 张三 | 修改文档 | 完成 | 进行中 | |

## 10. 验证记录

| # | 验证项 | 验证内容 | 验证方法 | 验证结果 | 验证结论 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|----------|--------|----------|
"""


def _build_chg_without_section9() -> str:
    """构建不包含 §9 实施记录的变更单（状态：implementing）"""
    content = _build_chg_with_implementation()
    # 完全移除 §9 章节的表格（仅保留标题，无任何表格行）
    content = content.replace(
        """## 9. 实施记录

| 日期 | 实施人 | 变更内容 | 实施结果 | 状态 | 备注 |
|------|--------|----------|----------|------|------|
| 2026-01-20 | 张三 | 修改文档 | 完成 | 进行中 | |""",
        """## 9. 实施记录

（暂无实施记录）"""
    )
    return content


# ── fixtures ─────────────────────────────────────────────


@pytest.fixture
def acceptance_workspace(tmp_path: Path) -> str:
    """临时工作空间，含 implementing 状态的变更单"""
    project_id = "TEST-2026-001"
    project_path = tmp_path / project_id
    project_path.mkdir(parents=True, exist_ok=True)
    # 创建项目标志文件，使 ChangeFileLocator._is_project_dir 识别为项目目录
    (project_path / f"PM_SESSION_{project_id}.md").write_text(
        "# PM_SESSION\n", encoding="utf-8"
    )
    chg_dir = project_path / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-DOCU"
    chg_dir.mkdir(parents=True, exist_ok=True)
    chg_file = chg_dir / "CHG-DOCU-2026-001.md"
    chg_file.write_text(_build_chg_with_implementation(), encoding="utf-8")

    # 创建台帐目录
    ledger_dir = project_path / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "01_版本变更台帐.md").write_text(
        "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n",
        encoding="utf-8",
    )
    return str(tmp_path)


@pytest.fixture
def acceptance_workspace_no_sec9(tmp_path: Path) -> str:
    """临时工作空间，含 implementing 状态但 §9 为空的变更单"""
    project_id = "TEST-2026-001"
    project_path = tmp_path / project_id
    project_path.mkdir(parents=True, exist_ok=True)
    # 创建项目标志文件，使 ChangeFileLocator._is_project_dir 识别为项目目录
    (project_path / f"PM_SESSION_{project_id}.md").write_text(
        "# PM_SESSION\n", encoding="utf-8"
    )
    chg_dir = project_path / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-DOCU"
    chg_dir.mkdir(parents=True, exist_ok=True)
    chg_file = chg_dir / "CHG-DOCU-2026-001.md"
    chg_file.write_text(_build_chg_without_section9(), encoding="utf-8")

    # 创建台帐目录
    ledger_dir = project_path / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "01_版本变更台帐.md").write_text(
        "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n",
        encoding="utf-8",
    )
    return str(tmp_path)


# ── 状态流转合法性测试 ─────────────────────────────────


class TestAcceptanceStatusFlow:
    """验收流程状态流转合法性测试"""

    def test_implementing_to_pending_acceptance_valid(self) -> None:
        """implementing → pending_acceptance 合法"""
        validate_status_transition("implementing", "pending_acceptance")

    def test_pending_acceptance_to_accepting_valid(self) -> None:
        """pending_acceptance → accepting 合法"""
        validate_status_transition("pending_acceptance", "accepting")

    def test_accepting_to_completed_valid(self) -> None:
        """accepting → completed 合法"""
        validate_status_transition("accepting", "completed")

    def test_accepting_to_implementing_valid(self) -> None:
        """accepting → implementing 合法（返工路径）"""
        validate_status_transition("accepting", "implementing")

    def test_pending_acceptance_to_completed_invalid(self) -> None:
        """pending_acceptance → completed 非法（必须经过 accepting）"""
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("pending_acceptance", "completed")

    def test_implementing_to_accepting_invalid(self) -> None:
        """implementing → accepting 非法（必须经过 pending_acceptance）"""
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("implementing", "accepting")

    def test_completed_to_implementing_invalid(self) -> None:
        """completed → implementing 非法（不可逆）"""
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("completed", "implementing")


# ── 完整验收流程测试（成功路径） ───────────────────────


class TestFullAcceptanceFlow:
    """完整验收流程测试：implementing → pending_acceptance → accepting → completed"""

    def test_full_acceptance_flow(self, acceptance_workspace: str) -> None:
        """完整验收流程（成功路径）"""
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 初始状态：implementing
        cr = svc.get_change_request(chg_number)
        assert cr is not None
        assert cr.status == "implementing"

        # Step 1: implementing → pending_acceptance
        cr = svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        assert cr is not None
        assert cr.status == "pending_acceptance"

        # Step 2: pending_acceptance → accepting
        cr = svc.transition_status(chg_number, "accepting", approver="李四")
        assert cr is not None
        assert cr.status == "accepting"

        # Step 3: accepting → completed
        cr = svc.transition_status(
            chg_number, "completed",
            approver="李四",
            verification_conclusion="全部通过",
        )
        assert cr is not None
        assert cr.status == "completed"

    def test_submit_acceptance_requires_section9(
        self, acceptance_workspace_no_sec9: str
    ) -> None:
        """提交验收时 §9 实施记录为空应抛门禁错误"""
        svc = ChangeService(acceptance_workspace_no_sec9)
        chg_number = "CHG-DOCU-2026-001"

        with pytest.raises(TransitionGuardError, match="§9 实施记录未填写"):
            svc.transition_status(chg_number, "pending_acceptance", approver="张三")

    def test_complete_requires_all_pass(self, acceptance_workspace: str) -> None:
        """完成验收时 verification_conclusion 必须通过规则校验（V0.3.0-M0.5-Phase1）

        规则：包含"通过"且不包含"不通过"/"部分通过"/"未通过"。
        "部分通过"应被拒绝（部分通过不是全部通过）。
        """
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 先走到 accepting 状态
        svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        svc.transition_status(chg_number, "accepting", approver="李四")

        # 尝试用「部分通过」完成验收（应失败）
        with pytest.raises(TransitionGuardError, match="验证结论"):
            svc.transition_status(
                chg_number, "completed",
                approver="李四",
                verification_conclusion="部分通过",
            )


# ── 返工路径测试 ───────────────────────────────────────


class TestReworkFlow:
    """返工路径测试：accepting → implementing → pending_acceptance → accepting → completed"""

    def test_rework_flow(self, acceptance_workspace: str) -> None:
        """返工流程：验收不通过 → 返工 → 重新提交 → 验收通过"""
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 走到 accepting 状态
        svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        cr = svc.transition_status(chg_number, "accepting", approver="李四")
        assert cr is not None
        assert cr.status == "accepting"

        # 验收不通过，返工
        cr = svc.transition_status(
            chg_number, "implementing",
            approver="李四",
            comment="验证不通过，需修改文档格式",
        )
        assert cr is not None
        assert cr.status == "implementing"

        # 重新提交验收
        cr = svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        assert cr is not None
        assert cr.status == "pending_acceptance"

        # 重新验收
        cr = svc.transition_status(chg_number, "accepting", approver="李四")
        assert cr is not None
        assert cr.status == "accepting"

        # 验收通过
        cr = svc.transition_status(
            chg_number, "completed",
            approver="李四",
            verification_conclusion="全部通过",
        )
        assert cr is not None
        assert cr.status == "completed"

    def test_rework_records_comment(self, acceptance_workspace: str) -> None:
        """返工时应记录返工原因到 §9 实施记录"""
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 走到 accepting 状态
        svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        svc.transition_status(chg_number, "accepting", approver="李四")

        # 返工
        svc.transition_status(
            chg_number, "implementing",
            approver="李四",
            comment="文档格式不符合规范",
        )

        # 验证 §9 中记录了返工原因
        cr = svc.get_change_request(chg_number)
        assert cr is not None
        assert cr.has_section_9 is True


# ── 门禁校验测试 ───────────────────────────────────────


class TestAcceptanceGuards:
    """验收流程门禁校验测试"""

    def test_pending_acceptance_guard_passes_with_section9(
        self, acceptance_workspace: str
    ) -> None:
        """§9 有实施记录时，pending_acceptance 门禁通过"""
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        cr = svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        assert cr is not None
        assert cr.status == "pending_acceptance"

    def test_pending_acceptance_guard_fails_without_section9(
        self, acceptance_workspace_no_sec9: str
    ) -> None:
        """§9 无实施记录时，pending_acceptance 门禁失败"""
        svc = ChangeService(acceptance_workspace_no_sec9)
        chg_number = "CHG-DOCU-2026-001"

        with pytest.raises(TransitionGuardError, match="§9"):
            svc.transition_status(chg_number, "pending_acceptance", approver="张三")

    def test_accepting_has_no_extra_guards(
        self, acceptance_workspace: str
    ) -> None:
        """pending_acceptance → accepting 无额外门禁"""
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        # 无 approver/comment 也应通过
        cr = svc.transition_status(chg_number, "accepting")
        assert cr is not None
        assert cr.status == "accepting"

    def test_completed_guard_requires_all_pass(
        self, acceptance_workspace: str
    ) -> None:
        """accepting → completed 必须 verification_conclusion 通过规则校验（V0.3.0-M0.5-Phase1）

        规则：包含"通过"且不包含"不通过"/"部分通过"/"未通过"。
        "部分通过"应被拒绝（部分通过不是全部通过）。
        """
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        svc.transition_status(chg_number, "accepting", approver="李四")

        # 部分通过应失败
        with pytest.raises(TransitionGuardError):
            svc.transition_status(
                chg_number, "completed",
                approver="李四",
                verification_conclusion="部分通过",
            )

    def test_rework_has_no_extra_guards(
        self, acceptance_workspace: str
    ) -> None:
        """accepting → implementing（返工）无额外门禁"""
        svc = ChangeService(acceptance_workspace)
        chg_number = "CHG-DOCU-2026-001"

        svc.transition_status(chg_number, "pending_acceptance", approver="张三")
        svc.transition_status(chg_number, "accepting", approver="李四")

        # 无 comment 也应通过（返工无额外门禁）
        cr = svc.transition_status(chg_number, "implementing", approver="李四")
        assert cr is not None
        assert cr.status == "implementing"


# ── 状态标签测试 ───────────────────────────────────────


class TestAcceptanceStatusLabels:
    """验收流程状态标签测试"""

    def test_status_labels_exist(self) -> None:
        """验收流程状态标签存在"""
        from auto_pm.change.constants import STATUS_LABELS

        assert STATUS_LABELS["pending_acceptance"] == "待验收"
        assert STATUS_LABELS["accepting"] == "验收中"
        assert STATUS_LABELS["completed"] == "已完成"

    def test_status_flow_includes_acceptance_states(self) -> None:
        """STATUS_FLOW 包含验收流程状态"""
        from auto_pm.change.constants import STATUS_FLOW

        assert "pending_acceptance" in STATUS_FLOW
        assert "accepting" in STATUS_FLOW
        assert "completed" in STATUS_FLOW
        assert "pending_acceptance" in STATUS_FLOW["implementing"]
        assert "accepting" in STATUS_FLOW["pending_acceptance"]
        assert "completed" in STATUS_FLOW["accepting"]
        assert "implementing" in STATUS_FLOW["accepting"]  # 返工路径
