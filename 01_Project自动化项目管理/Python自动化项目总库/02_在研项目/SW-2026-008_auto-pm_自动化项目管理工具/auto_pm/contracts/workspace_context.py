"""Read-only, fail-closed workspace context contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ContextProject(BaseModel):
    """The project established by a verifiable workspace anchor."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    name: str
    path: str
    stack: str
    phase: str
    source: str


class ContextEvidence(BaseModel):
    """One bounded input that was read while resolving an invocation."""

    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str


# 项目性质、项目状态（CHG-SCPT-2026-650，RC-004）：登记表是这两栏的唯一真源。存英文值，界面显示中文，一一对应。
# 两栏都可以缺省：缺省（没有这一栏或空串）读成“未分类”“在研”，所以老版本写出的条目照样能读，
# schema_version 不升（现役和上一版只认 workspace-registry.v1，升了就不能回退）。
ProjectKind = Literal["", "equipment", "library", "test", "tool"]
ProjectStatus = Literal["", "active", "paused", "archived", "deleted"]

KIND_LABELS: dict[str, str] = {"": "未分类", "equipment": "设备", "library": "公共库", "test": "测试", "tool": "工具"}
STATUS_LABELS: dict[str, str] = {"": "在研", "active": "在研", "paused": "暂停", "archived": "已归档", "deleted": "已删除"}
#: 用户能直接选的状态（RC-004 默认三档）。“已删除”是内部值：只由删除写上、由搬回改回，不让人手填。
USER_STATUSES: tuple[str, ...] = ("active", "paused", "archived")
#: “工具与验证”一组：看板把这两种性质的项目收在一起（替代以前写死在看板里的名单）。
TOOL_KINDS: frozenset[str] = frozenset({"tool", "test"})


def kind_label(kind: str) -> str:
    """性质的中文显示；认不出的值原样显示，不猜。"""

    return KIND_LABELS.get(kind, kind)


def status_label(status: str) -> str:
    """状态的中文显示；缺省按“在研”。"""

    return STATUS_LABELS.get(status, status)


class WorkspaceProjectMapping(BaseModel):
    """One explicit project topology entry."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    project_root: str
    development_root: str
    control_project_id: str = ""
    control_pm_session: str = ""
    runtime_root: str = ""
    kind: ProjectKind = ""
    status: ProjectStatus = ""
    # 删除时记下删除前的状态，搬回时改回去（只在 status 是 deleted 时有意义）
    status_before_delete: ProjectStatus = ""


class WorkspaceRegistry(BaseModel):
    """Versioned topology registry consumed without workspace-wide scanning."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["workspace-registry.v1"] = "workspace-registry.v1"
    projects: tuple[WorkspaceProjectMapping, ...]


class WorkspaceContext(BaseModel):
    """A bounded identity card for one invocation, never global state."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["workspace-context.v2"] = "workspace-context.v2"
    workspace_root: str
    control_root: str = ""
    execution_root: str = ""
    candidate_commit: str = ""
    resolution_source: Literal["explicit", "directory"]
    subject_project_id: str
    subject: ContextProject
    control_project_id: str = ""
    control_pm_session: str = ""
    development_root: str
    runtime_root: str = ""
    # Backward-compatible alias for the configured active-release pointer.
    release_id: str = ""
    configured_release_id: str = ""
    effective_release_id: str = ""
    runtime_load_path: str = ""
    runtime_fallback_reason: str = ""
    read_set: tuple[ContextEvidence, ...]
    evidence_id: str
    conflicts: tuple[str, ...] = ()
