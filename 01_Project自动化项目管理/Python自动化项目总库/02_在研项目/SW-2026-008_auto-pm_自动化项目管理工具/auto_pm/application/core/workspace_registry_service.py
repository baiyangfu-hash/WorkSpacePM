"""Register one existing project in the Workspace Registry (the only writer of that file).

Before this service the registry could only be edited by hand, so a project created from a template
was unknown to ``pm orient``, approval and the cockpit.  The service adds exactly one entry, never
rewrites or reorders the existing ones, and proves the result with the same resolver ``pm orient``
uses; if that proof fails the registry is restored byte for byte.

CHG-SCPT-2026-650: an entry also carries the project's kind and status (both optional).  Deleting a project does not
remove its entry: ``mark_deleted`` sets the status to ``deleted`` and keeps what it was, ``mark_restored`` puts it back
when the folder comes back from the recycle area.  Those two touch only that one entry; every other entry keeps its
bytes, and the file is checked against ``WorkspaceRegistry`` before it replaces the old one.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from auto_pm.application.core.project_scanner import ProjectScanner, first_problem
from auto_pm.application.core.workspace_context_service import WorkspaceContextService
from auto_pm.contracts.workspace_context import (
    KIND_LABELS,
    USER_STATUSES,
    WorkspaceProjectMapping,
    WorkspaceRegistry,
    kind_label,
    status_label,
)
from auto_pm.domain.models import ProjectInfo
from auto_pm.domain.models.project import VALID_BUSINESS_LINES


class WorkspaceRegistryError(RuntimeError):
    """Raised when a project cannot be registered safely; the registry is then unchanged."""


@dataclass(frozen=True)
class RegistrationResult:
    """What was (or, for a dry run, would be) written."""

    mapping: WorkspaceProjectMapping
    already_registered: bool
    written: bool


@dataclass(frozen=True)
class StatusChange:
    """One entry's status before and after ``mark_deleted`` / ``mark_restored``; ``written`` is False for a no-op."""

    project_id: str
    before: str
    after: str
    written: bool


