"""PLC 语言服务检查的类型与端口（M3-PLUGIN）。

用户的 PLC 门禁实际依赖 VS Code 插件 Dynamic Siemens Language Support 自带的命令行（``siemens-lsp check`` 诊断、
``siemens-lsp test`` 运行 ``.scltest``）。本模块只定义领域层看得见的结果类型与端口协议；调用命令行的实现在
``auto_pm.infrastructure.siemens_language_service``（领域层不直接起子进程）。

“未找到插件”是一种独立的结果（``available=False``）：它不是通过，调用方必须把它当作“未验证”，在交付阶段按失败处理。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class LanguageServiceBinary:
    """本机找到的命令行程序（只记录，不复制、不分发）。"""

    path: str
    version: str
    sha256: str


@dataclass(frozen=True)
class LanguageServiceResult:
    """一次 ``check`` 或 ``test`` 的结果。"""

    command: str  # "check" | "test"
    available: bool
    exit_code: int | None
    error_count: int = 0
    messages: tuple[str, ...] = ()
    summary: str = ""
    binary: LanguageServiceBinary | None = None
    cases_run: int | None = None  # ``test``：诊断行里的 "running X/Y cases"
    cases_total: int | None = None

    @property
    def passed(self) -> bool:
        """命令行可用、退出码为 0、没有解析到错误。"""
        return self.available and self.exit_code == 0 and self.error_count == 0


class LanguageService(Protocol):
    """领域层依赖的端口：对一个 PLC 工程根目录运行插件命令行。"""

    @property
    def available(self) -> bool: ...

    def check(self, root: Path) -> LanguageServiceResult: ...

    def test(self, root: Path) -> LanguageServiceResult: ...


# ── 工程范围与结果汇总（纯文件系统与纯数据，不起子进程）──────────────────────────────

_SKIP_DIRS = frozenset({".git", "archive", "_archive", "node_modules", "__pycache__", ".venv"})
_SOURCE_SUFFIXES = (".scl", ".db", ".scltest", ".udt", ".awl", ".st")
MAX_SHOWN_MESSAGES = 5


def plc_scope_roots(project_root: Path) -> list[Path]:
    """插件的“PLC 范围”根目录：含 ``.plc.json`` 且自己名下（最近的上级 ``.plc.json`` 就是它）有源文件的目录。

    标准项目有两层 ``.plc.json``（工程根与 ``02_PLC程序/PLC_ST``），程序源码在内层，所以只在内层运行；活体基准项目只有工程根一层，就在工程根运行。
    找不到任何 ``.plc.json`` 时返回空列表；有标记但没有源文件时返回最外层的标记目录。
    """
    import os

    markers: list[Path] = []
    sources: list[Path] = []
    for current, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS]
        here = Path(current)
        if ".plc.json" in files:
            markers.append(here)
        sources.extend(here / name for name in files if name.lower().endswith(_SOURCE_SUFFIXES))
    if not markers:
        return []

    def nearest(path: Path) -> Path | None:
        best: Path | None = None
        for marker in markers:
            if marker == path.parent or marker in path.parents:
                if best is None or len(marker.parts) > len(best.parts):
                    best = marker
        return best

    owned = {m for m in (nearest(s) for s in sources) if m is not None}
    chosen = [m for m in markers if m in owned]
    return sorted(chosen or [min(markers, key=lambda m: len(m.parts))], key=lambda p: str(p))


def has_scltest(scope: Path) -> bool:
    import os

    for _, dirs, names in os.walk(scope):
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS]
        if any(name.lower().endswith(".scltest") for name in names):
            return True
    return False


def merge_results(command: str, project_root: Path, parts: list[tuple[Path, LanguageServiceResult]]) -> LanguageServiceResult:
    """把多个范围的结果合成一个：任何一个不可用 → 不可用；任何一个失败 → 失败；消息带上范围前缀。"""
    if not parts:
        return LanguageServiceResult(command=command, available=False, exit_code=None, summary="没有可运行的 PLC 范围")
    if any(not r.available for _, r in parts):
        return LanguageServiceResult(command=command, available=False, exit_code=None, summary=parts[0][1].summary, binary=parts[0][1].binary)
    multi = len(parts) > 1
    messages: list[str] = []
    for scope, result in parts:
        try:
            tag = scope.relative_to(project_root).as_posix()
        except ValueError:
            tag = scope.as_posix()
        messages.extend((f"[{tag}] {m}" if multi else m) for m in result.messages)
    codes = [r.exit_code for _, r in parts]
    worst = next((c for c in codes if c not in (0, None)), 0)
    run = [r.cases_run for _, r in parts if r.cases_run is not None]
    total = [r.cases_total for _, r in parts if r.cases_total is not None]
    return LanguageServiceResult(
        command=command, available=True, exit_code=worst, error_count=sum(r.error_count for _, r in parts), messages=tuple(messages[:MAX_SHOWN_MESSAGES]),
        summary=parts[-1][1].summary, binary=parts[0][1].binary, cases_run=sum(run) if run else None, cases_total=sum(total) if total else None,
    )


@dataclass(frozen=True)
class ProjectLanguageReport:
    """一个工程的语言服务结果：``check`` 一定有；有 ``.scltest`` 时才有 ``test``。"""

    scopes: tuple[Path, ...]
    check: LanguageServiceResult
    test: LanguageServiceResult | None


def evaluate_project(service: LanguageService, project_root: Path) -> ProjectLanguageReport:
    """在工程的每个 PLC 范围上运行 check（以及有测试文件的范围上运行 test）并合并。服务不可用时只返回不可用的 check 结果。"""
    scopes = plc_scope_roots(project_root) or [project_root]
    if not service.available:
        missing = LanguageServiceResult(command="check", available=False, exit_code=None, summary="未找到 Dynamic Siemens Language Support 插件命令行")
        return ProjectLanguageReport(tuple(scopes), missing, None)
    check = merge_results("check", project_root, [(s, service.check(s)) for s in scopes])
    tested = [(s, service.test(s)) for s in scopes if has_scltest(s)]
    return ProjectLanguageReport(tuple(scopes), check, merge_results("test", project_root, tested) if tested else None)
