"""auto_pm.domain.change.decision_service - 决策包管理服务

负责阶段 1 审批后决策包（Decision Package）的生成、检索与校验。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from auto_pm.change.parser import ChgParser
from auto_pm.contracts.decision_package import (
    RUNTIME_CAPABILITY_KEY,
    SCHEMA_VERSION,
    DecisionPackageDTO,
    RuntimeDecisionCapability,
    is_canonical_decision_id,
    is_canonical_runtime_change_id,
)
from auto_pm.contracts.workspace_context import WorkspaceRegistry
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    require_control_root,
    require_safe_workspace_path,
)
from auto_pm.models import ChangeRequest
from auto_pm.models.enums import ChangeStatus

log = logging.getLogger(__name__)

_RUNTIME_CHANGE_STATUSES = frozenset({"approved", "implementing"})


class DecisionError(Exception):
    """决策包通用异常基类"""


class DecisionValidationError(DecisionError):
    """决策包校验失败"""


class DecisionNotFoundError(DecisionError):
    """决策包未找到"""


class DecisionService:
    """决策包领域服务"""

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.decisions_dir = self.workspace_root / ".auto-pm" / "decisions"

    def _generate_decision_id(self) -> str:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        token = uuid.uuid4().hex[:8].upper()
        return f"DEC-{date_str}-{token}"

    def _is_runtime_worktree_candidate(self, path: Path) -> bool:
        """判断候选是否来自本机运行态 worktree 镜像，而非正式项目资产。"""
        try:
            relative_path = path.resolve().relative_to(self.workspace_root.resolve())
        except ValueError:
            return False
        parts = relative_path.parts
        return len(parts) >= 2 and parts[:2] == (".auto-pm", "worktrees")

    def create_decision(
        self,
        change_id: str,
        approver: str,
        *,
        project_id: str = "",
        approved_files: list[str] | None = None,
        conditions: list[str] | None = None,
        decision_id: str = "",
        runtime_capability: RuntimeDecisionCapability | None = None,
    ) -> DecisionPackageDTO:
        """从已审批的变更单生成固化的结构化决策包"""
        resolved_approver = approver.strip()
        if not change_id.strip():
            raise DecisionValidationError("必须指定 change_id")
        if not resolved_approver:
            raise DecisionValidationError("必须指定 approver (审批人)")
        if runtime_capability is not None and not decision_id.strip():
            raise DecisionValidationError("runtime_capability 必须绑定显式 decision_id")
        if runtime_capability is not None:
            self._validate_runtime_change_id(change_id)
            if not project_id or project_id != project_id.strip():
                raise DecisionValidationError("runtime_capability 必须绑定规范的 project_id")
            if conditions:
                raise DecisionValidationError("runtime_capability 不允许附加条件")

        resolved_dec_id = self._canonical_decision_id(decision_id or self._generate_decision_id())
        self._require_control_root()
        self._decision_target(resolved_dec_id)

        # 变更编号只在项目账内唯一。跨项目可能存在同号单据，因此决策包必须
        # 使用 project_id 消歧；未限定项目且命中多个单据时必须 fail-closed。
        runtime_source: tuple[Path, str, str, str] | None = None
        if runtime_capability is not None:
            runtime_path, runtime_change, runtime_sha256 = self._runtime_change(
                change_id,
                project_id,
            )
            candidates = [(runtime_path, runtime_change)]
            runtime_source = (
                runtime_path,
                runtime_sha256,
                runtime_change.status,
                self._runtime_authority_projection(runtime_change),
            )
        else:
            candidates = self._legacy_change_candidates(change_id, project_id)

        if not candidates:
            suffix = f"（项目 {project_id}）" if project_id else ""
            raise DecisionNotFoundError(f"未找到变更单文件: {change_id}.md{suffix}")
        if len(candidates) > 1:
            projects = sorted({str(item.project_id) for _, item in candidates})
            raise DecisionValidationError(
                f"变更单编号跨项目重号: {change_id}，请通过 --pid 指定项目；"
                f"候选项目: {', '.join(projects)}"
            )
        _, cr = candidates[0]

        valid_statuses = (
            "approved",
            "conditionally_approved",
            "implementing",
            "pending_acceptance",
            "accepting",
            "completed",
            "closed",
        )
        if cr.status not in valid_statuses:
            raise DecisionValidationError(
                f"变更单当前状态为 '{cr.status}'，尚未获得批准，无法生成决策包"
            )
        if runtime_capability is not None and cr.status not in _RUNTIME_CHANGE_STATUSES:
            raise DecisionValidationError(
                f"运行态 Decision 仅接受 approved/implementing CHG，当前为: {cr.status}"
            )

        resolved_pid = project_id or cr.project_id
        scope_raw = cr.impact_scope
        if isinstance(scope_raw, list):
            resolved_scope = "/".join(str(s) for s in scope_raw) or "MODULE"
        else:
            resolved_scope = str(scope_raw or "MODULE")
        conclusion = (
            "conditionally_approved" if cr.status == "conditionally_approved" else "approved"
        )

        # 提取或使用传入的批准文件清单
        effective_files: list[str] = []
        if approved_files:
            effective_files = [str(f).strip() for f in approved_files if str(f).strip()]
        else:
            # 从 §5 提取文件
            s5_text = (getattr(cr, "sections", {}) or {}).get("5", "")
            for line in s5_text.splitlines():
                if "涉及文件/交付物" in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2:
                        raw_files = parts[1].replace("<br>", "\n").splitlines()
                        for rf in raw_files:
                            rf_clean = rf.strip().strip("-").strip("*").strip()
                            if rf_clean and rf_clean not in (
                                "（待填写）",
                                "(待填写)",
                                "无涉及文件记录",
                            ):
                                effective_files.append(rf_clean)
        # 去重并保持顺序
        effective_files = list(dict.fromkeys(effective_files))

        now_iso = datetime.now(UTC).isoformat()

        dto = DecisionPackageDTO(
            decision_id=resolved_dec_id,
            project_id=resolved_pid,
            change_id=change_id,
            approved_scope=resolved_scope,
            approved_files=effective_files,
            approver=resolved_approver,
            approved_at=now_iso,
            decision_conclusion=conclusion,
            conditions=list(conditions or []),
            schema_version=SCHEMA_VERSION,
            metadata=(
                {RUNTIME_CAPABILITY_KEY: runtime_capability.to_dict()}
                if runtime_capability is not None
                else {}
            ),
        )

        serialized = json.dumps(dto.to_dict(), ensure_ascii=False, indent=2) + "\n"
        self._require_control_root()
        if runtime_source is not None:
            current_path, current_change, current_sha256 = self._runtime_change(
                change_id,
                project_id,
            )
            (
                expected_path,
                expected_sha256,
                expected_status,
                expected_projection,
            ) = runtime_source
            if (
                self._path_key(current_path) != self._path_key(expected_path)
                or current_sha256 != expected_sha256
                or current_change.status != expected_status
                or self._runtime_authority_projection(current_change) != expected_projection
            ):
                raise DecisionValidationError("运行态 CHG 真源在 Decision 签发前发生漂移，拒绝固化")
        self._decision_directory().mkdir(parents=True, exist_ok=True)
        target_file = self._decision_target(resolved_dec_id)
        try:
            with target_file.open("x", encoding="utf-8", errors="strict", newline="\n") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise DecisionValidationError(
                f"Decision ID 已存在，拒绝覆盖: {resolved_dec_id}"
            ) from error
        except OSError as error:
            raise DecisionValidationError(f"决策包无法固化: {resolved_dec_id}") from error
        log.info("决策包已成功固化: %s", target_file)
        return dto

    def get_decision(self, decision_id: str) -> DecisionPackageDTO:
        """获取指定决策包"""
        decision, _digest = self.get_decision_with_sha256(decision_id)
        return decision

    def get_decision_with_sha256(self, decision_id: str) -> tuple[DecisionPackageDTO, str]:
        """Read one exact Decision byte snapshot and return its audit digest."""

        resolved_id = self._canonical_decision_id(decision_id)
        target_file = self._decision_target(resolved_id)
        if not target_file.is_file():
            raise DecisionNotFoundError(f"未找到决策包: {resolved_id}")
        try:
            identity_before = self._unique_regular_file_identity(
                target_file,
                label="Decision 文件",
            )
            raw = target_file.read_bytes()
            identity_after = self._unique_regular_file_identity(
                target_file,
                label="Decision 文件",
            )
            if identity_before != identity_after:
                raise DecisionValidationError(f"Decision 文件读取期间发生漂移: {resolved_id}")
            text = raw.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                raise DecisionValidationError(f"决策包包含无效 UTF-8: {resolved_id}")
            data = json.loads(text, object_pairs_hook=self._reject_duplicate_json_fields)
            decision = DecisionPackageDTO.from_dict(data)
            if decision.decision_id != resolved_id:
                raise DecisionValidationError(
                    "Decision filename/request/payload identity 不一致: "
                    f"requested={resolved_id}; payload={decision.decision_id}"
                )
            self._validate_loaded_runtime_authority(decision)
            return decision, hashlib.sha256(raw).hexdigest()
        except DecisionError:
            raise
        except ValueError as error:
            raise DecisionValidationError(f"决策包契约非法: {resolved_id}: {error}") from error
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise DecisionValidationError(f"决策包无法读取: {resolved_id}") from error

    def list_decisions(
        self,
        project_id: str = "",
        change_id: str = "",
    ) -> list[DecisionPackageDTO]:
        """列出决策包列表，支持按项目与变更单过滤"""
        results: list[DecisionPackageDTO] = []
        decisions_dir = self._decision_directory()
        if not decisions_dir.is_dir():
            return results
        for file in sorted(decisions_dir.glob("DEC-*.json")):
            try:
                decision_id = self._canonical_decision_id(file.stem)
                dto = self.get_decision(decision_id)
                if project_id and dto.project_id != project_id:
                    continue
                if change_id and dto.change_id != change_id:
                    continue
                results.append(dto)
            except DecisionError as error:
                raise DecisionValidationError(
                    f"决策包列表包含无效文件: {file.name}: {error}"
                ) from error
        return results

    def _legacy_change_candidates(
        self, change_id: str, project_id: str
    ) -> list[tuple[Path, ChangeRequest]]:
        parser = ChgParser()
        candidates: list[tuple[Path, ChangeRequest]] = []
        for path in sorted(self.workspace_root.glob(f"**/{change_id}.md")):
            if not path.is_file() or self._is_runtime_worktree_candidate(path):
                continue
            try:
                parsed = parser.parse(str(path))
            except Exception as error:
                log.warning("变更单候选解析失败 %s: %s", path, error)
                continue
            if project_id and parsed.project_id != project_id:
                continue
            candidates.append((path, parsed))
        return candidates

    def _runtime_change(
        self,
        change_id: str,
        project_id: str,
    ) -> tuple[Path, ChangeRequest, str]:
        """Resolve one current standard CHG source without archives, links, or aliases."""

        self._validate_runtime_change_id(change_id)
        project_root = self._registered_project_root(project_id)
        family = "-".join(change_id.split("-")[:2])
        candidate = (
            project_root / "04_监控" / "01_变更管理" / "01_变更单" / family / f"{change_id}.md"
        )
        try:
            path = require_safe_workspace_path(
                self.workspace_root,
                candidate,
                label="运行态 CHG 真源",
            )
        except ControlRootGuardError as error:
            raise DecisionValidationError(str(error)) from error
        if not path.is_file():
            raise DecisionValidationError(
                f"未找到指定项目的当前标准运行态 CHG 真源: {project_id}/{change_id}"
            )
        try:
            identity_before = self._unique_regular_file_identity(
                path,
                label="运行态 CHG 真源",
            )
            source_before = path.read_bytes()
        except OSError as error:
            raise DecisionValidationError(f"运行态 CHG 真源无法读取: {change_id}") from error
        try:
            source_text = source_before.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise DecisionValidationError(f"运行态 CHG 真源不是有效 UTF-8: {change_id}") from error
        authority_source = self._runtime_authority_view(source_text)
        if self._hidden_runtime_authority_marker(source_text, authority_source):
            raise DecisionValidationError(
                "运行态 CHG 不得在 fenced/indented code、HTML comment 或 <pre> 中伪造授权"
            )
        section_three, section_five = self._validate_runtime_top_level_sections(authority_source)
        explicit_change_id = self._unique_runtime_chg_field(
            authority_source,
            section_three=section_three,
            section="3.0",
            field="变更编号",
        )
        explicit_project_id = self._unique_runtime_chg_field(
            authority_source,
            section_three=section_three,
            section="3.0",
            field="项目编号",
        )
        explicit_status = self._unique_runtime_chg_field(
            authority_source,
            section_three=section_three,
            section="3.4",
            field="变更状态",
        )
        if explicit_change_id != change_id:
            raise DecisionValidationError("运行态 CHG filename/request/payload identity 不一致")
        if explicit_project_id != project_id:
            raise DecisionValidationError("运行态 CHG project_id 与 Workspace Registry 不一致")
        if explicit_status not in _RUNTIME_CHANGE_STATUSES:
            raise DecisionValidationError(
                f"运行态 Decision 仅接受 approved/implementing CHG，当前为: {explicit_status}"
            )
        try:
            change = self._parse_runtime_change_snapshot(
                authority_source,
                path=path,
                explicit_status=explicit_status,
                section_three=section_three,
                section_five=section_five,
            )
        except Exception as error:
            raise DecisionValidationError(f"运行态 CHG 真源无法解析: {change_id}") from error
        try:
            verified_path = require_safe_workspace_path(
                self.workspace_root,
                candidate,
                label="运行态 CHG 真源",
            )
            source_after = verified_path.read_bytes()
            identity_after = self._unique_regular_file_identity(
                verified_path,
                label="运行态 CHG 真源",
            )
        except (ControlRootGuardError, OSError) as error:
            raise DecisionValidationError(f"运行态 CHG 真源无法复核: {change_id}") from error
        if (
            self._path_key(verified_path) != self._path_key(path)
            or identity_before != identity_after
            or source_before != source_after
        ):
            raise DecisionValidationError("运行态 CHG 真源读取期间发生漂移，拒绝签发")
        if change.project_id != project_id:
            raise DecisionValidationError("运行态 CHG 真源 project_id 与 Workspace Registry 不一致")
        if change.change_number != change_id:
            raise DecisionValidationError("运行态 CHG filename/request/payload identity 不一致")
        if change.status != explicit_status:
            raise DecisionValidationError("运行态 CHG 显式状态与解析状态不一致")
        if change.status not in _RUNTIME_CHANGE_STATUSES:
            raise DecisionValidationError(
                f"运行态 Decision 仅接受 approved/implementing CHG，当前为: {change.status}"
            )
        return path, change, hashlib.sha256(source_after).hexdigest()

    @staticmethod
    def _runtime_authority_projection(change: ChangeRequest) -> str:
        projection = {
            "change_number": change.change_number,
            "project_id": change.project_id,
            "status": change.status,
            "impact_scope": [str(item) for item in change.impact_scope],
            "section_5": change.sections.get("5", ""),
        }
        canonical = json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_runtime_change_snapshot(
        source: str,
        *,
        path: Path,
        explicit_status: str,
        section_three: str,
        section_five: str,
    ) -> ChangeRequest:
        """Parse signed CHG facts from the already-read immutable byte snapshot."""

        parser = ChgParser()
        sections = parser._split_sections(source)
        sections["3"] = section_three
        if section_five:
            sections["5"] = section_five
        else:
            sections.pop("5", None)
        change = ChangeRequest(
            file_path=str(path),
            status=cast(ChangeStatus, explicit_status),
        )
        parser._parse_change_info(section_three, change)
        change.status = cast(ChangeStatus, explicit_status)
        change.sections = sections
        return change

    def _registered_project_root(self, project_id: str) -> Path:
        registry_candidate = (
            self.workspace_root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
        )
        try:
            registry_path = require_safe_workspace_path(
                self.workspace_root,
                registry_candidate,
                label="Workspace Registry",
            )
        except ControlRootGuardError as error:
            raise DecisionValidationError(str(error)) from error
        if not registry_path.is_file():
            raise DecisionValidationError("runtime Decision 签发要求 Workspace Registry 真源")
        try:
            identity_before = self._unique_regular_file_identity(
                registry_path,
                label="Workspace Registry",
            )
            text = registry_path.read_text(encoding="utf-8", errors="replace")
            identity_after = self._unique_regular_file_identity(
                registry_path,
                label="Workspace Registry",
            )
            if identity_before != identity_after:
                raise DecisionValidationError("Workspace Registry 读取期间发生漂移")
            if "\ufffd" in text:
                raise DecisionValidationError("Workspace Registry 包含无效 UTF-8")
            payload = json.loads(text, object_pairs_hook=self._reject_duplicate_registry_fields)
            if not isinstance(payload, dict) or set(payload) != {"schema_version", "projects"}:
                raise DecisionValidationError("Workspace Registry 顶层字段不完整或未知")
            projects = payload.get("projects")
            if not isinstance(projects, list):
                raise DecisionValidationError("Workspace Registry projects 必须是数组")
            required_project_fields = {"project_id", "project_root", "development_root"}
            allowed_project_fields = required_project_fields | {
                "control_project_id",
                "control_pm_session",
                "runtime_root",
            }
            for item in projects:
                if (
                    not isinstance(item, dict)
                    or not required_project_fields.issubset(item)
                    or not set(item).issubset(allowed_project_fields)
                ):
                    raise DecisionValidationError("Workspace Registry project 字段不完整或未知")
            registry = WorkspaceRegistry.model_validate(payload)
        except DecisionError:
            raise
        except (OSError, ValueError) as error:
            raise DecisionValidationError("Workspace Registry schema 无效") from error
        matches = [item for item in registry.projects if item.project_id == project_id]
        if len(matches) != 1:
            raise DecisionValidationError(
                f"Workspace Registry 必须唯一登记 runtime project: {project_id}"
            )
        mapping = matches[0]
        roots: list[Path] = []
        for label, raw in (
            ("project_root", mapping.project_root),
            ("development_root", mapping.development_root),
        ):
            if not raw or raw != raw.strip() or Path(raw).is_absolute():
                raise DecisionValidationError(f"Workspace Registry {label} 必须是规范相对路径")
            if any(self._is_archive_or_backup_part(part) for part in Path(raw).parts):
                raise DecisionValidationError(f"Workspace Registry {label} 不得指向归档或备份")
            try:
                resolved = require_safe_workspace_path(
                    self.workspace_root,
                    raw,
                    label=f"Workspace Registry {label}",
                )
            except ControlRootGuardError as error:
                raise DecisionValidationError(str(error)) from error
            if not resolved.is_dir():
                raise DecisionValidationError(f"Workspace Registry {label} 不存在或不是目录")
            roots.append(resolved)
        if self._path_key(roots[0]) != self._path_key(roots[1]):
            raise DecisionValidationError("runtime project_root 与 development_root 必须一致")
        return roots[0]

    def _validate_loaded_runtime_authority(self, decision: DecisionPackageDTO) -> None:
        if decision.runtime_capability is None:
            return
        self._validate_runtime_change_id(decision.change_id)
        if not decision.project_id or decision.project_id != decision.project_id.strip():
            raise DecisionValidationError("运行态 Decision project_id 非规范")
        if decision.decision_conclusion != "approved" or decision.conditions:
            raise DecisionValidationError("运行态 Decision 必须是无条件 approved")

    def _require_control_root(self) -> None:
        try:
            require_control_root(self.workspace_root)
        except ControlRootGuardError as error:
            raise DecisionValidationError(str(error)) from error

    def _decision_directory(self) -> Path:
        runtime_dir = self.workspace_root / ".auto-pm"
        try:
            require_safe_workspace_path(
                self.workspace_root,
                runtime_dir,
                label="Decision runtime 目录",
            )
            return require_safe_workspace_path(
                self.workspace_root,
                self.decisions_dir,
                label="Decision 目录",
            )
        except ControlRootGuardError as error:
            raise DecisionValidationError(str(error)) from error

    def _decision_target(self, decision_id: str) -> Path:
        decisions_dir = self._decision_directory()
        target = decisions_dir / f"{decision_id}.json"
        try:
            return require_safe_workspace_path(
                self.workspace_root,
                target,
                label="Decision 文件",
            )
        except ControlRootGuardError as error:
            raise DecisionValidationError(str(error)) from error

    @staticmethod
    def _unique_regular_file_identity(path: Path, *, label: str) -> tuple[int, int, int, int]:
        try:
            metadata = path.stat()
        except OSError as error:
            raise DecisionValidationError(f"{label}无法读取") from error
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise DecisionValidationError(f"{label}必须是唯一链接的普通文件")
        return (
            int(metadata.st_dev),
            int(metadata.st_ino),
            int(metadata.st_size),
            int(metadata.st_mtime_ns),
        )

    @staticmethod
    def _canonical_decision_id(decision_id: str) -> str:
        if not isinstance(decision_id, str) or decision_id != decision_id.strip():
            raise DecisionValidationError("Decision ID 前后不得包含空白")
        if not is_canonical_decision_id(decision_id):
            raise DecisionValidationError("Decision ID 格式非法")
        return decision_id

    @staticmethod
    def _reject_duplicate_json_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise DecisionValidationError(f"Decision JSON 包含重复字段: {key}")
            result[key] = value
        return result

    @staticmethod
    def _reject_duplicate_registry_fields(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise DecisionValidationError(f"Workspace Registry 包含重复字段: {key}")
            result[key] = value
        return result

    @staticmethod
    def _validate_runtime_change_id(change_id: str) -> None:
        if change_id != change_id.strip() or not is_canonical_runtime_change_id(change_id):
            raise DecisionValidationError(
                "runtime capability change_id 必须是 canonical CHG basename"
            )

    @staticmethod
    def _unique_runtime_chg_field(
        source: str,
        *,
        section_three: str,
        section: str,
        field: str,
    ) -> str:
        section_pattern = re.compile(
            rf"^###[ \t]+{re.escape(section)}(?:[ \t]+[^\r\n]*)?[ \t]*\r?\n"
            rf"(?P<body>.*?)(?=^#{{1,6}}(?:[ \t]+|$)|\Z)",
            flags=re.MULTILINE | re.DOTALL,
        )
        sections = [match.group("body") for match in section_pattern.finditer(section_three)]
        if len(sections) != 1:
            raise DecisionValidationError(f"运行态 CHG §{section} 必须唯一且显式存在")
        field_pattern = re.compile(
            rf"^\|\s*(?:\*\*)?{re.escape(field)}(?:\*\*)?\s*\|"
            rf"\s*([^|\r\n]+?)\s*\|\s*$",
            flags=re.MULTILINE,
        )
        values = [match.group(1).strip() for match in field_pattern.finditer(sections[0])]
        if len(values) != 1 or not values[0]:
            raise DecisionValidationError(f"运行态 CHG §{section} 的{field}必须恰好出现一次")
        all_occurrences = list(field_pattern.finditer(source))
        if len(all_occurrences) != 1:
            raise DecisionValidationError(f"运行态 CHG 的{field}只能出现在唯一 §{section} 内")
        return values[0]

    @staticmethod
    def _without_fenced_code_blocks(source: str) -> str:
        """Mask Markdown fenced code so examples cannot become runtime authority."""

        masked: list[str] = []
        fence_character = ""
        fence_length = 0
        opener = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})")
        for line in source.splitlines(keepends=True):
            if not fence_character:
                match = opener.match(line)
                if match is None:
                    masked.append(line)
                    continue
                fence = match.group("fence")
                fence_character = fence[0]
                fence_length = len(fence)
            else:
                closer = re.compile(
                    rf"^[ \t]{{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*(?:\r?\n)?$"
                )
                if closer.match(line):
                    fence_character = ""
                    fence_length = 0
            if line.endswith("\r\n"):
                masked.append("\r\n")
            elif line.endswith("\n"):
                masked.append("\n")
            else:
                masked.append("")
        return "".join(masked)

    @classmethod
    def _runtime_authority_view(cls, source: str) -> str:
        """Remove non-rendered Markdown/HTML blocks from the signing projection."""

        def mask(match: re.Match[str]) -> str:
            return re.sub(r"[^\r\n]", " ", match.group(0))

        visible = cls._without_fenced_code_blocks(source)
        visible = re.sub(r"<!--.*?(?:-->|\Z)", mask, visible, flags=re.DOTALL)
        # Runtime authority must stay visibly reviewable as Markdown. Raw HTML
        # can conceal authority through CSS, malformed markup, nested elements,
        # or terminator-looking attribute values, so signing fails closed on a
        # line-start HTML block. Inline tags inside a table cell remain valid.
        html_scan = re.sub(r"<br\s*/?>", "", visible, flags=re.IGNORECASE)
        if re.search(
            r"<(?:(?:/)?[A-Za-z][A-Za-z0-9-]*(?:\s|/?>|$)|\?|!\[CDATA\[|![A-Z])",
            html_scan,
            flags=re.IGNORECASE,
        ):
            raise DecisionValidationError("运行态 CHG 不允许 raw HTML block")
        visible = re.sub(
            r"^(?: {4}|\t)[^\r\n]*(?:\r?\n|\Z)",
            mask,
            visible,
            flags=re.MULTILINE,
        )
        return visible

    @staticmethod
    def _without_raw_html_blocks(source: str) -> str:
        """Mask CommonMark-style raw HTML blocks, including unclosed blocks."""

        def masked_line(line: str) -> str:
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            return " " * (len(line) - len(ending)) + ending

        masked: list[str] = []
        terminator = ""
        raw_tag = re.compile(r"<(?P<tag>pre|script|style|textarea)\b", re.IGNORECASE)
        generic_tag = re.compile(r"<(?P<closing>/)?(?P<tag>[A-Za-z][A-Za-z0-9-]*)(?:\s|/?>|$)")
        void_tags = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
        for line in source.splitlines(keepends=True):
            content = (
                line[:-2] if line.endswith("\r\n") else line[:-1] if line.endswith("\n") else line
            )
            start = re.match(r"^[ \t]{0,3}(?P<body>.*)$", content)
            body = start.group("body") if start is not None else content
            if terminator:
                masked.append(masked_line(line))
                if terminator.casefold() in body.casefold():
                    terminator = ""
                continue

            raw_match = raw_tag.match(body)
            if body.startswith("<!--"):
                terminator = "-->"
            elif body.startswith("<?"):
                terminator = "?>"
            elif body.startswith("<![CDATA["):
                terminator = "]]>"
            elif re.match(r"<![A-Z]", body):
                terminator = ">"
            elif raw_match is not None:
                terminator = f"</{raw_match.group('tag')}>"
            elif (generic_match := generic_tag.match(body)) is not None:
                tag = generic_match.group("tag").casefold()
                if (
                    generic_match.group("closing") is None
                    and tag not in void_tags
                    and "/>" not in body
                ):
                    terminator = f"</{tag}>"
            else:
                masked.append(line)
                continue

            masked.append(masked_line(line))
            if terminator and terminator.casefold() in body.casefold():
                terminator = ""
        return "".join(masked)

    @staticmethod
    def _hidden_runtime_authority_marker(source: str, visible: str) -> bool:
        """Reject authority-shaped data concealed from rendered Markdown."""

        marker = re.compile(
            r"(?:^\s*#{2,3}\s*(?:3(?:\.[04])?|5(?:\.\d+)?)"
            r"(?:[\s.、：:]|$))|"
            r"(?:^\s*\|\s*(?:\*\*)?"
            r"(?:变更编号|项目编号|变更状态|涉及文件/交付物)"
            r"(?:\*\*)?\s*\|)"
        )
        for original_line, visible_line in zip(
            source.splitlines(), visible.splitlines(), strict=True
        ):
            if original_line != visible_line and marker.search(original_line):
                return True
        return False

    @staticmethod
    def _runtime_top_level_section(
        source: str,
        section: str,
        *,
        required: bool,
    ) -> str:
        wrong_hierarchy = re.compile(
            rf"^##(?!#)[ \t]+{re.escape(section)}\.[0-9]",
            flags=re.MULTILINE,
        )
        if wrong_hierarchy.search(source):
            raise DecisionValidationError(f"运行态 CHG §{section} 层级非法")
        heading = re.compile(
            rf"^##(?!#)[ \t]+{re.escape(section)}"
            rf"(?=[ \t、：:]|\.(?![0-9])|$)[^\r\n]*(?:\r?\n|\Z)",
            flags=re.MULTILINE,
        )
        matches = list(heading.finditer(source))
        if len(matches) != 1:
            if required:
                raise DecisionValidationError(f"运行态 CHG §{section} 必须唯一")
            if matches:
                raise DecisionValidationError(f"运行态 CHG §{section} 不得重复")
            return ""
        start = matches[0].end()
        next_heading = re.search(r"^#{1,2}(?!#)[ \t]+", source[start:], flags=re.MULTILINE)
        end = start + next_heading.start() if next_heading is not None else len(source)
        return source[start:end]

    @classmethod
    def _validate_runtime_top_level_sections(cls, source: str) -> tuple[str, str]:
        section_three = cls._runtime_top_level_section(source, "3", required=True)
        section_five = cls._runtime_top_level_section(source, "5", required=False)
        file_authority = re.compile(
            r"^\|\s*(?:\*\*)?涉及文件/交付物(?:\*\*)?\s*\|",
            flags=re.MULTILINE,
        )
        if len(file_authority.findall(source)) != len(file_authority.findall(section_five)):
            raise DecisionValidationError("运行态 CHG 的涉及文件/交付物只能出现在唯一 §5 内")
        return section_three, section_five

    @staticmethod
    def _is_archive_or_backup_part(part: str) -> bool:
        folded = part.casefold()
        return (
            folded == ".auto-pm"
            or "archive" in folded
            or "backup" in folded
            or "归档" in part
            or "备份" in part
        )

    @staticmethod
    def _path_key(path: Path) -> str:
        normalized = os.path.normcase(os.path.normpath(str(path.resolve())))
        return normalized.casefold() if os.name == "nt" else normalized
