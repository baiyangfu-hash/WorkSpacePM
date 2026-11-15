"""PLC-HMI 概念映射：SFB 库函数（项目扫描器（递归扫描工作空间发现项目））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

项目扫描器 - 递归扫描工作空间，识别项目

从 ProjectService 提取的单一职责模块，负责：
- 递归扫描目录
- 识别项目（.copier-answers.yml / .plc.json / PM_SESSION_*.md）
- 读取项目元数据

ProjectService 通过组合方式使用本模块，保持向后兼容。
"""

from __future__ import annotations

import json
import logging
import os
import re

import yaml
from pydantic import ValidationError

from auto_pm.application.core.asset_summary_service import AssetSummaryService
from auto_pm.domain.models import ProjectInfo
from auto_pm.domain.models.enums import Stack
from auto_pm.domain.models.project import VALID_BUSINESS_LINES, extract_business_line

log = logging.getLogger(__name__)


def first_problem(error: ValidationError) -> str:
    """一句人话：哪个字段、什么问题（不带 pydantic 的整页栈）。"""

    details = error.errors()
    if not details:
        return "元数据无效"
    field = ".".join(str(part) for part in details[0]["loc"]) or "?"
    return f"字段 {field} 的值无效（{details[0]['msg']}）"



def scan_skips_folder(name: str) -> bool:
    """扫描器跳过的文件夹名：以 . 或 _ 开头，或名字里带“归档”、archive、trash（不分大小写）。"""

    return name.startswith((".", "_")) or "归档" in name or "archive" in name.lower() or "trash" in name.lower()


def unfindable_project_folder(name: str) -> str:
    """项目文件夹叫这个名字时建得出来却找不到的原因；名字没问题返回空串（TD-SW008-619，D-354）。

    扫描器跳过上面那几类名字，登记表还拒绝路径里带 backup、备份 的（``WorkspaceRegistryService``），
    这样的项目 project register、show、archive 都找不到，所以 project create、project import 先拒绝。
    """

    folded = name.casefold()
    if scan_skips_folder(name) or "backup" in folded or "备份" in name:
        return (
            f"项目文件夹名 {name} 以 . 或 _ 开头，或带“归档”“备份”、archive、trash、backup 这类字样，"
            "扫描和登记都会跳过它，建出来也找不到；换个名字"
        )
    return ""