def check_kind_status(kind: str, status: str) -> None:
    """Refuse a kind or status the registry does not know; ``deleted`` is never typed in by hand."""

    if kind and kind not in KIND_LABELS:
        allowed = "、".join(f"{value}（{kind_label(value)}）" for value in KIND_LABELS if value)
        raise WorkspaceRegistryError(f"项目性质 {kind!r} 不认识，只能是：{allowed}")
    if status and status not in USER_STATUSES:
        allowed = "、".join(f"{value}（{status_label(value)}）" for value in USER_STATUSES)
        raise WorkspaceRegistryError(f"项目状态 {status!r} 不能这样填，只能是：{allowed}（“已删除”只由删除命令写上）")


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
        kind: str = "",
        status: str = "",
    ) -> RegistrationResult:
        """Register ``project_id``; a project already registered at the same path is left as it is.

        ``kind`` and ``status`` are optional; left out they are written empty and read as 未分类 / 在研.
        """
        project_id = project_id.strip()
        if not project_id:
            raise WorkspaceRegistryError("项目编号不能为空")
        check_kind_status(kind, status)
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
            kind=kind,  # checked by check_kind_status above
            status=status,
        )
        if dry_run:
            return RegistrationResult(mapping=mapping, already_registered=False, written=False)

        projects = payload["projects"]
        if not isinstance(projects, list):
            raise WorkspaceRegistryError("Workspace Registry schema 无效，拒绝改写")
        projects.append(mapping.model_dump(exclude={"status_before_delete"}))  # 删除前状态只在删除时才写
        try:
            self._write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            WorkspaceContextService(str(self._workspace_root), registry_path=self._registry_path).resolve(
                project_id, start_path=self._workspace_root / relative_root
            )
        except BaseException as error:
            # Whatever went wrong (resolver refusal, I/O error, interrupt), the registry goes back byte for byte.
            self._restore(original)
            if isinstance(error, Exception):
                raise WorkspaceRegistryError(f"登记后校验失败，已恢复原登记表: {error}") from error
            raise
        return RegistrationResult(mapping=mapping, already_registered=False, written=True)

    def registry(self) -> WorkspaceRegistry:
        """Read-only: the whole registry, validated; raises ``WorkspaceRegistryError`` when it cannot be read."""
        return self._load()[2]

    def find(self, project_id: str) -> WorkspaceProjectMapping | None:
        """The entry for ``project_id``, or None; the registry must be readable."""
        return next((item for item in self.registry().projects if item.project_id == project_id), None)

    def mark_deleted(self, project_id: str) -> StatusChange | None:
        """After a project folder went into the recycle area: set its entry to ``deleted`` and keep the old status.

        The entry stays (the ID can still be looked up); None when the project was never registered (or there is no
        registry file at all).  Called by both
        delete paths (``project delete`` and the workbench window), never by ``recycle_project`` itself, because
        ``project import --force`` also recycles a folder and that is not deleting a project.
        """
        def change(entry: dict[str, object]) -> tuple[str, str] | None:
            before = str(entry.get("status") or "")
            if before == "deleted":
                return None
            entry["status_before_delete"] = before
            entry["status"] = "deleted"
            return before, "deleted"

        return self._change_status(project_id, change)

    def mark_restored(self, project_id: str) -> StatusChange | None:
        """After a folder came back from the recycle area: put the entry's status back to what it was before delete."""
        def change(entry: dict[str, object]) -> tuple[str, str] | None:
            if str(entry.get("status") or "") != "deleted":
                return None
            after = str(entry.get("status_before_delete") or "")
            entry["status"] = after
            entry["status_before_delete"] = ""
            return "deleted", after

        return self._change_status(project_id, change)

    def _change_status(self, project_id: str, change: Callable[[dict[str, object]], tuple[str, str] | None]) -> StatusChange | None:
        if not self._registry_path.is_file():
            return None  # 没有登记表的工作区（如单独拷出来的项目）：谁都没登记，不建登记表
        original, payload, registry = self._load()
        if not any(item.project_id == project_id for item in registry.projects):
            return None
        projects = payload["projects"]
        if not isinstance(projects, list):
            raise WorkspaceRegistryError("Workspace Registry schema 无效，拒绝改写")
        matches = [entry for entry in projects if isinstance(entry, dict) and entry.get("project_id") == project_id]
        if len(matches) != 1:
            raise WorkspaceRegistryError(f"登记表里项目 {project_id} 有 {len(matches)} 条，拒绝改写")
        entry = matches[0]
        current = str(entry.get("status") or "")
        changed = change(entry)
        if changed is None:
            return StatusChange(project_id, current, current, written=False)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        try:
            WorkspaceRegistry.model_validate(json.loads(text))
        except ValidationError as error:
            raise WorkspaceRegistryError(f"改完的登记表通不过校验，没有写：{first_problem(error)}") from error
        try:
            self._write(text)
        except BaseException:
            self._restore(original)
            raise
        return StatusChange(project_id, changed[0], changed[1], written=True)

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
            candidate = self._unique_project_directory(project_id)
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
        try:
            info = self._scanner.try_identify_project(str(path))
        except ValidationError as error:
            raise WorkspaceRegistryError(
                f"项目元数据无效（{first_problem(error)}），"
                f"请先修正 {relative.as_posix()} 下的 .copier-answers.yml / .plc.json"
            ) from error
        if info is None:
            raise WorkspaceRegistryError(
                f"目录缺少项目锚点（.copier-answers.yml / .plc.json / PM_SESSION）: {relative.as_posix()}"
            )
        if info.project_id != project_id:
            raise WorkspaceRegistryError(f"目录锚点的项目编号不一致: {info.project_id} != {project_id}")
        declared = (info.extra or {}).get("business_line")
        if declared and declared not in VALID_BUSINESS_LINES:
            raise WorkspaceRegistryError(
                f"项目 {project_id} 在 .copier-answers.yml 里写的业务线 {declared!r} 不在白名单"
                f"（{'、'.join(VALID_BUSINESS_LINES)}），不登记；请先改成合法业务线或删掉这一行"
            )
        return relative.as_posix()

    def _unique_project_directory(self, project_id: str) -> Path:
        """Without ``--path`` the ID must name exactly one directory; ``scan()`` would silently keep one of several."""
        found: list[ProjectInfo] = []
        root_info = self._scanner.try_identify_project(str(self._workspace_root))
        if root_info is not None:
            found.append(root_info)
        self._scanner._scan(str(self._workspace_root), found, depth=0, max_depth=4)
        directories = sorted({Path(info.path).resolve() for info in found if info.project_id == project_id})
        if not directories:
            for skipped, problem in self._scanner.skipped_invalid:
                if project_id in Path(skipped).name:
                    raise WorkspaceRegistryError(
                        f"项目元数据无效（{problem}），请先修正 {self._display(Path(skipped))} 下的 "
                        ".copier-answers.yml / .plc.json"
                    )
            raise WorkspaceRegistryError(f"工作区内找不到项目目录: {project_id}（可用 --path 指定）")
        if len(directories) > 1:
            listed = "、".join(self._display(path) for path in directories)
            raise WorkspaceRegistryError(
                f"项目编号 {project_id} 对应多个目录（{listed}），请用 --path 指定要登记的那一个"
            )
        return directories[0]

    def _display(self, path: Path) -> str:
        try:
            return path.relative_to(self._workspace_root).as_posix()
        except ValueError:
            return str(path)

    def _restore(self, original: bytes) -> None:
        try:
            self._write_bytes(original)
        finally:
            self._registry_path.with_name(self._registry_path.name + ".tmp").unlink(missing_ok=True)

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
        self._write_bytes(text.encode("utf-8"))

    def _write_bytes(self, data: bytes) -> None:
        temporary = self._registry_path.with_name(self._registry_path.name + ".tmp")
        temporary.write_bytes(data)
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
