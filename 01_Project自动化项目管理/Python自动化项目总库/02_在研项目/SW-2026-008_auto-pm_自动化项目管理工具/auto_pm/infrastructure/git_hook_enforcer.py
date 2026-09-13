"""auto_pm.infrastructure.git_hook_enforcer - Git 物理提交门禁护航器

用于在 Git 底层（.git/hooks/pre-commit 与 .git/hooks/commit-msg）执行刚性拦截，
彻底杜绝 AI 或开发者“未经提单直接改代码”与“台账未闭环直接 commit”的行为。
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from auto_pm.change.parser import ChgParser

log = logging.getLogger(__name__)

PRODUCTION_EXTENSIONS = (".py", ".scl", ".st", ".qml")
EXCLUDED_PATH_KEYWORDS = (
    "tests/",
    "test_",
    "tests\\",
    "docs/",
    "docs\\",
    "scratch/",
    "scratch\\",
    ".auto-pm/",
    ".auto-pm\\",
    "00_Obsidian_Base",
    "PM_SESSION_",
)
_CHG_ID_PATTERN = re.compile(r"CHG-[A-Z0-9]+-\d{4}-\d+")
_PROJECT_ID_ROW_PATTERN = re.compile(
    r"^\|\s*(?:\*\*)?项目编号(?:\*\*)?\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)
_VALID_CHANGE_STATUSES = (
    "approved",
    "conditionally_approved",
    "implementing",
    "pending_acceptance",
    "accepting",
    "completed",
    "closed",
)


class StagedSnapshotError(RuntimeError):
    """暂存区快照不完整、漂移或无法安全解析。"""


@dataclass(frozen=True)
class StagedIndexEntry:
    """一个冻结的暂存文件路径及其 index blob 标识。"""

    path: str
    object_id: str


@dataclass(frozen=True)
class StagedSnapshot:
    """一次 ``git diff --cached --raw`` 读取产生的不可变暂存快照。"""

    entries: tuple[StagedIndexEntry, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.entries)


@dataclass(frozen=True)
class ProjectBinding:
    """注册项目与其工作区相对根目录的受控映射。"""

    project_id: str
    relative_root: str


def _normalise_git_path(path: str) -> str:
    """验证并规范化 Git 相对路径，拒绝路径遍历。"""
    normalised = path.replace("\\", "/")
    parts = tuple(part for part in normalised.split("/") if part)
    if not parts or normalised.startswith("/") or any(part in (".", "..") for part in parts):
        raise StagedSnapshotError(f"暂存区路径非法: {path!r}")
    return "/".join(parts)


def _parse_raw_index_entries(raw_output: str) -> tuple[StagedIndexEntry, ...]:
    """解析 ``git diff --cached --raw -z --no-renames`` 的 ACM 清单。"""
    fields = raw_output.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 2 != 0:
        raise StagedSnapshotError("暂存区 raw 快照格式不完整")

    entries: list[StagedIndexEntry] = []
    for header, path in zip(fields[0::2], fields[1::2], strict=True):
        header_parts = header.split()
        if len(header_parts) != 5 or not header_parts[0].startswith(":"):
            raise StagedSnapshotError(f"暂存区 raw 快照头格式非法: {header!r}")
        status = header_parts[-1]
        object_id = header_parts[3]
        if status not in {"A", "C", "M"} or not object_id.strip("0"):
            raise StagedSnapshotError(f"暂存区 raw 快照包含不支持的状态: {status!r}")
        entries.append(StagedIndexEntry(_normalise_git_path(path), object_id))
    return tuple(entries)


def get_staged_snapshot(workspace_root: Path) -> StagedSnapshot:
    """冻结当前 index 的 ACM 清单及 blob 标识，不读取工作区文件内容。"""
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--raw",
                "-z",
                "--no-abbrev",
                "--no-renames",
                "--diff-filter=ACM",
            ],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return StagedSnapshot(_parse_raw_index_entries(result.stdout))
    except Exception as exc:
        log.error("获取暂存区快照失败: %s", exc)
        raise StagedSnapshotError(f"获取暂存区快照失败: {exc}") from exc


def _get_staged_snapshot_or_reject(
    workspace_root: Path, hook_name: str
) -> StagedSnapshot | None:
    """读取暂存快照；读取失败时拒绝提交，避免将故障误判为无变更。"""
    try:
        return get_staged_snapshot(workspace_root)
    except Exception as exc:
        print(
            f"❌ [auto-pm {hook_name}] 物理拦截：无法读取 Git 暂存区，"
            f"为防止绕过门禁已拒绝提交: {exc}"
        )
        return None


def get_staged_files(workspace_root: Path) -> list[str]:
    """获取 Git 当前暂存区的文件相对路径列表"""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception as exc:
        log.error("获取暂存区文件失败: %s", exc)
        raise RuntimeError(f"获取暂存区文件失败: {exc}") from exc


def _get_staged_files_or_reject(workspace_root: Path, hook_name: str) -> list[str] | None:
    """读取暂存区；读取失败时拒绝提交，避免将故障误判为无变更。"""
    try:
        return get_staged_files(workspace_root)
    except Exception as exc:
        print(
            f"❌ [auto-pm {hook_name}] 物理拦截：无法读取 Git 暂存区，"
            f"为防止绕过门禁已拒绝提交: {exc}"
        )
        return None


def filter_production_files(files: list[str]) -> list[str]:
    """从暂存区筛选出生产代码文件"""
    prod_files: list[str] = []
    for f in files:
        f_norm = f.replace("\\", "/")
        # 排除纯文档、测试、草稿及会话文件
        if any(keyword in f_norm for keyword in EXCLUDED_PATH_KEYWORDS):
            continue
        if any(f_norm.endswith(ext) for ext in PRODUCTION_EXTENSIONS):
            prod_files.append(f)
    return prod_files


def _project_bindings(workspace_root: Path, projects: list[object]) -> tuple[ProjectBinding, ...]:
    """将注册项目转成可与 index 相对路径比对的受控根目录。"""
    workspace = workspace_root.resolve()
    bindings: list[ProjectBinding] = []
    for project in projects:
        project_id = str(
            getattr(project, "project_id", getattr(project, "id", ""))
        ).strip()
        project_path = getattr(project, "path", None)
        if not project_id or not project_path:
            continue
        try:
            relative = Path(project_path).resolve().relative_to(workspace)
        except (OSError, ValueError):
            continue
        if not relative.parts:
            continue
        bindings.append(ProjectBinding(project_id, _normalise_git_path(relative.as_posix())))
    return tuple(bindings)


def _binding_for_staged_file(
    path: str, bindings: tuple[ProjectBinding, ...]
) -> ProjectBinding:
    """要求每一个生产文件恰好归属一个注册项目。"""
    matches = [
        binding
        for binding in bindings
        if path == binding.relative_root or path.startswith(f"{binding.relative_root}/")
    ]
    if len(matches) != 1:
        raise StagedSnapshotError(f"暂存生产文件归属未知或不唯一: {path}")
    return matches[0]


def _production_project_ids(
    snapshot: StagedSnapshot, bindings: tuple[ProjectBinding, ...]
) -> tuple[str, ...]:
    """从冻结快照计算生产代码归属 PID，不接受跨项目提交。"""
    project_ids = {
        _binding_for_staged_file(path, bindings).project_id
        for path in filter_production_files(list(snapshot.paths))
    }
    return tuple(sorted(project_ids))


def _path_is_in_project(path: str, binding: ProjectBinding) -> bool:
    return path == binding.relative_root or path.startswith(f"{binding.relative_root}/")


def _change_entry(
    snapshot: StagedSnapshot, binding: ProjectBinding, chg_id: str
) -> StagedIndexEntry:
    """要求关联 CHG 文件本身是当前 index 快照的一部分。"""
    expected_name = f"{chg_id}.md"
    matches = [
        entry
        for entry in snapshot.entries
        if Path(entry.path).name == expected_name and _path_is_in_project(entry.path, binding)
    ]
    if len(matches) != 1:
        raise StagedSnapshotError(f"暂存快照缺少或重复关联变更单: {expected_name}")
    return matches[0]


def _ledger_entry(snapshot: StagedSnapshot, binding: ProjectBinding) -> StagedIndexEntry:
    """要求关联项目的台账文件也在同一个 index 快照中。"""
    ledger_suffixes = (
        "04_监控/01_变更管理/02_变更记录/01_版本变更台账.md",
        "11_监控/01_变更管理/02_变更记录/01_版本变更台账.md",
    )
    expected_paths = {f"{binding.relative_root}/{suffix}" for suffix in ledger_suffixes}
    matches = [entry for entry in snapshot.entries if entry.path in expected_paths]
    if len(matches) != 1:
        raise StagedSnapshotError("暂存快照缺少或重复关联项目台账")
    return matches[0]


def _read_staged_blob(workspace_root: Path, entry: StagedIndexEntry) -> bytes:
    """按已冻结的 blob 标识读取内容，不重新读取 index 或工作区。"""
    try:
        result = subprocess.run(
            ["git", "cat-file", "blob", entry.object_id],
            cwd=str(workspace_root),
            capture_output=True,
            check=True,
        )
    except Exception as exc:
        raise StagedSnapshotError(f"无法读取暂存 blob {entry.path}: {exc}") from exc
    if not isinstance(result.stdout, bytes):
        raise StagedSnapshotError(f"暂存 blob {entry.path} 返回了非字节内容")
    return result.stdout


def _working_tree_path(workspace_root: Path, entry: StagedIndexEntry) -> Path:
    """安全解析快照条目的工作区路径，仅用于检验字节一致性。"""
    try:
        workspace = workspace_root.resolve()
        candidate = (workspace / entry.path).resolve(strict=False)
    except OSError as exc:
        raise StagedSnapshotError(f"无法解析暂存快照路径 {entry.path}: {exc}") from exc
    if not candidate.is_relative_to(workspace):
        raise StagedSnapshotError(f"暂存快照路径越出工作区: {entry.path}")
    return candidate


def _normalise_line_endings(content: bytes) -> bytes:
    """对齐 Git text/eol 转换后的等价文本表示。"""
    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _require_working_tree_match(entry: StagedIndexEntry, expected: bytes, path: Path) -> None:
    """防止未暂存的本地修复掩盖 index 内被检治理证据。"""
    try:
        actual = path.read_bytes()
    except OSError as exc:
        raise StagedSnapshotError(f"无法读取工作区快照证据 {entry.path}: {exc}") from exc
    # Git 的 text/eol 转换可令工作区合法 CRLF 与 index blob 的 LF 不同；
    # 只消除该表示差异，其他内容变化仍必须拒绝。
    if _normalise_line_endings(actual) != _normalise_line_endings(expected):
        raise StagedSnapshotError(f"工作区证据与暂存快照不一致: {entry.path}")


def _staged_change_project_id(content: str, chg_id: str) -> str:
    """从 index 中的 CHG 内容读取其显式项目编号。"""
    if chg_id not in _CHG_ID_PATTERN.findall(content):
        raise StagedSnapshotError(f"暂存变更单内容未声明关联编号: {chg_id}")
    project_ids = {match.group(1).strip() for match in _PROJECT_ID_ROW_PATTERN.finditer(content)}
    if len(project_ids) != 1 or not next(iter(project_ids), ""):
        raise StagedSnapshotError(f"暂存变更单项目编号缺失或不唯一: {chg_id}")
    return next(iter(project_ids))


def _validate_staged_change_evidence(
    workspace_root: Path,
    snapshot: StagedSnapshot,
    binding: ProjectBinding,
    chg_id: str,
) -> Path:
    """绑定同一 index 内的 CHG、PID、台账和代码项目归属。"""
    change_entry = _change_entry(snapshot, binding, chg_id)
    ledger_entry = _ledger_entry(snapshot, binding)
    change_blob = _read_staged_blob(workspace_root, change_entry)
    ledger_blob = _read_staged_blob(workspace_root, ledger_entry)
    change_path = _working_tree_path(workspace_root, change_entry)
    ledger_path = _working_tree_path(workspace_root, ledger_entry)
    _require_working_tree_match(change_entry, change_blob, change_path)
    _require_working_tree_match(ledger_entry, ledger_blob, ledger_path)

    change_content = change_blob.decode("utf-8", errors="replace")
    ledger_content = ledger_blob.decode("utf-8", errors="replace")
    staged_project_id = _staged_change_project_id(change_content, chg_id)
    if staged_project_id != binding.project_id:
        raise StagedSnapshotError(
            f"暂存变更单 PID 与生产代码归属不一致: {staged_project_id} != {binding.project_id}"
        )
    if chg_id not in ledger_content:
        raise StagedSnapshotError(f"暂存项目台账未包含关联变更单: {chg_id}")
    return change_path


def enforce_pre_commit(workspace_root: Path) -> int:
    """pre-commit 阶段拦截检查：
    1. 扫描暂存区关联项目的版本变更台账一致性；
    2. 若全仓台账存在缺失/孤儿/不一致，直接 exit 1 阻断。
    """
    staged = _get_staged_files_or_reject(workspace_root, "pre-commit")
    if staged is None:
        return 1
    if not staged:
        return 0

    print("🔍 [auto-pm pre-commit] 正在执行全仓台账一致性物理门禁预检...")
    try:
        # 调用 auto-pm change verify 验证台账
        from auto_pm.core.project_service import ProjectService
        from auto_pm.domain.change.ledger_reconciler import LedgerReconciler

        ps = ProjectService(str(workspace_root))
        projects = ps.list_projects()
        reconciler = LedgerReconciler()

        has_ledger_error = False
        for p in projects:
            p_root = getattr(p, "path", None)
            pid = getattr(p, "id", "")
            if not p_root:
                continue
            ledger_file = Path(p_root) / "04_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台账.md"
            if not ledger_file.is_file():
                ledger_file = Path(p_root) / "11_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台账.md"
            if not ledger_file.is_file():
                continue

            report = reconciler.reconcile(str(p_root))
            if not report.is_clean:
                print(
                    f"❌ [auto-pm pre-commit] 项目 [{pid}] 台账对账不一致: "
                    f"缺失 {len(report.missing_in_ledger)} 条, "
                    f"孤儿 {len(report.orphan_in_ledger)} 条, "
                    f"状态差异 {len(report.status_mismatches)} 条！"
                )
                has_ledger_error = True

        if has_ledger_error:
            print("🚨 [auto-pm pre-commit] 物理阻断：台账未闭环，严禁直接 Commit！请先运行 auto-pm ledger reconcile <PID> --fix")
            return 1

    except Exception as exc:
        print(
            "❌ [auto-pm pre-commit] 物理拦截：台账检查异常，"
            f"为防止绕过门禁已拒绝提交: {exc}"
        )
        return 1

    print("✅ [auto-pm pre-commit] 全仓台账门禁校验通过。")
    return 0


def enforce_commit_msg(workspace_root: Path, commit_msg_file: Path) -> int:
    """commit-msg 阶段拦截检查：
    1. 若暂存区包含生产代码（.py, .scl 等），强制 Commit Message 必须注明关联单号；
    2. 在同一 index 快照内校验 CHG、PID、项目台账及其合法执行态。
    """
    snapshot = _get_staged_snapshot_or_reject(workspace_root, "commit-msg")
    if snapshot is None:
        return 1
    staged = list(snapshot.paths)
    prod_files = filter_production_files(staged)

    if not prod_files:
        # 纯文档/治理/会话提交，豁免变更单号要求
        return 0

    try:
        if not commit_msg_file.is_file():
            print(f"❌ [auto-pm commit-msg] 未找到提交信息文件: {commit_msg_file}")
            return 1

        msg_content = commit_msg_file.read_text(encoding="utf-8", errors="replace").strip()

        # 匹配变更单号，如 CHG-SCPT-2026-170, CHG-PLC-2026-012
        chg_matches = tuple(dict.fromkeys(_CHG_ID_PATTERN.findall(msg_content)))
    except Exception as exc:
        print(
            "❌ [auto-pm commit-msg] 物理拦截：无法读取或解析提交信息，"
            f"为防止绕过门禁已拒绝提交: {exc}"
        )
        return 1

    if not chg_matches:
        print("=" * 70)
        print("❌ [auto-pm commit-msg] 物理拦截：检测到暂存区包含生产代码变更，但 Commit Message 未绑定变更单！")
        print("📄 涉及生产文件:")
        for pf in prod_files[:5]:
            print(f"   - {pf}")
        if len(prod_files) > 5:
            print(f"   ... (共 {len(prod_files)} 个文件)")
        print("\n👉 规程要求：生产代码提交必须显式注明合法变更单号，例如:")
        print("   feat(core): [CHG-SCPT-2026-170] 落地决策包与门禁护航机制")
        print("=" * 70)
        return 1

    if len(chg_matches) != 1:
        print(
            "❌ [auto-pm commit-msg] 物理拦截：生产代码提交必须且只能绑定一个变更单，"
            "为防止快照关联歧义已拒绝提交！"
        )
        return 1

    chg_id = chg_matches[0]
    # 同一 index 快照内必须同时具备代码、CHG、PID 与项目台账证据。
    try:
        from auto_pm.core.project_service import ProjectService

        bindings = _project_bindings(
            workspace_root,
            list(ProjectService(str(workspace_root)).list_projects()),
        )
        project_ids = _production_project_ids(snapshot, bindings)
        if len(project_ids) != 1:
            project_id_text = ", ".join(project_ids) or "无"
            raise StagedSnapshotError(f"暂存生产代码归属项目不唯一: {project_id_text}")
        matched_bindings = [
            binding for binding in bindings if binding.project_id == project_ids[0]
        ]
        if len(matched_bindings) != 1:
            raise StagedSnapshotError(f"项目 PID 映射不唯一: {project_ids[0]}")
        binding = matched_bindings[0]
        change_path = _validate_staged_change_evidence(
            workspace_root, snapshot, binding, chg_id
        )
    except Exception as exc:
        print(
            "❌ [auto-pm commit-msg] 物理拦截：暂存快照的 CHG/PID/台账证据"
            f"不完整或不一致，为防止绕过门禁已拒绝提交: {exc}"
        )
        return 1

    # 检查变更单状态是否为合法执行态
    try:
        parser = ChgParser()
        cr = parser.parse(str(change_path))
        if cr.change_number != chg_id or cr.project_id != binding.project_id:
            print(
                "❌ [auto-pm commit-msg] 物理拦截：变更单解析结果与暂存快照的"
                " CHG/PID 关联不一致！"
            )
            return 1
        if cr.status not in _VALID_CHANGE_STATUSES:
            print(
                f"❌ [auto-pm commit-msg] 物理拦截：关联变更单 {chg_id} 当前状态为 '{cr.status}'，"
                "尚未获得审批批准，严禁提交代码！"
            )
            return 1
    except Exception as exc:
        print(
            "❌ [auto-pm commit-msg] 物理拦截：解析关联变更单状态失败，"
            f"为防止绕过门禁已拒绝提交: {exc}"
        )
        return 1

    print(f"✅ [auto-pm commit-msg] 生产代码与变更单 {chg_id} 强校验绑定通过！")
    return 0
