"""auto_pm.tests.contracts.test_workflow_dtos - 工作流契约 DTO 单元测试

覆盖 TransactionStatus 枚举类型安全性、全字段构造、默认值行为及 to_dict / from_dict 往返序列化。
"""

from __future__ import annotations

import pytest

from auto_pm.contracts.workflow_dtos import (
    TransactionStatus,
    WorkflowExecuteRequestDTO,
    WorkflowExecuteResultDTO,
    WorkflowPlanRequestDTO,
    WorkflowPlanResultDTO,
    WorkflowResumeDTO,
)


class TestTransactionStatus:
    """TransactionStatus 状态枚举测试"""

    def test_enum_members_and_values(self) -> None:
        """验证枚举成员定义与值正确性"""
        assert TransactionStatus.PENDING.value == "pending"
        assert TransactionStatus.ACTIVE.value == "active"
        assert TransactionStatus.COMMITTED.value == "committed"
        assert TransactionStatus.ROLLED_BACK.value == "rolled_back"
        assert TransactionStatus.FAILED.value == "failed"
        assert isinstance(TransactionStatus.PENDING, str)

    def test_enum_type_safety(self) -> None:
        """验证枚举类型安全性及非法值抛错"""
        assert TransactionStatus("pending") is TransactionStatus.PENDING
        assert TransactionStatus("committed") is TransactionStatus.COMMITTED

        with pytest.raises(ValueError):
            TransactionStatus("invalid_status")


class TestWorkflowPlanRequestDTO:
    """WorkflowPlanRequestDTO 测试"""

    def test_default_values(self) -> None:
        """验证默认字段值"""
        dto = WorkflowPlanRequestDTO(
            project_id="SW-2026-008",
            title="Cockpit OS 契约定义",
        )
        assert dto.project_id == "SW-2026-008"
        assert dto.title == "Cockpit OS 契约定义"
        assert dto.change_type == "OPT"
        assert dto.domain == "SCPT"
        assert dto.target_files == []
        assert dto.approver == ""
        assert dto.metadata == {}

    def test_roundtrip_serialization(self) -> None:
        """验证全字段构造与 to_dict / from_dict 往返一致性"""
        dto = WorkflowPlanRequestDTO(
            project_id="SW-2026-008",
            title="Cockpit OS Phase 0",
            change_type="FEAT",
            domain="CORE",
            target_files=["contracts/workflow_dtos.py", "tests/contracts/test_workflow_dtos.py"],
            approver="fubai",
            metadata={"priority": "high", "iteration": 2},
        )
        data = dto.to_dict()
        assert data["project_id"] == "SW-2026-008"
        assert data["title"] == "Cockpit OS Phase 0"
        assert data["change_type"] == "FEAT"
        assert data["domain"] == "CORE"
        assert len(data["target_files"]) == 2
        assert data["approver"] == "fubai"
        assert data["metadata"]["priority"] == "high"

        restored = WorkflowPlanRequestDTO.from_dict(data)
        assert restored == dto
        assert restored.target_files is not dto.target_files
        assert restored.metadata is not dto.metadata

    def test_from_dict_defaults(self) -> None:
        """验证从空或部分字段字典恢复的默认回退"""
        restored = WorkflowPlanRequestDTO.from_dict({})
        assert restored.project_id == ""
        assert restored.title == ""
        assert restored.change_type == "OPT"
        assert restored.domain == "SCPT"
        assert restored.target_files == []
        assert restored.approver == ""
        assert restored.metadata == {}