class ProjectScanner:
    """项目扫描器 - 递归扫描工作空间，识别项目"""

    # 项目识别标志文件
    COPIER_ANSWERS_FILE = ".copier-answers.yml"
    PLC_JSON_FILE = ".plc.json"
    PM_SESSION_PREFIX = "PM_SESSION_"

    # 项目编号正则：SW-2026-001, DJ-2026-010 等格式（前缀 2-4 位大写字母）
    _PROJECT_ID_RE = re.compile(r"^([A-Z]{2,4}-\d{4}-\d{3})")

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self._asset_summary_service = AssetSummaryService()
        # 扫描时因元数据无效被跳过的目录：(目录, 一句话原因)。写入口（如登记）据此给出准确的人话。
        self.skipped_invalid: list[tuple[str, str]] = []

    # 来源优先级（数值越小优先级越高）
    _SOURCE_PRIORITY: dict[str, int] = {
        "copier": 0,
        "plc_json": 1,
        "pm_session": 2,
        "dirname": 3,
    }

    def scan(self, scan_depth: int = 4) -> list[ProjectInfo]:
        """扫描工作空间，返回所有项目

        Args:
            scan_depth: 最大扫描深度（默认4层）

        Returns:
            项目列表，按 project_id 排序

        V0.2.1-P2-1: 按项目根目录 + project_id 双重去重，
        合并多来源元数据（copier > plc_json > pm_session）。
        """
        raw_results: list[ProjectInfo] = []
        # Check workspace root itself (auto-pm project itself)
        try:
            root_info = self.try_identify_project(self.workspace_root)
        except ValidationError as error:
            log.warning("跳过元数据无效的工作区根项目: %s", first_problem(error))
            root_info = None
        if root_info is not None:
            raw_results.append(root_info)
        self._scan(self.workspace_root, raw_results, depth=0, max_depth=scan_depth)
        # V0.2.1-P2-1: 去重 + 合并多来源元数据
        results = self._deduplicate_projects(raw_results)
        results.sort(key=lambda p: p.project_id)
        log.info(
            "扫描完成: 发现 %d 个项目（去重前 %d）",
            len(results), len(raw_results),
        )
        return results

    def _deduplicate_projects(
        self, projects: list[ProjectInfo]
    ) -> list[ProjectInfo]:
        """按项目根目录 + project_id 双重去重，合并多来源元数据

        策略：
        1. 按项目根目录分组：同一目录被多来源识别时，保留优先级最高的来源，
           并合并其他来源的非空字段。
        2. 按 project_id 分组：不同目录但相同 project_id 时（如嵌套子目录被
           误识别为独立项目），保留来源优先级更高的记录。
        """
        # ── 第1步：按项目根目录去重 ──
        by_path: dict[str, list[ProjectInfo]] = {}
        for p in projects:
            by_path.setdefault(p.path, []).append(p)

        path_deduped: list[ProjectInfo] = []
        for _path, group in by_path.items():
            # 按来源优先级排序
            group.sort(
                key=lambda p: self._SOURCE_PRIORITY.get(p.source, 99)
            )
            primary = group[0]
            # 合并其他来源的非空字段（仅当 primary 字段为空时）
            for other in group[1:]:
                if not primary.name and other.name:
                    primary.name = other.name
                if not primary.version and other.version:
                    primary.version = other.version
                if not primary.description and other.description:
                    primary.description = other.description
                if not primary.phase and other.phase:
                    primary.phase = other.phase
                if not primary.business_line and other.business_line:
                    primary.business_line = other.business_line
                if not primary.project_type and other.project_type:
                    primary.project_type = other.project_type
                if not primary.equipment_type and other.equipment_type:
                    primary.equipment_type = other.equipment_type
                if not primary.plc_vendor and other.plc_vendor:
                    primary.plc_vendor = other.plc_vendor
                if not primary.plc_model and other.plc_model:
                    primary.plc_model = other.plc_model
                if primary.stack == "unknown" and other.stack != "unknown":
                    primary.stack = other.stack
            path_deduped.append(primary)

        # ── 第2步：按 project_id 去重 ──
        by_id: dict[str, ProjectInfo] = {}
        for p in path_deduped:
            if p.project_id in by_id:
                existing = by_id[p.project_id]
                existing_pri = self._SOURCE_PRIORITY.get(existing.source, 99)
                current_pri = self._SOURCE_PRIORITY.get(p.source, 99)
                if current_pri < existing_pri:
                    log.debug(
                        "项目重复（按 project_id=%s）: 保留 %s@%s, 跳过 %s@%s",
                        p.project_id, p.source, p.path,
                        existing.source, existing.path,
                    )
                    by_id[p.project_id] = p
                else:
                    log.debug(
                        "项目重复（按 project_id=%s）: 保留 %s@%s, 跳过 %s@%s",
                        p.project_id, existing.source, existing.path,
                        p.source, p.path,
                    )
            else:
                by_id[p.project_id] = p

        return list(by_id.values())

    def try_identify_project(self, project_path: str) -> ProjectInfo | None:
        r"""尝试识别目录是否为项目，并提取元数据

        优先级：.copier-answers.yml > .plc.json > PM_SESSION_*.md > 目录名

        V0.2.1-P2-11: 当项目通过 PM_SESSION 识别但 stack=unknown 时，
        递归查找子目录的 .plc.json 补充元数据（适配 02_PLC程序/PLC_ST/.plc.json 嵌套结构）。

        V0.5.3 Fix 2: 当所有识别手段都无法确定 stack 时，根据项目路径兜底推断
        （路径含 `01_Project自动化项目管理\Python自动化项目总库\` → python；
         路径含 `0100_PLC自动化\` → plc；其他 → unknown）。
        """
        # 1. Copier 答案文件（最可靠）
        info = self.read_copier_answers(project_path)
        if info is not None:
            info.file_mtime = self.get_project_mtime(project_path)
            self._apply_stack_fallback(info)
            return info

        # 2. .plc.json（PLC 项目，仅检查根目录）
        info = self.read_plc_json(project_path)
        if info is not None:
            info.file_mtime = self.get_project_mtime(project_path)
            self._apply_stack_fallback(info)
            return info

        # 3. PM_SESSION_*.md
        info = self.read_pm_session(project_path)
        if info is not None:
            info.file_mtime = self.get_project_mtime(project_path)
            # V0.2.1-P2-11: 递归查找 .plc.json 补充元数据
            info = self._enrich_from_plc_json(info)
            # V0.5.3 Fix 2: 仍为 unknown 时按路径兜底推断
            self._apply_stack_fallback(info)
            return info

        return None

    def _apply_stack_fallback(self, info: ProjectInfo) -> None:
        """V0.5.3 Fix 2: stack 兜底推断

        当 ProjectInfo.stack 仍为 "unknown" 时，根据项目路径推断 stack：
        - 路径含 `01_Project自动化项目管理\\Python自动化项目总库\\` → "python"
        - 路径含 `0100_PLC自动化\\` → "plc"
        - 其他 → 保持 "unknown"

        Args:
            info: ProjectInfo 原地修改（仅在 stack=unknown 时生效）
        """
        if info.stack != "unknown":
            return
        inferred = self._infer_stack_from_path(info.path)
        if inferred != "unknown":
            info.stack = inferred

    @staticmethod
    def _infer_stack_from_path(project_path: str) -> Stack:
        """V0.5.3 Fix 2: 从项目路径推断 stack

        依赖工作空间目录结构稳定：
        - `01_Project自动化项目管理\\Python自动化项目总库\\` → "python"
        - `0100_PLC自动化\\` → "plc"
        - 其他 → "unknown"（如 SYS-2026-001 跨域项目）

        Args:
            project_path: 项目绝对路径

        Returns:
            推断的 stack 值（"python" / "plc" / "unknown"）
        """
        # 两种分隔符都统一为 "/"：Windows 写下的反斜杠路径在 Linux 上也要能识别
        norm_path = project_path.replace("\\", "/")
        if "01_Project自动化项目管理/Python自动化项目总库/" in norm_path:
            return "python"
        if "0100_PLC自动化/" in norm_path:
            return "plc"
        return "unknown"

    def read_copier_answers(self, project_path: str) -> ProjectInfo | None:
        """从 .copier-answers.yml 读取项目元数据

        V0.3.0-M0.5-Phase1: 修复元数据契约不一致问题。
        - description: 兼容 project_description（copier-python-template 标准）和 description
        - version: 优先从 answers 读取，回退到 pyproject.toml [project].version
        - phase: 只从 answers 读取（CHG-SCPT-2026-650：PM_SESSION 已退役，不再从它推阶段；项目状态看工作区登记表）
        """
        answers_path = os.path.join(project_path, self.COPIER_ANSWERS_FILE)
        if not os.path.isfile(answers_path):
            return None

        try:
            with open(answers_path, encoding="utf-8") as f:
                answers = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as e:
            log.warning("读取 .copier-answers.yml 失败: %s: %s", project_path, e)
            return None

        project_id = answers.get("project_id", "")
        project_name = answers.get("project_name", "")

        # project_id 为空时，从目录名提取编号（如 SW-2026-008）
        if not project_id:
            project_id = self.extract_id_from_dirname(project_path)

        # V0.2.1-P1-3: 优先从 answers 读取 stack，回退到从 _src_path 推断
        stack = answers.get("stack", "")
        if not stack:
            src_path = answers.get("_src_path", "")
            stack = self.infer_stack(src_path)

        # 业务线：优先从 answers 读取，否则从 project_id 提取。
        # answers 里写了白名单以外的值（如旧版 project create 把编号前缀 ZZ 原样写进来）时不能让整个扫描崩：
        # 退回按编号提取，原值仍留在 info.extra["business_line"]，由登记等写入口决定是否拒绝（D2）。
        business_line = answers.get("business_line", "") or extract_business_line(project_id)
        if business_line and business_line not in VALID_BUSINESS_LINES:
            log.warning(
                "项目 %s 的 business_line=%r 不在白名单（%s），按编号前缀推断",
                project_id or project_path, business_line, "/".join(VALID_BUSINESS_LINES),
            )
            business_line = extract_business_line(project_id)
        # V0.3.7: 防 None（copier 模板未填字段会写 null，Pydantic str 字段拒绝 None）
        project_type = answers.get("project_type", "") or ""
        equipment_type = answers.get("equipment_type", "") or ""
        plc_vendor = answers.get("plc_vendor", "") or ""
        plc_model = answers.get("plc_model", "") or ""

        # V0.3.0-M0.5-Phase1: description 兼容 project_description（copier-python-template 标准）
        description = answers.get("project_description", "") or answers.get("description", "") or ""

        # V0.3.0-M0.5-Phase1: version 回退到 pyproject.toml
        version = answers.get("version", "") or ""
        if not version:
            version = self._read_version_from_pyproject(project_path)

        phase = answers.get("phase", "") or ""

        extra = dict(answers)
        info = ProjectInfo(
            project_id=project_id,
            name=project_name or answers.get("project_name", "") or os.path.basename(project_path),
            path=project_path,
            stack=stack,
            version=version,
            description=description,
            phase=phase,
            business_line=business_line,
            project_type=project_type,
            equipment_type=equipment_type,
            plc_vendor=plc_vendor,
            plc_model=plc_model,
            source="copier",
            extra=extra,
        )
        self._attach_asset_summary(info)
        return info

    def _read_version_from_pyproject(self, project_path: str) -> str:
        """从 pyproject.toml 读取版本号（Python 项目回退策略）"""
        pyproject_path = os.path.join(project_path, "pyproject.toml")
        if not os.path.isfile(pyproject_path):
            return ""
        try:
            with open(pyproject_path, encoding="utf-8") as f:
                content = f.read()
            # 简单正则提取 [project].version，避免引入 tomli 依赖
            match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            return match.group(1) if match else ""
        except OSError:
            return ""

    def read_plc_json(self, project_path: str) -> ProjectInfo | None:
        """从 .plc.json 读取项目元数据（仅检查项目根目录，用于项目识别）

        注意：递归查找 .plc.json 仅在 _enrich_from_plc_json 中使用，
        用于补充已识别项目的元数据，避免父目录被误识别为项目。
        """
        plc_json_path = os.path.join(project_path, self.PLC_JSON_FILE)
        if not os.path.isfile(plc_json_path):
            return None

        try:
            with open(plc_json_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("读取 .plc.json 失败: %s: %s", project_path, e)
            return None

        name = cfg.get("name", "")
        info = ProjectInfo(
            project_id=name or os.path.basename(project_path),
            name=name or os.path.basename(project_path),
            path=project_path,
            stack="plc",
            version=cfg.get("version", ""),
            description=cfg.get("description", ""),
            phase=cfg.get("phase", ""),
            project_type=cfg.get("project_type", ""),
            equipment_type=cfg.get("equipment_type", ""),
            plc_vendor=cfg.get("plc_vendor", ""),
            plc_model=cfg.get("plc_model", ""),
            source="plc_json",
            extra=dict(cfg),
        )
        self._attach_asset_summary(info)
        return info

    def _enrich_from_plc_json(self, info: ProjectInfo) -> ProjectInfo:
        """递归查找 .plc.json 补充项目元数据（不用于项目识别）

        V0.2.1-P2-11: 适配 02_PLC程序/PLC_ST/.plc.json 嵌套结构。
        当项目通过 PM_SESSION 或 copier 识别但 stack=unknown 时，
        递归查找子目录的 .plc.json 来补充 stack/version/description 等字段。

        Args:
            info: 已识别的项目信息（通常 source=pm_session, stack=unknown）

        Returns:
            补充后的项目信息（原地修改并返回）
        """
        plc_json_path = self._find_plc_json_recursive(info.path)
        if not plc_json_path:
            return info

        try:
            with open(plc_json_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            return info

        # .plc.json 为 PLC 项目版本真源
        if info.stack == "unknown":
            info.stack = "plc"
        if cfg.get("version"):
            info.version = cfg.get("version", "")
        if not info.description:
            info.description = cfg.get("description", "")
        if not info.project_type:
            info.project_type = cfg.get("project_type", "")
        if not info.equipment_type:
            info.equipment_type = cfg.get("equipment_type", "")
        if not info.plc_vendor:
            info.plc_vendor = cfg.get("plc_vendor", "")
        if not info.plc_model:
            info.plc_model = cfg.get("plc_model", "")
        # 如果 project_id 来自 PM_SESSION 但 .plc.json 有更准确的 name，使用 .plc.json 的 name
        plc_name = cfg.get("name", "")
        if plc_name and info.name == os.path.basename(info.path):
            info.name = plc_name
        self._attach_asset_summary(info)
        return info

    def _attach_asset_summary(self, info: ProjectInfo) -> None:
        """向项目信息附加工程资产摘要"""
        extra = dict(info.extra)
        extra["asset_summary"] = self._asset_summary_service.build_summary(
            project_path=info.path,
            stack=info.stack,
            project_type=info.project_type,
        )
        info.extra = extra

    # Python 仓库的标志文件（TD-SW008-563）
    PYTHON_MARKER_FILES = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    _SKIP_DIRS = frozenset({".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".auto-pm"})

    @staticmethod
    def looks_like_python_repo(project_path: str, max_depth: int = 2) -> bool:
        """目录看起来是不是 Python 仓库（TD-SW008-563）：有 pyproject/setup/requirements，或前两层里有 .py 文件"""
        if any(os.path.isfile(os.path.join(project_path, name)) for name in ProjectScanner.PYTHON_MARKER_FILES):
            return True

        def _has_py(dir_path: str, depth: int) -> bool:
            try:
                entries = sorted(os.listdir(dir_path))
            except OSError:
                return False
            for entry in entries:
                entry_path = os.path.join(dir_path, entry)
                if entry.endswith(".py") and os.path.isfile(entry_path):
                    return True
            if depth >= max_depth:
                return False
            return any(
                _has_py(os.path.join(dir_path, e), depth + 1)
                for e in entries
                if e not in ProjectScanner._SKIP_DIRS and os.path.isdir(os.path.join(dir_path, e))
            )

        return _has_py(project_path, 1)

    @staticmethod
    def _find_plc_json_recursive(project_path: str, max_depth: int = 3) -> str | None:
        """递归查找 .plc.json（仅用于补充元数据，不用于项目识别）

        查找顺序：
        1. 项目根目录
        2. 子目录递归查找（适配 02_PLC程序/PLC_ST/.plc.json 嵌套结构）

        Args:
            project_path: 项目根目录
            max_depth: 最大递归深度（默认3层）

        Returns:
            .plc.json 绝对路径，未找到返回 None
        """
        # 1. 根目录
        root_plc_json = os.path.join(project_path, ProjectScanner.PLC_JSON_FILE)
        if os.path.isfile(root_plc_json):
            return root_plc_json

        # 2. 递归查找子目录
        def _search_dir(dir_path: str, depth: int) -> str | None:
            if depth > max_depth:
                return None
            try:
                entries = os.listdir(dir_path)
            except OSError:
                return None
            for entry in entries:
                entry_path = os.path.join(dir_path, entry)
                # 注意：不能跳过 .plc.json（它以 . 开头）
                if os.path.isfile(entry_path) and entry == ProjectScanner.PLC_JSON_FILE:
                    return entry_path
                # 跳过隐藏目录和 Python 缓存目录（但保留 .plc.json 等配置文件）
                if entry.startswith(".") or entry.startswith("__"):
                    continue
                if os.path.isdir(entry_path):
                    found = _search_dir(entry_path, depth + 1)
                    if found:
                        return found
            return None

        return _search_dir(project_path, 1)

    def read_pm_session(self, project_path: str) -> ProjectInfo | None:
        """从 PM_SESSION_*.md 的文件名提取项目编号（只作识别锚点）

        CHG-SCPT-2026-650：不再从 PM_SESSION 内容推阶段（PM_SESSION 已于 2026-10-10 退役，推出来的 developing
        不是真状态）；phase 留空，项目状态以工作区登记表为准。
        """
        try:
            entries = os.listdir(project_path)
        except OSError:
            return None

        for entry in entries:
            if entry.startswith(self.PM_SESSION_PREFIX) and entry.endswith(".md"):
                # PM_SESSION_DJ-2026-010.md -> DJ-2026-010
                project_id = entry[len(self.PM_SESSION_PREFIX) : -len(".md")]
                return ProjectInfo(
                    project_id=project_id,
                    name=os.path.basename(project_path),
                    path=project_path,
                    stack="unknown",
                    source="pm_session",
                )
        return None

    @staticmethod
    def extract_id_from_dirname(project_path: str) -> str:
        """从目录名提取项目编号（如 SW-2026-008）"""
        dirname = os.path.basename(project_path)
        m = ProjectScanner._PROJECT_ID_RE.match(dirname)
        return m.group(1) if m else dirname

    @staticmethod
    def infer_stack(src_path: str) -> str:
        """根据模板源路径推断技术栈"""
        src_lower = src_path.lower()
        if "plc" in src_lower:
            return "plc"
        if "python" in src_lower:
            return "python"
        return "unknown"

    @staticmethod
    def get_project_mtime(project_path: str) -> float:
        """获取项目标志文件的 mtime（增量扫描判据）"""
        mtime = 0.0
        for marker in (".copier-answers.yml", ".plc.json"):
            path = os.path.join(project_path, marker)
            if os.path.isfile(path):
                mtime = max(mtime, os.path.getmtime(path))
        try:
            for entry in os.listdir(project_path):
                if entry.startswith("PM_SESSION_") and entry.endswith(".md"):
                    path = os.path.join(project_path, entry)
                    mtime = max(mtime, os.path.getmtime(path))
        except OSError:
            pass
        return mtime

    def _scan(
        self,
        path: str,
        results: list[ProjectInfo],
        depth: int,
        max_depth: int,
    ) -> None:
        """递归扫描目录，识别项目"""
        if depth > max_depth:
            return

        try:
            entries = os.listdir(path)
        except OSError:
            return

        for entry in entries:
            entry_path = os.path.join(path, entry)
            if not os.path.isdir(entry_path):
                continue
            if scan_skips_folder(entry):
                continue

            # 判断是否是项目目录；一个项目的元数据坏了只跳过它，不能拖垮整个工作区的扫描（D2）
            try:
                info = self.try_identify_project(entry_path)
            except ValidationError as error:
                problem = first_problem(error)
                log.warning("跳过元数据无效的项目目录 %s: %s", entry_path, problem)
                self.skipped_invalid.append((entry_path, problem))
                continue
            if info is not None:
                results.append(info)
            else:
                # 非项目目录，继续递归
                self._scan(entry_path, results, depth + 1, max_depth)
