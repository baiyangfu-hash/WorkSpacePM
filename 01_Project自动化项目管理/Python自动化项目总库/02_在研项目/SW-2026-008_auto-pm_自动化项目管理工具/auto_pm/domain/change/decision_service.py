"""Fail-closed loading and consumption of immutable decision packages."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auto_pm.change.parser import ChgParser
from auto_pm.contracts.decision_package import (
    SCHEMA_VERSION,
    DecisionDispositionDTO,
    DecisionPackageDTO,
    DecisionPackageValidationError,
    normalize_approved_path,
)

log = logging.getLogger(__name__)


class DecisionError(Exception):
    """Base error for decision-package operations."""


class DecisionValidationError(DecisionError):
    """Raised when an authority package cannot safely be consumed."""


class DecisionNotFoundError(DecisionError):
    """Raised when a requested immutable decision is absent."""


class DecisionService:
    """Read decisions as execution authority only after all integrity gates pass."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.decisions_dir = self.workspace_root / ".auto-pm" / "decisions"

    def _generate_decision_id(self) -> str:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        token = uuid.uuid4().hex[:8].upper()
        return f"DEC-{date_str}-{token}"

    @staticmethod
    def _read_json_object(path: Path, label: str) -> tuple[bytes, Mapping[str, Any]]:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise DecisionNotFoundError(f"{label} 不可读取: {path}") from exc
        try:
            data = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DecisionValidationError(f"{label} JSON 损坏: {path}") from exc
        if not isinstance(data, Mapping):
            raise DecisionValidationError(f"{label} 根节点必须是 JSON 对象: {path}")
        return raw, data

    @staticmethod
    def _validate_decision_id(decision_id: str) -> str:
        try:
            DecisionPackageDTO(
                decision_id=decision_id,
                project_id="validation",
                change_id="validation",
                approved_scope="MODULE",
                approved_files=["validation/file.py"],
                approver="validation",
                approved_at="2026-01-01T00:00:00+00:00",
            ).validate()
        except DecisionPackageValidationError as exc:
            raise DecisionValidationError(str(exc)) from exc
        return decision_id

    def _decision_path(self, decision_id: str) -> Path:
        checked_id = self._validate_decision_id(decision_id)
        return self.decisions_dir / f"{checked_id}.json"

    def _load_dispositions(self) -> list[DecisionDispositionDTO]:
        dispositions_dir = self.decisions_dir / "dispositions"
        if not dispositions_dir.exists():
            return []
        if not dispositions_dir.is_dir():
            raise DecisionValidationError("dispositions 路径不是目录，拒绝消费决策")

        records: list[DecisionDispositionDTO] = []
        for path in sorted(dispositions_dir.glob("*.json")):
            _, data = self._read_json_object(path, "处置记录")
            try:
                records.append(DecisionDispositionDTO.from_dict(data))
            except DecisionPackageValidationError as exc:
                raise DecisionValidationError(f"处置记录无效: {path}: {exc}") from exc
        return records

    def _enforce_disposition(self, decision_id: str, decision_bytes: bytes) -> None:
        matches = [
            record
            for record in self._load_dispositions()
            if record.target_decision_id == decision_id
        ]
        if not matches:
            return
        if len(matches) != 1:
            raise DecisionValidationError(f"决策 {decision_id} 存在多个处置记录，状态冲突")

        record = matches[0]
        actual_hash = hashlib.sha256(decision_bytes).hexdigest()
        if actual_hash != record.target_decision_sha256:
            raise DecisionValidationError(
                f"决策 {decision_id} 的 SHA-256 与处置记录不匹配，拒绝消费"
            )
        raise DecisionValidationError(
            f"决策 {decision_id} 已被 disposition {record.record_id} {record.terminal_status}，拒绝消费"
        )

    @staticmethod
    def _validate_requested_files(requested_files: Iterable[str]) -> list[str]:
        if isinstance(requested_files, (str, bytes)):
            raise DecisionValidationError("target_files 必须是路径迭代器，不能是单个字符串")
        normalized = [normalize_approved_path(path) for path in requested_files]
        if not normalized:
            raise DecisionValidationError("target_files 不得为空")
        if len(set(normalized)) != len(normalized):
            raise DecisionValidationError("target_files 不得含有重复路径")
        return normalized

    def assert_files_authorized(
        self, decision: DecisionPackageDTO, target_files: Iterable[str]
    ) -> None:
        """Require every requested path to be present in the exact DEC allow-list."""
        try:
            decision.validate()
        except DecisionPackageValidationError as exc:
            raise DecisionValidationError(str(exc)) from exc
        requested = self._validate_requested_files(target_files)
        approved = set(decision.approved_files)
        unapproved = [path for path in requested if path not in approved]
        if unapproved:
            raise DecisionValidationError(
                f"目标文件未获精确批准: {unapproved}; 批准清单: {decision.approved_files}"
            )

    def get_decision(
        self,
        decision_id: str,
        *,
        target_files: Iterable[str] | None = None,
    ) -> DecisionPackageDTO:
        """Load a decision only when bytes, schema, disposition, and scope agree.

        Passing ``target_files`` makes this an execution-authorisation check.
        Callers that merely inspect a valid current decision may omit it, but a
        blocked or superseded decision is never returned in either mode.
        """
        target_file = self._decision_path(decision_id)
        if not target_file.is_file():
            raise DecisionNotFoundError(f"未找到决策包: {decision_id}")
        raw, data = self._read_json_object(target_file, "决策包")
        try:
            dto = DecisionPackageDTO.from_dict(data)
        except DecisionPackageValidationError as exc:
            raise DecisionValidationError(f"决策包无效: {decision_id}: {exc}") from exc
        self._enforce_disposition(decision_id, raw)
        if target_files is not None:
            self.assert_files_authorized(dto, target_files)
        return dto

    def create_decision(
        self,
        change_id: str,
        approver: str,
        *,
        project_id: str = "",
        approved_files: list[str] | None = None,
        conditions: list[str] | None = None,
        decision_id: str = "",
    ) -> DecisionPackageDTO:
        """Create a new strict decision package from an approved change record."""
        if not change_id.strip():
            raise DecisionValidationError("必须指定 change_id")
        if not approver.strip():
            raise DecisionValidationError("必须指定 approver (审批人)")

        chg_file: Path | None = None
        for path in self.workspace_root.glob(f"**/{change_id}.md"):
            if path.is_file():
                chg_file = path
                break
        if chg_file is None:
            raise DecisionNotFoundError(f"未找到变更单文件: {change_id}.md")

        parser = ChgParser()
        try:
            cr = parser.parse(str(chg_file))
        except Exception as exc:
            raise DecisionValidationError(f"变更单解析失败: {exc}") from exc

        valid_statuses = {
            "approved",
            "conditionally_approved",
            "implementing",
            "pending_acceptance",
            "accepting",
            "completed",
            "closed",
        }
        if cr.status not in valid_statuses:
            raise DecisionValidationError(
                f"变更单当前状态为 '{cr.status}'，尚未获得批准，无法生成决策包"
            )

        scope_raw = cr.impact_scope
        resolved_scope = (
            "/".join(str(item) for item in scope_raw)
            if isinstance(scope_raw, list)
            else str(scope_raw or "MODULE")
        )
        effective_files = [str(path).strip() for path in approved_files or [] if str(path).strip()]
        if not effective_files:
            raise DecisionValidationError("必须提供非空的精确 approved_files 白名单")
        dto = DecisionPackageDTO(
            decision_id=decision_id or self._generate_decision_id(),
            project_id=project_id or cr.project_id,
            change_id=change_id,
            approved_scope=resolved_scope,
            approved_files=effective_files,
            approver=approver,
            approved_at=datetime.now(UTC).isoformat(),
            decision_conclusion=(
                "conditionally_approved" if cr.status == "conditionally_approved" else "approved"
            ),
            conditions=list(conditions or []),
            schema_version=SCHEMA_VERSION,
        )
        try:
            payload = dto.to_dict()
        except DecisionPackageValidationError as exc:
            raise DecisionValidationError(str(exc)) from exc

        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        target_file = self._decision_path(dto.decision_id)
        try:
            target_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise DecisionValidationError(f"决策包写入失败: {target_file}") from exc
        log.info("决策包已成功固化: %s", target_file)
        return dto

    def list_decisions(
        self,
        project_id: str = "",
        change_id: str = "",
    ) -> list[DecisionPackageDTO]:
        """List only decisions that remain structurally valid and consumable."""
        if not self.decisions_dir.is_dir():
            return []
        results: list[DecisionPackageDTO] = []
        for file in sorted(self.decisions_dir.glob("DEC-*.json")):
            try:
                dto = self.get_decision(file.stem)
            except DecisionError as exc:
                log.warning("跳过不可消费决策包 %s: %s", file, exc)
                continue
            if project_id and dto.project_id != project_id:
                continue
            if change_id and dto.change_id != change_id:
                continue
            results.append(dto)
        return results
