"""PLC-HMI 概念映射：SFB 库函数（ProjectService）

像 PLC 的 SFB/SFC 系统函数，提供底层项目数据操作能力。
被 FB_Workbench（workbench_facade.py）调用，不直接暴露给 HMI 画面。

--- 原始注释 ---
项目 CRUD Service

扫描工作空间内的项目，读取项目元数据，提供列表/查询能力。
项目识别规则（满足任一）：
- 目录下存在 .copier-answers.yml（Copier 生成的项目）
- 目录下存在 .plc.json（PLC 项目配置）
- 目录下存在 PM_SESSION_*.md（项目管理会话文件）

M3-Iter1 重构：扫描/识别逻辑提取到 ProjectScanner，本类通过组合方式使用。
保留旧方法签名（_read_copier_answers 等）以向后兼容，内部委托给 scanner。
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import yaml
from auto_pm.core.constants import get_template_name
from auto_pm.core.paths import PROJECT_INIT_PATH, WORKSPACE_PROJECTS_SUBDIR
from auto_pm.core.project_scanner import ProjectScanner
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository, ProjectRepository
from auto_pm.models import ProjectInfo, ProjectListItem, ProjectRecord
from auto_pm.models.project import extract_business_line
from auto_pm.utils.file_utils import StaleFileError, get_mtime, write_file

if TYPE_CHECKING:
    from auto_pm.core.project_archive_service import ArchiveResult, ProjectArchiveService

    from auto_pm.domain.project.archive_contracts import ArchiveRequest

log = logging.getLogger(__name__)

# C Fix (CHG-SCPT-2026-148): import 阶段自动生成 SHC-014 兼容索引
# 按文件名后缀扫描 req/int/tec/dsn 文档，追加到 PM_SESSION §4
_SHC014_SCAN_PATTERNS: list[tuple[str, str]] = [
    ("req", "_REQ"),
    ("int", "_INT"),
    ("tec", "_TEC"),
    ("dsn", "_DSN"),
]
_SHC014_MARKER = "<!-- auto-pm SHC-014 兼容索引，由 import 自动生成 -->"
_SHC014_SEC4_RE = re.compile(r"^## 4[.\s]", re.MULTILINE)
_SHC014_ENTRY_RE = re.compile(r"^-\s*(req|int|dsn|tec)\s*:", re.MULTILINE | re.IGNORECASE)
_SHC014_NEXT_SEC_RE = re.compile(r"^## \d", re.MULTILINE)


class ProjectService:
    """项目 CRUD Service

    通过组合 ProjectScanner 实现扫描/识别职责分离。
    本类保留对外的旧方法签名（如 _read_copier_answers）以避免破坏调用方，
    内部全部委托给 self._scanner。
    """

    # 保留旧常量名以兼容外部引用
    COPIER_ANSWERS_FILE = ProjectScanner.COPIER_ANSWERS_FILE
    PLC_JSON_FILE = ProjectScanner.PLC_JSON_FILE
    PM_SESSION_PREFIX = ProjectScanner.PM_SESSION_PREFIX

    def __init__(self, workspace_root: str, db: DatabaseManager | None = None) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.db = db
        self._repo: ProjectRepository | None = ProjectRepository(db) if db else None
        self._repo_change: ChangeRequestRepository | None = (
            ChangeRequestRepository(db) if db else None
        )
        # M3-Iter1: 组合 ProjectScanner，委托扫描/识别逻辑
        self._scanner = ProjectScanner(self.workspace_root)
        self._archive_service: ProjectArchiveService | None = None

    def inject_db(self, db: DatabaseManager) -> None:
        """运行时注入 DatabaseManager 并重建 Repository

        用于无法在构造时传入 db 的场景（如 UI 层先创建 Service，后初始化 DB）。

        Args:
            db: DatabaseManager 实例
        """
        self.db = db
        self._repo = ProjectRepository(db)
        self._repo_change = ChangeRequestRepository(db)

    # ── 项目列表 ──────────────────────────────────────────

    def list_projects(self, scan_depth: int = 4) -> list[ProjectInfo]:
        """扫描工作空间，返回所有项目

        Args:
            scan_depth: 最大扫描深度（默认4层）

        Returns:
            项目列表，按 project_id 排序
        """
        return cast(list[ProjectInfo], self._scanner.scan(scan_depth=scan_depth))

    def configure_archive_service(self, service: ProjectArchiveService) -> None:
        """Inject the authorized archive boundary explicitly."""
        service_root = os.path.normcase(os.path.realpath(service.workspace_root))
        own_root = os.path.normcase(os.path.realpath(self.workspace_root))
        if service_root != own_root:
            raise ValueError("归档服务工作区与项目服务不一致")
        self._archive_service = service

    def archive_project(self, request: ArchiveRequest) -> ArchiveResult:
        """Delegate an exact archive request; no force or delete path exists."""
        from auto_pm.domain.project.archive_contracts import ArchiveOperation

        if request.operation is not ArchiveOperation.ARCHIVE:
            raise ValueError("archive_project 仅接受 archive 请求")
        if self._archive_service is None:
            raise RuntimeError("未配置安全归档服务")
        return self._archive_service.execute(request)

    def restore_project(self, request: ArchiveRequest) -> ArchiveResult:
        """Delegate an exact restore request after checking its typed operation."""
        from auto_pm.domain.project.archive_contracts import ArchiveOperation

        if request.operation is not ArchiveOperation.RESTORE:
            raise ValueError("restore_project 仅接受 restore 请求")
        if self._archive_service is None:
            raise RuntimeError("未配置安全归档服务")
        return self._archive_service.execute(request)

    def list_archived_projects(self) -> tuple[dict[str, str], ...]:
        """Read archived records only through the configured safe service."""
        if self._archive_service is None:
            raise RuntimeError("未配置安全归档服务")
        return cast(tuple[dict[str, str], ...], self._archive_service.list_archived())

    def list_projects_cached(self) -> list[ProjectInfo]:
        """从 DB 缓存读取项目列表（不扫描文件系统）

        Returns:
            项目列表，按 project_id 排序

        Raises:
            RuntimeError: 未注入 DatabaseManager
        """
        if self._repo is None:
            raise RuntimeError("未注入 DatabaseManager，无法使用缓存模式")
        records = self._repo.list_all()
        return [self._record_to_info(r) for r in records]

    def get_project_cached(self, project_id: str) -> ProjectInfo | None:
        """从 DB 缓存按 project_id 查询项目

        Raises:
            RuntimeError: 未注入 DatabaseManager
        """
        if self._repo is None:
            raise RuntimeError("未注入 DatabaseManager，无法使用缓存模式")
        record = self._repo.get_by_id(project_id)
        return self._record_to_info(record) if record else None

    def list_projects_filtered(
        self,
        stack: str | None = None,
        phase: str | None = None,
        business_line: str | None = None,
    ) -> list[ProjectInfo]:
        """按条件筛选项目（从 DB 缓存查询）

        Args:
            stack: 技术栈筛选 (plc/python/unknown)
            phase: 阶段筛选 (developing/commissioning/production/archived)
            business_line: 业务线筛选 (SW/DJ/ZD/XT/WX)

        Returns:
            筛选后的项目列表

        Raises:
            RuntimeError: 未注入 DatabaseManager
        """
        if self._repo is None:
            raise RuntimeError("未注入 DatabaseManager，无法使用缓存模式")

        # stack+phase 联合筛选 → Repository 无此方法，用 list_projects_cached 后内存筛选
        if stack and phase:
            projects = self.list_projects_cached()
            return [
                p
                for p in projects
                if p.stack == stack
                and p.phase == phase
                and (business_line is None or p.business_line == business_line)
            ]
        elif stack:
            records = self._repo.list_by_stack(stack)
        elif phase:
            records = self._repo.list_by_phase(phase)
        elif business_line:
            records = self._repo.list_by_business_line(business_line)
        else:
            return self.list_projects_cached()

        projects = [self._record_to_info(r) for r in records]

        # 叠加 business_line 筛选（当已按 stack 或 phase 筛选时）
        if business_line and (stack or phase):
            projects = [p for p in projects if p.business_line == business_line]
        return projects

    def list_projects_with_change_count(self) -> list[ProjectListItem]:
        """返回带变更数统计的项目列表（用于卡片展示）

        Raises:
            RuntimeError: 未注入 DatabaseManager
        """
        if self._repo is None:
            raise RuntimeError("未注入 DatabaseManager，无法使用缓存模式")

        projects = self.list_projects_cached()
        result: list[ProjectListItem] = []
        for p in projects:
            change_count = (
                self._repo_change.count_by_project(p.project_id)
                if self._repo_change is not None
                else 0
            )
            result.append(
                ProjectListItem(
                    project_id=p.project_id,
                    name=p.name,
                    path=p.path,
                    stack=p.stack,
                    version=p.version,
                    phase=p.phase,
                    business_line=str(p.business_line) if p.business_line else "",
                    change_count=change_count,
                )
            )
        return result

    def generate_project_code(self, business_line: str) -> str:
        """自动生成项目编号：{业务线}-{年份}-{序号:03d}

        扫描工作空间中同业务线同年份的已有项目，取最大序号 +1。
        若未找到任何项目，从 001 开始。

        Args:
            business_line: 业务线代码（如 "SW", "DJ"）

        Returns:
            项目编号字符串（如 "SW-2026-009"）
        """
        import datetime

        year = datetime.datetime.now().year
        prefix = f"{business_line}-{year}-"
        max_seq = 0

        try:
            projects = self.list_projects()
        except Exception:
            projects = []

        for p in projects:
            pid = p.project_id if hasattr(p, "project_id") else str(p)
            if pid.startswith(prefix):
                try:
                    seq = int(pid.split("-")[-1])
                    if seq > max_seq:
                        max_seq = seq
                except (ValueError, IndexError):
                    pass

        return f"{business_line}-{year}-{max_seq + 1:03d}"

    def get_project_count(self) -> int:
        """获取项目总数（优先查缓存）"""
        if self._repo is not None and hasattr(self._repo, "count"):
            try:
                return int(self._repo.count())
            except Exception as e:
                log.warning("DB count 查询失败，返回 0: %s", e, exc_info=True)
                return 0
        try:
            return len(self.list_projects_cached())
        except Exception as e:
            log.warning("list_projects_cached 失败，返回 0: %s", e, exc_info=True)
            return 0

    def get_db_path(self) -> str:
        """获取 DB 文件路径（若未初始化则返回空字符串）"""
        if self.db is not None and hasattr(self.db, "db_path"):
            return str(self.db.db_path)
        return ""

    # ── 内部辅助方法 ──────────────────────────────────────────

    def get_project(self, project_id: str) -> ProjectInfo | None:
        """按 project_id 查询项目（优先 DB 缓存，降级文件扫描）

        Args:
            project_id: 项目编号，如 DJ-2026-010

        Returns:
            ProjectInfo 或 None（未找到）
        """
        if not project_id or not str(project_id).strip():
            return None

        if self._repo is not None:
            try:
                cached = self.get_project_cached(project_id)
                if cached is not None:
                    return cached
            except Exception as e:
                log.warning("DB 缓存查询失败，降级到文件扫描: %s", e)
        for proj in self.list_projects():
            if proj.project_id == project_id:
                return proj
        log.debug("项目未找到: %s", project_id)
        return None

    def find_project_path(self, project_id: str) -> str | None:
        """按 project_id 查询项目路径

        Args:
            project_id: 项目编号

        Returns:
            项目绝对路径或 None
        """
        if not project_id or not str(project_id).strip():
            return None
        proj = self.get_project(project_id)
        return proj.path if proj else None

    # ── 项目导入/分类/搜索 ──────────────────────────────

    def import_project(
        self,
        src_path: str,
        business_line: str | None = None,
        move: bool = False,
        force: bool = False,
    ) -> str:
        """导入外部项目目录到工作空间的 02_在研项目/ 下

        Args:
            src_path: 源项目目录路径
            business_line: 业务线（默认从项目编号前缀推断）
            move: True 移动，False 复制
            force: True 强制覆盖已存在的目标目录

        Returns:
            导入后的项目绝对路径

        Raises:
            FileExistsError: 目标路径已存在且未指定 force
            FileNotFoundError: 源目录不存在
        """
        import shutil

        src = os.path.abspath(src_path)
        if not os.path.isdir(src):
            raise FileNotFoundError(f"源目录不存在: {src}")

        dirname = os.path.basename(src)
        dest_path = os.path.join(self.workspace_root, WORKSPACE_PROJECTS_SUBDIR, dirname)

        if os.path.exists(dest_path):
            if not force:
                raise FileExistsError(f"目标路径已存在: {dest_path}（使用 force=True 覆盖）")
            shutil.rmtree(dest_path, ignore_errors=True)

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        if move:
            shutil.move(src, dest_path)
        else:
            shutil.copytree(src, dest_path)

        # 补全 .copier-answers.yml
        try:
            self.retrofit_project_by_path(dest_path)
        except FileExistsError:
            pass  # 已有 .copier-answers.yml，正常

        # 同步到 DB 缓存（如果 DB 已注入）
        if self.db is not None:
            try:
                self.sync_to_cache(force_full=True)
            except Exception as e:
                log.warning("导入后 DB 缓存同步失败: %s", e)

        log.info("项目已导入: %s -> %s", src, dest_path)
        return dest_path

    def classify_project(self, project_id: str, business_line: str) -> ProjectInfo:
        """更新项目业务线分类（写入 .copier-answers.yml 覆盖值）

        Args:
            project_id: 项目编号
            business_line: 业务线 (SW/DJ/ZD/XT/WX)

        Returns:
            更新后的 ProjectInfo

        Raises:
            FileNotFoundError: 项目不存在
        """
        return self.update_project_meta(project_id, business_line=business_line)

    def search_projects(self, keyword: str) -> list[ProjectInfo]:
        """关键字搜索项目（匹配项目编号/名称/描述）

        Args:
            keyword: 搜索关键字（不区分大小写）

        Returns:
            匹配的项目列表
        """
        keyword_lower = keyword.lower()
        try:
            all_projects = self.list_projects_cached()
        except RuntimeError:
            all_projects = self.list_projects()
        return [
            p
            for p in all_projects
            if keyword_lower in p.project_id.lower()
            or keyword_lower in p.name.lower()
            or keyword_lower in p.description.lower()
        ]

    # ── 项目编辑 ──────────────────────────────────────────

    def update_project_meta(self, project_id: str, **kwargs: str) -> ProjectInfo:
        """更新项目元数据（按来源写入对应标志文件）

        - plc_json 来源 → 写 .plc.json
        - 其他来源 → 写 .copier-answers.yml

        Args:
            project_id: 项目编号
            **kwargs: 可更新字段（如 phase/description/version/project_type 等）

        Returns:
            更新后的 ProjectInfo

        Raises:
            FileNotFoundError: 项目不存在
        """
        proj = self.get_project(project_id)
        if proj is None:
            raise FileNotFoundError(f"项目不存在: {project_id}")

        if proj.source == "plc_json":
            self._update_plc_json(proj.path, kwargs)
        else:
            self._update_copier_answers(proj.path, kwargs, proj)

        log.info("项目元数据已更新: %s -> %s", project_id, kwargs)
        updated = self.get_project(project_id)
        if updated is None:
            raise RuntimeError(f"更新后重新查询项目失败: {project_id}")

        # 同步到 DB 缓存
        if self._repo is not None:
            self._upsert_to_cache(updated)

        return updated

    def _update_copier_answers(
        self, project_path: str, kwargs: dict[str, str], proj: ProjectInfo
    ) -> None:
        """写入 .copier-answers.yml

        确保关键字段（project_id/project_name）不丢失，
        避免 PM_SESSION/dirname 来源项目更新后重新扫描时 project_id 变为目录名。
        """
        answers_path = os.path.join(project_path, self.COPIER_ANSWERS_FILE)
        answers: dict[str, Any] = {}
        if os.path.isfile(answers_path):
            with open(answers_path, encoding="utf-8") as f:
                answers = yaml.safe_load(f) or {}

        # 保证关键字段存在（防止重新扫描时识别失败）
        answers.setdefault("project_id", proj.project_id)
        answers.setdefault("project_name", proj.name)
        answers.setdefault("project_type", proj.project_type)
        answers.setdefault("equipment_type", proj.equipment_type)
        answers.setdefault("plc_vendor", proj.plc_vendor)
        answers.setdefault("plc_model", proj.plc_model)

        for key, value in kwargs.items():
            if value is not None:
                answers[key] = value

        original_mtime = get_mtime(answers_path)
        try:
            write_file(
                answers_path,
                yaml.safe_dump(answers, allow_unicode=True, sort_keys=False),
                expected_mtime=original_mtime,
            )
        except StaleFileError as exc:
            raise RuntimeError(f".copier-answers.yml 已被外部修改: {answers_path}") from exc

    def _update_plc_json(self, project_path: str, kwargs: dict[str, str]) -> None:
        """写入 .plc.json（保留原有字段，更新指定字段）"""
        plc_json_path = os.path.join(project_path, self.PLC_JSON_FILE)
        cfg: dict[str, Any] = {}
        if os.path.isfile(plc_json_path):
            with open(plc_json_path, encoding="utf-8") as f:
                cfg = json.load(f)

        for key, value in kwargs.items():
            if value is not None:
                cfg[key] = value

        original_mtime = get_mtime(plc_json_path)
        try:
            write_file(
                plc_json_path,
                json.dumps(cfg, ensure_ascii=False, indent=2),
                expected_mtime=original_mtime,
            )
        except StaleFileError as exc:
            raise RuntimeError(f".plc.json 已被外部修改: {plc_json_path}") from exc

    # ── 项目补全 ──────────────────────────────────────────

    def retrofit_project_by_path(self, project_path: str) -> str:
        """为指定路径的项目补全 .copier-answers.yml 元数据文件

        从目录名提取 project_id，从 .plc.json/PM_SESSION 读取已有元数据。
        用于导入外部项目后补全标志文件。

        Args:
            project_path: 项目目录路径

        Returns:
            创建的 .copier-answers.yml 路径

        Raises:
            FileNotFoundError: 项目目录不存在
            FileExistsError: .copier-answers.yml 已存在
        """
        if not os.path.isdir(project_path):
            raise FileNotFoundError(f"项目目录不存在: {project_path}")

        answers_path = os.path.join(project_path, self.COPIER_ANSWERS_FILE)
        if os.path.isfile(answers_path):
            raise FileExistsError(f".copier-answers.yml 已存在: {answers_path}")

        project_id = self._extract_id_from_dirname(project_path)
        project_name = os.path.basename(project_path)
        description = ""
        version = ""
        stack = "unknown"
        plc_extra: dict[str, str] = {}

        plc_info = self._read_plc_json(project_path)
        if plc_info is not None:
            # 根目录存在 .plc.json
            project_id = plc_info.project_id
            project_name = plc_info.name
            description = plc_info.description
            version = plc_info.version
            stack = "plc"
            for key in ("project_type", "equipment_type", "plc_vendor", "plc_model"):
                value = getattr(plc_info, key, "")
                if value:
                    plc_extra[key] = value
        else:
            # B1 Fix: 根目录无 .plc.json 时递归查找子目录
            # 适配 02_PLC程序/PLC_ST/.plc.json 嵌套结构（V0.2.1-P2-11 已有该能力）
            plc_json_nested = self._scanner._find_plc_json_recursive(project_path)
            if plc_json_nested:
                try:
                    with open(plc_json_nested, encoding="utf-8") as _f:
                        _cfg = json.load(_f)
                    stack = "plc"
                    project_name = _cfg.get("name", "") or project_name
                    description = _cfg.get("description", "")
                    version = _cfg.get("version", "") or version
                    for key in ("project_type", "equipment_type", "plc_vendor", "plc_model"):
                        val = _cfg.get(key, "")
                        if val:
                            plc_extra[key] = val
                except (OSError, json.JSONDecodeError):
                    pass

            if stack == "unknown":
                # 仍未识别为 PLC，尝试从 PM_SESSION 读取 project_id
                session_info = self._read_pm_session(project_path)
                if session_info is not None:
                    project_id = session_info.project_id

        template_name = get_template_name(stack)
        content: dict[str, str] = {
            "_commit": "HEAD",
            "_src_path": f"templates/{template_name}",
            "project_id": project_id,
            "project_name": project_name,
            "description": description or project_name,
            "version": version or "V1.0.0",
        }
        content.update(plc_extra)

        write_file(answers_path, yaml.safe_dump(content, allow_unicode=True, sort_keys=False))

        # C Fix (CHG-SCPT-2026-148): PLC 项目接管后自动追加 SHC-014 兼容文档索引
        # 让存量项目无需手动补条目即可通过 CHG completed 门禁
        if stack == "plc":
            doc_index = self._scan_doc_index_candidates(project_path)
            self._append_shc014_index_to_pm_session(project_path, doc_index)

        log.info("已补全 .copier-answers.yml: %s", answers_path)
        return answers_path

    @staticmethod
    def _scan_doc_index_candidates(
        project_path: str,
        max_depth: int = 5,
    ) -> dict[str, str]:
        """递归扫描项目目录，按文件名后缀识别 req/int/tec/dsn 文档

        适配 LSP-907 命名规范（*_REQ.md / *_INT.md / *_TEC.md / *_DSN.md）。
        仅返回实际存在的文档（路径相对于 project_path），不生成占位符。
        每类文档取找到的第一个，跳过隐藏目录和缓存目录。

        Args:
            project_path: 项目根目录
            max_depth: 最大递归深度（默认 5 层）

        Returns:
            {doc_type: relative_path_from_project_root}，如 {"req": "00_doc\\xxx_REQ.md"}
        """
        found: dict[str, str] = {}
        total = len(_SHC014_SCAN_PATTERNS)

        def _walk(dir_path: str, depth: int) -> None:
            if depth > max_depth or len(found) >= total:
                return
            try:
                entries = sorted(os.listdir(dir_path))
            except OSError:
                return
            for entry in entries:
                if entry.startswith(".") or entry.startswith("__"):
                    continue
                entry_path = os.path.join(dir_path, entry)
                if os.path.isfile(entry_path) and entry.upper().endswith(".MD"):
                    name_upper = entry.upper()
                    for doc_type, suffix in _SHC014_SCAN_PATTERNS:
                        if doc_type not in found and suffix in name_upper:
                            rel = os.path.relpath(entry_path, project_path)
                            found[doc_type] = rel
                            break
                elif os.path.isdir(entry_path):
                    _walk(entry_path, depth + 1)

        _walk(project_path, 0)
        return found

    def _append_shc014_index_to_pm_session(
        self,
        project_path: str,
        doc_index: dict[str, str],
    ) -> bool:
        """在 PM_SESSION §4 末尾追加 SHC-014 兼容的标准索引条目

        幂等设计：已存在的条目不重复追加，标记已注入时跳过。
        仅在找到 §4 章节时才写入；无 PM_SESSION 或无 §4 时静默跳过。

        Args:
            project_path: 项目根目录
            doc_index: _scan_doc_index_candidates 的返回值

        Returns:
            True 表示文件被修改，False 表示跳过（无需修改或无可追加条目）
        """
        if not doc_index:
            return False

        # 找 PM_SESSION_*.md（取第一个）
        pm_files = [
            os.path.join(project_path, f)
            for f in os.listdir(project_path)
            if f.startswith("PM_SESSION_") and f.endswith(".md")
        ]
        if not pm_files:
            log.debug("未找到 PM_SESSION_*.md，跳过 SHC-014 索引追加: %s", project_path)
            return False
        pm_path = pm_files[0]

        try:
            raw = open(pm_path, encoding="utf-8").read()
        except OSError as exc:
            log.warning("读取 PM_SESSION 失败，跳过 SHC-014 索引追加: %s", exc)
            return False

        # §4 章节必须存在
        m4 = _SHC014_SEC4_RE.search(raw)
        if not m4:
            log.debug("PM_SESSION 无 §4 章节，跳过 SHC-014 索引追加: %s", pm_path)
            return False

        # 幂等：标记已存在则跳过（防止重复 import）
        if _SHC014_MARKER in raw:
            log.debug("SHC-014 兼容索引已存在，跳过: %s", pm_path)
            return False

        # 找已有的标准关键词条目，避免重复
        existing = {m.group(1).lower() for m in _SHC014_ENTRY_RE.finditer(raw)}
        missing = {k: v for k, v in doc_index.items() if k not in existing}
        if not missing:
            log.debug("所有 SHC-014 条目已存在，跳过追加: %s", pm_path)
            return False

        # 定位插入点：§4 结束处（下一个 ## N 章节之前，或文件末尾）
        sec4_start = m4.start()
        rest_after_sec4 = raw[sec4_start + len(m4.group(0)) :]
        nm = _SHC014_NEXT_SEC_RE.search(rest_after_sec4)
        insert_pos = sec4_start + len(m4.group(0)) + nm.start() if nm else len(raw)

        # 构建追加块
        lines = [f"\n{_SHC014_MARKER}\n"]
        for doc_type in ("req", "int", "tec", "dsn"):
            if doc_type in missing:
                lines.append(f"- {doc_type}: {missing[doc_type]}\n")
        lines.append("\n")

        new_raw = raw[:insert_pos] + "".join(lines) + raw[insert_pos:]
        write_file(pm_path, new_raw)
        log.info(
            "已在 PM_SESSION §4 追加 SHC-014 兼容索引 %d 条: %s",
            len(missing),
            pm_path,
        )
        return True

    def init_project_pm_framework(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        stack_type: str,
        author: str | None = None,
    ) -> None:
        """为指定路径的项目执行非侵入式 PM 基础文档与目录的初始化补全

        Args:
            project_path: 项目目录绝对路径
            project_id: 项目编号（例如 DJ-2026-000）
            project_name: 项目名称
            stack_type: 技术栈，'plc' 或 'python'
            author: 主设计人/申请人名称（如果为 None 则动态获取）
        """
        if author is None:
            author = (
                os.getenv("AUTO_PM_AUTHOR")
                or os.getenv("USERNAME")
                or os.getenv("USER")
                or getpass.getuser()
            )

        if not os.path.isdir(project_path):
            raise FileNotFoundError(f"项目目录不存在: {project_path}")

        # 1. 补全 .copier-answers.yml
        answers_path = os.path.join(project_path, self.COPIER_ANSWERS_FILE)
        if not os.path.isfile(answers_path):
            try:
                self.retrofit_project_by_path(project_path)
            except Exception as e:
                log.warning("补全 .copier-answers.yml 失败: %s", e)

        # 2. 根据 stack_type 补齐基础 PM 目录
        # CHG-SCPT-2026-146: 5大过程组统一路径，PLC/Python 均使用 01_启动/
        today_str = datetime.now().strftime("%Y-%m-%d")
        if stack_type == "plc":
            pm_dir = os.path.join(project_path, *PROJECT_INIT_PATH)
            proj_doc_name = f"{project_id}_PROJ.md"
            proj_doc_template = (
                f"# Westwell PLC 项目立项需求说明书（{project_id}）\n\n"
                f"## 1. 项目基础信息\n"
                f"- **项目名称**：{project_name}\n"
                f"- **项目编号**：{project_id}\n"
                f"- **主设计人**：{author}\n"
                f"- **创建日期**：{today_str}\n\n"
                f"## 2. 需求定义\n"
                f"- 初始化项目框架与基础文档。\n"
            )
        else:
            pm_dir = os.path.join(project_path, *PROJECT_INIT_PATH)
            proj_doc_name = f"{project_id}_PM.md"
            proj_doc_template = (
                f"# Westwell Python 项目立项表（{project_id}）\n\n"
                f"## 1. 项目基础信息\n"
                f"- **项目名称**：{project_name}\n"
                f"- **项目编号**：{project_id}\n"
                f"- **主设计人**：{author}\n"
                f"- **创建日期**：{today_str}\n\n"
                f"## 2. 项目背景与目标\n"
                f"- 初始化项目框架与基础文档。\n"
            )

        os.makedirs(pm_dir, exist_ok=True)

        # 3. 创建立项表草稿 (如果不存在)
        proj_doc_path = os.path.join(pm_dir, proj_doc_name)
        if not os.path.isfile(proj_doc_path):
            write_file(proj_doc_path, proj_doc_template)
            log.info("已初始化立项表: %s", proj_doc_path)

        # 4. 创建 PM_SESSION 骨架 (如果不存在)
        session_path = os.path.join(project_path, f"PM_SESSION_{project_id}.md")
        if not os.path.isfile(session_path):
            session_template = (
                f"# PM_SESSION_{project_id}\n\n"
                f"> 项目管理会话\n\n"
                f"## 0. Meta\n"
                f"| 字段 | 内容 |\n"
                f"| --- | --- |\n"
                f"| 项目编号 | {project_id} |\n"
                f"| 项目名称 | {project_name} |\n"
                f"| 技术栈 | {stack_type} |\n"
                f"| 版本 | V1.0.0 |\n\n"
                f"## 1. Positioning（项目定位）\n"
                f"- **一句话描述**：{project_name} 基础文档初始化。\n\n"
                f"## 2. Milestone/Version（里程碑/版本）\n"
                f"- [ ] V1.0.0 初始化版本归档\n\n"
                f"## 3. Backlog/UserStories（待办/用户故事）\n"
                f"- 无\n\n"
                f"## 4. Current Iteration（当前迭代）\n"
                f"- 无\n\n"
                f"## 5. Execution Records（执行记录）\n"
                f"- 无\n\n"
                f"## 6. Change Records（变更历史）\n"
                f"| 序号 | 变更单号 | 状态 | 描述 |\n"
                f"| --- | --- | --- | --- |\n\n"
                f"## 7. Risk & Decision Log（风险与决策日志）\n"
                f"| 日期 | 类型 | 描述 | 决策 |\n"
                f"| --- | --- | --- | --- |\n\n"
                f"## 8. Handoff Notes（交接记录）\n"
                f"- current_state: {project_name} 项目于 {today_str} 完成了项目管理框架与变更自愈系统的初始化。\n\n"
                f"## 9. Spec Snapshot（规范快照）\n"
                f"| 序号 | 规范项 | 版本 | 状态 |\n"
                f"| --- | --- | --- | --- |\n"
            )
            write_file(session_path, session_template)
            log.info("已初始化 PM_SESSION: %s", session_path)

    # ── DB 缓存同步 ──────────────────────────────────────

    def sync_to_cache(self, force_full: bool = False) -> dict[str, Any]:
        """同步文件系统项目到 DB 缓存

        Args:
            force_full: True 强制全量扫描

        Returns:
            扫描结果 dict

        Raises:
            RuntimeError: 未注入 DatabaseManager
        """
        if self.db is None:
            raise RuntimeError("未注入 DatabaseManager，无法同步缓存")

        # 延迟导入避免循环依赖
        from auto_pm.change.change_service import ChangeService
        from auto_pm.db.sync import SyncService

        change_service = ChangeService(workspace_root=self.workspace_root, db=self.db)
        sync = SyncService(self.db, self, change_service=change_service)
        return cast(dict[str, Any], sync.sync(force_full=force_full))

    def get_last_sync_time(self) -> str:
        """获取上次同步时间（M3-Iter5：UI 层不再直接访问 Repository）

        Returns:
            格式化的同步时间 YYYY-MM-DD HH:MM，无记录或未注入 DB 时返回 '—'
        """
        if self.db is None:
            return "—"
        try:
            from auto_pm.db.repository import ScanLogRepository

            repo = ScanLogRepository(self.db)
            latest = repo.get_latest()
            if latest is None:
                return "—"
            timestamp = cast(str, latest.get("timestamp", ""))
            if not timestamp:
                return "—"
            # 截取 YYYY-MM-DD HH:MM 部分
            return timestamp[:16].replace("T", " ")
        except Exception as e:
            log.warning("获取上次同步时间失败: %s", e)
            return "—"

    def is_cache_available(self) -> bool:
        """DB 缓存是否可用（M3-Iter5：UI 层通过此方法判断而非直接访问 db 属性）"""
        return self.db is not None

    def clear_cache(self) -> dict[str, Any]:
        """清除 DB 缓存文件并重新初始化 schema

        删除 db 主文件及 -wal/-shm 侧车文件，然后重新 init_schema()。
        调用后 self._repo / self._repo_change 会基于新 db 重建。

        Windows 上 WAL 模式可能短暂持有 -wal/-shm 文件锁，
        因此先释放 Repository 引用并强制 GC 回收 sqlite3 连接，
        再重试删除；若仍失败则降级为 drop_all + init_schema。

        Returns:
            {"success": bool, "message": str}

        Raises:
            RuntimeError: 未注入 DatabaseManager
        """
        if self.db is None:
            raise RuntimeError("未注入 DatabaseManager，无法清除缓存")

        import gc
        import os
        import time

        db_path = self.get_db_path()

        # 1. 释放 Repository 引用，强制 GC 回收 sqlite3 连接（释放文件锁）
        self._repo = None
        self._repo_change = None
        gc.collect()

        # 2. 尝试删除 db 主文件及 -wal/-shm 侧车文件（重试 3 次）
        file_deleted = False
        for attempt in range(3):
            try:
                for suffix in ("", "-wal", "-shm"):
                    file_path = db_path + suffix
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                file_deleted = True
                break
            except PermissionError:
                # Windows 上文件被锁，等待后重试
                gc.collect()
                time.sleep(0.1 * (attempt + 1))

        # 3. 重新初始化 schema
        if hasattr(self.db, "init_schema"):
            self.db.init_schema()

        # 4. 重建 Repository
        self._repo = ProjectRepository(self.db)
        self._repo_change = ChangeRequestRepository(self.db)

        if file_deleted:
            msg = "缓存已清除并重新初始化"
        else:
            # 删除失败时已通过 init_schema() 重建（幂等，会保留旧数据）
            # 此处降级用 drop_all 清空数据
            if hasattr(self.db, "drop_all"):
                self.db.drop_all()
                if hasattr(self.db, "init_schema"):
                    self.db.init_schema()
            msg = "缓存已清空（DB 文件被锁，已通过 drop_all 清理数据）"

        log.info("DB 缓存已清除: %s (%s)", db_path, msg)
        return {"success": True, "message": msg}

    def _upsert_to_cache(self, proj: ProjectInfo) -> None:
        """将单个项目 UPSERT 到 DB 缓存"""
        if self._repo is None:
            return
        mtime = self._get_project_mtime(proj.path)
        # 优先使用 proj.business_line，为空时从 project_id 提取
        business_line = proj.business_line or extract_business_line(proj.project_id)
        extra = dict(proj.extra)
        for key, value in (
            ("project_type", proj.project_type),
            ("equipment_type", proj.equipment_type),
            ("plc_vendor", proj.plc_vendor),
            ("plc_model", proj.plc_model),
        ):
            if value:
                extra[key] = value
        record = ProjectRecord(
            project_id=proj.project_id,
            name=proj.name,
            path=proj.path,
            stack=proj.stack,
            version=proj.version,
            description=proj.description,
            source=proj.source,
            phase=proj.phase,
            business_line=business_line,
            project_type=proj.project_type,
            equipment_type=proj.equipment_type,
            plc_vendor=proj.plc_vendor,
            plc_model=proj.plc_model,
            extra=extra,
            file_mtime=mtime,
            last_scanned=datetime.now().isoformat(),
        )
        self._repo.upsert(record)

    @staticmethod
    def _record_to_info(record: ProjectRecord) -> ProjectInfo:
        """将 DB 记录转换为 ProjectInfo"""
        return ProjectInfo(
            project_id=record.project_id,
            name=record.name,
            path=record.path,
            stack=record.stack,
            version=record.version,
            description=record.description,
            source=record.source,
            phase=record.phase,
            business_line=record.business_line,
            project_type=record.project_type or str(record.extra.get("project_type", "")),
            equipment_type=record.equipment_type or str(record.extra.get("equipment_type", "")),
            plc_vendor=record.plc_vendor or str(record.extra.get("plc_vendor", "")),
            plc_model=record.plc_model or str(record.extra.get("plc_model", "")),
            extra=record.extra,
            file_mtime=record.file_mtime,
        )

    # ── 向后兼容的委托方法（M3-Iter1 保留签名，内部委托给 scanner） ──

    def _try_identify_project(self, project_path: str) -> ProjectInfo | None:
        """[已委托] 尝试识别目录是否为项目（向后兼容包装）"""
        return self._scanner.try_identify_project(project_path)

    def _read_copier_answers(self, project_path: str) -> ProjectInfo | None:
        """[已委托] 从 .copier-answers.yml 读取项目元数据（向后兼容包装）"""
        return self._scanner.read_copier_answers(project_path)

    def _read_plc_json(self, project_path: str) -> ProjectInfo | None:
        """[已委托] 从 .plc.json 读取项目元数据（向后兼容包装）"""
        return self._scanner.read_plc_json(project_path)

    def _read_pm_session(self, project_path: str) -> ProjectInfo | None:
        """[已委托] 从 PM_SESSION_*.md 文件名提取项目编号（向后兼容包装）"""
        return self._scanner.read_pm_session(project_path)

    @staticmethod
    def _extract_id_from_dirname(project_path: str) -> str:
        """[已委托] 从目录名提取项目编号（向后兼容包装）"""
        return cast(str, ProjectScanner.extract_id_from_dirname(project_path))

    @staticmethod
    def _infer_stack(src_path: str) -> str:
        """[已委托] 根据模板源路径推断技术栈（向后兼容包装）"""
        return cast(str, ProjectScanner.infer_stack(src_path))

    @staticmethod
    def _get_project_mtime(project_path: str) -> float:
        """[已委托] 获取项目标志文件的 mtime（向后兼容包装）"""
        return cast(float, ProjectScanner.get_project_mtime(project_path))

    def is_git_hooks_installed(self, project_path: str) -> bool:
        """检查指定项目是否已安装 auto-pm Git 提交门禁钩子"""
        hook_path = os.path.join(project_path, ".git", "hooks", "pre-commit")
        if not os.path.isfile(hook_path):
            return False
        try:
            with open(hook_path, encoding="utf-8") as f:
                content = f.read()
            return "auto-pm pre-commit" in content
        except Exception:
            return False

    def install_git_hooks(self, project_path: str) -> dict[str, Any]:
        """为指定项目安装离线 Git Pre-commit 提交门禁与自愈钩子"""
        if not os.path.isdir(project_path):
            return {"success": False, "message": f"项目目录不存在: {project_path}"}

        git_dir = os.path.join(project_path, ".git")
        if not os.path.isdir(git_dir):
            return {"success": False, "message": "项目未初始化 Git 仓库，无法安装门禁"}

        hooks_dir = os.path.join(git_dir, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)
        hook_path = os.path.join(hooks_dir, "pre-commit")

        hook_content = """#!/bin/sh
