"""Compile bounded PM cold-start context from existing workspace evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.core.ai_handoff_service import AiHandoffService
from auto_pm.core.project_fact_service import ProjectFactService

from auto_pm.contracts.pm_resume_context import PmResumeContext, ResumeHandoff
from auto_pm.contracts.project_fact_snapshot import FileFingerprint


class PmResumeError(RuntimeError):
    """Raised when a cold-start context cannot be assembled safely."""


class PmResumeService:
    """Build a compact decision view without creating a second PM ledger."""

    MAX_ACTIVE_WBS = 8

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._facts = ProjectFactService(str(self._workspace_root))
        self._handoffs = AiHandoffService(self._workspace_root)

    def collect(self, project_id: str, control_project_id: str = "") -> PmResumeContext:
        """Return the provider-neutral context an AI must consume before planning."""
        fact = self._facts.collect(project_id)
        subject_session = Path(fact.pm_session.path)
        control_session = self._find_control_session(
            project_id,
            subject_session,
            control_project_id,
        )
        content = self._read_text(control_session)
        control_id = control_project_id or self._project_id_from_session(control_session) or project_id
        active = self._handoffs.list_active(project_id)
        handoffs = [
            ResumeHandoff(
                request_id=str(item["request_id"]),
                status=str(item["status"]),
                lifecycle_state=self._handoffs._lifecycle_state(item),
                executor_skill=str(item["executor_skill"]),
                summary=str(item["summary"]),
            )
            for item in active[:5]
        ]
        changes = self._active_changes(content, fact.open_changes)
        read_set = self._read_set(control_session, subject_session, fact.open_changes, changes)
        fingerprint = self._fingerprint(control_session)
        collected_at = datetime.now(UTC)
        evidence_seed = {
            "project_id": project_id,
            "control_session": fingerprint.model_dump(),
            "fact_evidence_id": fact.evidence_id,
            "handoffs": [item.model_dump() for item in handoffs],
            "changes": changes,
        }
        digest = hashlib.sha256(
            json.dumps(evidence_seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return PmResumeContext(
            evidence_id=f"RESUME-{digest[:16].upper()}",
            collected_at=collected_at,
            subject_project_id=project_id,
            control_project_id=control_id,
            fact_evidence_id=fact.evidence_id,
            git_head=fact.git.head,
            git_clean=not fact.git.status,
            control_pm_session=fingerprint,
            active_change_numbers=changes,
            current_focus=self._current_focus(content),
            active_wbs=self._active_wbs(content, project_id),
            active_handoffs=handoffs,
            next_legal_action=self._next_action(handoffs),
            read_set=read_set,
            expansion_triggers=[
                "事实包过期、Git/PM_SESSION 指纹变化或 control_project_id 存在多个候选。",
                "read_set 无法解释用户需求，或需要定位新的业务符号。",
            ],
        )

    def _find_control_session(
        self,
        project_id: str,
        subject_session: Path,
        control_project_id: str,
    ) -> Path:
        candidates = [
            path
            for path in sorted(self._workspace_root.rglob("PM_SESSION_*.md"))
            if not any(
                "archive" in part.lower() or "归档" in part or part == ".auto-pm"
                for part in path.parts
            )
        ]
        if control_project_id:
            matches = [path for path in candidates if self._project_id_from_session(path) == control_project_id]
            if len(matches) != 1:
                raise PmResumeError(f"control_project_id 未唯一解析到 PM_SESSION: {control_project_id}")
            return matches[0]
        referenced = [
            path
            for path in candidates
            if path != subject_session and project_id in self._read_text(path)
        ]
        if len(referenced) == 1:
            return referenced[0]
        if len(referenced) > 1:
            system_control = [
                path for path in referenced if self._project_id_from_session(path).startswith("SYS-")
            ]
            if len(system_control) == 1:
                return system_control[0]
            current = [path for path in referenced if "current_focus" in self._read_text(path)]
            if len(current) == 1:
                return current[0]
            raise PmResumeError("检测到多个治理 PM_SESSION；请显式提供 --control-pid")
        return subject_session

    @staticmethod
    def _project_id_from_session(path: Path) -> str:
        return path.stem.removeprefix("PM_SESSION_")

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise PmResumeError(f"无法读取 PM_SESSION: {path}") from error

    @staticmethod
    def _fingerprint(path: Path) -> FileFingerprint:
        content = path.read_bytes()
        return FileFingerprint(
            path=str(path),
            sha256=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
        )

    @staticmethod
    def _current_focus(content: str) -> str:
        match = re.search(r"^-\s*current_focus:\s*(.+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _active_wbs(self, content: str, project_id: str) -> list[str]:
        rows = [
            line.strip()
            for line in content.splitlines()
            if project_id in line and any(marker in line for marker in ("[待批准]", "[后续]", "[进行中]"))
        ]
        return rows[: self.MAX_ACTIVE_WBS]

    @staticmethod
    def _active_changes(content: str, open_changes: list[object]) -> list[str]:
        known = {str(getattr(change, "change_number", "")) for change in open_changes}
        mentioned = set(re.findall(r"CHG-[A-Z]+-\d{4}-\d{3}", content))
        return sorted(number for number in known if number in mentioned) or sorted(known)[:3]

    @staticmethod
    def _read_set(
        control_session: Path,
        subject_session: Path,
        open_changes: list[object],
        changes: list[str],
    ) -> list[str]:
        result = [str(control_session)]
        if subject_session != control_session:
            result.append(str(subject_session))
        for change in open_changes:
            if getattr(change, "change_number", "") in changes:
                result.append(str(getattr(change, "file_path", "")))
                break
        return result[:3]

    @staticmethod
    def _next_action(handoffs: list[ResumeHandoff]) -> str:
        states = {handoff.lifecycle_state for handoff in handoffs}
        if "completed" in states:
            return "PM 收口：预检 handoff_result 后执行 close 与台账落账。"
        if states & {"claimed", "in_progress"}:
            return "等待执行端心跳或 result-submit；租约到期后执行 handoff timeout。"
        if "awaiting_pickup" in states:
            return "执行端领取：选择可用执行器并执行 handoff claim/start。"
        if "stale" in states:
            return "执行端失联：审查 expired 请求后由 PM 重派或关闭。"
        return "阶段 0：基于事实包完成影响分析，再进入阶段 1 报批。"
