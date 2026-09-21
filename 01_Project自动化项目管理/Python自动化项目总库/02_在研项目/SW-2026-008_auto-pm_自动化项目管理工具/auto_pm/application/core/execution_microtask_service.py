"""Persist and materialize deterministic standalone repositories for approved microtasks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from auto_pm.contracts.continuity import RunItem, RunState
from auto_pm.contracts.execution_adapter import (
    ExecutionIntent,
    ExecutionMicrotaskFile,
    ExecutionMicrotaskMaterialization,
    ExecutionMicrotaskPlan,
)
from auto_pm.contracts.mission import Mission
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import clean_git_environment


class ExecutionMicrotaskError(RuntimeError):
    """Raised when a microtask cannot be proven or materialized without overwriting state."""


class ExecutionMicrotaskService:
    """Create one append-only plan before touching its deterministic standalone repository."""

    _MARKER = ".codex-microtask.json"

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        store: ContinuityStore | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._store = store or ContinuityStore(self._root)

    def prepare(self, operation_id: str) -> ExecutionMicrotaskMaterialization:
        """Reserve the exact plan, then create or strictly validate its repository."""

        try:
            intent = self._store.get_execution_intent(operation_id)
            if intent is None:
                raise ExecutionMicrotaskError("ExecutionIntent 不存在，拒绝规划微任务")
            run = self._store.get_run(intent.receipt.run_id)
            mission = self._store.get_mission(intent.receipt.mission_id)
        except ContinuityStoreError as error:
            raise ExecutionMicrotaskError(str(error)) from error
        if run.state is not RunState.READY:
            raise ExecutionMicrotaskError("只有 READY Run 可以规划未启动微任务")
        self._assert_source_facts(intent, run, mission)

        candidate = self._candidate(run)
        manifest = self._manifest(candidate, run)
        try:
            plan = self._plan(operation_id, run, manifest, intent, mission)
        except ValueError as error:
            raise ExecutionMicrotaskError("MicrotaskPlan 授权事实不满足契约") from error
        try:
            persisted, _created = self._store.reserve_execution_microtask_plan(plan)
        except ContinuityStoreError as error:
            raise ExecutionMicrotaskError(str(error)) from error
        if persisted != plan:
            raise ExecutionMicrotaskError("持久化 MicrotaskPlan 与候选载荷不一致")
        commit = self._materialize_or_validate(persisted)
        return ExecutionMicrotaskMaterialization(plan=persisted, commit=commit)

    @staticmethod
    def _assert_source_facts(intent: ExecutionIntent, run: RunItem, mission: Mission) -> None:
        receipt = intent.receipt
        routing = mission.authority.routing
        if (
            mission.mission_id != receipt.mission_id
            or mission.subject_project_id != receipt.subject_project_id
            or mission.root_work_id != receipt.work_id
        ):
            raise ExecutionMicrotaskError("persisted Mission 与 ExecutionIntent 不一致")
        if not routing.approved_model or routing.approved_model != receipt.executor_id:
            raise ExecutionMicrotaskError("approved_model 与 ExecutionIntent executor 不一致")
        if (
            run.run_id != receipt.run_id
            or run.work_id != receipt.work_id
            or run.executor_id != receipt.owner_id
            or run.adapter != receipt.adapter.value
            or run.git_head != receipt.git_head
            or run.worktree_path != receipt.worktree_path
        ):
            raise ExecutionMicrotaskError("ExecutionIntent 与 READY Run candidate 不一致")
        if not (
            run.owned_paths == receipt.owned_paths == mission.authority.scope_paths
        ):
            raise ExecutionMicrotaskError("Mission/ExecutionIntent/Run owned_paths 不一致")
        if not (
            run.declared_dirty_paths
            == receipt.declared_dirty_paths
            == routing.declared_dirty_paths
        ):
            raise ExecutionMicrotaskError(
                "Mission/ExecutionIntent/Run declared_dirty_paths 不一致"
            )

    def _candidate(self, run: RunItem) -> Path:
        raw = Path(run.worktree_path)
        if raw.is_symlink():
            raise ExecutionMicrotaskError("Run candidate 不允许符号链接")
        try:
            candidate = raw.resolve(strict=True)
        except OSError as error:
            raise ExecutionMicrotaskError("Run candidate 不存在") from error
        if not candidate.is_dir():
            raise ExecutionMicrotaskError("Run candidate 必须是目录")
        top = self._git_text(candidate, "rev-parse", "--show-toplevel")
        if self._path_key(Path(top)) != self._path_key(candidate):
            raise ExecutionMicrotaskError("Run candidate 不是 Git 根目录")
        if self._git_text(candidate, "rev-parse", "HEAD") != run.git_head:
            raise ExecutionMicrotaskError("Run candidate HEAD 已漂移")
        status = self._git_bytes(
            candidate, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        )
        if status:
            raise ExecutionMicrotaskError("Run candidate 存在 dirty 或 untracked 漂移")
        return candidate

    def _manifest(
        self, candidate: Path, run: RunItem
    ) -> tuple[ExecutionMicrotaskFile, ...]:
        declared = tuple(sorted(run.declared_dirty_paths))
        if not declared or len(set(declared)) != len(declared):
            raise ExecutionMicrotaskError("declared_dirty_paths 必须是非空精确文件集合")
        if not self._paths_covered(declared, run.owned_paths):
            raise ExecutionMicrotaskError("declared_dirty_paths 超出 owned_paths")
        result: list[ExecutionMicrotaskFile] = []
        for raw in declared:
            if any(character in raw for character in "*?["):
                raise ExecutionMicrotaskError("manifest path 不允许 Git pathspec 模式")
            normalized = PurePosixPath(raw).as_posix()
            if (
                normalized in {self._MARKER, ".git"}
                or normalized.startswith(".git/")
                or normalized.startswith(".auto-pm/microtasks/")
            ):
                raise ExecutionMicrotaskError("manifest 包含 marker、Git 或微任务仓自身路径")
            current = candidate.joinpath(*PurePosixPath(normalized).parts)
            if current.is_symlink() or not current.is_file():
                raise ExecutionMicrotaskError(f"manifest 不是常规文件: {normalized}")
            entry = self._git_bytes(
                candidate,
                "ls-tree",
                "-z",
                run.git_head,
                "--",
                normalized,
            )
            rows = tuple(item for item in entry.split(b"\0") if item)
            if len(rows) != 1:
                raise ExecutionMicrotaskError(f"候选基线缺少唯一文件 blob: {normalized}")
            try:
                metadata, recorded_path = rows[0].split(b"\t", 1)
                mode, kind, oid = metadata.decode("ascii").split(" ", 2)
                tree_path = recorded_path.decode("utf-8")
            except (UnicodeDecodeError, ValueError) as error:
                raise ExecutionMicrotaskError("git ls-tree 输出无法验证") from error
            if tree_path != normalized or kind != "blob" or mode not in {"100644", "100755"}:
                raise ExecutionMicrotaskError(f"manifest 拒绝目录或符号链接: {normalized}")
            content = self._git_bytes(candidate, "cat-file", "blob", oid)
            result.append(
                ExecutionMicrotaskFile(
                    path=normalized,
                    git_mode=mode,
                    blob_oid=oid,
                    content_sha256=hashlib.sha256(content).hexdigest(),
                )
            )
        return tuple(result)

    def _plan(
        self,
        operation_id: str,
        run: RunItem,
        manifest: tuple[ExecutionMicrotaskFile, ...],
        intent: ExecutionIntent,
        mission: Mission,
    ) -> ExecutionMicrotaskPlan:
        operation_digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        repository = (
            self._root / ".auto-pm" / "microtasks" / operation_digest[:24]
        ).resolve()
        manifest_payload = [item.model_dump(mode="json") for item in manifest]
        manifest_sha256 = self._hash(manifest_payload)
        request_payload = {
            "operation_id": operation_id,
            "mission_id": mission.mission_id,
            "run_id": run.run_id,
            "approved_model": mission.authority.routing.approved_model,
            "objective": mission.objective,
            "owned_paths": list(intent.receipt.owned_paths),
            "declared_dirty_paths": list(intent.receipt.declared_dirty_paths),
            "source_worktree_path": str(Path(run.worktree_path).resolve()),
            "baseline_git_head": run.git_head,
            "repository_path": str(repository),
            "manifest": manifest_payload,
            "manifest_sha256": manifest_sha256,
        }
        request_sha256 = self._hash(request_payload)
        marker = {
            "schema_version": "codex-microtask.v1",
            **request_payload,
            "request_sha256": request_sha256,
        }
        return ExecutionMicrotaskPlan(
            **request_payload,
            marker_sha256=hashlib.sha256(self._canonical(marker)).hexdigest(),
            request_sha256=request_sha256,
            created_at=run.created_at,
        )

    def _materialize_or_validate(self, plan: ExecutionMicrotaskPlan) -> str:
        target = Path(plan.repository_path)
        self._require_safe_target(target)
        if target.exists() or target.is_symlink():
            return self._validate_repository(plan)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.mkdir()
        except FileExistsError:
            return self._validate_repository(plan)
        self._git_text(target, "init", "--initial-branch=main")
        self._git_text(target, "config", "core.autocrlf", "false")
        self._git_text(target, "config", "core.safecrlf", "false")
        source = Path(plan.source_worktree_path)
        for item in plan.manifest:
            destination = target.joinpath(*PurePosixPath(item.path).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = self._git_bytes(source, "cat-file", "blob", item.blob_oid)
            if hashlib.sha256(content).hexdigest() != item.content_sha256:
                raise ExecutionMicrotaskError("候选 baseline blob 内容漂移")
            destination.write_bytes(content)
            if item.git_mode == "100755":
                destination.chmod(destination.stat().st_mode | 0o111)
        marker = self._marker(plan)
        (target / self._MARKER).write_bytes(self._canonical(marker) + b"\n")
        for item in plan.manifest:
            oid = self._git_text(target, "hash-object", "-w", "--no-filters", "--", item.path)
            if oid != item.blob_oid:
                raise ExecutionMicrotaskError("standalone repository blob 与候选基线不一致")
            self._git_text(
                target,
                "update-index",
                "--add",
                "--cacheinfo",
                f"{item.git_mode},{oid},{item.path}",
            )
        marker_oid = self._git_text(
            target, "hash-object", "-w", "--no-filters", "--", self._MARKER
        )
        self._git_text(
            target,
            "update-index",
            "--add",
            "--cacheinfo",
            f"100644,{marker_oid},{self._MARKER}",
        )
        env = clean_git_environment()
        instant = plan.created_at.isoformat()
        env.update(
            {
                "GIT_AUTHOR_NAME": "auto-pm microtask",
                "GIT_AUTHOR_EMAIL": "auto-pm@example.invalid",
                "GIT_COMMITTER_NAME": "auto-pm microtask",
                "GIT_COMMITTER_EMAIL": "auto-pm@example.invalid",
                "GIT_AUTHOR_DATE": instant,
                "GIT_COMMITTER_DATE": instant,
            }
        )
        self._git_text(target, "commit", "-m", "Prepare approved microtask", env=env)
        return self._validate_repository(plan)

    def _validate_repository(self, plan: ExecutionMicrotaskPlan) -> str:
        target = Path(plan.repository_path)
        if target.is_symlink() or not target.is_dir():
            raise ExecutionMicrotaskError("microtask repository 是符号链接或非目录")
        git_dir = target / ".git"
        if git_dir.is_symlink() or not git_dir.is_dir():
            raise ExecutionMicrotaskError("microtask repository 不是完整 standalone Git 仓")
        if self._path_key(Path(self._git_text(target, "rev-parse", "--show-toplevel"))) != self._path_key(target):
            raise ExecutionMicrotaskError("microtask repository Git 根不一致")
        if self._git_text(target, "rev-list", "--count", "HEAD") != "1":
            raise ExecutionMicrotaskError("microtask repository 必须精确包含一个提交")
        if self._git_bytes(target, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            raise ExecutionMicrotaskError("microtask repository 已 dirty，拒绝覆盖或清理")
        tracked_raw = self._git_bytes(target, "ls-files", "-z")
        tracked = tuple(sorted(item.decode("utf-8") for item in tracked_raw.split(b"\0") if item))
        expected = tuple(sorted((self._MARKER, *(item.path for item in plan.manifest))))
        if tracked != expected:
            raise ExecutionMicrotaskError("microtask repository tracked 文件集合漂移")
        stage_rows = self._git_bytes(target, "ls-files", "--stage", "-z")
        staged: dict[str, tuple[str, str]] = {}
        try:
            for row in (item for item in stage_rows.split(b"\0") if item):
                metadata, raw_path = row.split(b"\t", 1)
                mode, oid, stage = metadata.decode("ascii").split(" ", 2)
                if stage != "0":
                    raise ValueError("stage")
                staged[raw_path.decode("utf-8")] = (mode, oid)
        except (UnicodeDecodeError, ValueError) as error:
            raise ExecutionMicrotaskError("microtask repository index 无法验证") from error
        for item in plan.manifest:
            if staged.get(item.path) != (item.git_mode, item.blob_oid):
                raise ExecutionMicrotaskError("microtask repository baseline blob/mode 漂移")
        marker_path = target / self._MARKER
        expected_marker = self._canonical(self._marker(plan)) + b"\n"
        if marker_path.is_symlink() or marker_path.read_bytes() != expected_marker:
            raise ExecutionMicrotaskError("microtask marker/hash 漂移")
        if hashlib.sha256(expected_marker[:-1]).hexdigest() != plan.marker_sha256:
            raise ExecutionMicrotaskError("MicrotaskPlan marker_sha256 非法")
        marker_oid = self._git_text(
            target, "hash-object", "--no-filters", "--", self._MARKER
        )
        if staged.get(self._MARKER) != ("100644", marker_oid):
            raise ExecutionMicrotaskError("microtask marker index 漂移")
        for item in plan.manifest:
            path = target.joinpath(*PurePosixPath(item.path).parts)
            if path.is_symlink() or not path.is_file():
                raise ExecutionMicrotaskError("microtask 文件类型漂移")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item.content_sha256:
                raise ExecutionMicrotaskError("microtask 文件内容漂移")
        return self._git_text(target, "rev-parse", "HEAD")

    def _require_safe_target(self, target: Path) -> None:
        root = (self._root / ".auto-pm" / "microtasks").resolve()
        try:
            target.resolve().relative_to(root)
        except ValueError as error:
            raise ExecutionMicrotaskError("microtask repository path 越界") from error
        current = self._root
        for part in target.relative_to(self._root).parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise ExecutionMicrotaskError("microtask repository path 含符号链接")

    @staticmethod
    def _paths_covered(paths: Iterable[str], roots: tuple[str, ...]) -> bool:
        return all(
            any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots)
            for path in paths
        )

    @staticmethod
    def _marker(plan: ExecutionMicrotaskPlan) -> dict[str, object]:
        return {
            "schema_version": "codex-microtask.v1",
            "operation_id": plan.operation_id,
            "mission_id": plan.mission_id,
            "run_id": plan.run_id,
            "approved_model": plan.approved_model,
            "objective": plan.objective,
            "owned_paths": list(plan.owned_paths),
            "declared_dirty_paths": list(plan.declared_dirty_paths),
            "source_worktree_path": plan.source_worktree_path,
            "baseline_git_head": plan.baseline_git_head,
            "repository_path": plan.repository_path,
            "manifest": [item.model_dump(mode="json") for item in plan.manifest],
            "manifest_sha256": plan.manifest_sha256,
            "request_sha256": plan.request_sha256,
        }

    @staticmethod
    def _canonical(payload: object) -> bytes:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @classmethod
    def _hash(cls, payload: object) -> str:
        return hashlib.sha256(cls._canonical(payload)).hexdigest()

    @staticmethod
    def _path_key(path: Path) -> str:
        value = os.path.normcase(os.path.normpath(str(path.resolve(strict=True))))
        return value.casefold() if os.name == "nt" else value

    @staticmethod
    def _git_bytes(root: Path, *args: str, env: dict[str, str] | None = None) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
            timeout=30,
            env=env or clean_git_environment(),
        )
        if result.returncode != 0 or result.stderr:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ExecutionMicrotaskError(
                f"Git 命令无法证明微任务状态 ({result.returncode}): {detail}"
            )
        return result.stdout

    @classmethod
    def _git_text(
        cls, root: Path, *args: str, env: dict[str, str] | None = None
    ) -> str:
        return cls._git_bytes(root, *args, env=env).decode(
            "utf-8", errors="replace"
        ).strip()


__all__ = ["ExecutionMicrotaskError", "ExecutionMicrotaskService"]