# auto-pm pre-commit hook (automatically installed)
PROJECT_ROOT=$(git rev-parse --show-toplevel)
VENV_DIR=""
CUR_DIR="$PROJECT_ROOT"
while [ "$CUR_DIR" != "/" ] && [ -n "$CUR_DIR" ]; do
    if [ -d "$CUR_DIR/.venv" ]; then
        VENV_DIR="$CUR_DIR/.venv"
        break
    fi
    if [ "$CUR_DIR" = "C:" ] || [ "$CUR_DIR" = "c:" ] || [ "$CUR_DIR" = "D:" ] || [ "$CUR_DIR" = "d:" ]; then
        break
    fi
    PARENT_DIR=$(dirname "$CUR_DIR")
    if [ "$PARENT_DIR" = "$CUR_DIR" ]; then
        break
    fi
    CUR_DIR="$PARENT_DIR"
done

if [ -z "$VENV_DIR" ]; then
    echo "⚠️ [auto-pm pre-commit] 警告: 未找到虚拟环境 .venv，跳过门禁检查！"
    exit 0
fi

if [ -f "$VENV_DIR/Scripts/python" ]; then
    PYTHON_EXE="$VENV_DIR/Scripts/python"
    RUFF_EXE="$VENV_DIR/Scripts/ruff"
    MYPY_EXE="$VENV_DIR/Scripts/mypy"
    PYTEST_EXE="$VENV_DIR/Scripts/pytest"
