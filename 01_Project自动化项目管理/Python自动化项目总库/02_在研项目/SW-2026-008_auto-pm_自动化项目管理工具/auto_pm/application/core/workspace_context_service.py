"""Resolve per-invocation project context from workspace evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from auto_pm.core.project_scanner import ProjectScanner

from auto_pm.contracts.workspace_context import ContextEvidence, ContextProject, WorkspaceContext


class WorkspaceContextError(RuntimeError):
    """Raised when an invocation cannot be assigned safely to one project."""


class WorkspaceContextService:
    """Resolve context without consulting or changing global active-project state."""

    _RUNTIME_ROOT_RE = re.compile(r"^-\s*runtime_root:\s*`?([^`\r\n]+)`?\s*$", re.MULTILINE)
    _CONTROL_ID_RE = re.compile(r"^-\s*control_project_id:\s*([A-Z]{2,4}-\d{4}-\d{3})\s*$", re.MULTILINE)
    _CONTROL_SESSION_RE = re.compile(r"^-\s*control_pm_session:\s*`?([^`\r\n]+)`?\s*$", re.MULTILINE)

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._scanner = ProjectScanner(str(self._workspace_root))

    def resolve(
        self,
        project_id: str = "",
        start_path: str | Path | None = None,
    ) -> WorkspaceContext:
        """Return a project card from explicit identity or a directory ancestor.

        A stale UI selection is deliberately not a fallback: it belongs to a
        previous invocation and cannot prove the identity of this one.
        """
        candidate_path = Path(start_path) if start_path is not None else Path.cwd()
        candidate_path = candidate_path.resolve()
        self._require_workspace_path(candidate_path, "调用目录")
        if project_id.strip():
            project = self._project_for_explicit_id(project_id.strip(), candidate_path)
            source: Literal["explicit", "directory"] = "explicit"
        else:
            project = self._project_for_directory(candidate_path)
            source = "directory"

        project_path = Path(project.path).resolve()
        self._require_workspace_path(project_path, "项目路径")
        session = self._find_subject_session(project_path, project.project_id)
        runtime_root = self._runtime_root(session)
        control_id, control_session = self._find_control(session)
        release_id, release_pointer = self._release_pointer(runtime_root)
        read_set = self._read_set(project_path, session, release_pointer)
        evidence_id = self._evidence_id(project.project_id, read_set, control_id, runtime_root, release_id)
        return WorkspaceContext(
            workspace_root=str(self._workspace_root),
            resolution_source=source,
            subject=ContextProject(
                project_id=project.project_id,
                name=project.name,
                path=self._relative(project_path),
                stack=project.stack,
                phase=project.phase,
                source=project.source,
            ),
            control_project_id=control_id,
            control_pm_session=self._relative(control_session) if control_session else "",
            development_root=self._relative(project_path),
            runtime_root=self._relative(Path(runtime_root)) if runtime_root else "",
            release_id=release_id,
            read_set=tuple(read_set),
            evidence_id=evidence_id,
        )

    def _project_for_directory(self, start_path: Path) -> Any:
        anchors = self._ancestor_anchors(start_path)
        if not anchors:
            raise WorkspaceContextError("调用目录未解析到项目；请提供项目编号或从项目目录执行命令")
        return anchors[0][1]

    def _project_for_explicit_id(self, project_id: str, start_path: Path) -> Any:
        matches = [(path, project) for path, project in self._candidate_anchors(start_path) if project.project_id == project_id]
        unique = dict(matches)
        if len(unique) != 1:
            if not unique:
                raise WorkspaceContextError(
                    f"显式项目未在调用目录的局部锚点中解析: {project_id}；请使用该项目目录的 --path"
                )
            choices = ", ".join(sorted(self._relative(path) for path in unique))
            raise WorkspaceContextError(f"显式项目存在多个局部锚点: {project_id}: {choices}")
        return next(iter(unique.values()))

    def _ancestor_anchors(self, start_path: Path) -> list[tuple[Path, Any]]:
        anchors: list[tuple[Path, Any]] = []
        for path in self._ancestors_within_workspace(start_path):
            project = self._scanner.try_identify_project(str(path))
            if project is not None:
                anchors.append((path, project))
        return anchors

    def _candidate_anchors(self, start_path: Path) -> list[tuple[Path, Any]]:
        candidates = self._ancestor_anchors(start_path)
        for parent in self._ancestors_within_workspace(start_path):
            for child in sorted(parent.iterdir()):
                if not child.is_dir() or self._is_archived(child):
                    continue
                project = self._scanner.try_identify_project(str(child))
                if project is not None:
                    candidates.append((child.resolve(), project))
        return candidates

    def _ancestors_within_workspace(self, start_path: Path) -> list[Path]:
        paths: list[Path] = []
        current = start_path
        while True:
            paths.append(current)
            if current == self._workspace_root:
                return paths
            current = current.parent

    def _find_control(self, subject_session: Path | None) -> tuple[str, Path | None]:
        if subject_session is None:
            return "", None
        content = self._read_text(subject_session)
        control_id = self._single_match(self._CONTROL_ID_RE, content, "control_project_id")
        control_session_value = self._single_match(
            self._CONTROL_SESSION_RE, content, "control_pm_session"
        )
        if not control_id and not control_session_value:
            return "", None
        if not control_id or not control_session_value:
            raise WorkspaceContextError("治理映射必须同时声明 control_project_id 与 control_pm_session")
        candidate = Path(control_session_value)
        control_session = candidate if candidate.is_absolute() else self._workspace_root / candidate
        control_session = control_session.resolve()
        self._require_workspace_path(control_session, "control_pm_session")
        if not control_session.is_file():
            raise WorkspaceContextError(f"control_pm_session 不存在: {self._relative(control_session)}")
        if control_session.stem != f"PM_SESSION_{control_id}":
            raise WorkspaceContextError("control_project_id 与 control_pm_session 不一致")
        return control_id, control_session

    def _find_subject_session(self, project_path: Path, project_id: str) -> Path | None:
        expected = project_path / f"PM_SESSION_{project_id}.md"
        if expected.is_file():
            return expected
        candidates = sorted(project_path.glob("PM_SESSION_*.md"))
        return candidates[0] if len(candidates) == 1 else None

    def _runtime_root(self, session: Path | None) -> str:
        if session is None:
            return ""
        match = self._RUNTIME_ROOT_RE.search(self._read_text(session))
        if not match:
            return ""
        candidate = Path(match.group(1).strip())
        resolved = candidate if candidate.is_absolute() else self._workspace_root / candidate
        if not resolved.is_dir():
            return ""
        resolved = resolved.resolve()
        self._require_workspace_path(resolved, "runtime_root")
        return str(resolved)

    def _release_pointer(self, runtime_root: str) -> tuple[str, Path | None]:
        if not runtime_root:
            return "", None
        pointer = Path(runtime_root) / "active_release.json"
        if not pointer.is_file():
            return "", None
        try:
            data = json.loads(self._read_text(pointer))
        except json.JSONDecodeError as error:
            raise WorkspaceContextError(f"active_release.json 不是有效 JSON: {pointer}") from error
        release_id = data.get("release_id", "")
        if not isinstance(release_id, str):
            raise WorkspaceContextError("active_release.json 缺少字符串 release_id")
        return release_id, pointer

    def _read_set(
        self, project_path: Path, session: Path | None, release_pointer: Path | None
    ) -> list[ContextEvidence]:
        anchor = self._anchor_file(project_path)
        paths: list[Path] = []
        for path in (anchor, session, release_pointer):
            if path is not None and path not in paths:
                paths.append(path)
        return [ContextEvidence(path=self._relative(path), sha256=self._sha256(path)) for path in paths]

    def _anchor_file(self, project_path: Path) -> Path:
        for name in (".copier-answers.yml", ".plc.json"):
            candidate = project_path / name
            if candidate.is_file():
                return candidate
        sessions = sorted(project_path.glob("PM_SESSION_*.md"))
        if len(sessions) == 1:
            return sessions[0]
        raise WorkspaceContextError(f"项目缺少可验证锚点: {self._relative(project_path)}")

    @staticmethod
    def _single_match(pattern: re.Pattern[str], content: str, label: str) -> str:
        values = {value.strip() for value in pattern.findall(content) if value.strip()}
        if len(values) > 1:
            raise WorkspaceContextError(f"{label} 存在冲突声明")
        return next(iter(values), "")

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _evidence_id(
        project_id: str,
        read_set: list[ContextEvidence],
        control_id: str,
        runtime_root: str,
        release_id: str,
    ) -> str:
        payload = {
            "project_id": project_id,
            "control_project_id": control_id,
            "runtime_root": runtime_root,
            "release_id": release_id,
            "read_set": [entry.model_dump() for entry in read_set],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        return f"CTX-{digest.upper()}"

    @staticmethod
    def _is_archived(path: Path) -> bool:
        return any(part.lower() == "archive" or "归档" in part for part in path.parts)

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise WorkspaceContextError(f"无法读取 PM_SESSION: {path}") from error

    def _require_workspace_path(self, path: Path, label: str) -> None:
        try:
            path.relative_to(self._workspace_root)
        except ValueError as error:
            raise WorkspaceContextError(f"{label}位于工作空间外，拒绝解析: {path}") from error

    def _relative(self, path: Path) -> str:
        self._require_workspace_path(path, "路径")
        return path.relative_to(self._workspace_root).as_posix()
