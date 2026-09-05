"""auto_pm.contracts.workflow_dtos - Cockpit OS 工作流核心契约层 DTO

遵循 Clean Architecture 强类型规范与 DEV-300 Google SRE 规范，
定义工作流规划、执行、恢复、事务状态的核心数据结构。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TransactionStatus(str, Enum):
    """Saga / 工作流事务状态枚举"""

    PENDING = "pending"
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class WorkflowPlanRequestDTO:
    """工作流规划请求 DTO"""

    project_id: str
    title: str
    change_type: str = "OPT"
    domain: str = "SCPT"
    target_files: list[str] = field(default_factory=list)
    approver: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将 DTO 转换为字典"""
        return {
            "project_id": self.project_id,
            "title": self.title,
            "change_type": self.change_type,
            "domain": self.domain,
            "target_files": list(self.target_files),
            "approver": self.approver,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowPlanRequestDTO:
        """从字典还原 DTO"""
        return cls(
            project_id=str(data.get("project_id", "")),
            title=str(data.get("title", "")),
            change_type=str(data.get("change_type", "OPT")),
            domain=str(data.get("domain", "SCPT")),
            target_files=[str(f) for f in data.get("target_files", [])],
            approver=str(data.get("approver", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorkflowPlanResultDTO:
    """工作流规划执行结果 DTO"""

    success: bool
    project_id: str
    change_id: str
    decision_id: str = ""
    specs_bound: list[str] = field(default_factory=list)
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将 DTO 转换为字典"""
        return {
            "success": self.success,
            "project_id": self.project_id,
            "change_id": self.change_id,
            "decision_id": self.decision_id,
            "specs_bound": list(self.specs_bound),
            "message": self.message,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowPlanResultDTO:
        """从字典还原 DTO"""
        return cls(
            success=bool(data.get("success", False)),
            project_id=str(data.get("project_id", "")),
            change_id=str(data.get("change_id", "")),
            decision_id=str(data.get("decision_id", "")),
            specs_bound=[str(s) for s in data.get("specs_bound", [])],
            message=str(data.get("message", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorkflowExecuteRequestDTO:
    """工作流执行请求 DTO"""

    project_id: str
    change_id: str
    verify_only: bool = False
    auto_commit: bool = False
    commit_message: str = ""
    actor: str = "pm-workflow"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将 DTO 转换为字典"""
        return {
            "project_id": self.project_id,
            "change_id": self.change_id,
            "verify_only": self.verify_only,
            "auto_commit": self.auto_commit,
            "commit_message": self.commit_message,
            "actor": self.actor,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowExecuteRequestDTO:
        """从字典还原 DTO"""
        return cls(
            project_id=str(data.get("project_id", "")),
            change_id=str(data.get("change_id", "")),
            verify_only=bool(data.get("verify_only", False)),
            auto_commit=bool(data.get("auto_commit", False)),
            commit_message=str(data.get("commit_message", "")),
            actor=str(data.get("actor", "pm-workflow")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorkflowExecuteResultDTO:
    """工作流执行结果 DTO"""

    success: bool
    project_id: str
    change_id: str
    status: str
    files_changed: list[str] = field(default_factory=list)
    ledger_clean: bool = True
    git_committed: bool = False
    commit_hash: str = ""
    message: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将 DTO 转换为字典"""
        return {
            "success": self.success,
            "project_id": self.project_id,
            "change_id": self.change_id,
            "status": self.status,
            "files_changed": list(self.files_changed),
            "ledger_clean": self.ledger_clean,
            "git_committed": self.git_committed,
            "commit_hash": self.commit_hash,
            "message": self.message,
            "error": self.error,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowExecuteResultDTO:
        """从字典还原 DTO"""
        return cls(
            success=bool(data.get("success", False)),
            project_id=str(data.get("project_id", "")),
            change_id=str(data.get("change_id", "")),
            status=str(data.get("status", "")),
            files_changed=[str(f) for f in data.get("files_changed", [])],
            ledger_clean=bool(data.get("ledger_clean", True)),
            git_committed=bool(data.get("git_committed", False)),
            commit_hash=str(data.get("commit_hash", "")),
            message=str(data.get("message", "")),
            error=str(data.get("error", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorkflowResumeDTO:
    """工作流恢复与快照 DTO"""

    project_id: str
    fact_fingerprint: str
    git_head: str
    git_clean: bool
    active_changes: list[str] = field(default_factory=list)
    next_legal_action: str = ""
    read_set: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将 DTO 转换为字典"""
        return {
            "project_id": self.project_id,
            "fact_fingerprint": self.fact_fingerprint,
            "git_head": self.git_head,
            "git_clean": self.git_clean,
            "active_changes": list(self.active_changes),
            "next_legal_action": self.next_legal_action,
            "read_set": list(self.read_set),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowResumeDTO:
        """从字典还原 DTO"""
        return cls(
            project_id=str(data.get("project_id", "")),
            fact_fingerprint=str(data.get("fact_fingerprint", "")),
            git_head=str(data.get("git_head", "")),
            git_clean=bool(data.get("git_clean", False)),
            active_changes=[str(c) for c in data.get("active_changes", [])],
            next_legal_action=str(data.get("next_legal_action", "")),
            read_set=[str(r) for r in data.get("read_set", [])],
            metadata=dict(data.get("metadata", {})),
        )