class TestWorkflowPlanResultDTO:
    """WorkflowPlanResultDTO 测试"""

    def test_default_values(self) -> None:
        """验证默认字段值"""
        dto = WorkflowPlanResultDTO(
            success=True,
            project_id="SW-2026-008",
            change_id="CHG-SCPT-2026-173",
        )
        assert dto.success is True
        assert dto.project_id == "SW-2026-008"
        assert dto.change_id == "CHG-SCPT-2026-173"
        assert dto.decision_id == ""
        assert dto.specs_bound == []
        assert dto.message == ""
        assert dto.metadata == {}

    def test_roundtrip_serialization(self) -> None:
        """验证全字段构造与 to_dict / from_dict 往返一致性"""
        dto = WorkflowPlanResultDTO(
            success=True,
            project_id="SW-2026-008",
            change_id="CHG-SCPT-2026-173",
            decision_id="DEC-20260904-E69C03FE",
            specs_bound=["PM-042", "DEV-210", "DEV-300"],
            message="规划成功并绑定决策包",
            metadata={"gate_checks": 3},
        )
        data = dto.to_dict()
        assert data["success"] is True
        assert data["decision_id"] == "DEC-20260904-E69C03FE"
        assert data["specs_bound"] == ["PM-042", "DEV-210", "DEV-300"]
        assert data["message"] == "规划成功并绑定决策包"

        restored = WorkflowPlanResultDTO.from_dict(data)
        assert restored == dto
        assert restored.specs_bound is not dto.specs_bound
        assert restored.metadata is not dto.metadata

    def test_from_dict_defaults(self) -> None:
        """验证从空字典恢复"""
        restored = WorkflowPlanResultDTO.from_dict({})
        assert restored.success is False
        assert restored.project_id == ""
        assert restored.change_id == ""
        assert restored.decision_id == ""
        assert restored.specs_bound == []
        assert restored.message == ""
        assert restored.metadata == {}


class TestWorkflowExecuteRequestDTO:
    """WorkflowExecuteRequestDTO 测试"""

    def test_default_values(self) -> None:
        """验证默认字段值"""
        dto = WorkflowExecuteRequestDTO(
            project_id="SW-2026-008",
            change_id="CHG-SCPT-2026-173",
        )
        assert dto.project_id == "SW-2026-008"
        assert dto.change_id == "CHG-SCPT-2026-173"
        assert dto.verify_only is False
        assert dto.auto_commit is False
        assert dto.commit_message == ""
        assert dto.actor == "pm-workflow"
        assert dto.metadata == {}

    def test_roundtrip_serialization(self) -> None:
        """验证全字段构造与 to_dict / from_dict 往返一致性"""
        dto = WorkflowExecuteRequestDTO(
            project_id="SW-2026-008",
            change_id="CHG-SCPT-2026-173",
            verify_only=True,
            auto_commit=True,
            commit_message="feat(core): [CHG-SCPT-2026-173] 契约 DTO 落地",
            actor="fullstack-engineer",
            metadata={"retry_count": 1},
        )
        data = dto.to_dict()
        assert data["verify_only"] is True
        assert data["auto_commit"] is True
        assert data["commit_message"] == "feat(core): [CHG-SCPT-2026-173] 契约 DTO 落地"
        assert data["actor"] == "fullstack-engineer"

        restored = WorkflowExecuteRequestDTO.from_dict(data)
        assert restored == dto
        assert restored.metadata is not dto.metadata

    def test_from_dict_defaults(self) -> None:
        """验证从空字典恢复"""
        restored = WorkflowExecuteRequestDTO.from_dict({})
        assert restored.project_id == ""
        assert restored.change_id == ""
        assert restored.verify_only is False
        assert restored.auto_commit is False
        assert restored.commit_message == ""
        assert restored.actor == "pm-workflow"
        assert restored.metadata == {}


