"""PLC-HMI 概念映射：SFB 库函数（PLC 检查器（验证 PLC 项目结构完整性））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

PLC 项目结构检查器（LSP-907 907_项目配置规范_LSP）

迁移自 SW-2026-005 的 PlcProjectService.check_project/check_workspace。
检查项：.plc.json / PM_SESSION / PRD 文档 / 目录结构 / Spec Snapshot 规范漂移。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import cast

from auto_pm.core.paths import find_prd_dir
from auto_pm.models.enums import ProjectType
from auto_pm.plc.models import (
    _LEGACY_PROJECT_INIT_PLC_PATH,
    FB_PRD_SCAN_DIR,
    FB_PRD_SKIP_DIRS,
    FB_PRDS,
    NAMING_RULES,
    PM_DIR_CANDIDATES,
    REQUIRED_PLC_JSON_FIELDS,
    SKIP_PLC_JSON_TYPES,
    STD_DIRS,
    STD_PRDS,
    CheckResult,
)
from auto_pm.plc.scl_linter import SclLinter
from auto_pm.plc.spec_snapshot import (
    compare_versions,
    load_spec_registry,
    parse_spec_snapshot,
)

log = logging.getLogger(__name__)

# SysLib 关键文件清单（相对路径），用于 libraries 路径深度校验
_KEY_FILES = [
    "timer/FB_TON.scl",
    "counter/FB_CTD.scl",
    "counter/FB_CTU.scl",
    "edge/FB_R_TRIG.scl",
    "edge/FB_F_TRIG.scl",
]

# 真实历史 PLC 项目中常见的 PRD 文档落点。
# 仅在这些已知目录中做兼容识别，避免把任意散落文档误判为标准 PRD。
_LEGACY_PRD_DIRS = [
    os.path.join(*_LEGACY_PROJECT_INIT_PLC_PATH),
    "01_需求与设计",
    "01_需求与设计/13_软件方案",
    "02_PLC程序/PLC_ST/PRD",
    "02_PLC程序/程序文档",
]


class _LegacyPlcCheckerCore:
    """PLC 项目结构检查器遗留核心实现。"""

    # ── 检查项清单（静态定义，供 --list 使用） ──────────────

    CHECK_ITEMS: list[dict[str, str]] = [
        {
            "id": "1",
            "category": "配置",
            "item": ".plc.json",
            "description": "检查 .plc.json 配置文件存在性、JSON 格式有效性、必填字段完整性（name/description/version）",
            "spec": "LSP-907 §1.1",
        },
        {
            "id": "2",
            "category": "配置",
            "item": ".plc.json libraries",
            "description": "检查 libraries 字段是否配置，库路径是否存在，关键文件（timer/counter/edge）是否完整",
            "spec": "LSP-907 §1.2",
        },
        {
            "id": "3",
            "category": "文档",
            "item": "PM_SESSION",
            "description": "检查 PM_SESSION_<项目编号>.md 是否存在，文件名是否与项目编号匹配",
            "spec": "PM-042",
        },
        {
            "id": "4",
            "category": "文档",
            "item": "PM_SESSION 行数",
            "description": "检查 PM_SESSION 行数是否超过阈值（>150 行 warn，>300 行 fail），建议归档",
            "spec": "PM-042 双层结构",
        },
        {
            "id": "5",
            "category": "文档",
            "item": "PRD 目录",
            "description": "检查 PRD/（或 00_程序方案/）目录是否存在，兼容历史文档目录（01_需求与设计、02_PLC程序/PLC_ST/PRD 等）",
            "spec": "LSP-907 §2",
        },
        {
            "id": "6",
            "category": "文档",
            "item": "PRD 四件套",
            "description": "检查 PRD 目录下需求分析文档_REQ.md、接口文档_INT.md、详细设计说明书_DSN.md、技术方案文档_TEC.md 四件套是否齐全",
            "spec": "LSP-907 §2.1",
        },
        {
            "id": "7",
            "category": "文档",
            "item": "PRD 内容质量",
            "description": "深度校验 FB 模块 PRD 内容质量：关联源码路径有效性、文档版本与项目主版本滞后检测（≥2 个大版本 warn）",
            "spec": "CHG-SCPT-2026-153",
        },
        {
            "id": "8",
            "category": "文档",
            "item": "FB PRD 四件套",
            "description": "检查每个 FB 模块的 PRD/ 子目录下接口文档_IFC-*.md、详细设计说明书_DSN-*.md、变更记录_CHG-*.md、使用说明_UM-*.md 四件套是否齐全",
            "spec": "CHG-SCPT-2026-153",
        },
        {
            "id": "9",
            "category": "结构",
            "item": "标准目录",
            "description": "检查 12 个标准目录是否存在（01_启动/00_项目管理、01_需求与设计、02_PLC程序、03_HMI设计、04_现场调试、04_驱动器与设备、05_测试与验证、06_文档与交付、07_技术支持、08_备件管理、09_项目总结、10_知识库）",
            "spec": "LSP-907 §3.1",
        },
        {
            "id": "10",
            "category": "规范",
            "item": "Spec Snapshot",
            "description": "检查 PM_SESSION 中的 Spec Snapshot 表格与 spec_registry.json 是否一致，检测主版本/次版本/补丁版本漂移",
            "spec": "V2.0.3",
        },
    ]

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)

    # ── 单项目检查 ────────────────────────────────────────

    def check_project(self, project_path: str) -> CheckResult:
        """检查项目结构是否符合 LSP-907 规范

        Args:
            project_path: 项目根目录绝对路径

        Returns:
            CheckResult: 检查结果，包含所有检查项及其状态

        V0.4.1 Step 3: Python 项目（无 .plc.json + 有 pyproject.toml）直接返回
        not_applicable=True 的 CheckResult，不跑 5 项检查；规则与 _is_project_dir
        的 pyproject.toml 排除逻辑保持一致，避免 --all 模式与单项目模式行为分歧。
        """
        result = CheckResult(project_path=project_path)

        # V0.4.1 Step 3: Python 项目不适用 PLC 检查
        if not self._find_plc_json(project_path):
            if os.path.isfile(os.path.join(project_path, "pyproject.toml")):
                result.not_applicable = True
                result.not_applicable_reason = (
                    "Python 项目（无 .plc.json + 有 pyproject.toml），PLC 检查不适用"
                )
                log.info(
                    "Python 项目跳过 PLC 检查（not_applicable=True）: %s",
                    os.path.basename(project_path),
                )
                return result
            # V0.5.4: 位于 Python 项目管理区域且无 .plc.json 的遗留项目，PLC 检查不适用
            if self._is_in_python_area(project_path):
                result.not_applicable = True
                result.not_applicable_reason = (
                    "Python 区域遗留项目（无 .plc.json），PLC 检查不适用"
                )
                log.info(
                    "Python 区域遗留项目跳过 PLC 检查（not_applicable=True）: %s",
                    os.path.basename(project_path),
                )
                return result

        # 检测项目类型
        project_type = self._detect_project_type(project_path)
        result.project_type = cast(ProjectType, project_type)

        # 1. 检查 .plc.json
        self._check_plc_json(project_path, result)

        # 2. 检查 PM_SESSION
        self._check_pm_session(project_path, result)

        # 3. 检查 PRD 文档
        self._check_prd_docs(project_path, result)

        # 3.5. 检查 FB 级 PRD 四件套（CHG-SCPT-2026-153）
        self._check_fb_prd_docs(project_path, result)

        # 4. 检查目录结构（仅标准项目）
        if project_type == "standard":
            self._check_directory_structure(project_path, result)
            self._check_hmi_prototype(project_path, result)
            self._check_software_scheme(project_path, result)
            self._check_change_management_and_governance(project_path, result)
            self._check_lifecycle_delivery_templates(project_path, result)

        # 4.5. 检查目录唯一性与影子冗余冲突（DEV-001/DEV-003/LSP-907）
        self._check_naming_and_shadow_duplicates(project_path, result)

        # 5. 检查 Spec Snapshot 规范漂移
        self._check_spec_snapshot(project_path, result)

        # 6. 检查 SCL 代码语法与命名规范 (LSP-905)
        self._check_scl_code_compliance(project_path, result)

        log.info(
            "项目检查完成: %s - pass=%d warn=%d fail=%d",
            os.path.basename(project_path),
            result.pass_count,
            result.warn_count,
            result.fail_count,
        )
        return result

    def _check_scl_code_compliance(self, project_path: str, result: CheckResult) -> None:
        """检查 SCL 文件的命名与语法合规性 (Siemens LSP-905)"""
        scl_files: list[str] = []
        for root, _, files in os.walk(project_path):
            for file in files:
                if file.lower().endswith(".scl"):
                    scl_files.append(os.path.join(root, file))

        if not scl_files:
            result.add("SCL 代码规范", "pass", "未包含 .scl 代码文件，无需排查")
            return

        total_errors = 0
        total_warnings = 0
        error_messages: list[str] = []

        for scl_file in scl_files:
            report = SclLinter.lint_file(scl_file)
            total_errors += report.errors_count
            total_warnings += report.warnings_count
            rel_name = os.path.relpath(scl_file, project_path)
            for v in report.violations:
                if v.severity == "ERROR" and len(error_messages) < 3:
                    error_messages.append(f"{rel_name}:{v.line_number} {v.message}")

        if total_errors > 0:
            msg = f"发现 {total_errors} 个规范错误"
            if error_messages:
                msg += f"（如: {'; '.join(error_messages)}）"
            result.add("SCL 代码规范", "fail", msg)
        elif total_warnings > 0:
            result.add("SCL 代码规范", "warn", f"全量 SCL 结构合规，包含 {total_warnings} 个规范建议")
        else:
            result.add("SCL 代码规范", "pass", f"全量 {len(scl_files)} 个 .scl 文件 100% 遵从 LSP-905 命名与安全闭环规范")

    # ── 工作空间批量检查 ──────────────────────────────────

    def check_workspace(self, scan_depth: int = 4) -> list[CheckResult]:
        """扫描工作空间下所有项目并逐一检查

        Args:
            scan_depth: 扫描深度（默认4层）

        Returns:
            所有项目的检查结果列表
        """
        results: list[CheckResult] = []
        self._scan_and_check(self.workspace_root, results, depth=0, max_depth=scan_depth)
        return results

    # ── 内部方法 ──────────────────────────────────────────

    def _detect_project_type(self, project_path: str) -> str:
        """检测项目类型

        - standard: 标准 PLC 项目（有 00_项目管理 等标准目录结构）
        - shared-library: PLC 共享库（有 actuator/timer/counter 等模块目录）
        - test-suite: 测试套件项目（有 DB1/OB1/Test 但无标准目录）
        - syslib_fb: SysLib 功能块项目（单 FB 目录，无标准子目录）
        """
        basename = os.path.basename(project_path)
        if basename.startswith("FB_") and "SysLib" in project_path:
            return "syslib_fb"

        try:
            entries = set(os.listdir(project_path))
        except OSError:
            entries = set()

        # standard: 有项目管理目录（01_启动 或 00_项目管理，CHG-SCPT-2026-146 双向兼容）
        if any(c in entries for c in PM_DIR_CANDIDATES):
            return "standard"

        # shared-library: 有共享库特征目录
        shared_lib_markers = {
            "actuator",
            "timer",
            "counter",
            "edge",
            "convert",
            "log",
            "pulse",
            "communication",
            "types",
        }
        if shared_lib_markers & entries:
            return "shared-library"

        # test-suite: 有 DB1/OB1/Test 但无 00_项目管理
        test_suite_markers = {"DB1", "OB1", "Test"}
        if test_suite_markers & entries:
            return "test-suite"

        # 默认按 standard 检查（触发目录缺失告警）
        return "standard"

    @staticmethod
    def resolve_project_id(project_path: str) -> str:
        """从目录名解析项目编号

        支持多种命名模式：
        - DJ-2026-005_项目名 → DJ-2026-005
        - FB_1011_功能块名 → FB1011
        - SW-2026-005_项目名 → SW-2026-005

        V0.2.1-P2-4: 改为 staticmethod，供 CLI 层无实例调用。
        """
        basename = os.path.basename(project_path)
        parts = basename.split("_", 1)
        if not parts:
            return basename
        first = parts[0]
        # FB 项目: FB_1011_Name → FB1011
        if first == "FB" and len(parts) > 1:
            second_parts = parts[1].split("_", 1)
            return f"FB{second_parts[0]}"
        return first

    @staticmethod
    def _find_plc_json(project_path: str, max_depth: int = 3) -> str | None:
        """递归查找 .plc.json（与模板生成位置对齐）

        查找顺序：
        1. 项目根目录（标准位置）
        2. 子目录递归查找（适配 02_PLC程序/02_PLC程序/.plc.json 嵌套结构）

        Args:
            project_path: 项目根目录
            max_depth: 最大递归深度（默认3层）

        Returns:
            .plc.json 绝对路径，未找到返回 None
        """
        # 1. 根目录
        root_plc_json = os.path.join(project_path, ".plc.json")
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
                if os.path.isfile(entry_path) and entry == ".plc.json":
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

    def _check_plc_json(self, project_path: str, result: CheckResult) -> None:
        """检查 .plc.json（LSP-907 §1）"""
        if result.project_type in SKIP_PLC_JSON_TYPES:
            result.add(
                ".plc.json",
                "warn",
                "SysLib FB 项目通常无 .plc.json，如需要请手动创建",
            )
            return

        plc_json_path = self._find_plc_json(project_path)
        if not plc_json_path:
            result.add(".plc.json", "fail", "缺少 .plc.json 配置文件（LSP-907 §1.1）")
            return

        try:
            with open(plc_json_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            result.add(".plc.json", "fail", f".plc.json 解析失败: {e}")
            return

        # 必填字段检查
        missing = [f for f in REQUIRED_PLC_JSON_FIELDS if f not in cfg]
        if missing:
            result.add(
                ".plc.json",
                "fail",
                f".plc.json 缺少必填字段: {', '.join(missing)}（LSP-907 §1.1）",
            )
        else:
            result.add(
                ".plc.json",
                "pass",
                f"配置完整: name={cfg['name']}, version={cfg['version']}",
            )

        # libraries 字段检查
        if "libraries" not in cfg or not cfg["libraries"]:
            result.add(
                ".plc.json libraries",
                "warn",
                "未配置 libraries 字段，引用 SysLib 时需添加（LSP-907 §1.2）",
            )
        else:
            for lib_path in cfg["libraries"]:
                abs_lib = os.path.normpath(os.path.join(os.path.dirname(plc_json_path), lib_path))
                if not os.path.isdir(abs_lib):
                    result.add(
                        f".plc.json libraries[{lib_path}]",
                        "warn",
                        f"库路径不存在: {abs_lib}",
                    )
                    continue

                # 检查关键文件（深度校验）
                found_keys = [
                    key_file
                    for key_file in _KEY_FILES
                    if os.path.isfile(os.path.join(abs_lib, key_file))
                ]

                if found_keys:
                    result.add(
                        f".plc.json libraries[{lib_path}]",
                        "pass",
                        f"库路径有效，关键文件 {len(found_keys)}/{len(_KEY_FILES)}",
                    )
                else:
                    result.add(
                        f".plc.json libraries[{lib_path}]",
                        "warn",
                        "库路径存在但关键文件缺失（期望: timer/counter/edge 等）",
                    )

    def _check_pm_session(self, project_path: str, result: CheckResult) -> None:
        """检查 PM_SESSION"""
        project_id = self.resolve_project_id(project_path)

        pm_session = os.path.join(project_path, f"PM_SESSION_{project_id}.md")
        pm_path: str | None = None
        if os.path.isfile(pm_session):
            pm_path = pm_session
            result.add("PM_SESSION", "pass", f"PM_SESSION_{project_id}.md 存在")
        else:
            # 尝试模糊匹配
            found = None
            try:
                for f in os.listdir(project_path):
                    if f.startswith("PM_SESSION_") and f.endswith(".md"):
                        found = f
                        break
            except OSError:
                pass
            if found:
                pm_path = os.path.join(project_path, found)
                result.add(
                    "PM_SESSION",
                    "warn",
                    f"存在但命名不匹配: {found}，期望 PM_SESSION_{project_id}.md",
                )
            else:
                result.add("PM_SESSION", "fail", f"缺少 PM_SESSION_{project_id}.md")
                return

        # PM_SESSION 行数门禁（CHG-SCPT-2026-153: P1-4）
        # warn >150（接近双层结构阈值），fail >300（严重膨胀）
        if pm_path:
            line_count = self._count_file_lines(pm_path)
            if line_count > 300:
                result.add(
                    "PM_SESSION 行数",
                    "fail",
                    f"PM_SESSION 严重膨胀: {line_count} 行（阈值: 150 行，"
                    f"建议执行 pm-session archive 归档）",
                )
            elif line_count > 150:
                result.add(
                    "PM_SESSION 行数",
                    "warn",
                    f"PM_SESSION 接近阈值: {line_count} 行（阈值: 150 行，"
                    f"建议执行 pm-session archive 归档）",
                )
            else:
                result.add(
                    "PM_SESSION 行数",
                    "pass",
                    f"{line_count} 行（阈值: 150 行）",
                )

    @staticmethod
    def _count_file_lines(file_path: str) -> int:
        """统计文件行数（高效方式，不加载全部内容到内存）"""
        count = 0
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                for _ in f:
                    count += 1
        except OSError:
            return 0
        return count

    def _check_spec_snapshot(self, project_path: str, result: CheckResult) -> None:
        """检查 Spec Snapshot 规范漂移（V2.0.3）

        解析 PM_SESSION 中的 Spec Snapshot 表格，对比 spec_registry.json，
        根据漂移级别设置检查项状态：
        - major 漂移 → FAIL
        - minor/patch 漂移 → WARN
        - 无漂移 → PASS

        边界情况：
        - PM_SESSION 不存在 → 跳过（已在 PM_SESSION 检查中报告）
        - spec_registry.json 缺失 → WARN
        - Spec Snapshot 表格缺失 → WARN
        """
        # 查找 PM_SESSION 文件路径（复用现有查找逻辑）
        project_id = self.resolve_project_id(project_path)
        pm_session = os.path.join(project_path, f"PM_SESSION_{project_id}.md")
        if not os.path.isfile(pm_session):
            # 尝试模糊匹配
            found = None
            try:
                for f in os.listdir(project_path):
                    if f.startswith("PM_SESSION_") and f.endswith(".md"):
                        found = f
                        break
            except OSError:
                pass
            if found:
                pm_session = os.path.join(project_path, found)
            else:
                # PM_SESSION 不存在，已在第 2 项检查中报告
                return

        # 加载 spec_registry.json
        registry = load_spec_registry(self.workspace_root)
        if registry is None:
            result.add(
                "Spec Snapshot",
                "warn",
                "未找到 spec_registry.json，跳过漂移检测",
            )
            return

        # 解析 Spec Snapshot 表格
        snapshot = parse_spec_snapshot(pm_session)
        if not snapshot:
            result.add(
                "Spec Snapshot",
                "warn",
                "PM_SESSION 缺少 Spec Snapshot 表格",
            )
            return

        # 对比版本
        drifts = compare_versions(snapshot, registry)
        if not drifts:
            result.add(
                "Spec Snapshot",
                "pass",
                "Spec Snapshot 与 spec_registry.json 一致",
            )
            return

        # 根据漂移级别设置状态
        level_names = {
            "major": "主版本漂移",
            "minor": "次版本漂移",
            "patch": "补丁漂移",
        }
        drift_msgs = [
            f"{d.spec_id}: {d.snapshot_version} → {d.registry_version} "
            f"({level_names[d.drift_level]})"
            for d in drifts
        ]
        has_major = any(d.drift_level == "major" for d in drifts)
        status = "fail" if has_major else "warn"
        result.add("Spec Snapshot", status, "; ".join(drift_msgs))

    def _check_prd_docs(self, project_path: str, result: CheckResult) -> None:
        """检查 PRD 文档完整性"""
        found = find_prd_dir(project_path)
        legacy_dirs = self._get_existing_legacy_prd_dirs(project_path)

        if found is None:
            if legacy_dirs:
                result.add(
                    "PRD 目录",
                    "warn",
                    "未使用 root PRD/ 或 00_程序方案/，检测到历史文档目录: "
                    + ", ".join(legacy_dirs),
                )
            else:
                result.add("PRD 目录", "fail", "缺少 PRD/（或 00_程序方案/）目录")
                return
        else:
            prd_path, prd_name = found
            result.add("PRD 目录", "pass", f"{prd_name}/ 目录存在")

        existing: set[str] = set()
        try:
            if found is not None:
                prd_path = found[0]
                existing = {f for f in os.listdir(prd_path) if f.endswith(".md")}
        except OSError:
            pass

        prd_display_name = found[1] if found else "PRD"
        for doc in STD_PRDS:
            if doc in existing:
                result.add(f"{prd_display_name}/{doc}", "pass", "存在")
            else:
                # 尝试模糊匹配
                prefix = doc.split("_")[0]
                matched = [f for f in existing if f.startswith(prefix)]
                if matched:
                    result.add(
                        f"{prd_display_name}/{doc}",
                        "warn",
                        f"命名不匹配，实际文件: {', '.join(matched)}",
                    )
                else:
                    legacy_matches = self._find_legacy_prd_docs(project_path, doc)
                    if legacy_matches:
                        result.add(
                            f"{prd_display_name}/{doc}",
                            "warn",
                            "历史路径存在: "
                            + ", ".join(legacy_matches)
                            + f"，建议后续收口到 {prd_display_name}/",
                        )
                    else:
                        result.add(
                            f"{prd_display_name}/{doc}", "fail", f"缺少 {doc}"
                        )

        # 深度校验各 FB 模块 PRD 内容质量（关联源码路径有效性与版本滞后）
        self._check_sub_prd_substance(project_path, result)

    def _check_sub_prd_substance(self, project_path: str, result: CheckResult) -> None:
        """深度校验 FB 模块 PRD 内容质量（关联源码路径有效性与版本滞后）"""
        plc_st_path = os.path.join(project_path, "02_PLC程序", "PLC_ST")
        if not os.path.isdir(plc_st_path):
            plc_st_path = os.path.join(project_path, "PLC_ST")
            if not os.path.isdir(plc_st_path):
                return

        for root, _dirs, files in os.walk(plc_st_path):
            if os.path.basename(root) != "PRD":
                continue
            for f in sorted(files):
                if not f.endswith(".md"):
                    continue
                file_path = os.path.join(root, f)
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                except OSError:
                    continue

                # 校验关联源码路径
                source_match = re.search(r"\|\s*\*\*关联源码\*\*\s*\|\s*([^|\r\n]+)\|", content)
                if source_match:
                    source_rel = source_match.group(1).strip()
                    resolved_source = os.path.normpath(os.path.join(plc_st_path, source_rel))
                    if not os.path.isfile(resolved_source):
                        result.add(
                            f"PRD内容质量 [{f}]",
                            "warn",
                            f"关联源码路径失效: '{source_rel}' (实际文件不存在)",
                        )

                # 校验文档版本与项目主版本滞后
                version_match = re.search(r"\|\s*\*\*文档版本\*\*\s*\|\s*(V\d+\.\d+\.\d+)", content)
                if version_match:
                    doc_version = version_match.group(1).strip()
                    plc_json_path = self._find_plc_json(project_path)
                    if plc_json_path:
                        try:
                            with open(plc_json_path, encoding="utf-8") as jf:
                                cfg = json.load(jf)
                                main_version = cfg.get("version", "")
                                if main_version and main_version.startswith("V") and doc_version.startswith("V"):
                                    main_major = int(main_version[1:].split(".")[0])
                                    doc_major = int(doc_version[1:].split(".")[0])
                                    if main_major - doc_major >= 2:
                                        result.add(
                                            f"PRD内容质量 [{f}]",
                                            "warn",
                                            f"文档版本严重滞后: {doc_version} (项目主版本 {main_version})",
                                        )
                        except Exception:
                            pass

    def _check_fb_prd_docs(self, project_path: str, result: CheckResult) -> None:
        """检查 FB 级 PRD 四件套（L3 层，每个 FB 模块的 PRD/ 子目录下 IFC/DSN/CHG/UM）

        CHG-SCPT-2026-153: 基于 DJ-2026-005 实战，plc check 原只检查 L2 级 REQ/INT/DSN/TEC，
        不检查 FB 级 IFC/DSN/CHG/UM，导致 4/7 模块四件套不完整仍 21/21 全绿通过。
        """
        # 定位 PLC_ST 目录
        plc_st_path = os.path.join(project_path, FB_PRD_SCAN_DIR)
        if not os.path.isdir(plc_st_path):
            # 尝试兼容旧路径（PLC_ST 直接在项目根目录下）
            plc_st_path = os.path.join(project_path, "PLC_ST")
            if not os.path.isdir(plc_st_path):
                return

        try:
            fb_dirs = sorted(
                d for d in os.listdir(plc_st_path)
                if os.path.isdir(os.path.join(plc_st_path, d))
                and d not in FB_PRD_SKIP_DIRS
                and not d.startswith(".")
                and not d.startswith("00_")  # 基础设施/文档目录，非 FB 模块
            )
        except OSError:
            return

        if not fb_dirs:
            return

        total_modules = 0
        complete_modules = 0
        for fb_dir in fb_dirs:
            total_modules += 1
            prd_path = os.path.join(plc_st_path, fb_dir, "PRD")
            if not os.path.isdir(prd_path):
                result.add(
                    f"FB PRD [{fb_dir}]",
                    "fail",
                    "缺少 PRD/ 子目录（期望: IFC/DSN/CHG/UM 四件套）",
                )
                continue

            try:
                prd_files = set(os.listdir(prd_path))
            except OSError:
                result.add(
                    f"FB PRD [{fb_dir}]",
                    "fail",
                    "PRD/ 目录不可读",
                )
                continue

            module_complete = True
            for doc_type, prefix in FB_PRDS:
                matched = [f for f in prd_files if f.startswith(prefix) and f.endswith(".md")]
                if matched:
                    result.add(
                        f"FB PRD [{fb_dir}]/{doc_type}",
                        "pass",
                        matched[0],
                    )
                else:
                    module_complete = False
                    result.add(
                        f"FB PRD [{fb_dir}]/{doc_type}",
                        "fail",
                        f"缺少 {prefix}*.md",
                    )

            if module_complete:
                complete_modules += 1

        # 汇总统计
        if total_modules > 0:
            if complete_modules == total_modules:
                result.add(
                    "FB PRD 四件套",
                    "pass",
                    f"全部 {total_modules}/{total_modules} 模块 PRD 四件套完整",
                )
            else:
                result.add(
                    "FB PRD 四件套",
                    "fail",
                    f"{complete_modules}/{total_modules} 模块 PRD 四件套完整"
                    f"（缺 {total_modules - complete_modules} 个）",
                )

    @staticmethod
    def _get_existing_legacy_prd_dirs(project_path: str) -> list[str]:
        """返回存在的历史 PRD 目录（相对路径，使用 / 分隔）"""
        existing_dirs: list[str] = []
        for rel_dir in _LEGACY_PRD_DIRS:
            abs_dir = os.path.join(project_path, rel_dir)
            if os.path.isdir(abs_dir):
                existing_dirs.append(rel_dir.replace(os.sep, "/"))
        return existing_dirs

    @staticmethod
    def _find_legacy_prd_docs(project_path: str, doc_name: str) -> list[str]:
        """在受控历史目录中查找等价 PRD 文档"""
        rule = NAMING_RULES.get(doc_name, {})
        patterns = [re.compile(p) for p in rule.get("patterns", [])]
        prefix = doc_name.split("_")[0]
        matches: list[str] = []

        for rel_dir in _LEGACY_PRD_DIRS:
            abs_dir = os.path.join(project_path, rel_dir)
            if not os.path.isdir(abs_dir):
                continue

            try:
                md_files = sorted(f for f in os.listdir(abs_dir) if f.endswith(".md"))
            except OSError:
                continue

            for filename in md_files:
                if filename == doc_name:
                    matches.append(f"{rel_dir}/{filename}".replace(os.sep, "/"))
                    continue

                if filename.startswith(prefix) or any(
                    pattern.search(filename) for pattern in patterns
                ):
                    matches.append(f"{rel_dir}/{filename}".replace(os.sep, "/"))

        return matches

    def _check_directory_structure(self, project_path: str, result: CheckResult) -> None:
        """检查目录结构是否符合 LSP-907 §3.1

        CHG-SCPT-2026-146: 双向兼容 01_启动（新模板）和 00_项目管理（旧项目）
        """
        for d in STD_DIRS:
            full_path = os.path.join(project_path, d)
            if os.path.isdir(full_path):
                result.add(f"目录 {d}", "pass", "存在")
            # 项目管理目录：接受任一候选（01_启动 或 00_项目管理）
            elif d in PM_DIR_CANDIDATES and any(
                os.path.isdir(os.path.join(project_path, c))
                for c in PM_DIR_CANDIDATES
            ):
                # 找到实际存在的候选目录名用于报告
                actual = next(
                    c for c in PM_DIR_CANDIDATES
                    if os.path.isdir(os.path.join(project_path, c))
                )
                result.add(f"目录 {actual}", "pass", "存在（5大过程组兼容）")
            else:
                result.add(f"目录 {d}", "fail", f"缺少目录 {d}（LSP-907 §3.1）")

    def _check_naming_and_shadow_duplicates(self, project_path: str, result: CheckResult) -> None:
        """检查目录前缀冲突、影子冗余文件与版本后缀违规（DEV-001/DEV-003/LSP-907）"""
        # 1. 检查根目录序号前缀冲突 (例如不能同时存在 04_现场调试 与 04_驱动器与设备)
        prefix_map: dict[str, list[str]] = {}
        try:
            for entry in os.listdir(project_path):
                if os.path.isdir(os.path.join(project_path, entry)) and not entry.startswith("."):
                    m = re.match(r"^(\d{2})_", entry)
                    if m:
                        pfx = m.group(1)
                        prefix_map.setdefault(pfx, []).append(entry)
        except OSError:
            pass

        duplicate_prefixes = {
            p: dirs
            for p, dirs in prefix_map.items()
            if len(dirs) > 1 and not self._is_allowed_stage_prefix_overlap(p, dirs)
        }
        if duplicate_prefixes:
            conflict_descs = [f"序号 {p}: {', '.join(dirs)}" for p, dirs in duplicate_prefixes.items()]
            result.add(
                "目录唯一性与冲突排查",
                "fail",
                f"检测到同级目录前缀序号冲突: {'; '.join(conflict_descs)}",
            )
        else:
            compat_descs = [
                f"序号 {p}: {', '.join(dirs)}"
                for p, dirs in prefix_map.items()
                if len(dirs) > 1 and self._is_allowed_stage_prefix_overlap(p, dirs)
            ]
            if compat_descs:
                result.add(
                    "目录唯一性与冲突排查",
                    "pass",
                    "兼容双目录结构: " + "; ".join(compat_descs),
                )
            else:
                result.add("目录唯一性与冲突排查", "pass", "同级阶段目录序号唯一，无冲突")

        # 2. 检查 02_PLC程序/程序文档 下的影子镜像与版本号违规
        doc_dir = os.path.join(project_path, "02_PLC程序", "程序文档")
        if os.path.isdir(doc_dir):
            try:
                files = [f for f in os.listdir(doc_dir) if f.endswith(".md")]
                # 检查带版本号文件名 (如 -V1.0.0.md, _V1.0.md)
                versioned_files = [f for f in files if re.search(r"[-_]V\d+(\.\d+)*\.md$", f, re.IGNORECASE)]
                if versioned_files:
                    result.add(
                        "文档命名版本号约束 (DEV-001)",
                        "fail",
                        f"基准文档严禁携带版本号后缀: {', '.join(versioned_files)}",
                    )
                else:
                    result.add("文档命名版本号约束 (DEV-001)", "pass", "基准文档文件名均未包含版本号后缀")

                # 检查同类文档镜像重复 (例如 015_... 与 015_PID_... 同时存在)
                prefixes: dict[str, list[str]] = {}
                for f in files:
                    m = re.match(r"^(\d{3})_", f)
                    if m:
                        prefixes.setdefault(m.group(1), []).append(f)
                    elif "VAR" in f.upper():
                        prefixes.setdefault("VAR", []).append(f)

                conflicts = [f"{k}: {', '.join(v)}" for k, v in prefixes.items() if len(v) > 1]
                if conflicts:
                    result.add(
                        "程序文档镜像排他检查",
                        "fail",
                        f"检测到同类文档重复/镜像冲突: {'; '.join(conflicts)}",
                    )
                else:
                    result.add("程序文档镜像排他检查", "pass", "程序文档无冗余镜像冲突")
            except OSError:
                pass

    @staticmethod
    def _is_allowed_stage_prefix_overlap(prefix: str, dirs: list[str]) -> bool:
        allowed_overlap = {
            "01": {"01_启动", "01_需求与设计"},
        }
        allowed_dirs = allowed_overlap.get(prefix)
        if not allowed_dirs:
            return False
        return set(dirs).issubset(allowed_dirs)

    def _check_change_management_and_governance(self, project_path: str, result: CheckResult) -> None:
        """检查变更管理体系与版本变更台帐 (PM-042 / PM-043 / PROJ-016)"""
        # 1. 检查变更管理根目录 (支持 04_监控/01_变更管理 或 11_监控/01_变更管理)
        chg_candidates = [
            os.path.join(project_path, "04_监控", "01_变更管理"),
            os.path.join(project_path, "11_监控", "01_变更管理"),
            os.path.join(project_path, "00_项目管理", "04_变更管理"),
            os.path.join(project_path, "04_监控"),
            os.path.join(project_path, "11_监控"),
        ]
        # 优先选择包含 01_变更单 或 02_变更记录 的目录
        active_chg_dir = None
        for d in chg_candidates:
            if os.path.isdir(d):
                if os.path.isdir(os.path.join(d, "01_变更单")) or os.path.isdir(os.path.join(d, "02_变更记录")):
                    active_chg_dir = d
                    break
        if not active_chg_dir:
            active_chg_dir = next((d for d in chg_candidates if os.path.isdir(d)), None)

        if active_chg_dir:
            rel_path = os.path.relpath(active_chg_dir, project_path)
            result.add("变更管理目录", "pass", f"存在: {rel_path}")

            # 检查 01_变更单 子目录
            chg_tickets_dir = os.path.join(active_chg_dir, "01_变更单")
            if os.path.isdir(chg_tickets_dir):
                result.add("变更单管理体系", "pass", "01_变更单 目录就绪")
            else:
                result.add("变更单管理体系", "fail", f"缺少 {rel_path}/01_变更单/ 目录")

            # 检查版本变更台帐
            has_ledger = False
            rec_dir = os.path.join(active_chg_dir, "02_变更记录")
            if os.path.isdir(rec_dir):
                for f in os.listdir(rec_dir):
                    if "变更台帐" in f or "变更台账" in f or "台帐" in f:
                        has_ledger = True
                        break

            if has_ledger:
                result.add("版本变更台帐", "pass", "02_变更记录/版本变更台帐 存在")
            else:
                result.add("版本变更台帐", "fail", f"缺少 {rel_path}/02_变更记录/01_版本变更台帐.md")
        else:
            result.add(
                "变更管理目录",
                "fail",
                "缺少变更管理目录 (04_监控/01_变更管理/ 或 11_监控/01_变更管理/，PM-043)",
            )

    def _check_lifecycle_delivery_templates(self, project_path: str, result: CheckResult) -> None:
        """检查现场调试、文档与交付等关键生命周期文档实质化 (拒绝纯 .gitkeep 空壳)"""
        # 1. 检查 04_现场调试
        debug_dir = os.path.join(project_path, "04_现场调试")
        if os.path.isdir(debug_dir):
            files = [f for f in os.listdir(debug_dir) if f.endswith(".md")]
            if files:
                result.add("现场调试方案与跟踪", "pass", f"存在 {len(files)} 份调试文档")
            else:
                result.add("现场调试方案与跟踪", "fail", "04_现场调试 仅为空目录，缺少调试计划/问题跟踪模板")

        # 2. 检查 06_文档与交付
        deliv_dir = os.path.join(project_path, "06_文档与交付")
        if os.path.isdir(deliv_dir):
            has_md = False
            for _r, _, fs in os.walk(deliv_dir):
                if any(f.endswith(".md") for f in fs):
                    has_md = True
                    break
            if has_md:
                result.add("交付与维护手册", "pass", "交付与维护手册模板就绪")
            else:
                result.add("交付与维护手册", "fail", "06_文档与交付 缺少维护手册/验收交付清单等模板")

    def _scan_and_check(
        self, path: str, results: list[CheckResult], depth: int, max_depth: int
    ) -> None:
        """递归扫描目录并检查项目

        项目识别规则（满足任一即识别为项目）：
        - 目录下存在 .plc.json（标准项目配置文件）
        - 目录下存在 PM_SESSION_*.md（项目管理会话文件）
        - 目录名以 FB_ 开头（SysLib 功能块项目）
        """
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
            if entry.startswith(".") or entry.startswith("__"):
                continue

            # 判断是否是项目目录
            if self._is_project_dir(entry_path):
                results.append(self.check_project(entry_path))
            else:
                # 非项目目录，继续递归
                self._scan_and_check(entry_path, results, depth + 1, max_depth)

    @staticmethod
    def _is_project_dir(project_path: str) -> bool:
        """判断目录是否为 PLC 项目

        识别规则（满足任一）：
        - 存在 .plc.json（仅根目录，不递归查找，避免将容器目录误判为项目）
        - 存在 PM_SESSION_*.md 且位于 PLC 区域
        - 目录名以 FB_ 开头（SysLib FB 项目）

        排除规则：
        - 存在 pyproject.toml 且无 .plc.json → Python 项目，跳过
        - 位于 Python 项目管理区域且无 .plc.json → 非 PLC 项目，跳过
        - 仅靠 PM_SESSION 识别且不在 PLC 区域 → 非 PLC 项目（如 SYS-2026-001 跨域治理项目），跳过
        """
        # .plc.json（仅根目录，不递归查找，防止将 0100_PLC自动化 等容器目录误判为项目）
        if os.path.isfile(os.path.join(project_path, ".plc.json")):
            return True

        # 排除 Python 项目（有 pyproject.toml 且无 .plc.json）
        if os.path.isfile(os.path.join(project_path, "pyproject.toml")):
            return False

        # 排除 Python 项目管理区域的项目（无 .plc.json 且位于 Python 项目目录下）
        if PlcChecker._is_in_python_area(project_path):
            return False

        # PM_SESSION_*.md（仅 PLC 区域内的项目，避免将 SYS-2026-001 等跨域项目误判为 PLC 项目）
        has_pm_session = False
        try:
            for f in os.listdir(project_path):
                if f.startswith("PM_SESSION_") and f.endswith(".md"):
                    has_pm_session = True
                    break
        except OSError:
            pass

        if has_pm_session and PlcChecker._is_in_plc_area(project_path):
            return True

        # FB_ 开头（SysLib FB 项目）
        if os.path.basename(project_path).startswith("FB_"):
            return True

        return False

    def _check_hmi_prototype(self, project_path: str, result: CheckResult) -> None:
        """检查 HMI 交互原型与点表映射文件 (STD-910)"""
        hmi_dir = os.path.join(project_path, "03_HMI设计")
        if not os.path.isdir(hmi_dir):
            result.add("HMI 交互原型", "fail", "缺少 03_HMI设计 目录")
            return

        html_paths = [
            os.path.join(hmi_dir, "原型", "files", "HMI原型设计.html"),
            os.path.join(hmi_dir, "HMI原型设计.html"),
        ]
        has_html = any(os.path.isfile(p) for p in html_paths)
        mapping_path = os.path.join(hmi_dir, "hmi_tag_mapping.json")
        has_mapping = os.path.isfile(mapping_path)

        if not has_html:
            result.add("HMI 交互原型", "warn", "未检测到 HMI 原型 HTML 文件 (建议添加 03_HMI设计/原型/files/HMI原型设计.html)")
        elif not has_mapping:
            result.add("HMI 交互原型", "warn", "缺少 hmi_tag_mapping.json 点表映射文件")
        else:
            result.add("HMI 交互原型", "pass", "11页高保真 HMI 原型与点表映射完备")

    def _check_software_scheme(self, project_path: str, result: CheckResult) -> None:
        """检查 01_需求与设计/13_软件方案 或 PRD 下的需求规格说明书与工艺流程图"""
        scheme_dirs = [
            os.path.join(project_path, "02_PLC程序", "PLC_ST", "00_程序方案"),
            os.path.join(project_path, "02_PLC程序", "PLC_ST", "PRD"),
            os.path.join(project_path, "02_PLC程序", "程序文档"),
            os.path.join(project_path, "01_需求与设计", "13_软件方案"),
            os.path.join(project_path, "01_需求与设计"),
            os.path.join(project_path, "00_项目管理", "01_启动"),
            os.path.join(project_path, "01_启动", "13_软件方案"),
            os.path.join(project_path, "01_启动"),
            os.path.join(project_path, "PRD"),
        ]
        has_req_spec = False
        has_flow_chart = False

        for s_dir in scheme_dirs:
            if not os.path.isdir(s_dir):
                continue
            for f in os.listdir(s_dir):
                if ("需求规格说明书" in f or "需求分析文档" in f) and f.endswith(".md"):
                    has_req_spec = True
                if f.endswith(".mmd") or "流程图" in f:
                    has_flow_chart = True

        if not has_req_spec:
            result.add("需求规格说明书", "fail", "缺少需求规格说明书 (01_需求与设计/13_软件方案/ 或 PRD/)")
        else:
            result.add("需求规格说明书", "pass", "需求规格说明书就绪")

        if not has_flow_chart:
            result.add("工艺流程图", "warn", "缺少 Mermaid 工艺流程图 (*.mmd)")
        else:
            result.add("工艺流程图", "pass", "Mermaid 工艺流程图就绪")

    @staticmethod
    def _is_in_python_area(project_path: str) -> bool:
        """判断项目路径是否位于 Python 项目管理区域

        用于在 PLC 扫描中排除非 PLC 项目。
        规则：路径中包含 01_Project自动化项目管理/Python自动化项目总库 即视为 Python 区域。
        """
        norm_path = project_path.replace("/", os.sep)
        python_marker = "01_Project自动化项目管理" + os.sep + "Python自动化项目总库" + os.sep
        return python_marker in norm_path

    @staticmethod
    def _is_in_plc_area(project_path: str) -> bool:
        """判断项目路径是否位于 PLC 自动化区域

        规则：路径中包含 0100_PLC自动化 即视为 PLC 区域。
        """
        norm_path = project_path.replace("/", os.sep)
        plc_marker = os.sep + "0100_PLC自动化" + os.sep
        return plc_marker in norm_path


class _CheckGroupBase:
    """PLC 检查分组基类，仅承载共享上下文。"""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)


# ── 分组 A：配置 / 文档检查 ──────────────────────────────
class _PlcConfigChecks(_CheckGroupBase):
    _check_plc_json = _LegacyPlcCheckerCore._check_plc_json
    _check_pm_session = _LegacyPlcCheckerCore._check_pm_session
    _check_spec_snapshot = _LegacyPlcCheckerCore._check_spec_snapshot
    _check_prd_docs = _LegacyPlcCheckerCore._check_prd_docs
    _check_sub_prd_substance = _LegacyPlcCheckerCore._check_sub_prd_substance
    _check_fb_prd_docs = _LegacyPlcCheckerCore._check_fb_prd_docs


# ── 分组 B：结构 / 命名检查 ──────────────────────────────
class _PlcStructChecks(_CheckGroupBase):
    _check_directory_structure = _LegacyPlcCheckerCore._check_directory_structure
    _check_naming_and_shadow_duplicates = _LegacyPlcCheckerCore._check_naming_and_shadow_duplicates
    _check_change_management_and_governance = _LegacyPlcCheckerCore._check_change_management_and_governance
    _check_lifecycle_delivery_templates = _LegacyPlcCheckerCore._check_lifecycle_delivery_templates
    _check_hmi_prototype = _LegacyPlcCheckerCore._check_hmi_prototype
    _check_software_scheme = _LegacyPlcCheckerCore._check_software_scheme


# ── 分组 C：代码质量检查 ────────────────────────────────
class _SclCodeChecks(_CheckGroupBase):
    _check_scl_code_compliance = _LegacyPlcCheckerCore._check_scl_code_compliance


class PlcChecker(_PlcConfigChecks, _PlcStructChecks, _SclCodeChecks, _LegacyPlcCheckerCore):
    """PLC 项目结构检查器（LSP-907）。"""
