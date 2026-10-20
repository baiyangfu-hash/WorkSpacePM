"""Register one existing project in the Workspace Registry (the only writer of that file).

Before this service the registry could only be edited by hand, so a project created from a template
was unknown to ``pm orient``, approval and the cockpit.  The service adds exactly one entry, never
rewrites or reorders the existing ones, and proves the result with the same resolver ``pm orient``
uses; if that proof fails the registry is restored byte for byte.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from auto_pm.core.project_scanner import ProjectScanner
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService

from auto_pm.contracts.workspace_context import WorkspaceProjectMapping, WorkspaceRegistry


class WorkspaceRegistryError(RuntimeError):
    """Raised when a project cannot be registered safely; the registry is then unchanged."""


@dataclass(frozen=True)
class RegistrationResult:
    """What was (or, for a dry run, would be) written."""

    mapping: WorkspaceProjectMapping
    already_registered: bool
    written: bool


class WorkspaceRegistryService:
    """Append one verified project mapping to ``workspace_registry.json``."""

    _DEFAULT_REGISTRY = Path("SYS-2026-001_WorkspaceGovernance", "workspace_registry.json")

    def __init__(self, workspace_root: str | Path, registry_path: str | Path | None = None) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        selected = Path(registry_path) if registry_path is not None else self._DEFAULT_REGISTRY
        self._registry_path = (
            selected.resolve() if selected.is_absolute() else (self._workspace_root / selected).resolve()
        )
        self._scanner = ProjectScanner(str(self._workspace_root))

    def register(
        self,
        project_id: str,
        project_root: str | Path | None = None,
        *,
        dry_run: bool = False,
    ) -> RegistrationResult:
        """Register ``project_id``; a project already registered at the same path is left as it is."""
        project_id = project_id.strip()
        if not project_id:
            raise WorkspaceRegistryError("项目编号不能为空")
        original, payload, registry = self._load()
        relative_root = self._project_relative_root(project_id, project_root)

        for existing in registry.projects:
            if existing.project_id == project_id:
                if existing.project_root == relative_root:
                    return RegistrationResult(mapping=existing, already_registered=True, written=False)
                raise WorkspaceRegistryError(
                    f"项目已登记在别的目录: {project_id} -> {existing.project_root}（本次指定 {relative_root}）"
                )
            if existing.project_root == relative_root:
                raise WorkspaceRegistryError(
                    f"该目录已登记为另一个项目: {relative_root} -> {existing.project_id}"
                )

        control_project_id, control_pm_session, runtime_root = self._shared_control(registry)
        mapping = WorkspaceProjectMapping(
            project_id=project_id,
            project_root=relative_root,
            development_root=relative_root,
            control_project_id=control_project_id,
            control_pm_session=control_pm_session,
            runtime_root=runtime_root,
        )
        if dry_run:
            return RegistrationResult(mapping=mapping, already_registered=False, written=False)

        projects = payload["projects"]
        if not isinstance(projects, list):
            raise WorkspaceRegistryError("Workspace Registry schema 无效，拒绝改写")
        projects.append(mapping.model_dump())
        self._write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        try:
            WorkspaceContextService(str(self._workspace_root), registry_path=self._registry_path).resolve(
                project_id, start_path=self._workspace_root / relative_root
            )
        except (WorkspaceContextError, OSError, ValueError) as error:
            self._registry_path.write_bytes(original)
            raise WorkspaceRegistryError(f"登记后校验失败，已恢复原登记表: {error}") from error
        return RegistrationResult(mapping=mapping, already_registered=False, written=True)

    def _load(self) -> tuple[bytes, dict[str, object], WorkspaceRegistry]:
        self._require_inside(self._registry_path, "Workspace Registry")
        if not self._registry_path.is_file():
            raise WorkspaceRegistryError(f"Workspace Registry 不存在: {self._registry_path}")
        original = self._registry_path.read_bytes()
        try:
            payload = json.loads(original.decode("utf-8"))
            registry = WorkspaceRegistry.model_validate(payload)
        except (UnicodeDecodeError, ValueError) as error:
            raise WorkspaceRegistryError("Workspace Registry schema 无效，拒绝改写") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list):
            raise WorkspaceRegistryError("Workspace Registry schema 无效，拒绝改写")
        return original, payload, registry

    def _project_relative_root(self, project_id: str, project_root: str | Path | None) -> str:
        if project_root is None:
            matches = [info for info in self._scanner.scan() if info.project_id == project_id]
            if not matches:
                raise WorkspaceRegistryError(f"工作区内找不到项目目录: {project_id}（可用 --path 指定）")
            candidate = Path(matches[0].path)
        else:
            candidate = Path(project_root)
            if not candidate.is_absolute():
                candidate = self._workspace_root / candidate
        path = candidate.resolve()
        self._require_inside(path, "项目目录")
        if not path.is_dir():
            raise WorkspaceRegistryError(f"项目目录不存在: {path}")
        relative = path.relative_to(self._workspace_root)
        if not relative.parts:
            raise WorkspaceRegistryError("不能把工作区根目录登记为项目")
        if any(self._is_archive_or_backup_part(part) for part in relative.parts):
            raise WorkspaceRegistryError(f"不能登记归档、备份或 .auto-pm 下的目录: {relative.as_posix()}")
        info = self._scanner.try_identify_project(str(path))
        if info is None:
            raise WorkspaceRegistryError(
                f"目录缺少项目锚点（.copier-answers.yml / .plc.json / PM_SESSION）: {relative.as_posix()}"
            )
        if info.project_id != project_id:
            raise WorkspaceRegistryError(f"目录锚点的项目编号不一致: {info.project_id} != {project_id}")
        return relative.as_posix()

    @staticmethod
    def _shared_control(registry: WorkspaceRegistry) -> tuple[str, str, str]:
        """Reuse the control project and runtime that the registered projects already share."""
        settings = Counter(
            (item.control_project_id, item.control_pm_session, item.runtime_root)
            for item in registry.projects
            if item.control_project_id
        )
        if not settings:
            return "", "", ""
        return settings.most_common(1)[0][0]

    def _write(self, text: str) -> None:
        temporary = self._registry_path.with_name(self._registry_path.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, self._registry_path)

    def _require_inside(self, path: Path, label: str) -> None:
        try:
            path.relative_to(self._workspace_root)
        except ValueError as error:
            raise WorkspaceRegistryError(f"{label}位于工作空间外: {path}") from error

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