class TestWorkflowExecuteResultDTO:
    """WorkflowExecuteResultDTO 测试"""

    def test_default_values(self) -> None:
        """验证默认字段值"""
        dto = WorkflowExecuteResultDTO(
            success=True,
            project_id="SW-2026-008",
            change_id="CHG-SCPT-2026-173",
            status=TransactionStatus.COMMITTED.value,
        )
        assert dto.success is True
        assert dto.project_id == "SW-2026-008"
        assert dto.change_id == "CHG-SCPT-2026-173"
        assert dto.status == "committed"
        assert dto.files_changed == []
        assert dto.ledger_clean is True
        assert dto.git_committed is False
        assert dto.commit_hash == ""
        assert dto.message == ""
        assert dto.error == ""
        assert dto.metadata == {}

    def test_roundtrip_serialization(self) -> None:
        """验证全字段构造与 to_dict / from_dict 往返一致性"""
        dto = WorkflowExecuteResultDTO(
            success=True,
            project_id="SW-2026-008",
            change_id="CHG-SCPT-2026-173",
            status=TransactionStatus.COMMITTED.value,
            files_changed=["auto_pm/contracts/workflow_dtos.py"],
            ledger_clean=True,
            git_committed=True,
            commit_hash="abc12345",
            message="执行完毕并提交",
            error="",
            metadata={"execution_time_s": 1.25},
        )
        data = dto.to_dict()
        assert data["files_changed"] == ["auto_pm/contracts/workflow_dtos.py"]
        assert data["ledger_clean"] is True
        assert data["git_committed"] is True
        assert data["commit_hash"] == "abc12345"

        restored = WorkflowExecuteResultDTO.from_dict(data)
        assert restored == dto
        assert restored.files_changed is not dto.files_changed
        assert restored.metadata is not dto.metadata

    def test_from_dict_defaults(self) -> None:
        """验证从空字典恢复"""
        restored = WorkflowExecuteResultDTO.from_dict({})
        assert restored.success is False
        assert restored.project_id == ""
        assert restored.change_id == ""
        assert restored.status == ""
        assert restored.files_changed == []
        assert restored.ledger_clean is True
        assert restored.git_committed is False
        assert restored.commit_hash == ""
        assert restored.message == ""
        assert restored.error == ""
        assert restored.metadata == {}


class TestWorkflowResumeDTO:
    """WorkflowResumeDTO 测试"""

    def test_default_values(self) -> None:
        """验证默认字段值"""
        dto = WorkflowResumeDTO(
            project_id="SW-2026-008",
            fact_fingerprint="fp-998877",
            git_head="c0ffee",
            git_clean=True,
        )
        assert dto.project_id == "SW-2026-008"
        assert dto.fact_fingerprint == "fp-998877"
        assert dto.git_head == "c0ffee"
        assert dto.git_clean is True
        assert dto.active_changes == []
        assert dto.next_legal_action == ""
        assert dto.read_set == []
        assert dto.metadata == {}

    def test_roundtrip_serialization(self) -> None:
        """验证全字段构造与 to_dict / from_dict 往返一致性"""
        dto = WorkflowResumeDTO(
            project_id="SW-2026-008",
            fact_fingerprint="fp-998877",
            git_head="c0ffee",
            git_clean=False,
            active_changes=["CHG-SCPT-2026-173"],
            next_legal_action="workflow execute",
            read_set=["PM_SESSION.md", "DEC-20260904-E69C03FE.json"],
            metadata={"resumed_from": "saga_log"},
        )
        data = dto.to_dict()
        assert data["fact_fingerprint"] == "fp-998877"
        assert data["git_head"] == "c0ffee"
        assert data["git_clean"] is False
        assert data["active_changes"] == ["CHG-SCPT-2026-173"]
        assert data["next_legal_action"] == "workflow execute"
        assert data["read_set"] == ["PM_SESSION.md", "DEC-20260904-E69C03FE.json"]

        restored = WorkflowResumeDTO.from_dict(data)
        assert restored == dto
        assert restored.active_changes is not dto.active_changes
        assert restored.read_set is not dto.read_set
        assert restored.metadata is not dto.metadata

    def test_from_dict_defaults(self) -> None:
        """验证从空字典恢复"""
        restored = WorkflowResumeDTO.from_dict({})
        assert restored.project_id == ""
        assert restored.fact_fingerprint == ""
        assert restored.git_head == ""
        assert restored.git_clean is False
        assert restored.active_changes == []
        assert restored.next_legal_action == ""
        assert restored.read_set == []
        assert restored.metadata == {}
