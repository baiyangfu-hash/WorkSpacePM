"""Fail-closed Git worktree selection for provider-neutral execution."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from auto_pm.contracts.execution_adapter import WorktreeMode
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    clean_git_environment,
    require_control_root,
    require_git_worktree_root,
    require_safe_workspace_path,
)


class WorktreePolicyError(RuntimeError):
    """Raised when a Run cannot receive an unambiguous, isolated Git baseline."""


@dataclass(frozen=True)
class WorktreePlan:
    """A verified Git baseline; materialization never removes an existing worktree."""

    worktree_mode: WorktreeMode
    worktree_path: Path
    git_head: str
    branch_name: str
    origin_dirty_paths: tuple[str, ...]


class WorktreePolicyService:
    """Keep controlled worktrees clean and create isolated branches only when authorized."""

    _BRANCH_PREFIX = "codex/"

    def __init__(self, workspace_root: str | Path) -> None:
        self._root = Path(workspace_root).resolve()

    def select(
        self,
        *,
        run_id: str,
        allow_branch_creation: bool,
        force_isolation: bool = False,
    ) -> WorktreePlan:
        """Select the clean current worktree or an uncreated isolated target.

        Any dirty controlled tree is isolated rather than reused.  The pending
        changes remain untouched in their original worktree and the new branch
        starts at its independently observed ``HEAD``.
        """

        self._require_root_git_worktree()
        git_head = self._git_output("rev-parse", "HEAD")
        dirty_paths = self._dirty_paths()
        if not dirty_paths and not force_isolation:
            return WorktreePlan(
                worktree_mode=WorktreeMode.CURRENT,
                worktree_path=self._root,
                git_head=git_head,
                branch_name="",
                origin_dirty_paths=(),
            )
        if not allow_branch_creation:
            reason = "存在未声明改动" if dirty_paths else "请求了隔离工作树"
            raise WorktreePolicyError(f"{reason}，但 AuthorityEnvelope 未授权执行分支变更")
        branch_name = self._branch_name(run_id)
        target = self._target_path(run_id)
        if target.exists():
            raise WorktreePolicyError(f"隔离工作树目标已存在，拒绝复用: {target}")
        self._require_branch_absent(branch_name)
        return WorktreePlan(
            worktree_mode=WorktreeMode.ISOLATED,
            worktree_path=target,
            git_head=git_head,
            branch_name=branch_name,
            origin_dirty_paths=dirty_paths,
        )

    def materialize(self, plan: WorktreePlan) -> WorktreePlan:
        """Create an authorized isolated worktree without cleaning or reusing anything."""

        self.require_control_root()
        if plan.worktree_mode is WorktreeMode.CURRENT:
            if plan.worktree_path != self._root:
                raise WorktreePolicyError("CURRENT worktree plan 与控制工作树不一致")
            if self._git_output("rev-parse", "HEAD") != plan.git_head:
                raise WorktreePolicyError("Git baseline drift，拒绝复用 CURRENT worktree")
            if self._dirty_paths():
                raise WorktreePolicyError("CURRENT worktree 已变脏，拒绝开始 Run")
            return plan
        if plan.worktree_mode is not WorktreeMode.ISOLATED:
            raise WorktreePolicyError(f"未知 worktree mode: {plan.worktree_mode}")
        self._validate_target_path(plan.worktree_path)
        if plan.worktree_path.exists():
            raise WorktreePolicyError(f"隔离工作树目标已存在，拒绝覆盖: {plan.worktree_path}")
        if self._git_output("rev-parse", "HEAD") != plan.git_head:
            raise WorktreePolicyError("Git baseline drift，拒绝创建隔离工作树")
        self._require_branch_absent(plan.branch_name)
        self._validate_target_path(plan.worktree_path)
        plan.worktree_path.parent.mkdir(parents=True, exist_ok=True)
        self._validate_target_path(plan.worktree_path)
        result = self._run_git(
            "worktree", "add", "-b", plan.branch_name, str(plan.worktree_path), plan.git_head
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "unknown git error"
            raise WorktreePolicyError(f"创建隔离工作树失败: {details}")
        child_root = Path(
            self._git_output("rev-parse", "--show-toplevel", cwd=plan.worktree_path)
        ).resolve()
        if child_root != plan.worktree_path.resolve():
            raise WorktreePolicyError("新工作树 Git 根目录不匹配，保留现场并拒绝继续")
        if self._git_output("rev-parse", "HEAD", cwd=plan.worktree_path) != plan.git_head:
            raise WorktreePolicyError("新工作树 Git HEAD 不匹配，保留现场并拒绝继续")
        if self._dirty_paths(cwd=plan.worktree_path):
            raise WorktreePolicyError("新工作树不是干净基线，保留现场并拒绝继续")
        return plan

    def branch_name_for(self, worktree_path: str | Path) -> str:
        """Read the checked-out branch of an existing isolated worktree."""

        path = Path(worktree_path).resolve()
        self._validate_target_path(path)
        branch_name = self._git_output("branch", "--show-current", cwd=path)
        if not branch_name:
            raise WorktreePolicyError("隔离工作树必须位于已命名分支，拒绝 detached HEAD")
        return branch_name

    def require_control_root(self) -> None:
        """Reject linked worktrees before any control-plane mutation is initialized."""

        try:
            require_control_root(self._root)
        except ControlRootGuardError as error:
            raise WorktreePolicyError(str(error)) from error

    def _require_root_git_worktree(self) -> None:
        try:
            require_git_worktree_root(self._root)
        except ControlRootGuardError as error:
            raise WorktreePolicyError(str(error)) from error

    def _target_path(self, run_id: str) -> Path:
        target = self._worktree_root() / self._slug(run_id)
        self._validate_target_path(target)
        return target

    def _worktree_root(self) -> Path:
        try:
            return require_safe_workspace_path(
                self._root,
                self._root / ".auto-pm" / "worktrees",
                label="Git worktree 目录",
            )
        except ControlRootGuardError as error:
            raise WorktreePolicyError(str(error)) from error

    def _validate_target_path(self, target: Path) -> None:
        try:
            safe_target = require_safe_workspace_path(
                self._root,
                target,
                label="Git worktree target",
            )
            safe_target.relative_to(self._worktree_root())
        except (ControlRootGuardError, ValueError) as error:
            raise WorktreePolicyError("隔离工作树必须位于 .auto-pm/worktrees 内") from error

    def _branch_name(self, run_id: str) -> str:
        return f"{self._BRANCH_PREFIX}{self._slug(run_id)}"

    @staticmethod
    def _slug(run_id: str) -> str:
        slug = re.sub(r"[^a-z0-9._-]+", "-", run_id.strip().lower()).strip(".-")
        if not slug:
            raise WorktreePolicyError("run_id 无法转换为安全工作树名称")
        return slug[:63]

    def _require_branch_absent(self, branch_name: str) -> None:
        checked = self._run_git("check-ref-format", "--branch", branch_name)
        if checked.returncode != 0:
            raise WorktreePolicyError(f"非法隔离分支名称: {branch_name}")
        result = self._run_git("show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}")
        if result.returncode == 0:
            raise WorktreePolicyError(f"隔离分支已存在，拒绝复用: {branch_name}")
        if result.returncode != 1:
            details = result.stderr.strip() or result.stdout.strip() or "unknown git error"
            raise WorktreePolicyError(f"无法验证隔离分支状态: {details}")

    def _dirty_paths(self, *, cwd: Path | None = None) -> tuple[str, ...]:
        dirty: set[str] = set()
        for args in (
            ("diff", "--name-only", "-z"),
            ("diff", "--cached", "--name-only", "-z"),
            ("ls-files", "--others", "--exclude-standard", "-z"),
        ):
            output = self._git_output(*args, cwd=cwd)
            dirty.update(path.replace("\\", "/") for path in output.split("\0") if path)
        return tuple(sorted(dirty))

    def _git_output(self, *args: str, cwd: Path | None = None) -> str:
        result = self._run_git(*args, cwd=cwd)
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "unknown git error"
            raise WorktreePolicyError(f"Git 事实采集失败: {details}")
        if result.stderr.strip():
            raise WorktreePolicyError(f"Git 事实采集包含诊断: {result.stderr.strip()}")
        return result.stdout.strip()

    def _run_git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(cwd or self._root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=clean_git_environment(),
        )


__all__ = ["WorktreePlan", "WorktreePolicyError", "WorktreePolicyService"]
