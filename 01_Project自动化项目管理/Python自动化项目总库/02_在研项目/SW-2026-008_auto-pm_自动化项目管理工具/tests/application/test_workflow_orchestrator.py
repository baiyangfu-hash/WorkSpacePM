"""auto_pm.tests.application.test_workflow_orchestrator - 编排内核单测

覆盖 DEV-300 SRE 工程可靠性与 DEV-210 编程规范：
- 非法项目物理拦截与异常保护
- 方案规划成功流水线（草稿创建/复用、规范动态绑定、审批流转、决策包白名单锁死）
- PM_SESSION 意图自动登记
- 领域规范映射与 SpecRegistry 动态过滤
- 未提供 approver 时保持 draft 与不生成决策包
- WBS 2.2 execute 与 WBS 2.3 resume 骨架方法断言
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auto_pm.application.core.workflow_orchestrator import (
    WorkflowOrchestrator,
)
from auto_pm.contracts.workflow_dtos import (
    WorkflowExecuteRequestDTO,
    WorkflowPlanRequestDTO,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """初始化包含标准 Python 项目的临时工作空间"""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    # 创建标准项目目录
    proj_dir = ws / "02_在研项目" / "SW-2026-001_测试项目"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # 写入项目标志文件
    (proj_dir / ".copier-answers.yml").write_text(
        "project_id: SW-2026-001\nproject_name: 测试项目\nstack: python\n",
        encoding="utf-8",
    )
    (proj_dir / "PM_SESSION_SW-2026-001.md").write_text(
        "# PM_SESSION_SW-2026-001\n\n## 0. Meta\n- project_id: SW-2026-001\n\n## 5. Logs\n- change_log:\n",
        encoding="utf-8",
    )

    # 创建监控与变更单存放根目录（对齐 5 大过程组）
    (proj_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT").mkdir(
        parents=True, exist_ok=True
    )
    (proj_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC").mkdir(
        parents=True, exist_ok=True
    )
    (proj_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-HMI").mkdir(
        parents=True, exist_ok=True
    )
    # 创建版本变更台账
    ledger_file = proj_dir / "04_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台帐.md"
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text("# 版本变更台帐\n\n| 变更编号 | 状态 |\n|---|---|\n", encoding="utf-8")

    return ws


@pytest.fixture
def orchestrator(workspace: Path) -> WorkflowOrchestrator:
    return WorkflowOrchestrator(workspace_root=workspace)


class TestWorkflowOrchestratorPlan:
    """WBS 2.1 WorkflowOrchestrator.plan 测试集"""

    def test_plan_nonexistent_project_intercepted(self, orchestrator: WorkflowOrchestrator) -> None:
        req = WorkflowPlanRequestDTO(
            project_id="NON-EXISTENT-999",
            title="测试非法项目",
            target_files=["src/foo.py"],
        )
        res = orchestrator.plan(req)
        assert res.success is False
        assert res.change_id == ""
        assert res.decision_id == ""
        assert "项目不存在" in res.message

    def test_plan_creates_new_change_and_locks_decision_package(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="新增用户认证模块",
            domain="SCPT",
            change_type="OPT",
            target_files=["src/auth.py", "tests/test_auth.py"],
            approver="architect-pm",
        )
        res = orchestrator.plan(req)

        # 1. 断言返回值
        assert res.success is True
        assert res.project_id == "SW-2026-001"
        assert res.change_id.startswith("CHG-SCPT-")
        assert res.decision_id.startswith("DEC-")
        assert res.specs_bound == ["PM-042", "DEV-210", "DEV-300"]
        assert "规划成功" in res.message

        # 2. 断言决策包物理文件锁死
        dec_file = workspace / ".auto-pm" / "decisions" / f"{res.decision_id}.json"
        assert dec_file.exists()
        dec_data = json.loads(dec_file.read_text(encoding="utf-8"))
        assert dec_data["decision_id"] == res.decision_id
        assert dec_data["change_id"] == res.change_id
        assert dec_data["approver"] == "architect-pm"
        assert dec_data["approved_files"] == ["src/auth.py", "tests/test_auth.py"]

        # 3. 断言 PM_SESSION 意图已记录
        pm_session_file = (
            workspace / "02_在研项目" / "SW-2026-001_测试项目" / "PM_SESSION_SW-2026-001.md"
        )
        pm_content = pm_session_file.read_text(encoding="utf-8")
        assert res.change_id in pm_content
        assert "新增用户认证模块" in pm_content
        assert "src/auth.py" in pm_content

    def test_plan_reuses_existing_draft(self, orchestrator: WorkflowOrchestrator) -> None:
        # 先以无审批人模式生成一个草稿
        req1 = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="待完善的初始草案",
            domain="SCPT",
            approver="",
        )
        res1 = orchestrator.plan(req1)
        assert res1.success is True
        draft_id = res1.change_id
        assert res1.decision_id == ""

        # 再次执行规划，应复用已有草稿并推进批准与生成决策包
        req2 = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="正式方案规划",
            domain="SCPT",
            target_files=["src/reused.py"],
            approver="lead-dev",
        )
        res2 = orchestrator.plan(req2)
        assert res2.success is True
        assert res2.change_id == draft_id
        assert res2.decision_id.startswith("DEC-")

    def test_plan_without_approver_keeps_draft_no_decision(
        self, orchestrator: WorkflowOrchestrator
    ) -> None:
        req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="草稿方案规划",
            domain="SCPT",
            target_files=["src/draft.py"],
            approver="",
        )
        res = orchestrator.plan(req)
        assert res.success is True
        assert res.change_id.startswith("CHG-SCPT-")
        assert res.decision_id == ""

        # 验证单据状态仍为草稿
        cr = orchestrator.change_service.get_change_request(res.change_id, project_id="SW-2026-001")
        assert cr is not None
        assert cr.status == "draft"

    def test_specs_binding_by_domain(self, orchestrator: WorkflowOrchestrator) -> None:
        # PLC 领域
        req_plc = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="PLC逻辑变更",
            domain="PLC",
        )
        res_plc = orchestrator.plan(req_plc)
        assert res_plc.specs_bound == ["PM-042", "LSP-905", "STD-830"]

        # HMI 领域
        req_hmi = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="HMI画面设计",
            domain="HMI",
        )
        res_hmi = orchestrator.plan(req_hmi)
        assert res_hmi.specs_bound == ["PM-042", "DEV-216", "DEV-218"]

        # 未知/默认领域
        req_other = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="其他配置变更",
            domain="OTHER",
        )
        res_other = orchestrator.plan(req_other)
        assert res_other.specs_bound == ["PM-042", "DEV-300"]

    def test_specs_filtered_by_spec_registry(self, workspace: Path) -> None:
        mock_registry = MagicMock()
        mock_registry.raw = {"specs": {"PM-042": {}, "DEV-210": {}}}
        mock_registry.get_spec.side_effect = lambda s: (
            MagicMock() if s in ("PM-042", "DEV-210") else None
        )

        orch = WorkflowOrchestrator(workspace_root=workspace, spec_registry=mock_registry)
        req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="过滤规范测试",
            domain="SCPT",
        )
        res = orch.plan(req)
        # 候选为 ["PM-042", "DEV-210", "DEV-300"]，经过滤仅保留 registry 存在的 ["PM-042", "DEV-210"]
        assert res.specs_bound == ["PM-042", "DEV-210"]

    def test_plan_exception_returns_graceful_failure(
        self, orchestrator: WorkflowOrchestrator
    ) -> None:
        req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="异常容错测试",
        )
        with patch.object(
            orchestrator.change_service,
            "create_change_request",
            side_effect=RuntimeError("Simulated disk error"),
        ):
            res = orchestrator.plan(req)
            assert res.success is False
            assert "Simulated disk error" in res.message


class TestWorkflowOrchestratorSkeletonMethods:
    """恢复能力必须在没有认证断点时明确 fail-closed。"""

    def test_resume_returns_non_resumable_snapshot(
        self, orchestrator: WorkflowOrchestrator
    ) -> None:
        snapshot = orchestrator.resume("SW-2026-001")
        assert snapshot.project_id == "SW-2026-001"
        assert snapshot.git_clean is False
        assert snapshot.next_legal_action == "manual_fact_package_required"
        assert snapshot.metadata["resumable"] is False


class TestWorkflowOrchestratorExecute:
    """WBS 2.2 WorkflowOrchestrator.execute 测试集"""

    def test_execute_nonexistent_project_intercepted(
        self, orchestrator: WorkflowOrchestrator
    ) -> None:
        """非法项目拦截测试"""
        req = WorkflowExecuteRequestDTO(
            project_id="NON-EXISTENT-999",
            change_id="CHG-SCPT-2026-001",
        )
        res = orchestrator.execute(req)
        assert res.success is False
        assert res.status == "failed"
        assert "项目不存在" in res.error

    def test_execute_unapproved_change_rejected(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        """未获批单据（draft/rejected）拒绝执行测试"""
        # 1. 存在性拦截
        req_missing = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id="CHG-SCPT-9999-999",
        )
        res_missing = orchestrator.execute(req_missing)
        assert res_missing.success is False
        assert res_missing.status == "failed"
        assert "变更单不存在" in res_missing.error

        # 2. draft 状态拒绝执行
        cr = orchestrator.change_service.create_change_request(
            project_id="SW-2026-001",
            domain="SCPT",
            business_nature="OPT",
            impact_scope=["MODULE"],
            applicant="tester",
            background="草稿拒绝执行测试",
            necessity="测试未获批单据",
        )
        assert cr.status == "draft"

        req_draft = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cr.change_number,
        )
        res_draft = orchestrator.execute(req_draft)
        assert res_draft.success is False
        assert res_draft.status == "draft"
        assert "仅允许 approved 或 implementing" in res_draft.error

        # 3. rejected 状态拒绝执行
        orchestrator.change_service.transition_status(
            cr.change_number, "submitted", approver="tester", project_id="SW-2026-001"
        )
        orchestrator.change_service.transition_status(
            cr.change_number, "under_review", approver="tester", project_id="SW-2026-001"
        )
        orchestrator.change_service.transition_status(
            cr.change_number,
            "rejected",
            approver="lead",
            comment="门禁未通过驳回",
            project_id="SW-2026-001",
        )

        req_rej = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cr.change_number,
        )
        res_rej = orchestrator.execute(req_rej)
        assert res_rej.success is False
        assert res_rej.status == "rejected"
        assert "仅允许 approved 或 implementing" in res_rej.error

    def test_execute_whitelist_violation_blocked(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        """白名单越界拦截测试"""
        plan_req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="白名单测试变更",
            domain="SCPT",
            target_files=["src/allowed.py"],
            approver="architect",
        )
        plan_res = orchestrator.plan(plan_req)
        assert plan_res.success is True
        cid = plan_res.change_id

        # 请求声明了白名单以外的文件
        exec_req = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cid,
            metadata={"target_files": ["src/unauthorized.py"]},
        )
        res = orchestrator.execute(exec_req)
        assert res.success is False
        assert "超出审批决策白名单范围" in res.error

        # 尝试通过 files 字典写入未授权文件
        exec_req2 = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cid,
            metadata={"files": {"src/evil.py": "evil code"}},
        )
        res2 = orchestrator.execute(exec_req2)
        assert res2.success is False
        assert "超出审批决策白名单范围" in res2.error
        assert not (workspace / "src" / "evil.py").exists()

    def test_execute_atomic_rollback_on_error(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        """沙箱原子回滚测试（模拟异常触发自动回滚，断言物理文件无残留）"""
        plan_req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="原子回滚变更",
            domain="SCPT",
            target_files=["src/existing.py", "src/newly_created.py"],
            approver="architect",
        )
        plan_res = orchestrator.plan(plan_req)
        assert plan_res.success is True
        cid = plan_res.change_id

        # 预先创建基线文件
        existing_file = workspace / "src" / "existing.py"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("baseline content", encoding="utf-8")

        new_file = workspace / "src" / "newly_created.py"
        assert not new_file.exists()

        # 任意回调不属于已批准的文件内容映射，必须在写入前拒绝。
        called = False

        def failing_action(tx: Any) -> None:
            nonlocal called
            called = True
            tx.backup_file(existing_file)
            existing_file.write_text("corrupted content", encoding="utf-8")
            tx.track_created_file(new_file)
            new_file.write_text("partial new content", encoding="utf-8")
            raise RuntimeError("Pipeline failed abruptly during compilation")

        exec_req = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cid,
            metadata={"action": failing_action},
        )

        res = orchestrator.execute(exec_req)
        # 回调从未执行，因此不会产生或回滚不受控副作用。
        assert res.success is False
        assert "metadata.action" in res.error
        assert called is False

        # 断言物理文件原子恢复与清理：无任何残留
        assert existing_file.exists()
        assert existing_file.read_text(encoding="utf-8") == "baseline content"
        assert not new_file.exists()

        # 断言变更单状态被恢复，无残留事务目录
        cr_after = orchestrator.change_service.get_change_request(cid, project_id="SW-2026-001")
        assert cr_after is not None
        assert cr_after.status == "approved"

        tx_dir = workspace / ".auto-pm" / "transactions"
        if tx_dir.exists():
            assert list(tx_dir.iterdir()) == []

    def test_execute_verify_only_mode(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        """只读预检测试 (verify_only=True)"""
        plan_req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="只读预检变更",
            domain="SCPT",
            target_files=["src/readonly.py"],
            approver="architect",
        )
        plan_res = orchestrator.plan(plan_req)
        assert plan_res.success is True
        cid = plan_res.change_id

        exec_req = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cid,
            verify_only=True,
        )
        res = orchestrator.execute(exec_req)

        assert res.success is True
        assert res.status == "verified"
        assert res.files_changed == []
        assert "预检验证通过" in res.message

        # 断言单据状态保持 approved，无实施副作用
        cr = orchestrator.change_service.get_change_request(cid, project_id="SW-2026-001")
        assert cr is not None
        assert cr.status == "approved"

    def test_verify_only_preserves_real_git_sentinel(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        """verify_only must not stage, commit, or alter a real Git sentinel."""
        plan_res = orchestrator.plan(
            WorkflowPlanRequestDTO(
                project_id="SW-2026-001",
                title="Git 哨兵预检",
                domain="SCPT",
                target_files=["src/sentinel_checked.py"],
                approver="architect",
            )
        )
        assert plan_res.success is True
        sentinel = workspace / ".workflow-sentinel"
        sentinel.write_text("immutable", encoding="utf-8")
        for args in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.invalid"],
            ["git", "config", "user.name", "workflow-test"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "baseline"],
        ):
            subprocess.run(args, cwd=workspace, check=True, capture_output=True, text=True)
        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=workspace, check=True, capture_output=True, text=True
        ).stdout.strip()
        status_before = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        result = orchestrator.execute(
            WorkflowExecuteRequestDTO(
                project_id="SW-2026-001", change_id=plan_res.change_id, verify_only=True
            )
        )

        head_after = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=workspace, check=True, capture_output=True, text=True
        ).stdout.strip()
        status_after = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert result.success is True
        assert head_after == head_before
        assert status_after == status_before == ""
        assert sentinel.read_text(encoding="utf-8") == "immutable"

    def test_execute_advances_implementing_to_pending_acceptance(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        """正常执行推进测试 (implementing ➔ pending_acceptance)"""
        target_rel = "src/feature.py"
        plan_req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="正常执行推进变更",
            domain="SCPT",
            target_files=[target_rel],
            approver="lead-dev",
        )
        plan_res = orchestrator.plan(plan_req)
        assert plan_res.success is True
        cid = plan_res.change_id

        exec_req = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cid,
            metadata={
                "files": {target_rel: "print('Feature implemented successfully')"},
                "target_status": "pending_acceptance",
            },
        )
        res = orchestrator.execute(exec_req)

        assert res.success is True
        assert res.status == "pending_acceptance"
        assert target_rel in res.files_changed
        assert "工作流执行成功" in res.message

        # 验证物理文件写入成功
        target_abs = workspace / target_rel
        assert target_abs.exists()
        assert "Feature implemented successfully" in target_abs.read_text(encoding="utf-8")

        # 验证变更单状态流转为 pending_acceptance
        cr = orchestrator.change_service.get_change_request(cid, project_id="SW-2026-001")
        assert cr is not None
        assert cr.status == "pending_acceptance"

    def test_execute_auto_commit_and_audit_log(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        """auto_commit 与审计日志记录测试"""
        plan_req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="Git提交与审计测试",
            domain="SCPT",
            target_files=["src/committed.py"],
            approver="architect",
        )
        plan_res = orchestrator.plan(plan_req)
        assert plan_res.success is True
        cid = plan_res.change_id

        exec_req = WorkflowExecuteRequestDTO(
            project_id="SW-2026-001",
            change_id=cid,
            auto_commit=True,
            commit_message="feat(SCPT): automated commit test",
            metadata={
                "files": {"src/committed.py": "# test commit content"},
            },
        )

        res = orchestrator.execute(exec_req)

        assert res.success is False
        assert res.git_committed is False
        assert res.commit_hash == ""
        assert "Git" in res.error
        assert not (workspace / "src" / "committed.py").exists()


class TestWorkflowOrchestratorEdgeCases:
    """边缘路径与容错分支覆盖"""

    def test_default_workspace_init(self) -> None:
        orch = WorkflowOrchestrator()
        assert isinstance(orch.workspace_root, Path)

    def test_project_found_via_project_service_fallback(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        proj_dir = str(workspace / "02_在研项目" / "SW-2026-001_测试项目")
        mock_info = MagicMock()
        mock_info.project_id = "SW-2026-001"
        mock_info.path = proj_dir

        with (
            patch.object(
                orchestrator.change_service._locator,
                "get_project_path",
                side_effect=[None, proj_dir, proj_dir, proj_dir],
            ),
            patch.object(orchestrator.project_service, "list_projects", return_value=[mock_info]),
        ):
            req = WorkflowPlanRequestDTO(
                project_id="SW-2026-001",
                title="降级项目扫描测试",
                domain="SCPT",
            )
            res = orchestrator.plan(req)
            assert res.success is True

    def test_spec_registry_load_failure_handled_gracefully(self, workspace: Path) -> None:
        mock_registry = MagicMock()
        mock_registry.load.side_effect = RuntimeError("Corrupted registry")
        mock_registry.raw = {}

        orch = WorkflowOrchestrator(workspace_root=workspace, spec_registry=mock_registry)
        req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="规范加载异常容错",
            domain="SCPT",
        )
        res = orch.plan(req)
        assert res.success is True
        assert res.specs_bound == ["PM-042", "DEV-210", "DEV-300"]

    def test_pm_session_creation_when_missing(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        pm_file = workspace / "02_在研项目" / "SW-2026-001_测试项目" / "PM_SESSION_SW-2026-001.md"
        if pm_file.exists():
            pm_file.unlink()

        req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="全新PM_SESSION创建测试",
            domain="SCPT",
        )
        res = orchestrator.plan(req)
        assert res.success is True
        assert pm_file.exists()
        assert "全新PM_SESSION创建测试" in pm_file.read_text(encoding="utf-8")

    def test_pm_session_logs_heading_insertion(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        pm_file = workspace / "02_在研项目" / "SW-2026-001_测试项目" / "PM_SESSION_SW-2026-001.md"
        pm_file.write_text(
            "# PM_SESSION_SW-2026-001\n\n## 5. Logs\n\n- other_log:\n", encoding="utf-8"
        )

        req = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="Logs插入测试",
            domain="SCPT",
        )
        res = orchestrator.plan(req)
        assert res.success is True
        assert "Logs插入测试" in pm_file.read_text(encoding="utf-8")

    def test_plan_advances_from_submitted_and_under_review(
        self, orchestrator: WorkflowOrchestrator, workspace: Path
    ) -> None:
        # 先以无审批人生成 draft
        req1 = WorkflowPlanRequestDTO(
            project_id="SW-2026-001",
            title="状态递进测试",
            domain="SCPT",
        )
        res1 = orchestrator.plan(req1)
        cid = res1.change_id

        # 手动将该单推进到 submitted
        orchestrator.change_service.transition_status(
            cid, "submitted", approver="dev", project_id="SW-2026-001"
        )
        # 再次调用 plan(approver="lead")，验证从 submitted 推进到 approved
        with patch.object(orchestrator.change_service, "list_change_requests", return_value=[]):
            with patch.object(orchestrator.change_service, "create_change_request") as mock_create:
                # 构造 mock 使其返回已有 cid
                mock_cr = MagicMock()
                mock_cr.change_number = cid
                mock_create.return_value = mock_cr

                req2 = WorkflowPlanRequestDTO(
                    project_id="SW-2026-001",
                    title="从submitted推进到approved",
                    domain="SCPT",
                    approver="lead",
                )
                res2 = orchestrator.plan(req2)
                assert res2.success is False
                assert "approved_files" in res2.message

        # 再测试当前已在 under_review 的流转
        # 先退回/新建一个单
        cr_new = orchestrator.change_service.create_change_request(
            project_id="SW-2026-001",
            domain="SCPT",
            business_nature="OPT",
            impact_scope=["MODULE"],
            applicant="dev",
            background="under_review测试",
            necessity="测试",
        )
        orchestrator.change_service.transition_status(
            cr_new.change_number, "submitted", approver="dev", project_id="SW-2026-001"
        )
        orchestrator.change_service.transition_status(
            cr_new.change_number, "under_review", approver="dev", project_id="SW-2026-001"
        )

        with patch.object(orchestrator.change_service, "list_change_requests", return_value=[]):
            with patch.object(orchestrator.change_service, "create_change_request") as mock_create:
                mock_create.return_value = cr_new
                req3 = WorkflowPlanRequestDTO(
                    project_id="SW-2026-001",
                    title="从under_review推进到approved",
                    domain="SCPT",
                    target_files=["src/under_review.py"],
                    approver="director",
                )
                res3 = orchestrator.plan(req3)
                assert res3.success is True
                assert res3.decision_id.startswith("DEC-")
