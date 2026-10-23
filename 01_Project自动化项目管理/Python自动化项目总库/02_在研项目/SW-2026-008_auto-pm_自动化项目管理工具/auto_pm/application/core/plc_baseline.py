"""从 Git 取出 PLC 工程在某个提交（Run 开工基线）上的样子，供“只拦新增失败”比对用。

只导出检查会读到的文件：工程目录本身、工程里每个 ``.plc.json`` 的 ``libraries`` 指向的共享库、规范登记表
``spec_registry.json``；导出到临时目录时保留它们在仓库里的相对位置，所以按路径判断的检查（PLC 区、库路径）
在基线和现在两边一样。只读 Git，不改工作树、不改索引；断网照样能用。
"""

from __future__ import annotations

import io
import json
import posixpath
import subprocess
import tarfile
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from auto_pm.domain.models.plc import CheckResult
from auto_pm.domain.plc.baseline_compare import (
    FailureDiff,
    RecordingLanguageService,
    diff_failures,
    failure_keys,
)
from auto_pm.domain.plc.language_service import LanguageService
from auto_pm.infrastructure.control_root_guard import clean_git_environment

SPEC_REGISTRY = "00_Obsidian_Base全局规范文件仓库/spec_registry.json"


class PlcBaselineError(RuntimeError):
    """基线取不出来（提交不存在、Git 出错）。"""


def _git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(repo), *arguments],
        capture_output=True,
        check=False,
        env=clean_git_environment(),
    )


def _exists(repo: Path, rev: str, path: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{rev}:{path}").returncode == 0


def _libraries(repo: Path, rev: str, project_rel: str) -> list[str]:
    listing = _git(repo, "ls-tree", "-r", "-z", "--name-only", rev, "--", project_rel)
    if listing.returncode != 0:
        raise PlcBaselineError(listing.stderr.decode("utf-8", "replace").strip() or "git ls-tree 失败")
    found: list[str] = []
    for name in listing.stdout.decode("utf-8").split("\0"):
        if not name.endswith(".plc.json"):
            continue
        shown = _git(repo, "show", f"{rev}:{name}")
        try:
            libraries = json.loads(shown.stdout.decode("utf-8")).get("libraries") or []
        except (ValueError, AttributeError):
            continue
        for library in libraries if isinstance(libraries, list) else []:
            if not isinstance(library, str):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), library.replace("\\", "/")))
            if not target.startswith("..") and target != "." and _exists(repo, rev, target):
                found.append(target)
    return found


def export_plc_baseline(repo: Path, rev: str, project_rel: str, destination: Path) -> Path | None:
    """把 ``project_rel`` 在 ``rev`` 上的样子导出到 ``destination``，返回导出后的工程目录；基线上没有这个工程返回 None。

    ``repo`` 必须是仓库（或 worktree）顶层，``project_rel`` 相对它。
    """

    project_rel = project_rel.strip("/") or "."
    if _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").returncode != 0:
        raise PlcBaselineError(f"基线提交不存在: {rev}")
    if not _exists(repo, rev, posixpath.join(project_rel, ".plc.json")):
        return None
    paths = [project_rel, *_libraries(repo, rev, project_rel)]
    if _exists(repo, rev, SPEC_REGISTRY):
        paths.append(SPEC_REGISTRY)
    archive = _git(repo, "archive", "--format=tar", rev, "--", *sorted(set(paths)))
    if archive.returncode != 0:
        raise PlcBaselineError(archive.stderr.decode("utf-8", "replace").strip() or "git archive 失败")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as bundle:
        _extract(bundle, destination)
    return destination / project_rel


def _extract(bundle: tarfile.TarFile, destination: Path) -> None:
    """解包到 ``destination``；Python 3.11.4 以前的 ``extractall`` 没有 ``filter``，就自己挡掉越界路径和链接。"""

    try:
        bundle.extractall(destination, filter="data")
        return
    except TypeError:
        pass
    root = destination.resolve()
    for member in bundle.getmembers():
        target = (destination / member.name).resolve()
        if not (member.isfile() or member.isdir()) or (target != root and root not in target.parents):
            raise PlcBaselineError(f"基线归档里有不安全的条目: {member.name}")
    bundle.extractall(destination)  # noqa: S202 - every member was checked above


def baseline_anchor_note(repo: Path, rev: str) -> str:
    """基线提交不在主线（main）上时的说明，否则空串。

    Run 开工时 worktree 的 HEAD 通常就是主线上的提交；手工开工指向一个已经带了自己提交的工位时，
    那些提交里已有的失败会被当成“基线已有”，所以要在记录里写明（审计 125 建议项）。找不到主线分支就不下结论。
    """

    for branch in ("main", "origin/main", "master"):
        if _git(repo, "rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}").returncode != 0:
            continue
        if _git(repo, "merge-base", "--is-ancestor", rev, branch).returncode == 0:
            return ""
        return (
            f"开工基线 {rev[:12]} 不在 {branch} 上（这个工位开工前已带了自己的提交），"
            "这些提交里已有的失败也算“基线已有”"
        )
    return ""


def repo_top(path: Path) -> Path:
    """``path`` 所在 Git 仓库（或 worktree）的顶层目录。"""

    top = _git(path, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise PlcBaselineError(top.stderr.decode("utf-8", "replace").strip() or "不是 Git 仓库")
    return Path(top.stdout.decode("utf-8").strip()).resolve()


def checked_keys(
    workspace: Path, project: Path, service: LanguageService | None
) -> tuple[CheckResult, Counter[str], bool]:
    """跑一次 ``PlcChecker``（插件每个范围只跑一次），返回结果、逐条失败键、插件是否没跑完。"""

    from auto_pm.plc.checker import PlcChecker

    recorder = RecordingLanguageService(service, project) if service is not None else None
    result = PlcChecker(str(workspace), language_service=recorder).check_project(str(project))
    language = recorder.diagnostics if recorder is not None else None
    incomplete = recorder.incomplete if recorder is not None else False
    return result, failure_keys(result, str(project), language), incomplete


def check_against_baseline(
    workspace: Path, project: Path, rev: str, service: LanguageService | None
) -> tuple[CheckResult, FailureDiff]:
    """``plc check --baseline``：现在的工程和 ``rev`` 上的工程各检查一次，逐条比（和验收门同一口径）。"""

    result, now, incomplete = checked_keys(workspace, project, service)
    if incomplete:
        raise PlcBaselineError("Siemens 语言服务命令行没有跑完（超时或起不来），这次检查不算数")
    top = repo_top(project)
    relative = project.resolve().relative_to(top).as_posix()
    anchor = baseline_anchor_note(top, rev)
    with TemporaryDirectory(prefix="pmb-") as temporary:
        exported = export_plc_baseline(top, rev, relative, Path(temporary))
        if exported is None:
            return result, diff_failures(now, None, baseline_note=f"{rev} 上还没有这个工程，现在的失败全部按新增算")
        base_result, base, base_incomplete = checked_keys(Path(temporary), exported, service)
    if base_incomplete:
        return result, diff_failures(now, None, baseline_note="基线上 Siemens 语言服务没有跑完，现在的失败全部按新增算")
    if base_result.not_applicable:
        return result, diff_failures(now, None, baseline_note="基线上这个工程不适用 PLC 检查，现在的失败全部按新增算")
    return result, diff_failures(now, base, baseline_note=anchor)


__all__ = [
    "PlcBaselineError",
    "baseline_anchor_note",
    "check_against_baseline",
    "checked_keys",
    "export_plc_baseline",
    "repo_top",
]
