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

from auto_pm.domain.models.plc import LANGUAGE_SERVICE_TEST, CheckResult
from auto_pm.domain.plc.baseline_compare import (
    FailureDiff,
    RecordingLanguageService,
    diff_failures,
    failure_keys,
)
from auto_pm.domain.plc.language_service import LanguageService
from auto_pm.infrastructure.control_root_guard import clean_git_environment
from auto_pm.infrastructure.git_timeout import run_git_bounded

SPEC_REGISTRY = "00_Obsidian_Base全局规范文件仓库/spec_registry.json"


class PlcBaselineError(RuntimeError):
    """基线取不出来（提交不存在、Git 出错）。"""


class PlcPluginPanicError(PlcBaselineError):
    """插件的测试进程 panic 退出：失败清单不完整，这次检查没有“修好／新增”可言，必须按失败处理（D-137）。

    带着这次检查的逐条失败键和不是因 panic 而没跑完的命令：基线那一边只丢掉测试用例那一段，其余照常比
    （:func:`baseline_failure_keys`）；现在这一版崩了照旧整门失败。
    """

    def __init__(self, message: str, keys: Counter[str] | None = None, unfinished: frozenset[str] = frozenset()) -> None:
        super().__init__(message)
        self.keys: Counter[str] = keys if keys is not None else Counter()
        self.unfinished = unfinished


def _git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return run_git_bounded(
        ["git", "-c", "core.quotePath=false", "-C", str(repo), *arguments],
        default_timeout=60.0,
        error_cls=PlcBaselineError,
        where=repo,
        capture_output=True,
        check=False,
        env=clean_git_environment(),
    )


def _exists(repo: Path, rev: str, path: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{rev}:{path}").returncode == 0


def _libraries(repo: Path, rev: str, project_rel: str) -> list[str]:
    listing = _git(repo, "ls-tree", "-r", "-z", "--name-only", rev, "--", project_rel)
    if listing.returncode != 0:
        raise PlcBaselineError(listing.stderr.decode("utf-8", "replace").strip() or "git ls-tree 失败")  # lenient-decode: git stderr only quoted in the error text
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
        raise PlcBaselineError(archive.stderr.decode("utf-8", "replace").strip() or "git archive 失败")  # lenient-decode: git stderr only quoted in the error text
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
        raise PlcBaselineError(top.stderr.decode("utf-8", "replace").strip() or "不是 Git 仓库")  # lenient-decode: git stderr only quoted in the error text
    return Path(top.stdout.decode("utf-8").strip()).resolve()


def checked_keys(
    workspace: Path, project: Path, service: LanguageService | None
) -> tuple[CheckResult, Counter[str], bool]:
    """跑一次 ``PlcChecker``（插件每个范围只跑一次），返回结果、逐条失败键、插件是否没跑完。

    插件测试进程 panic 就抛 :class:`PlcPluginPanicError`：用在现在这一版上整门失败（D-137）；基线那一边由
    :func:`baseline_failure_keys` 接住。
    """

    from auto_pm.domain.plc.checker import PlcChecker

    recorder = RecordingLanguageService(service, project) if service is not None else None
    result = PlcChecker(str(workspace), language_service=recorder).check_project(str(project))
    language = recorder.diagnostics if recorder is not None else None
    if recorder is not None and recorder.panic_note:
        raise PlcPluginPanicError(
            f"{recorder.panic_note}。进程一崩，哪些用例失败取决于谁先撞上崩点，每次不一样，"
            "所以不给“新增／修好”结论，按失败处理（根因是插件原生桩，见 D-37）",
            failure_keys(result, str(project), language),
            frozenset(recorder.unfinished),
        )
    incomplete = recorder.incomplete if recorder is not None else False
    return result, failure_keys(result, str(project), language), incomplete


BASELINE_PANIC_NOTE = (
    "基线上插件测试进程 panic 退出（D-37 原生定时器桩），测试用例这一段基线不可比：基线的测试失败一条都不用，"
    "现在的测试失败全部按新增算；其余检查照常和基线比"
)
BASELINE_INCOMPLETE_NOTE = "基线上 Siemens 语言服务没有跑完，现在的失败全部按新增算"
BASELINE_NOT_APPLICABLE_NOTE = "基线上这个工程不适用 PLC 检查，现在的失败全部按新增算"
_TEST_KEY_PREFIXES = (f"{LANGUAGE_SERVICE_TEST} · ", f"plc check · {LANGUAGE_SERVICE_TEST}：")


def baseline_failure_keys(
    workspace: Path, project: Path, service: LanguageService | None
) -> tuple[Counter[str] | None, str]:
    """开工基线那一边的逐条失败键和说明：``(None, 原因)`` 表示整个基线不可比，现在的失败全部算新增。

    * 插件**测试**进程 panic（D-37 原生定时器桩）：只有测试用例那一段的失败清单不完整（D-137），这一段一条都不用，
      现在的测试失败全部算新增、也不会有测试的“修好”行；插件 ``check`` 和其余检查项的失败清单是完整的，照常比。
      以前整门失败：基线上用原生定时器桩的工程每次都 panic，任何改动都过不了验收（DJ-2026-005 试车 A1）。
    * 插件没跑完（超时、起不来，不是 panic）：整个基线不用。
    * 工程在基线上不适用：整个基线不用。

    只有**现在这一版**崩了才整门失败：调用方先对现在这一版调 :func:`checked_keys`。
    """

    try:
        result, keys, incomplete = checked_keys(workspace, project, service)
    except PlcPluginPanicError as crash:
        if crash.unfinished:  # something besides the crashed test run did not finish either
            return None, BASELINE_INCOMPLETE_NOTE
        comparable = Counter({key: count for key, count in crash.keys.items() if not key.startswith(_TEST_KEY_PREFIXES)})
        return comparable, BASELINE_PANIC_NOTE
    if incomplete:
        return None, BASELINE_INCOMPLETE_NOTE
    if result.not_applicable:
        return None, BASELINE_NOT_APPLICABLE_NOTE
    return keys, ""


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
        base, note = baseline_failure_keys(Path(temporary), exported, service)
    if base is None:
        return result, diff_failures(now, None, baseline_note=note)
    return result, diff_failures(now, base, baseline_note="；".join(part for part in (note, anchor) if part))


__all__ = [
    "PlcBaselineError",
    "PlcPluginPanicError",
    "BASELINE_INCOMPLETE_NOTE",
    "BASELINE_NOT_APPLICABLE_NOTE",
    "BASELINE_PANIC_NOTE",
    "baseline_anchor_note",
    "baseline_failure_keys",
    "check_against_baseline",
    "checked_keys",
    "export_plc_baseline",
    "repo_top",
]
