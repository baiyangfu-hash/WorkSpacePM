"""Deterministic PM_SESSION project-summary projection."""

from __future__ import annotations

from pathlib import Path

from auto_pm.contracts.continuity_resume import ContinuityResume


class PmSessionProjectionError(RuntimeError):
    """Raised when a projection target is outside its subject project."""


class PmSessionProjectionService:
    """Render project identity only; Work and Run remain in Continuity Store."""

    @staticmethod
    def render(resume: ContinuityResume) -> str:
        context = resume.context
        return "\n".join(
            [
                f"# PM_SESSION_{context.subject_project_id}",
                "",
                "> schema_version: pm-session-projection.v1",
                "> source_of_truth: .auto-pm/continuity.db",
                "",
                "## 0. Project Summary",
                "",
                f"- project_id: {context.subject_project_id}",
                f"- project_name: {context.subject.name}",
                f"- phase: {context.subject.phase}",
                f"- control_project_id: {context.control_project_id}",
                f"- development_root: {context.development_root}",
                f"- runtime_root: {context.runtime_root}",
                f"- release_id: {context.release_id}",
                f"- projection_evidence_id: {resume.evidence_id}",
                "",
                "## 1. Execution State",
                "",
                "Work、Run、Checkpoint、lease 与 Handoff 不在本文件维护；请读取 Continuity Store。",
                "",
            ]
        )

    def write(self, resume: ContinuityResume, target: str | Path) -> Path:
        subject_root = (
            Path(resume.context.workspace_root) / resume.context.subject.path
        ).resolve()
        resolved = Path(target).resolve()
        try:
            resolved.relative_to(subject_root)
        except ValueError as error:
            raise PmSessionProjectionError("PM_SESSION 投影目标必须位于 subject project 内") from error
        resolved.write_text(self.render(resume), encoding="utf-8", errors="replace")
        return resolved
