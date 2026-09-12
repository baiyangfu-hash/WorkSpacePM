"""Central fail-closed Git control-root validation for mutable operations."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path, PurePosixPath


class ControlRootGuardError(RuntimeError):
    """Raised when a mutable control-plane operation is not at the primary Git root."""


def clean_git_environment() -> dict[str, str]:
    """Copy the process environment without caller-controlled Git repository overrides."""

    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


def _canonical_key(path: Path) -> str:
    """Return a stable filesystem identity key, including Windows case folding."""

    resolved = path.resolve(strict=True)
    normalized = os.path.normcase(os.path.normpath(str(resolved)))
    return normalized.casefold() if os.name == "nt" else normalized


def authority_path_parts(raw: str, *, windows: bool | None = None) -> tuple[str, ...]:
    """Return component-aware authority identity using host-appropriate casing."""

    parts = PurePosixPath(str(raw).replace("\\", "/")).parts
    fold = os.name == "nt" if windows is None else windows
    return tuple(part.casefold() for part in parts) if fold else parts


def _git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=clean_git_environment(),
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise ControlRootGuardError(f"Git 控制根事实采集失败: {details}")
    if result.stderr.strip():
        raise ControlRootGuardError(f"Git 控制根事实包含诊断: {result.stderr.strip()}")
    value = result.stdout.strip()
    if not value:
        raise ControlRootGuardError("Git 控制根事实为空")
    return value


def _git_optional_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=clean_git_environment(),
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise ControlRootGuardError(f"Git 工作树事实采集失败: {details}")
    if result.stderr.strip():
        raise ControlRootGuardError(f"Git 工作树事实包含诊断: {result.stderr.strip()}")
    if "\ufffd" in result.stdout:
        raise ControlRootGuardError("Git 工作树路径包含无法解码的字节")
    return result.stdout


def require_git_worktree_root(workspace_root: str | Path) -> Path:
    """Require ``workspace_root`` to be the top of its current Git worktree."""

    candidate = Path(workspace_root)
    if not candidate.is_dir():
        raise ControlRootGuardError(f"workspace_root 不存在或不是目录: {candidate}")
    try:
        root = candidate.resolve(strict=True)
        git_root = Path(
            _git_output(root, "rev-parse", "--path-format=absolute", "--show-toplevel")
        ).resolve(strict=True)
        if _canonical_key(git_root) != _canonical_key(root):
            raise ControlRootGuardError("workspace_root 必须是 Git worktree 顶层目录")
    except OSError as error:
        raise ControlRootGuardError("workspace_root 无法规范化为 Git worktree 顶层") from error
    return root


def require_control_root(workspace_root: str | Path) -> Path:
    """Require the primary Git worktree before any control-plane mutation."""

    root = require_git_worktree_root(workspace_root)
    try:
        expected_git_dir = _real_control_directory(root)
        git_dir = Path(
            _git_output(root, "rev-parse", "--path-format=absolute", "--absolute-git-dir")
        ).resolve(strict=True)
        common_dir = Path(
            _git_output(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve(strict=True)
        final_git_dir = _real_control_directory(root)
        identities = {
            _canonical_key(expected_git_dir),
            _canonical_key(final_git_dir),
            _canonical_key(git_dir),
            _canonical_key(common_dir),
        }
        if len(identities) != 1:
            raise ControlRootGuardError(
                "控制面写命令要求 workspace/.git、git-dir 与 common-dir 三方精确一致"
            )
    except OSError as error:
        raise ControlRootGuardError("Git 控制目录无法安全规范化") from error
    return root


def require_governed_worktree(
    workspace_root: str | Path,
    worktree_path: str | Path,
    *,
    expected_head: str | None = None,
) -> Path:
    """Require the primary root or one governed linked worktree from the same repository."""

    root = require_control_root(workspace_root)
    raw = Path(worktree_path)
    if not raw.is_absolute() or ".." in raw.parts:
        raise ControlRootGuardError("Run worktree_path 必须是无 traversal 的绝对路径")
    candidate = require_safe_workspace_path(root, raw, label="Run worktree")
    if not candidate.is_dir():
        raise ControlRootGuardError("Run worktree 不存在或不是目录")

    root_key = _canonical_key(root)
    candidate_key = _canonical_key(candidate)
    is_primary = candidate_key == root_key
    if not is_primary:
        try:
            relative = candidate.relative_to(root)
        except ValueError as error:  # pragma: no cover - safe-path guard already rejects this
            raise ControlRootGuardError("Run worktree 位于控制 workspace 外") from error
        folded = tuple(part.casefold() if os.name == "nt" else part for part in relative.parts)
        if len(folded) < 3 or folded[:2] != (".auto-pm", "worktrees"):
            raise ControlRootGuardError("Run worktree 必须位于受管 .auto-pm/worktrees 目录")

    marker = candidate / ".git"
    if is_link_like(marker):
        raise ControlRootGuardError("Run worktree .git 标记不得是 symlink/junction/reparse point")
    if is_primary:
        if not marker.is_dir():
            raise ControlRootGuardError("主 Run worktree 必须包含真实 .git 目录")
    elif not marker.is_file():
        raise ControlRootGuardError("受管 linked worktree 必须包含真实 .git 文件")

    try:
        reported_root = Path(
            _git_output(candidate, "rev-parse", "--path-format=absolute", "--show-toplevel")
        ).resolve(strict=True)
        git_dir = Path(
            _git_output(candidate, "rev-parse", "--path-format=absolute", "--absolute-git-dir")
        ).resolve(strict=True)
        common_dir = Path(
            _git_output(candidate, "rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve(strict=True)
        head = _git_output(candidate, "rev-parse", "--verify", "HEAD")
    except OSError as error:
        raise ControlRootGuardError("Run worktree Git 身份无法安全规范化") from error

    expected_common = _real_control_directory(root)
    if _canonical_key(reported_root) != candidate_key:
        raise ControlRootGuardError("Run worktree 的 Git top-level 与请求路径不一致")
    if _canonical_key(common_dir) != _canonical_key(expected_common):
        raise ControlRootGuardError("Run worktree 的 git common-dir 不属于控制 workspace")
    safe_git_dir = require_safe_workspace_path(root, git_dir, label="Run worktree git-dir")
    if not safe_git_dir.is_dir():
        raise ControlRootGuardError("Run worktree git-dir 不存在或不是目录")
    if is_primary:
        if _canonical_key(safe_git_dir) != _canonical_key(expected_common):
            raise ControlRootGuardError("主 Run worktree git-dir 与控制根不一致")
    else:
        managed_git_dirs = expected_common / "worktrees"
        try:
            git_relative = safe_git_dir.relative_to(managed_git_dirs)
        except ValueError as error:
            raise ControlRootGuardError(
                "linked Run worktree git-dir 不在受管 common-dir 内"
            ) from error
        if not git_relative.parts:
            raise ControlRootGuardError("linked Run worktree git-dir 身份不完整")
    if expected_head is not None and head != expected_head:
        raise ControlRootGuardError("Run git_head 与受管 worktree 当前 HEAD 不一致")

    final_candidate = require_safe_workspace_path(root, raw, label="Run worktree")
    if _canonical_key(final_candidate) != candidate_key or is_link_like(final_candidate / ".git"):
        raise ControlRootGuardError("Run worktree 在验证期间发生路径或 reparse 漂移")
    return final_candidate


def governed_worktree_snapshot(
    workspace_root: str | Path,
    worktree_path: str | Path,
) -> tuple[Path, str, tuple[str, ...]]:
    """Collect one stable HEAD/full-dirty snapshot from a governed worktree."""

    candidate = require_governed_worktree(workspace_root, worktree_path)
    head_before = _git_output(candidate, "rev-parse", "--verify", "HEAD")

    def dirty_paths() -> tuple[str, ...]:
        dirty: set[str] = set()
        commands = (
            ("diff", "--name-only", "-z"),
            ("diff", "--cached", "--name-only", "-z"),
            ("ls-files", "--others", "--exclude-standard", "-z"),
        )
        for command in commands:
            output = _git_optional_output(candidate, *command)
            dirty.update(path.replace("\\", "/") for path in output.split("\0") if path)
        return tuple(sorted(dirty))

    dirty_before = dirty_paths()
    head_after = _git_output(candidate, "rev-parse", "--verify", "HEAD")
    dirty_after = dirty_paths()
    final_candidate = require_governed_worktree(
        workspace_root,
        candidate,
        expected_head=head_before,
    )
    if head_before != head_after or dirty_before != dirty_after:
        raise ControlRootGuardError("Run worktree Git snapshot 在采集期间发生漂移")
    return final_candidate, head_before, dirty_before


def _real_control_directory(root: Path) -> Path:
    """Require the in-workspace ``.git`` entry to be a real directory, never an alias."""

    candidate = root / ".git"
    if is_link_like(candidate):
        raise ControlRootGuardError("workspace/.git 不得是 symlink/junction/reparse point")
    if not candidate.is_dir():
        raise ControlRootGuardError(
            "控制面写命令只能在含真实 .git 目录的主 Git 工作树执行；"
            "linked worktree 或 separate git-dir 已拒绝"
        )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ControlRootGuardError("workspace/.git 无法安全规范化") from error
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise ControlRootGuardError("workspace/.git 解析后位于 workspace 外") from error
    if relative.parts != (".git",):
        raise ControlRootGuardError("workspace/.git 必须是 workspace 内的真实控制目录")
    return resolved


def is_link_like(path: str | Path) -> bool:
    """Detect symlinks and Windows reparse points on Python 3.11 and newer."""

    candidate = Path(path)
    try:
        if candidate.is_symlink():
            return True
        junction_check = getattr(candidate, "is_junction", None)
        if junction_check and junction_check():
            return True
        if os.name == "nt":
            attributes = getattr(candidate.lstat(), "st_file_attributes", 0)
            return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ControlRootGuardError(f"无法读取路径 reparse-point 事实: {candidate}") from error
    return False


def require_safe_workspace_path(
    workspace_root: str | Path,
    candidate: str | Path,
    *,
    label: str,
) -> Path:
    """Resolve a workspace path while rejecting traversal and every reparse component."""

    try:
        root = Path(workspace_root).resolve(strict=True)
    except OSError as error:
        raise ControlRootGuardError(f"{label} 的 workspace_root 无法规范化") from error
    raw_segments = str(candidate).replace("\\", "/").split("/")
    if any(part in {".", ".."} for part in raw_segments):
        raise ControlRootGuardError(f"{label} 包含非 canonical 点路径段")
    raw = Path(candidate)
    lexical = Path(os.path.abspath(os.path.normpath(str(raw if raw.is_absolute() else root / raw))))
    root_key = os.path.normcase(os.path.normpath(str(root)))
    lexical_key = os.path.normcase(os.path.normpath(str(lexical)))
    try:
        common = os.path.commonpath((root_key, lexical_key))
        relative = Path(os.path.relpath(lexical, root))
    except ValueError as error:
        raise ControlRootGuardError(f"{label} 位于 workspace 外") from error
    if (common.casefold() if os.name == "nt" else common) != (
        root_key.casefold() if os.name == "nt" else root_key
    ):
        raise ControlRootGuardError(f"{label} 位于 workspace 外")
    cursor = root
    for part in relative.parts:
        if part in {"", ".", ".."} or "\x00" in part or ":" in part or part != part.rstrip(" ."):
            raise ControlRootGuardError(f"{label} 包含非法路径段")
        cursor /= part
        if is_link_like(cursor):
            raise ControlRootGuardError(f"{label} 不得经过 symlink/junction")
    resolved = cursor.resolve(strict=False)
    resolved_key = os.path.normcase(os.path.normpath(str(resolved)))
    try:
        resolved_common = os.path.commonpath((root_key, resolved_key))
    except ValueError as error:
        raise ControlRootGuardError(f"{label} 解析后位于 workspace 外") from error
    if (resolved_common.casefold() if os.name == "nt" else resolved_common) != (
        root_key.casefold() if os.name == "nt" else root_key
    ):
        raise ControlRootGuardError(f"{label} 解析后位于 workspace 外")
    return resolved


__all__ = [
    "ControlRootGuardError",
    "authority_path_parts",
    "clean_git_environment",
    "governed_worktree_snapshot",
    "is_link_like",
    "require_control_root",
    "require_governed_worktree",
    "require_git_worktree_root",
    "require_safe_workspace_path",
]
