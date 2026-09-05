"""Strict, immutable decision and disposition contracts.

A decision package is authority only when every required field is structurally
valid.  A disposition is a separate immutable record that can permanently
block or supersede a decision without rewriting its historical bytes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

SCHEMA_VERSION = "decision_package.v1"
DISPOSITION_SCHEMA_VERSION = "decision_disposition.v1"

_DECISION_ID = re.compile(r"DEC-\d{8}-[A-Z0-9]+\Z")
_DISPOSITION_ID = re.compile(r"DISP-\d{8}-[A-Z0-9-]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_APPROVED_CONCLUSIONS = frozenset({"approved", "conditionally_approved"})
_DEFERRED_SUPERSESSION = "DEFERRED_UNTIL_NEW_INDEPENDENTLY_APPROVED_DECISION"


class DecisionPackageValidationError(ValueError):
    """Raised when a decision or disposition cannot safely be consumed."""


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionPackageValidationError(f"{field_name} 必须是非空字符串")
    return value.strip()


def _validate_iso8601(value: object, field_name: str) -> str:
    text = _require_string(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionPackageValidationError(f"{field_name} 必须是 ISO 8601 时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DecisionPackageValidationError(f"{field_name} 必须包含时区")
    return text


def _validate_identifier(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    text = _require_string(value, field_name)
    if not pattern.fullmatch(text):
        raise DecisionPackageValidationError(f"{field_name} 格式非法: {text}")
    return text


def normalize_approved_path(value: object) -> str:
    """Return one canonical, exact relative source path or reject it.

    Decision files are not path-pattern language.  Backslashes, parent
    traversal, globs, and implicit normalisation are rejected so the stored
    allow-list has one unambiguous spelling across platforms.
    """
    path = _require_string(value, "approved_files 条目")
    if "\\" in path or any(token in path for token in ("*", "?", "[", "]")):
        raise DecisionPackageValidationError(f"approved_files 条目不是精确路径: {path}")
    candidate = PurePosixPath(path)
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise DecisionPackageValidationError(f"approved_files 条目必须是安全相对路径: {path}")
    normalized = candidate.as_posix()
    if normalized != path:
        raise DecisionPackageValidationError(f"approved_files 条目必须使用规范 POSIX 路径: {path}")
    return normalized


def _validate_string_list(value: object, field_name: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise DecisionPackageValidationError(f"{field_name} 必须是 JSON 数组")
    result: list[str] = []
    for item in value:
        result.append(_require_string(item, field_name))
    if nonempty and not result:
        raise DecisionPackageValidationError(f"{field_name} 不得为空")
    return result


@dataclass
class DecisionPackageDTO:
    """An execution authority package with a strict exact-path allow-list."""

    decision_id: str
    project_id: str
    change_id: str
    approved_scope: str
    approved_files: list[str] = field(default_factory=list)
    approver: str = ""
    approved_at: str = ""
    decision_conclusion: str = "approved"
    conditions: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate every authority-bearing field before serialisation or use."""
        if self.schema_version != SCHEMA_VERSION:
            raise DecisionPackageValidationError(f"decision schema 不兼容: {self.schema_version!r}")
        _validate_identifier(self.decision_id, "decision_id", _DECISION_ID)
        _require_string(self.project_id, "project_id")
        _require_string(self.change_id, "change_id")
        _require_string(self.approved_scope, "approved_scope")
        _require_string(self.approver, "approver")
        _validate_iso8601(self.approved_at, "approved_at")
        if self.decision_conclusion not in _APPROVED_CONCLUSIONS:
            raise DecisionPackageValidationError(
                f"decision_conclusion 未获得执行授权: {self.decision_conclusion!r}"
            )
        if not isinstance(self.approved_files, list) or not self.approved_files:
            raise DecisionPackageValidationError("approved_files 必须是非空 JSON 数组")
        normalized_files = [normalize_approved_path(path) for path in self.approved_files]
        if len(set(normalized_files)) != len(normalized_files):
            raise DecisionPackageValidationError("approved_files 不得含有重复路径")
        if normalized_files != self.approved_files:
            raise DecisionPackageValidationError("approved_files 未使用规范精确路径")
        _validate_string_list(self.conditions, "conditions")
        if not isinstance(self.metadata, dict):
            raise DecisionPackageValidationError("metadata 必须是 JSON 对象")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "change_id": self.change_id,
            "approved_scope": self.approved_scope,
            "approved_files": list(self.approved_files),
            "approver": self.approver,
            "approved_at": self.approved_at,
            "decision_conclusion": self.decision_conclusion,
            "conditions": list(self.conditions),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionPackageDTO:
        if not isinstance(data, Mapping):
            raise DecisionPackageValidationError("决策包根节点必须是 JSON 对象")
        approved_files = data.get("approved_files")
        conditions = data.get("conditions", [])
        metadata = data.get("metadata", {})
        if not isinstance(approved_files, list):
            raise DecisionPackageValidationError("approved_files 必须是 JSON 数组")
        if not isinstance(conditions, list):
            raise DecisionPackageValidationError("conditions 必须是 JSON 数组")
        if not isinstance(metadata, dict):
            raise DecisionPackageValidationError("metadata 必须是 JSON 对象")
        dto = cls(
            schema_version=_require_string(data.get("schema_version"), "schema_version"),
            decision_id=_require_string(data.get("decision_id"), "decision_id"),
            project_id=_require_string(data.get("project_id"), "project_id"),
            change_id=_require_string(data.get("change_id"), "change_id"),
            approved_scope=_require_string(data.get("approved_scope"), "approved_scope"),
            approved_files=_validate_string_list(approved_files, "approved_files", nonempty=True),
            approver=_require_string(data.get("approver"), "approver"),
            approved_at=_require_string(data.get("approved_at"), "approved_at"),
            decision_conclusion=_require_string(
                data.get("decision_conclusion"), "decision_conclusion"
            ),
            conditions=_validate_string_list(conditions, "conditions"),
            metadata=dict(metadata),
        )
        dto.validate()
        return dto