elif [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    PYTHON_EXE="$VENV_DIR/Scripts/python.exe"
    RUFF_EXE="$VENV_DIR/Scripts/ruff.exe"
    MYPY_EXE="$VENV_DIR/Scripts/mypy.exe"
    PYTEST_EXE="$VENV_DIR/Scripts/pytest.exe"
else
    PYTHON_EXE="$VENV_DIR/bin/python"
    RUFF_EXE="$VENV_DIR/bin/ruff"
    MYPY_EXE="$VENV_DIR/bin/mypy"
    PYTEST_EXE="$VENV_DIR/bin/pytest"
fi

echo "🔍 [auto-pm pre-commit] 正在执行本地增量门禁与自愈检查..."
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\\\\.py$')

if [ -z "$STAGED_FILES" ]; then
    echo "✅ [auto-pm pre-commit] 没有检测到 staged Python 文件，跳过检查。"
    exit 0
fi

if [ -f "$RUFF_EXE" ]; then
    echo "⚡ [auto-pm pre-commit] 运行 ruff check --fix 自愈..."
    "$RUFF_EXE" check --fix $STAGED_FILES
    RUFF_EXIT=$?
    git add $STAGED_FILES

    echo "⚡ [auto-pm pre-commit] 运行 ruff format..."
    "$RUFF_EXE" format $STAGED_FILES
    git add $STAGED_FILES

    if [ $RUFF_EXIT -ne 0 ]; then
        echo "❌ [auto-pm pre-commit] 错误: Ruff 静态检查未通过，请手动修复上述报错！"
        exit 1
    fi
else
    echo "⚠️ [auto-pm pre-commit] 警告: 未在虚拟环境中找到 ruff，跳过代码质量检查！"
fi

if [ -f "$MYPY_EXE" ]; then
    echo "⚡ [auto-pm pre-commit] 运行 mypy 类型检查..."
    "$MYPY_EXE" --ignore-missing-imports $STAGED_FILES
    if [ $? -ne 0 ]; then
        echo "❌ [auto-pm pre-commit] 错误: Mypy 类型校验失败，拒绝提交！"
        exit 1
    fi
else
    echo "⚠️ [auto-pm pre-commit] 警告: 未在虚拟环境中找到 mypy，跳过类型校验！"
fi

if [ -f "$PYTEST_EXE" ]; then
    echo "⚡ [auto-pm pre-commit] 运行 pytest 全量测试..."
    "$PYTEST_EXE" --no-cov -q
    if [ $? -ne 0 ]; then
        echo "❌ [auto-pm pre-commit] 错误: pytest 单元测试失败，拒绝提交！"
        exit 1
    fi
else
    echo "⚠️ [auto-pm pre-commit] 警告: 未在虚拟环境中找到 pytest，跳过单元测试回归！"
fi

echo "✅ [auto-pm pre-commit] 门禁与自愈检查全部通过，允许提交！"
exit 0
"""

        try:
            with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(hook_content)

            # 设置可执行权限
            try:
                import stat

                os.chmod(
                    hook_path,
                    os.stat(hook_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH,
                )
            except Exception as e:
                log.warning("设置钩子可执行权限失败: %s", e)

            log.info("项目已安装 Git 提交门禁钩子: %s", hook_path)
            return {"success": True, "message": "Git 提交门禁钩子安装成功"}
        except Exception as e:
            log.error("安装 Git 提交门禁钩子失败: %s", e)
            return {"success": False, "message": f"安装钩子失败: {e}"}

    def uninstall_git_hooks(self, project_path: str) -> dict[str, Any]:
        """为指定项目卸载 Git Pre-commit 提交门禁钩子"""
        hook_path = os.path.join(project_path, ".git", "hooks", "pre-commit")
        if not os.path.isfile(hook_path):
            return {"success": True, "message": "钩子不存在，无需卸载"}

        try:
            # 校验是否是 auto-pm 的钩子
            with open(hook_path, encoding="utf-8") as f:
                content = f.read()
            if "auto-pm pre-commit" in content:
                os.remove(hook_path)
                log.info("项目已卸载 Git 提交门禁钩子: %s", hook_path)
                return {"success": True, "message": "Git 提交门禁钩子卸载成功"}
            else:
                return {
                    "success": False,
                    "message": "检测到非 auto-pm 拥有的 pre-commit 钩子，已安全跳过以防覆盖",
                }
        except Exception as e:
            log.error("卸载 Git 提交门禁钩子失败: %s", e)
            return {"success": False, "message": f"卸载钩子失败: {e}"}
