"""归档流程端到端测试（M4-Iter5）

测试 PM-042 V2.3.0 §5.2 定义的归档流程：
    completed → archived（终态）

测试内容：
- 归档流程成功路径
- 归档门禁校验（仅 completed 状态可归档）
- archived 终态不可再流转
- 状态流转合法性校验
- 完整流程：implementing → ... → completed → archived
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import (
    SpecViolationError,
    validate_status_transition,
)

# ── 测试用变更单内容 ────────────────────────────────────


def _build_completed_chg() -> str:
    """构建 completed 状态的变更单（含完整验收记录）"""
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
| 变更状态 | completed |

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
| 1 | 实施完成验证 | 所有变更项已实施 | 文档审查 | 通过 | 通过 ☑全部通过 | 李四 | 2026-01-21 |
"""


def _build_implementing_chg() -> str:
    """构建 implementing 状态的变更单"""
    content = _build_completed_chg()
    content = content.replace("| 变更状态 | completed |", "| 变更状态 | implementing |")
    return content


# ── fixtures ─────────────────────────────────────────────


@pytest.fixture
def archive_workspace(tmp_path: Path) -> str:
    """临时工作空间，含 completed 状态的变更单"""
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
    chg_file.write_text(_build_completed_chg(), encoding="utf-8")

    # 创建台帐目录
    ledger_dir = project_path / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "01_版本变更台帐.md").write_text(
        "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n",
        encoding="utf-8",
    )
    return str(tmp_path)


@pytest.fixture
def implementing_workspace(tmp_path: Path) -> str:
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
    chg_file.write_text(_build_implementing_chg(), encoding="utf-8")

    # 创建台帐目录
    ledger_dir = project_path / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "01_版本变更台帐.md").write_text(
        "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n",
        encoding="utf-8",
    )
    return str(tmp_path)


# ── 状态流转合法性测试 ─────────────────────────────────


class TestArchiveStatusFlow:
    """归档流程状态流转合法性测试"""

    def test_completed_to_archived_valid(self) -> None:
        """completed → archived 合法"""
        validate_status_transition("completed", "archived")

    def test_completed_to_closed_valid(self) -> None:
        """completed → closed 合法"""
        validate_status_transition("completed", "closed")

    def test_archived_is_terminal_state(self) -> None:
        """archived 是终态，无合法的下一状态"""
        from auto_pm.change.constants import STATUS_FLOW
        assert STATUS_FLOW["archived"] == set()

    def test_closed_is_terminal_state(self) -> None:
        """closed 是终态，无合法的下一状态"""
        from auto_pm.change.constants import STATUS_FLOW
        assert STATUS_FLOW["closed"] == set()

    def test_archived_to_any_invalid(self) -> None:
        """archived → 任何状态都非法"""
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("archived", "completed")
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("archived", "implementing")

    def test_implementing_to_archived_invalid(self) -> None:
        """implementing → archived 非法（必须先完成验收）"""
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("implementing", "archived")

    def test_pending_acceptance_to_archived_invalid(self) -> None:
        """pending_acceptance → archived 非法"""
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("pending_acceptance", "archived")


# ── 归档流程测试 ───────────────────────────────────────


class TestArchiveFlow:
    """归档流程测试：completed → archived"""

    def test_archive_from_completed(self, archive_workspace: str) -> None:
        """completed 状态可以归档"""
        svc = ChangeService(archive_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 初始状态：completed
        cr = svc.get_change_request(chg_number)
        assert cr is not None
        assert cr.status == "completed"

        # 归档
        cr = svc.transition_status(chg_number, "archived", approver="管理员")
        assert cr is not None
        assert cr.status == "archived"

    def test_archive_from_implementing_fails(
        self, implementing_workspace: str
    ) -> None:
        """implementing 状态不能直接归档"""
        svc = ChangeService(implementing_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 状态流转合法性校验应先失败
        with pytest.raises(SpecViolationError, match="状态流转"):
            svc.transition_status(chg_number, "archived", approver="管理员")

    def test_archived_is_terminal(self, archive_workspace: str) -> None:
        """archived 状态不可再流转"""
        svc = ChangeService(archive_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 先归档
        svc.transition_status(chg_number, "archived", approver="管理员")

        # 尝试从 archived 流转到其他状态应失败
        with pytest.raises(SpecViolationError, match="状态流转"):
            svc.transition_status(chg_number, "completed", approver="管理员")
        with pytest.raises(SpecViolationError, match="状态流转"):
            svc.transition_status(chg_number, "implementing", approver="管理员")


# ── 归档门禁测试 ───────────────────────────────────────


class TestArchiveGuards:
    """归档门禁校验测试"""

    def test_archive_guard_passes_for_completed(
        self, archive_workspace: str
    ) -> None:
        """completed 状态归档门禁通过"""
        svc = ChangeService(archive_workspace)
        chg_number = "CHG-DOCU-2026-001"

        cr = svc.transition_status(chg_number, "archived", approver="管理员")
        assert cr is not None
        assert cr.status == "archived"

    def test_archive_from_implementing_fails(
        self, implementing_workspace: str
    ) -> None:
        """非 completed 状态归档门禁失败"""
        svc = ChangeService(implementing_workspace)
        chg_number = "CHG-DOCU-2026-001"

        # 状态流转合法性校验应先失败（implementing → archived 不在 STATUS_FLOW 中）
        with pytest.raises(SpecViolationError, match="状态流转"):
            svc.transition_status(chg_number, "archived", approver="管理员")


# ── 完整流程测试：实施 → 验收 → 完成 → 归档 ───────────


class TestFullFlowToArchive:
    """完整流程测试：implementing → pending_acceptance → accepting → completed → archived"""

    def test_full_flow_to_archive(
        self, implementing_workspace: str
    ) -> None:
        """从实施到归档的完整流程"""
        svc = ChangeService(implementing_workspace)
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

        # Step 4: completed → archived
        cr = svc.transition_status(chg_number, "archived", approver="管理员")
        assert cr is not None
        assert cr.status == "archived"


# ── 状态标签测试 ───────────────────────────────────────


class TestArchiveStatusLabels:
    """归档流程状态标签测试"""

    def test_status_labels_exist(self) -> None:
        """归档流程状态标签存在"""
        from auto_pm.change.constants import STATUS_LABELS

        assert STATUS_LABELS["completed"] == "已完成"
        assert STATUS_LABELS["archived"] == "已归档"
        assert STATUS_LABELS["closed"] == "已关闭"

    def test_status_flow_includes_archive_states(self) -> None:
        """STATUS_FLOW 包含归档流程状态"""
        from auto_pm.change.constants import STATUS_FLOW

        assert "completed" in STATUS_FLOW
        assert "archived" in STATUS_FLOW
        assert "closed" in STATUS_FLOW
        assert "archived" in STATUS_FLOW["completed"]
        assert "closed" in STATUS_FLOW["completed"]
        assert STATUS_FLOW["archived"] == set()  # 终态
        assert STATUS_FLOW["closed"] == set()    # 终态
