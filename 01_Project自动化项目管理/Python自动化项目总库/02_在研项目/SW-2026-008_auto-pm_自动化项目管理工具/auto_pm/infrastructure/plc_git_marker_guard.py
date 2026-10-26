"""Read-only Git marker checks for the narrowly scoped F01-a guard.

HEAD supplies historical identity only until a marker deletion is committed.
This module never registers projects, reads a cache, or authorizes a move.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from auto_pm.infrastructure.git_timeout import run_git_bounded_text

MOVE_RETIRE_HINT = "移动或退役请走 F01-b 的授权"
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_REGULAR_MODES = frozenset({"100644", "100755"})


class GitMarkerGuardError(RuntimeError):
    """Git identity or marker facts cannot be read safely."""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one bounded read command without optional index refresh locks."""
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    try:
        return run_git_bounded_text(
            ["git", *args],
            default_timeout=10.0,
            error_cls=GitMarkerGuardError,
            where=root,
            cwd=str(root),
            capture_output=True,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitMarkerGuardError(f"无法只读获取 Git 工程标记: {exc}") from exc


def _error(action: str, result: subprocess.CompletedProcess[str]) -> GitMarkerGuardError:
    """Keep the failed read visible instead of returning an empty identity."""
    return GitMarkerGuardError(f"{action}失败 (Exit {result.returncode}): {result.stderr.strip()}")


def _has_git_anchor(start: Path) -> bool:
    """Distinguish an absent repository from broken or unreadable metadata."""
    for parent in (start, *start.parents):
        try:
            (parent / ".git").lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise GitMarkerGuardError(f"无法核对 Git 仓库锚点: {exc}") from exc
        return True
    return False


def _repository_root(directory: Path, *, allow_non_git: bool) -> Path | None:
    """Resolve the selected working tree, with a narrow standalone exception."""
    try:
        start = directory.resolve(strict=True)
        if not start.is_dir():
            raise GitMarkerGuardError(f"Git 核验路径不是目录: {directory}")
    except OSError as exc:
        raise GitMarkerGuardError(f"Git 核验路径不可读取: {directory}: {exc}") from exc
    result = _git(start, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        # Only an explicit not-repository result without a local Git anchor is
        # compatible with the existing standalone, non-Git stage-gate API.
        if (
            allow_non_git
            and result.returncode == 128
            and result.stderr.startswith("fatal: not a git repository")
            and not _has_git_anchor(start)
        ):
            return None
        raise _error("解析 Git 工作树", result)
    reported_root = result.stdout.strip()
    if not reported_root:
        raise GitMarkerGuardError("Git 未返回工作树根")
    try:
        root = Path(reported_root).resolve(strict=True)
        start.relative_to(root)
    except (OSError, ValueError) as exc:
        raise GitMarkerGuardError(f"Git 仓库根与调用路径不一致: {exc}") from exc
    if not root.is_dir():
        raise GitMarkerGuardError("Git 工作树根不是目录")
    return root


def _head_commit(root: Path) -> str | None:
    """Return a verified commit or a positively identified unborn branch."""
    result = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if result.returncode == 0:
        oid = result.stdout.strip()
        if not _OBJECT_ID.fullmatch(oid):
            raise GitMarkerGuardError("Git HEAD 对象标识无效")
        return oid
    symbolic = _git(root, "symbolic-ref", "-q", "HEAD")
    ref = symbolic.stdout.strip()
    if (
        result.returncode == 1
        and not result.stderr.strip()
        and symbolic.returncode == 0
        and not symbolic.stderr.strip()
        and ref.startswith("refs/heads/")
        and "\n" not in ref
    ):
        exists = _git(root, "show-ref", "--verify", "--quiet", ref)
        if exists.returncode == 1 and not exists.stderr.strip():
            # A valid symbolic HEAD whose branch does not exist is unborn;
            # an existing ref with a broken/missing commit is a read failure.
            return None
    raise _error("读取 Git HEAD", result)


def _nul_records(output: str) -> list[str]:
    """Reject truncated or lossy Git paths before comparing marker identity."""
    if not output:
        return []
    if not output.endswith("\0") or "\ufffd" in output:
        raise GitMarkerGuardError("Git marker 清单不完整或编码无效")
    return output[:-1].split("\0")


def _marker_path(path: str) -> str:
    """Accept only repository-relative marker paths without traversal."""
    parts = PurePosixPath(path).parts
    if not parts or path.startswith("/") or "\\" in path or any(p in {".", ".."} for p in parts):
        raise GitMarkerGuardError(f"Git marker 路径不安全: {path!r}")
    return path


def _head_markers(root: Path, oid: str | None) -> frozenset[str]:
    """Read regular marker blobs from one fixed commit, including archives."""
    if oid is None:
        return frozenset()
    result = _git(root, "ls-tree", "-r", "-z", "--full-tree", oid)
    if result.returncode != 0:
        raise _error("读取 HEAD marker 树", result)
    markers: set[str] = set()
    for record in _nul_records(result.stdout):
        header, separator, path = record.partition("\t")
        if not separator:
            raise GitMarkerGuardError("HEAD 树条目格式无效")
        if PurePosixPath(path).name != ".plc.json":
            continue
        path = _marker_path(path)
        fields = header.split()
        if (
            len(fields) != 3
            or fields[0] not in _REGULAR_MODES
            or fields[1] != "blob"
            or not _OBJECT_ID.fullmatch(fields[2])
        ):
            raise GitMarkerGuardError(f"HEAD 中的 PLC marker 不是普通文件: {path}")
        markers.add(path)
    return frozenset(markers)


def _index_markers(root: Path) -> frozenset[tuple[str, str]]:
    """Read marker paths and blobs, rejecting conflicts and non-files."""
    result = _git(root, "ls-files", "--cached", "--stage", "-z", "--", ":(glob)**/.plc.json")
    if result.returncode != 0:
        raise _error("读取 index marker 清单", result)
    markers: set[tuple[str, str]] = set()
    for record in _nul_records(result.stdout):
        header, separator, path = record.partition("\t")
        fields = header.split()
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in _REGULAR_MODES
            or fields[2] != "0"
            or not _OBJECT_ID.fullmatch(fields[1])
        ):
            raise GitMarkerGuardError("index PLC marker 不是完整的普通文件条目")
        markers.add((_marker_path(path), fields[1]))
    return frozenset(markers)


def removed_index_markers(workspace_root: Path) -> tuple[str, ...]:
    """Return every HEAD marker whose exact path is absent in index.

    Archive paths and moves receive no marker-removal exception. Neither
    rename detection nor matching blobs authorize a changed root. Repeated
    reads reject observable HEAD/index drift.
    """
    root = _repository_root(workspace_root, allow_non_git=True)
    if root is None:
        return ()
    oid = _head_commit(root)
    before = _index_markers(root)
    head = _head_markers(root, oid)
    after = _index_markers(root)
    if before != after or _head_commit(root) != oid:
        raise GitMarkerGuardError("Git HEAD/index 在 marker 核验期间发生漂移")
    return tuple(sorted(head - {path for path, _blob in after}))


def marker_in_head(workspace_root: Path | None, project_path: Path) -> bool:
    """Read HEAD identity for the exact project root without a DB or scan.

    A verified standalone non-Git project and an unborn repository have no
    historical marker. Corrupt repositories and paths outside the selected
    repository are errors, never non-applicable results.
    """
    try:
        selected = (workspace_root or project_path).resolve(strict=True)
        project = project_path.resolve(strict=True)
        project.relative_to(selected)
    except (OSError, ValueError) as exc:
        raise GitMarkerGuardError(f"项目路径不属于选定工作区: {exc}") from exc
    root = _repository_root(selected, allow_non_git=True)
    if root is None:
        return False
    try:
        relative = project.relative_to(root)
    except (OSError, ValueError) as exc:
        raise GitMarkerGuardError(f"项目路径不属于选定的 Git 工作树: {exc}") from exc
    marker = (PurePosixPath(relative.as_posix()) / ".plc.json").as_posix()
    oid = _head_commit(root)
    markers = _head_markers(root, oid)
    if _head_commit(root) != oid:
        raise GitMarkerGuardError("Git HEAD 在阶段 marker 核验期间发生漂移")
    return marker in markers
