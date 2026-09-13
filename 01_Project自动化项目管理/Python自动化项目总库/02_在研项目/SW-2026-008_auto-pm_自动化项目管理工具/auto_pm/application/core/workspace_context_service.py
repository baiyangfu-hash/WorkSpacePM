"""Resolve bounded workspace identity from explicit topology evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from auto_pm.core.project_scanner import ProjectScanner

from auto_pm.contracts.workspace_context import (
    ContextEvidence,
    ContextProject,
    WorkspaceContext,
    WorkspaceProjectMapping,
    WorkspaceRegistry,
)


class WorkspaceContextError(RuntimeError):
    """Raised when an invocation cannot be assigned safely to one project."""


class WorkspaceContextService:
    """Resolve context without global scans, session text inference, or latest state."""

    _DEFAULT_REGISTRY = Path(
        "SYS-2026-001_WorkspaceGovernance",
        "workspace_registry.json",
    )

    def __init__(
        self,
        workspace_root: str,
        registry_path: str | Path | None = None,
        package_file_provider: Callable[[], str | Path | None] | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        selected = Path(registry_path) if registry_path is not None else self._DEFAULT_REGISTRY
        self._registry_path = (
            selected.resolve() if selected.is_absolute() else (self._workspace_root / selected).resolve()
        )
        self._require_workspace_path(self._registry_path, "Workspace Registry")
        self._scanner = ProjectScanner(str(self._workspace_root))
        self._package_file_provider = package_file_provider or self._loaded_package_file

    def resolve(
        self,
        project_id: str = "",
        start_path: str | Path | None = None,
    ) -> WorkspaceContext:
        """Return a context.v2 identity card from the registry and a local anchor."""
        candidate_path = Path(start_path) if start_path is not None else Path.cwd()
        candidate_path = candidate_path.resolve()
        self._require_workspace_path(candidate_path, "调用目录")
        _, mappings = self._load_registry()

        if project_id.strip():
            mapping = self._mapping_for_id(project_id.strip(), mappings)
            project_path, project = self._project_from_mapping(mapping)
            source: Literal["explicit", "directory"] = "explicit"
        else:
            project_path, project = self._project_for_directory(candidate_path)
            mapping = self._mapping_for_id(project.project_id, mappings)
            registered_path = self._mapped_directory(mapping.project_root, "project_root")
            if registered_path != project_path:
                raise WorkspaceContextError(
                    f"目录锚点与 Workspace Registry 冲突: {self._relative(project_path)}"
                )
            source = "directory"

        development_root = self._mapped_directory(mapping.development_root, "development_root")
        if development_root != project_path:
            raise WorkspaceContextError("development_root 必须与已验证项目根一致")
        control_id, control_session = self._control_mapping(mapping, mappings)
        runtime_root = self._optional_mapped_directory(mapping.runtime_root, "runtime_root")
        configured_release_id, release_pointer = self._release_pointer(runtime_root)
        (
            effective_release_id,
            runtime_load_path,
            runtime_fallback_reason,
            loaded_package_file,
        ) = self._runtime_identity(runtime_root, configured_release_id)
        conflicts = self._runtime_conflicts(
            runtime_root,
            configured_release_id,
            effective_release_id,
            runtime_fallback_reason,
        )
        anchor = self._anchor_file(project_path)
        read_set = self._read_set(
            self._registry_path,
            anchor,
            release_pointer,
            loaded_package_file,
        )
        runtime_relative = self._relative(runtime_root) if runtime_root else ""
        evidence_id = self._evidence_id(
            project.project_id,
            read_set,
            control_id,
            runtime_relative,
            configured_release_id,
            effective_release_id,
            runtime_load_path,
            runtime_fallback_reason,
            conflicts,
        )
        return WorkspaceContext(
            workspace_root=str(self._workspace_root),
            resolution_source=source,
            subject_project_id=project.project_id,
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
            development_root=self._relative(development_root),
            runtime_root=runtime_relative,
            release_id=configured_release_id,
            configured_release_id=configured_release_id,
            effective_release_id=effective_release_id,
            runtime_load_path=runtime_load_path,
            runtime_fallback_reason=runtime_fallback_reason,
            read_set=tuple(read_set),
            evidence_id=evidence_id,
            conflicts=conflicts,
        )

    def _load_registry(
        self,
    ) -> tuple[WorkspaceRegistry, dict[str, WorkspaceProjectMapping]]:
        if not self._registry_path.is_file():
            raise WorkspaceContextError(
                f"Workspace Registry 不存在: {self._relative(self._registry_path)}"
            )
        try:
            registry = WorkspaceRegistry.model_validate_json(self._read_text(self._registry_path))
        except ValueError as error:
            raise WorkspaceContextError("Workspace Registry schema 无效") from error
        mappings: dict[str, WorkspaceProjectMapping] = {}
        for mapping in registry.projects:
            if mapping.project_id in mappings:
                raise WorkspaceContextError(
                    f"Workspace Registry 存在重复项目: {mapping.project_id}"
                )
            mappings[mapping.project_id] = mapping
        return registry, mappings

    @staticmethod
    def _mapping_for_id(
        project_id: str,
        mappings: dict[str, WorkspaceProjectMapping],
    ) -> WorkspaceProjectMapping:
        mapping = mappings.get(project_id)
        if mapping is None:
            raise WorkspaceContextError(f"项目未登记到 Workspace Registry: {project_id}")
        return mapping

    def _project_from_mapping(self, mapping: WorkspaceProjectMapping) -> tuple[Path, Any]:
        project_path = self._mapped_directory(mapping.project_root, "project_root")
        project = self._scanner.try_identify_project(str(project_path))
        if project is None:
            raise WorkspaceContextError(f"登记路径缺少项目锚点: {self._relative(project_path)}")
        if project.project_id != mapping.project_id:
            raise WorkspaceContextError(
                f"登记项目与目录锚点不一致: {mapping.project_id} != {project.project_id}"
            )
        return project_path, project

    def _project_for_directory(self, start_path: Path) -> tuple[Path, Any]:
        for path in self._ancestors_within_workspace(start_path):
            project = self._scanner.try_identify_project(str(path))
            if project is not None:
                return path, project
        raise WorkspaceContextError("调用目录未解析到项目；请提供项目编号或从项目目录执行命令")

    def _ancestors_within_workspace(self, start_path: Path) -> list[Path]:
        paths: list[Path] = []
        current = start_path
        while True:
            paths.append(current)
            if current == self._workspace_root:
                return paths
            current = current.parent

    def _control_mapping(
        self,
        mapping: WorkspaceProjectMapping,
        mappings: dict[str, WorkspaceProjectMapping],
    ) -> tuple[str, Path | None]:
        control_id = mapping.control_project_id.strip()
        control_session_value = mapping.control_pm_session.strip()
        if not control_id and not control_session_value:
            return "", None
        if not control_id or not control_session_value:
            raise WorkspaceContextError(
                "Workspace Registry 必须同时声明 control_project_id 与 control_pm_session"
            )
        if control_id not in mappings:
            raise WorkspaceContextError(f"控制项目未登记到 Workspace Registry: {control_id}")
        control_session = self._mapped_file(control_session_value, "control_pm_session")
        if control_session.stem != f"PM_SESSION_{control_id}":
            raise WorkspaceContextError("control_project_id 与 control_pm_session 不一致")
        return control_id, control_session

    def _mapped_directory(self, value: str, label: str) -> Path:
        path = self._mapped_path(value, label)
        if not path.is_dir():
            raise WorkspaceContextError(f"{label} 不存在或不是目录: {self._relative(path)}")
        return path

    def _optional_mapped_directory(self, value: str, label: str) -> Path | None:
        return self._mapped_directory(value, label) if value.strip() else None

    def _mapped_file(self, value: str, label: str) -> Path:
        path = self._mapped_path(value, label)
        if not path.is_file():
            raise WorkspaceContextError(f"{label} 不存在或不是文件: {self._relative(path)}")
        return path

    def _mapped_path(self, value: str, label: str) -> Path:
        candidate = Path(value.strip())
        if not value.strip() or candidate.is_absolute():
            raise WorkspaceContextError(f"{label} 必须是非空工作区相对路径")
        path = (self._workspace_root / candidate).resolve()
        self._require_workspace_path(path, label)
        return path

    def _release_pointer(self, runtime_root: Path | None) -> tuple[str, Path | None]:
        if runtime_root is None:
            return "", None
        pointer = runtime_root / "active_release.json"
        if not pointer.is_file():
            raise WorkspaceContextError(
                f"runtime_root 缺少 active_release.json: {self._relative(runtime_root)}"
            )
        try:
            data = json.loads(self._read_text(pointer))
        except json.JSONDecodeError as error:
            raise WorkspaceContextError("active_release.json 不是有效 JSON") from error
        release_id = data.get("release_id", "")
        if not isinstance(release_id, str) or not release_id.strip():
            raise WorkspaceContextError("active_release.json 缺少非空字符串 release_id")
        release_root = runtime_root / "releases" / release_id
        if not release_root.is_dir():
            raise WorkspaceContextError(f"active release 不存在: {self._relative(release_root)}")
        return release_id, pointer

    def _runtime_identity(
        self,
        runtime_root: Path | None,
        configured_release_id: str,
    ) -> tuple[str, str, str, Path | None]:
        """Derive the active package identity from the module already loaded by Python."""
        if runtime_root is None:
            return "", "", "", None
        try:
            package_file_value = self._package_file_provider()
        except Exception:
            return "", "", "loaded_package_file_unavailable", None
        if not isinstance(package_file_value, (str, Path)) or not str(package_file_value).strip():
            return "", "", "loaded_package_file_unavailable", None

        try:
            package_file = Path(package_file_value).resolve()
        except (OSError, ValueError):
            return "", "", "loaded_package_file_unavailable", None
        if not package_file.is_file():
            return "", "", "loaded_package_file_unavailable", None
        try:
            package_file.relative_to(self._workspace_root)
        except ValueError:
            return "", "", "loaded_package_outside_workspace", None

        load_path = self._relative(package_file)
        releases_root = (runtime_root / "releases").resolve()
        try:
            release_relative = package_file.relative_to(releases_root)
        except ValueError:
            return "", load_path, "loaded_package_outside_runtime_releases", package_file

        parts = release_relative.parts
        if len(parts) != 3 or parts[1:] != ("auto_pm", "__init__.py"):
            return "", load_path, "loaded_package_not_release_package", package_file
        effective_release_id = parts[0]
        if not effective_release_id:
            return "", load_path, "loaded_package_release_id_unavailable", package_file
        return effective_release_id, load_path, "", package_file

    @staticmethod
    def _runtime_conflicts(
        runtime_root: Path | None,
        configured_release_id: str,
        effective_release_id: str,
        runtime_fallback_reason: str,
    ) -> tuple[str, ...]:
        if runtime_root is None:
            return ()
        if runtime_fallback_reason:
            return ("RUNTIME_IDENTITY_UNVERIFIED",)
        if effective_release_id != configured_release_id:
            return ("RUNTIME_IDENTITY_DIVERGENCE",)
        return ()

    @staticmethod
    def _loaded_package_file() -> str | None:
        package = sys.modules.get("auto_pm")
        module_file = getattr(package, "__file__", None) if package is not None else None
        return module_file if isinstance(module_file, str) else None

    def _read_set(self, *paths: Path | None) -> list[ContextEvidence]:
        unique: list[Path] = []
        for path in paths:
            if path is not None and path not in unique:
                unique.append(path)
        return [
            ContextEvidence(path=self._relative(path), sha256=self._sha256(path))
            for path in unique
        ]

    def _anchor_file(self, project_path: Path) -> Path:
        for name in (".copier-answers.yml", ".plc.json"):
            candidate = project_path / name
            if candidate.is_file():
                return candidate
        sessions = sorted(project_path.glob("PM_SESSION_*.md"))
        if len(sessions) == 1:
            return sessions[0]
        raise WorkspaceContextError(f"项目缺少唯一可验证锚点: {self._relative(project_path)}")

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _evidence_id(
        project_id: str,
        read_set: list[ContextEvidence],
        control_id: str,
        runtime_root: str,
        configured_release_id: str,
        effective_release_id: str,
        runtime_load_path: str,
        runtime_fallback_reason: str,
        conflicts: tuple[str, ...],
    ) -> str:
        payload = {
            "project_id": project_id,
            "control_project_id": control_id,
            "runtime_root": runtime_root,
            "configured_release_id": configured_release_id,
            "effective_release_id": effective_release_id,
            "runtime_load_path": runtime_load_path,
            "runtime_fallback_reason": runtime_fallback_reason,
            "conflicts": conflicts,
            "read_set": [entry.model_dump() for entry in read_set],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        return f"CTX-{digest.upper()}"

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise WorkspaceContextError(f"无法读取文件: {path}") from error

    def _require_workspace_path(self, path: Path, label: str) -> None:
        try:
            path.relative_to(self._workspace_root)
        except ValueError as error:
            raise WorkspaceContextError(f"{label}位于工作空间外，拒绝解析: {path}") from error

    def _relative(self, path: Path) -> str:
        self._require_workspace_path(path, "路径")
        return path.relative_to(self._workspace_root).as_posix()