@dataclass(frozen=True)
class DecisionDispositionDTO:
    """A validated immutable instruction to block or supersede one decision."""

    record_id: str
    target_decision_id: str
    target_decision_sha256: str
    disposition: str
    effect: str
    approver: str
    approved_at: str
    supersession_status: str
    superseding_decision_id: str | None

    @property
    def terminal_status(self) -> str:
        """Return the sole allowed future-consumption outcome for the target."""
        return "blocked" if self.disposition.startswith("BLOCKED") else "superseded"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionDispositionDTO:
        if not isinstance(data, Mapping):
            raise DecisionPackageValidationError("处置记录根节点必须是 JSON 对象")
        if data.get("schema_version") != DISPOSITION_SCHEMA_VERSION:
            raise DecisionPackageValidationError("处置记录 schema 不兼容")
        if (
            data.get("preserves_original") is not True
            or data.get("retroactive_mutation") is not False
        ):
            raise DecisionPackageValidationError("处置记录不得改写历史决策")

        semantics = data.get("authority_semantics")
        if not isinstance(semantics, Mapping):
            raise DecisionPackageValidationError("处置记录缺少 authority_semantics")
        if (
            semantics.get("future_consumption_only") is not True
            or semantics.get("rewrites_target_decision") is not False
            or semantics.get("grants_recovery_or_release_authority") is not False
        ):
            raise DecisionPackageValidationError("处置记录 authority_semantics 状态冲突")

        record_id = _validate_identifier(data.get("record_id"), "record_id", _DISPOSITION_ID)
        target_id = _validate_identifier(
            data.get("target_decision_id"), "target_decision_id", _DECISION_ID
        )
        target_sha = _require_string(data.get("target_decision_sha256"), "target_decision_sha256")
        if not _SHA256.fullmatch(target_sha):
            raise DecisionPackageValidationError("target_decision_sha256 必须是小写 SHA-256")
        disposition = _require_string(data.get("disposition"), "disposition").upper()
        effect = _require_string(data.get("effect"), "effect")
        approver = _require_string(data.get("approver"), "approver")
        approved_at = _validate_iso8601(data.get("approved_at"), "approved_at")
        supersession_status = _require_string(
            data.get("supersession_status"), "supersession_status"
        )
        superseding_value = data.get("superseding_decision_id")
        superseding_id: str | None
        if superseding_value is None:
            superseding_id = None
        else:
            superseding_id = _validate_identifier(
                superseding_value, "superseding_decision_id", _DECISION_ID
            )

        if disposition.startswith("BLOCKED"):
            if supersession_status != _DEFERRED_SUPERSESSION or superseding_id is not None:
                raise DecisionPackageValidationError("blocked 处置与 supersession 状态冲突")
        elif disposition == "SUPERSEDED":
            if supersession_status != "SUPERSEDED" or superseding_id is None:
                raise DecisionPackageValidationError("superseded 处置缺少一致的替代决策")
        else:
            raise DecisionPackageValidationError(f"不支持的 disposition 状态: {disposition}")

        return cls(
            record_id=record_id,
            target_decision_id=target_id,
            target_decision_sha256=target_sha,
            disposition=disposition,
            effect=effect,
            approver=approver,
            approved_at=approved_at,
            supersession_status=supersession_status,
            superseding_decision_id=superseding_id,
        )
