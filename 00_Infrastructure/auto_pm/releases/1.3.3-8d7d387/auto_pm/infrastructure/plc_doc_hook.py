"""auto_pm.infrastructure.plc_doc_hook - 提交前核对 PLC 项目的文档与代码是否一致（需求 REQ-SW008-M2-DOCSYNC，任务 V01D）

只检查本次提交暂存了 PLC 相关文件（SCL/DB 源文件、FB 接口文档、变量定义文档）的 PLC 项目（含 ``.plc.json`` 的目录）；
一律按**暂存区内容**判断，不看工作区。发现拦住项（名称/类型/方向/注释不一致、代码有文档无、文档有代码无、
代码无注释等）或文档里仍有带“待确认”标记的行，就拒绝提交，并在工作区里按代码自动补全文档（只写文档，从不写 SCL，
不改暂存区）；整份文档缺失只给警告。检查本身出现异常时同样拒绝提交（与既有门禁一致：不为故障让路）。
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Collection, Iterable
from pathlib import Path, PurePosixPath

from auto_pm.infrastructure.git_timeout import run_git_bounded_text
from auto_pm.plc import doc_consistency as dc

SOURCE_SUFFIXES = (".scl", ".db")
EXPORT_SUFFIXES = (".scl", ".db", ".md", ".json")
MAX_SHOWN = 12
ARCHIVE_PARTS = frozenset({"archive", "_archive"})


def _git(root: Path, args: list[str], stdin: str | None = None) -> str:
    result = run_git_bounded_text(
        ["git", "-c", "core.quotepath=false", *args],
        default_timeout=60.0,
        error_cls=RuntimeError,
        where=root,
        cwd=str(root), capture_output=True, check=True, input=stdin,
    )
    return result.stdout


def _nul_list(text: str) -> list[str]:
    return [item for item in text.split("\0") if item]


def is_plc_relevant(path: str) -> bool:
    name = PurePosixPath(path).name
    lower = name.lower()
    return lower.endswith(SOURCE_SUFFIXES) or (name.startswith(dc.IFC_GLOB_PREFIX) and lower.endswith(".md")) or name == dc.VAR_DOC_NAME


def plc_project_roots(root: Path) -> list[str]:
    """暂存区（含本次新增）里所有含 ``.plc.json`` 的目录；仓库根用空字符串表示。

    位于 ``archive`` / ``_archive`` 目录下的项目是历史存档，不核对（把整个项目移入归档的提交不可能靠改文档通过）。
    """

    listed = _nul_list(_git(root, ["ls-files", "--cached", "-z", "--", ":(glob)**/.plc.json"]))
    roots: set[str] = set()
    for item in listed:
        parent = PurePosixPath(item).parent
        if ARCHIVE_PARTS & {part.lower() for part in parent.parts}:
            continue
        roots.add("" if parent.as_posix() == "." else parent.as_posix())
    return sorted(roots)


def project_for(path: str, roots: list[str]) -> str | None:
    """路径所属的 PLC 项目：取包含它的最高一层 ``.plc.json`` 目录（与 V01 验收门一致）。"""

    owners = [r for r in roots if r == "" or path == r or path.startswith(r + "/")]
    return min(owners, key=len) if owners else None


def _analyze_staged(root: Path, project: str) -> dc.ProjectAnalysis:
    """把项目在暂存区里的内容导出到临时目录再核对（工作区的任何未暂存改动都不参与）。"""

    scope = project or "."
    files = [f for f in _nul_list(_git(root, ["ls-files", "--cached", "-z", "--", scope])) if f.lower().endswith(EXPORT_SUFFIXES)]
    tmp = Path(tempfile.mkdtemp(prefix="plc-docs-"))
    try:
        if files:
            prefix = tmp.as_posix().rstrip("/") + "/"
            _git(root, ["checkout-index", f"--prefix={prefix}", "-z", "--stdin"], stdin="\0".join(files) + "\0")
        return dc.analyze_project(str(tmp / project) if project else str(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _report(project: str, analysis: dc.ProjectAnalysis) -> tuple[bool, list[str]]:
    fails = [f for f in analysis.findings if f.severity == "fail"]
    marked = analysis.marked_rows
    lines: list[str] = []
    name = project or "(仓库根)"
    if fails or marked:
        lines.append(f"🚨 [auto-pm pre-commit] 物理阻断：PLC 项目 {name} 的文档与代码不一致（拦住项 {len(fails)}、待确认标记 {len(marked)}）：")
        for finding in fails[:MAX_SHOWN]:
            lines.append(f"    - {finding.render()}")
        if len(fails) > MAX_SHOWN:
            lines.append(f"    - ……另有 {len(fails) - MAX_SHOWN} 条，运行 plc docs check 查看全部")
        for doc_path, row in marked[:MAX_SHOWN]:
            lines.append(f"    - 待确认：{Path(doc_path).name} 第 {row.line} 行 {row.name}")
        if len(marked) > MAX_SHOWN:
            lines.append(f"    - ……另有 {len(marked) - MAX_SHOWN} 行待确认，运行 plc docs check --strict-markers 查看全部")
    for finding in analysis.findings:
        if finding.severity == "warn" and finding.kind in {"missing_doc", "unparsable_doc"}:
            lines.append(f"⚠️ [auto-pm pre-commit] {name}：{finding.render()}（建议运行 plc docs sync 生成草稿）")
    return bool(fails or marked), lines


def _auto_fill(workspace_root: Path, project: str, failing_objects: Collection[str] | None) -> list[str]:
    """只为本次被拒的对象补文档（TD-SW008-045）；没有拦住项时只提示审核。"""

    if failing_objects is None:
        return ["    审核待确认的行后运行 plc docs confirm，再 git add 并重新提交。"]
    try:
        result = dc.sync_project(
            str(workspace_root / project) if project else str(workspace_root), only_objects=failing_objects
        )
    except Exception as exc:  # the commit is refused anyway; report why the draft could not be written
        return [f"    自动补全未能完成：{exc}"]
    lines = [
        f"    已按代码在工作区补全文档（只写文档，不改 SCL，不改暂存区）：新建 {len(result.created)} 份、修改 {len(result.written)} 份、补入 {result.added_rows} 行（补入的行带“{dc.MARKER}”）。"
    ]
    if result.suggestions:
        lines.append(f"    另有 {len(result.suggestions)} 处差异无法自动补入，需要人工修改，或运行 plc docs sync --apply-suggestions。")
    lines.append("    请审核补全的内容，运行 plc docs confirm，再 git add 并重新提交。")
    return lines


def enforce_plc_docs(workspace_root: Path, staged: Iterable[str]) -> int:
    """pre-commit 的 PLC 文档/代码一致性门禁；0 通过，1 拒绝提交。

    ``staged`` 是调用方已冻结的暂存快照里的路径（新增、复制、修改），与台账检查看的是同一份证据。
    """

    try:
        from auto_pm.infrastructure.plc_git_marker_guard import (
            MOVE_RETIRE_HINT,
            removed_index_markers,
        )

        removed = removed_index_markers(workspace_root)
        if removed:
            print(f"❌ [auto-pm pre-commit] 物理拦截：HEAD 中的 PLC 工程标记在暂存区消失: {', '.join(removed)}；{MOVE_RETIRE_HINT}")
            return 1
        relevant = [p for p in staged if is_plc_relevant(p)]
        if not relevant:
            return 0
        roots = plc_project_roots(workspace_root)
        projects = sorted({owner for p in relevant if (owner := project_for(p, roots)) is not None})
        if not projects:
            return 0
        print("🔍 [auto-pm pre-commit] 正在核对暂存的 PLC 项目的文档与代码一致性...")
        blocked = False
        for project in projects:
            analysis = _analyze_staged(workspace_root, project)
            project_blocked, lines = _report(project, analysis)
            for line in lines:
                print(line)
            if project_blocked:
                blocked = True
                failing = {f.obj for f in analysis.findings if f.severity == "fail"}
                for line in _auto_fill(workspace_root, project, failing or None):
                    print(line)
        if blocked:
            return 1
    except Exception as exc:
        print(f"❌ [auto-pm pre-commit] 物理拦截：PLC 文档一致性检查异常，为防止绕过门禁已拒绝提交: {exc}")
        return 1
    print("✅ [auto-pm pre-commit] PLC 文档与代码一致性校验通过。")
    return 0
