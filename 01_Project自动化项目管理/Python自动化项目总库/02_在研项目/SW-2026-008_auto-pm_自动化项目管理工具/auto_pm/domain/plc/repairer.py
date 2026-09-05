"""PLC-HMI 概念映射：SFB 库函数（PLC 修复器（自动修复 PLC 项目结构问题））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

PLC 项目自动修复器（LSP-907 907_项目配置规范_LSP）

迁移自 SW-2026-005 的 PlcProjectService.repair_project/standardize_docs。
修复规则：
- 非破坏性操作（创建目录/文件/补全字段）：自动执行
- 破坏性操作（文件重命名）：需 rename_confirm=True
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime

from auto_pm.core.paths import PRD_DIR, PRD_DIR_CANDIDATES, find_prd_dir
from auto_pm.plc.checker import PlcChecker
from auto_pm.plc.models import (
    NAMING_RULES,
    CheckItem,
    RenamePlan,
    RepairResult,
    StandardizeResult,
)

log = logging.getLogger(__name__)


class PlcRepairer:
    """PLC 项目自动修复器（LSP-907）"""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self._checker = PlcChecker(workspace_root)

    # ── PRD 目录解析辅助 ──────────────────────────────────

    @staticmethod
    def _is_prd_doc_item(item_name: str) -> str | None:
        """判断检查项是否为 PRD 文档项，返回文档名（如 需求分析文档_REQ.md）

        兼容 item 名格式：
        - "PRD/需求分析文档_REQ.md"（标准命名）
        - "00_程序方案/需求分析文档_REQ.md"（定制命名）
        """
        for candidate in PRD_DIR_CANDIDATES:
            prefix = candidate + "/"
            if item_name.startswith(prefix):
                return item_name[len(prefix) :]
        return None

    @staticmethod
    def _resolve_prd_path(project_path: str) -> str:
        """解析实际存在的 PRD 目录路径，若都不存在则返回默认 PRD_DIR 路径"""
        found = find_prd_dir(project_path)
        if found is not None:
            return str(found[0])
        return os.path.join(project_path, PRD_DIR)

    # ── 单项目修复 ────────────────────────────────────────

    def repair_project(
        self,
        project_path: str,
        dry_run: bool = False,
        rename_confirm: bool = False,
    ) -> RepairResult:
        """自动修复项目结构问题

        Args:
            project_path: 项目根目录绝对路径
            dry_run: 仅预览不执行
            rename_confirm: 是否确认文件重命名（破坏性操作）

        Returns:
            RepairResult: 修复结果
        """
        log.info(
            "开始修复项目: %s (dry_run=%s, rename_confirm=%s)",
            project_path,
            dry_run,
            rename_confirm,
        )

        result = RepairResult(project_path=project_path)

        # 1. 修复前检查
        result.before_check = self._checker.check_project(project_path)

        project_id = self._checker.resolve_project_id(project_path)
        project_name = os.path.basename(project_path)

        # 2. 遍历检查项，对 FAIL 项执行修复；Spec Snapshot 的 WARN 也允许自动补齐
        for item in result.before_check.items:
            should_repair = item.status == "fail" or (
                item.item == "Spec Snapshot" and item.status == "warn"
            )
            if not should_repair:
                continue

            if item.item == ".plc.json":
                self._repair_plc_json(project_path, project_id, project_name, result, dry_run)
            elif item.item == "PM_SESSION":
                self._repair_pm_session(project_path, project_id, project_name, result, dry_run)
            elif item.item == "Spec Snapshot":
                self._repair_spec_snapshot(project_path, result, dry_run)
            elif item.item == "PRD 目录":
                self._repair_prd_dir(project_path, project_id, project_name, result, dry_run)
            elif (doc_name := self._is_prd_doc_item(item.item)) is not None:
                self._repair_prd_doc(
                    project_path, project_id, project_name, doc_name, result, dry_run
                )
            elif item.item.startswith("FB PRD "):
                self._repair_fb_prd_doc(
                    project_path, project_id, project_name, item, result, dry_run
                )
            elif item.item == "HMI 交互原型" or "hmi_tag_mapping.json" in item.message:
                self._repair_hmi_mapping(project_path, project_id, project_name, result, dry_run)
            elif item.item.startswith("目录 "):
                dir_name = item.item.split(" ", 1)[1]
                self._repair_std_dir(project_path, dir_name, result, dry_run)

        # 3. 处理 WARN 项中的命名不匹配（破坏性操作）
        if rename_confirm:
            for item in result.before_check.items:
                if item.status != "warn":
                    continue
                if "命名不匹配" in item.message or "命名不规范" in item.message:
                    self._repair_rename(project_path, item, result, dry_run)
        else:
            for item in result.before_check.items:
                if item.status == "warn" and (
                    "命名不匹配" in item.message or "命名不规范" in item.message
                ):
                    result.add(
                        item=item.item,
                        action="重命名文件（需确认）",
                        destructive=True,
                        status="skipped",
                        detail=f"未确认重命名，跳过: {item.message}",
                    )

        # 4. 修复后重新检查
        if not dry_run:
            result.after_check = self._checker.check_project(project_path)
        else:
            result.after_check = result.before_check

        log.info(
            "修复完成: %s - fixed=%d skipped=%d failed=%d",
            os.path.basename(project_path),
            result.fixed_count,
            result.skipped_count,
            result.failed_count,
        )
        return result

    # ── 工作空间批量修复 ──────────────────────────────────

    def repair_workspace(
        self, dry_run: bool = False, rename_confirm: bool = False
    ) -> list[RepairResult]:
        """批量修复工作空间所有项目

        Args:
            dry_run: 仅预览不执行
            rename_confirm: 是否确认文件重命名

        Returns:
            所有需要修复的项目的修复结果列表（跳过已通过的项目）
        """
        results: list[RepairResult] = []
        check_results = self._checker.check_workspace()
        for cr in check_results:
            if cr.all_pass:
                continue
            results.append(self.repair_project(cr.project_path, dry_run, rename_confirm))
        return results

    # ── 文档标准化 ────────────────────────────────────────

    def standardize_docs(self, project_path: str, apply: bool = False) -> StandardizeResult:
        """检测并修正 PRD 文档命名

        Args:
            project_path: 项目根目录绝对路径
            apply: False=仅检测预览, True=执行重命名

        Returns:
            StandardizeResult: 标准化结果
        """
        log.info("开始标准化文档: %s (apply=%s)", project_path, apply)

        result = StandardizeResult(project_path=project_path)
        prd_path = self._resolve_prd_path(project_path)

        if not os.path.isdir(prd_path):
            log.warning("PRD 目录不存在，跳过标准化: %s", prd_path)
            return result

        try:
            existing_files = [f for f in os.listdir(prd_path) if f.endswith(".md")]
        except OSError as e:
            log.error("扫描 PRD 目录失败: %s", e)
            return result

        for filename in existing_files:
            # 跳过已是标准命名的文件
            if filename in NAMING_RULES:
                continue

            # 匹配非标准命名模式
            for std_name, rule in NAMING_RULES.items():
                matched = any(re.search(p, filename) for p in rule["patterns"])
                if matched:
                    old_path = os.path.join(prd_path, filename)
                    new_path = os.path.join(prd_path, std_name)
                    plan = RenamePlan(
                        old_path=old_path,
                        new_path=new_path,
                        doc_type=rule["doc_type"],
                    )

                    if apply:
                        try:
                            backup_path = old_path + ".bak"
                            shutil.copy2(old_path, backup_path)
                            plan.backup_path = backup_path

                            os.rename(old_path, new_path)
                            plan.applied = True
                            result.applied_count += 1

                            updates = self._update_references(prd_path, filename, std_name)
                            result.reference_updates.extend(updates)

                            log.info("重命名: %s → %s", filename, std_name)
                        except OSError as e:
                            log.error("重命名失败: %s → %s: %s", filename, std_name, e)
                            result.skipped_count += 1
                    else:
                        result.skipped_count += 1

                    result.plans.append(plan)
                    break

        log.info(
            "标准化完成: %s - applied=%d skipped=%d",
            os.path.basename(project_path),
            result.applied_count,
            result.skipped_count,
        )
        return result

    def standardize_workspace(self, apply: bool = False) -> list[StandardizeResult]:
        """批量标准化工作空间所有项目"""
        results: list[StandardizeResult] = []
        check_results = self._checker.check_workspace()
        for cr in check_results:
            results.append(self.standardize_docs(cr.project_path, apply))
        return results

    # ── 内部修复方法 ──────────────────────────────────────

    def _repair_plc_json(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复 .plc.json（创建缺失文件或补全字段）

        V0.2.1-P1-5: 递归查找已有 .plc.json，避免在根目录重复创建
        V0.2.1-P2-9: 从 .copier-answers.yml 读取元数据（description/version）
        """
        # V0.2.1-P1-5: 递归查找已有 .plc.json（与 PlcChecker._find_plc_json 对齐）
        existing_plc_json = PlcChecker._find_plc_json(project_path)
        if existing_plc_json:
            # 已有 .plc.json（可能在嵌套目录），补全缺失字段
            plc_json_path = existing_plc_json
            try:
                with open(plc_json_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                result.add(
                    item=".plc.json",
                    action="修复 .plc.json 解析错误",
                    destructive=False,
                    status="failed",
                    detail=f"解析失败，需手动修复: {e}",
                )
                return

            changed = False
            if "name" not in cfg:
                cfg["name"] = project_id
                changed = True
            if "description" not in cfg:
                cfg["description"] = project_name
                changed = True
            if "version" not in cfg:
                cfg["version"] = "V1.0.0"
                changed = True

            if changed:
                if not dry_run:
                    from auto_pm.utils.file_utils import write_file

                    write_file(plc_json_path, json.dumps(cfg, indent=2, ensure_ascii=False))
                result.add(
                    item=".plc.json",
                    action="补全 .plc.json 必填字段",
                    destructive=False,
                    status="fixed",
                    detail=f"已补全缺失的必填字段: {plc_json_path}",
                )
            else:
                result.add(
                    item=".plc.json",
                    action="无需修复",
                    destructive=False,
                    status="skipped",
                    detail=f"字段完整，无需补全: {plc_json_path}",
                )
            return

        # 未找到 .plc.json，创建新的
        # V0.2.1-P2-9: 从 .copier-answers.yml 读取元数据
        copier_meta = self._read_copier_answers_meta(project_path)
        effective_name = copier_meta.get("project_id", project_id)
        effective_desc = copier_meta.get("description", project_name)
        effective_version = copier_meta.get("version", "V1.0.0")

        # V0.2.1-P1-5: 根据项目模式决定 .plc.json 创建位置
        plc_json_path = self._get_plc_json_create_path(project_path)
        content = self._minimal_plc_json(
            effective_name,
            effective_desc,
            project_path=project_path,
            plc_json_path=plc_json_path,
            version=effective_version,
        )
        if not dry_run:
            from auto_pm.utils.file_utils import write_file

            write_file(plc_json_path, content)
            result.add(
                item=".plc.json",
                action="创建 .plc.json",
                destructive=False,
                status="fixed",
                detail=f"已创建 .plc.json: name={effective_name}, path={plc_json_path}",
            )
        else:
            result.add(
                item=".plc.json",
                action="[DRY-RUN] 创建 .plc.json",
                destructive=False,
                status="skipped",
                detail=f"将创建: {plc_json_path}",
            )

    @staticmethod
    def _read_copier_answers_meta(project_path: str) -> dict[str, str]:
        """从 .copier-answers.yml 读取项目元数据

        V0.2.1-P2-9: repairer 创建 .plc.json 时同步 .copier-answers.yml 的元数据
        """
        answers_path = os.path.join(project_path, ".copier-answers.yml")
        if not os.path.isfile(answers_path):
            return {}
        try:
            import yaml

            with open(answers_path, encoding="utf-8") as f:
                answers = yaml.safe_load(f) or {}
            return {
                "project_id": answers.get("project_id", ""),
                "project_name": answers.get("project_name", ""),
                "description": answers.get("description", ""),
                "version": answers.get("version", ""),
            }
        except (OSError, Exception):
            return {}

    @staticmethod
    def _get_plc_json_create_path(project_path: str) -> str:
        """根据项目结构决定 .plc.json 的创建位置

        V0.2.1-P1-5: 与模板生成位置对齐
        - standard-project 模板: 02_PLC程序/PLC_ST/.plc.json
        - shared-library/test-suite 模板: .plc.json（项目根）
        - 未知模式: .plc.json（项目根，向后兼容）
        """
        current_plc_dir = os.path.join(project_path, "02_PLC程序", "PLC_ST")
        if os.path.isdir(current_plc_dir):
            return os.path.join(current_plc_dir, ".plc.json")
        nested_plc_dir = os.path.join(project_path, "02_PLC程序", "02_PLC程序")
        if os.path.isdir(nested_plc_dir):
            return os.path.join(nested_plc_dir, ".plc.json")
        # 默认：项目根目录
        return os.path.join(project_path, ".plc.json")

    def _repair_pm_session(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复 PM_SESSION（创建缺失文件）"""
        pm_session_path = os.path.join(project_path, f"PM_SESSION_{project_id}.md")
        content = self._minimal_pm_session(project_id, project_name, project_path)

        if not dry_run:
            from auto_pm.utils.file_utils import write_file

            write_file(pm_session_path, content)
        result.add(
            item="PM_SESSION",
            action=f"创建 PM_SESSION_{project_id}.md",
            destructive=False,
            status="fixed",
            detail="已创建最小 PM_SESSION 骨架",
        )

    def _repair_spec_snapshot(
        self,
        project_path: str,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复 Spec Snapshot 版本漂移

        读取 PM_SESSION 中的 Spec Snapshot 表格，对比 spec_registry.json，
        将漂移的版本号更新为注册表中的最新版本。

        Args:
            project_path: 项目根目录绝对路径
            result: 修复结果对象
            dry_run: 仅预览不执行
        """
        from auto_pm.plc.spec_snapshot import (
            compare_versions,
            ensure_spec_snapshot_section,
            load_spec_registry,
            parse_spec_snapshot,
            update_spec_snapshot,
        )

        # 1. 查找 PM_SESSION 文件路径
        project_id = self._checker.resolve_project_id(project_path)
        pm_session_path = os.path.join(project_path, f"PM_SESSION_{project_id}.md")

        if not os.path.isfile(pm_session_path):
            # PM_SESSION 不存在，跳过（由 _repair_pm_session 处理）
            result.add(
                item="Spec Snapshot",
                action="修复 Spec Snapshot 版本漂移",
                destructive=False,
                status="skipped",
                detail="PM_SESSION 文件不存在，跳过",
            )
            return

        # 2. 解析 Spec Snapshot 并加载注册表
        registry = load_spec_registry(self.workspace_root)
        snapshot = parse_spec_snapshot(pm_session_path)

        # 3. 边界情况：registry 缺失时无法修复
        if registry is None:
            result.add(
                item="Spec Snapshot",
                action="修复 Spec Snapshot 版本漂移",
                destructive=False,
                status="skipped",
                detail="spec_registry.json 不可用，无法修复",
            )
            return

        # 4. Spec Snapshot 缺失时，补齐基线章节而不是直接跳过
        if not snapshot:
            spec_ids = self._select_spec_snapshot_baseline(registry)
            detail = f"将补齐 Spec Snapshot 区块，写入 {len(spec_ids)} 条规范基线"
            if dry_run:
                result.add(
                    item="Spec Snapshot",
                    action="[DRY-RUN] 补齐 Spec Snapshot 区块",
                    destructive=False,
                    status="skipped",
                    detail=detail,
                )
                return

            success = ensure_spec_snapshot_section(
                pm_session_path,
                registry,
                spec_ids=spec_ids,
            )
            result.add(
                item="Spec Snapshot",
                action="补齐 Spec Snapshot 区块",
                destructive=False,
                status="fixed" if success else "failed",
                detail=detail if success else "写入 Spec Snapshot 区块失败",
            )
            return

        # 5. 对比版本，获取漂移项
        drifts = compare_versions(snapshot, registry)

        if not drifts:
            result.add(
                item="Spec Snapshot",
                action="修复 Spec Snapshot 版本漂移",
                destructive=False,
                status="skipped",
                detail="无版本漂移，无需修复",
            )
            return

        # 6. 构造漂移描述
        drift_descs = [f"{d.spec_id} {d.snapshot_version}→{d.registry_version}" for d in drifts]
        drift_summary = ", ".join(drift_descs)

        # 7. 执行修复或预览
        if dry_run:
            result.add(
                item="Spec Snapshot",
                action="[DRY-RUN] 更新 Spec Snapshot 版本号",
                destructive=False,
                status="skipped",
                detail=f"将更新 {len(drifts)} 条规范版本: {drift_summary}",
            )
            return

        # 8. 调用公共函数更新 PM_SESSION（V0.3.2 提取为 spec_snapshot.update_spec_snapshot）
        success = update_spec_snapshot(pm_session_path, drifts)
        if success:
            result.add(
                item="Spec Snapshot",
                action="更新 Spec Snapshot 版本号",
                destructive=False,
                status="fixed",
                detail=f"更新 {len(drifts)} 条规范版本: {drift_summary}",
            )
        else:
            result.add(
                item="Spec Snapshot",
                action="更新 Spec Snapshot 版本号",
                destructive=False,
                status="failed",
                detail=f"写入 PM_SESSION 失败或无内容变更: {drift_summary}",
            )

    @staticmethod
    def _select_spec_snapshot_baseline(registry: dict[str, str]) -> list[str]:
        preferred_ids = [
            "PM-042",
            "DEV-001",
            "PROJ-016",
            "LSP-905",
            "LSP-906",
            "LSP-907",
            "TOOL-908",
            "STD-850",
            "STD-901",
        ]
        selected = [spec_id for spec_id in preferred_ids if spec_id in registry]
        return selected or sorted(registry)

    def _repair_prd_dir(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复 PRD 目录（创建缺失目录）"""
        prd_path = os.path.join(project_path, PRD_DIR)
        if not dry_run:
            os.makedirs(prd_path, exist_ok=True)
        result.add(
            item="PRD 目录",
            action="创建 PRD/ 目录",
            destructive=False,
            status="fixed",
            detail="已创建 PRD/ 目录",
        )

    def _repair_prd_doc(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        doc_name: str,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复 PRD 文档（创建缺失文档）"""
        prd_path = self._resolve_prd_path(project_path)
        doc_path = os.path.join(prd_path, doc_name)
        content = self._minimal_prd_doc(doc_name, project_id, project_name)

        if not dry_run:
            from auto_pm.utils.file_utils import write_file

            write_file(doc_path, content)
        # 使用实际目录名构造 item 名，兼容 PRD 和 00_程序方案 等命名
        prd_dir_name = os.path.basename(prd_path)
        result.add(
            item=f"{prd_dir_name}/{doc_name}",
            action=f"创建 {doc_name}",
            destructive=False,
            status="fixed",
            detail=f"已创建最小 {doc_name} 骨架",
        )

    def _repair_std_dir(
        self,
        project_path: str,
        dir_name: str,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复标准目录（创建缺失目录）"""
        dir_path = os.path.join(project_path, dir_name)
        if not dry_run:
            os.makedirs(dir_path, exist_ok=True)
        result.add(
            item=f"目录 {dir_name}",
            action=f"创建目录 {dir_name}",
            destructive=False,
            status="fixed",
            detail=f"已创建目录 {dir_name}",
        )

    def _repair_fb_prd_doc(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        item: CheckItem,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复 FB 模块 PRD 四件套"""
        m = re.search(r"FB PRD \[([^\]]+)\](?:/(\w+))?", item.item)
        if not m:
            return
        fb_dir_name = m.group(1)
        doc_type = m.group(2)

        plc_st_path = os.path.join(project_path, "02_PLC程序", "PLC_ST")
        if not os.path.isdir(plc_st_path):
            plc_st_path = os.path.join(project_path, "PLC_ST")

        module_dir = os.path.join(plc_st_path, fb_dir_name)
        prd_dir = os.path.join(module_dir, "PRD")

        if not dry_run:
            os.makedirs(prd_dir, exist_ok=True)

        fb_identifier = fb_dir_name.split("_", 1)[-1] if "_" in fb_dir_name else fb_dir_name

        type_to_filename = {
            "IFC": f"接口文档_IFC-{fb_identifier}.md",
            "DSN": f"详细设计说明书_DSN-{fb_identifier}.md",
            "CHG": f"变更记录_CHG-{fb_identifier}.md",
            "UM": f"使用说明_UM-{fb_identifier}.md",
        }

        types_to_create = (
            [doc_type] if doc_type in type_to_filename else list(type_to_filename.keys())
        )

        for dt in types_to_create:
            fn = type_to_filename[dt]
            target_path = os.path.join(prd_dir, fn)
            if not os.path.exists(target_path):
                content = f"# {dt} - {fb_identifier}\n\n> 项目编号: {project_id}\n> 模块: {fb_dir_name}\n\n## 1. 概述\n待补充\n"
                if not dry_run:
                    from auto_pm.utils.file_utils import write_file

                    write_file(target_path, content)
                result.add(
                    item=f"FB PRD [{fb_dir_name}]/{dt}",
                    action=f"创建 {fn}",
                    destructive=False,
                    status="fixed",
                    detail=f"已创建最小 {dt} 骨架",
                )

    def _repair_hmi_mapping(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """修复 HMI 点表映射文件 (hmi_tag_mapping.json)"""
        hmi_dir = os.path.join(project_path, "03_HMI设计")
        target_path = os.path.join(hmi_dir, "hmi_tag_mapping.json")

        if os.path.exists(target_path):
            return

        if not dry_run:
            os.makedirs(hmi_dir, exist_ok=True)
            mapping_data = {
                "project_id": project_id,
                "project_name": project_name,
                "version": "V1.0.0",
                "mappings": {
                    "D100": {
                        "name": "GlobalStatusWord",
                        "type": "WORD",
                        "block": "GlobalVars.stGlobal.iStep",
                        "description": "全局状态字",
                    },
                    "D110": {
                        "name": "ActiveAlarmCode",
                        "type": "DINT",
                        "block": "GlobalVars.stGlobal.iAlarmCode",
                        "description": "当前首出报警代码",
                    },
                    "M100": {
                        "name": "AutoRunStart",
                        "type": "BOOL",
                        "block": "GlobalVars.stGlobal.bAutoRunning",
                        "description": "自动运行启动",
                    },
                    "M102": {
                        "name": "SystemReset",
                        "type": "BOOL",
                        "block": "GlobalVars.stGlobal.bReset",
                        "description": "系统故障复位",
                    },
                },
            }
            from auto_pm.utils.file_utils import write_file

            write_file(target_path, json.dumps(mapping_data, indent=2, ensure_ascii=False) + "\n")

        result.add(
            item="HMI 交互原型",
            action="创建 hmi_tag_mapping.json",
            destructive=False,
            status="fixed",
            detail="已补齐 hmi_tag_mapping.json 点表字典骨架",
        )

    def _repair_rename(
        self,
        project_path: str,
        item: CheckItem,
        result: RepairResult,
        dry_run: bool,
    ) -> None:
        """执行文件重命名（破坏性操作）"""
        # 从检查项消息中解析实际文件名
        message = item.message
        match = re.search(r"实际文件: (.+)", message)
        if not match:
            result.add(
                item=item.item,
                action="重命名文件",
                destructive=True,
                status="failed",
                detail=f"无法解析实际文件名: {message}",
            )
            return

        actual_filename = match.group(1).strip()
        prd_path = self._resolve_prd_path(project_path)
        old_path = os.path.join(prd_path, actual_filename)

        # 推断标准名
        std_name = None
        for sn, rule in NAMING_RULES.items():
            if any(re.search(p, actual_filename) for p in rule["patterns"]):
                std_name = sn
                break

        if std_name is None:
            result.add(
                item=item.item,
                action="重命名文件",
                destructive=True,
                status="failed",
                detail=f"无法匹配标准命名: {actual_filename}",
            )
            return

        new_path = os.path.join(prd_path, std_name)

        if not dry_run:
            try:
                backup_path = old_path + ".bak"
                shutil.copy2(old_path, backup_path)
                os.rename(old_path, new_path)
                result.add(
                    item=item.item,
                    action=f"重命名 {actual_filename} → {std_name}",
                    destructive=True,
                    status="fixed",
                    detail=f"已重命名（备份: {os.path.basename(backup_path)}）",
                )
            except OSError as e:
                result.add(
                    item=item.item,
                    action="重命名文件",
                    destructive=True,
                    status="failed",
                    detail=f"重命名失败: {e}",
                )
        else:
            result.add(
                item=item.item,
                action=f"[DRY-RUN] 重命名 {actual_filename} → {std_name}",
                destructive=True,
                status="skipped",
                detail="dry_run 模式，未执行",
            )

    @staticmethod
    def _update_references(prd_path: str, old_name: str, new_name: str) -> list[str]:
        """更新 PRD 目录内其他文档中对旧文件名的引用"""
        updates: list[str] = []
        try:
            for f in os.listdir(prd_path):
                if not f.endswith(".md") or f == new_name:
                    continue
                fpath = os.path.join(prd_path, f)
                try:
                    with open(fpath, encoding="utf-8") as fh:
                        content = fh.read()
                    if old_name in content:
                        new_content = content.replace(old_name, new_name)
                        from auto_pm.utils.file_utils import write_file

                        write_file(fpath, new_content)
                        updates.append(f"{f}: {old_name} → {new_name}")
                except OSError:
                    pass
        except OSError:
            pass
        return updates

    # ── 最小模板 ──────────────────────────────────────────

    @staticmethod
    def _minimal_plc_json(
        project_id: str,
        project_name: str,
        project_path: str = "",
        plc_json_path: str = "",
        version: str = "V1.0.0",
    ) -> str:
        """生成最小 .plc.json 内容

        Args:
            project_id: 项目ID
            project_name: 项目名称（或描述）
            project_path: 项目根目录，用于计算 SysLib 相对路径。
            plc_json_path: .plc.json 文件所在路径。
            version: 项目版本（V0.2.1-P2-9: 从 .copier-answers.yml 同步）
        """
        libraries_path = "../01_SharedLibraries/SysLib"
        if project_path and plc_json_path:
            plc_json_dir = os.path.dirname(plc_json_path)
            syslib_path = os.path.join(
                os.path.dirname(project_path), "01_SharedLibraries", "SysLib"
            )
            libraries_path = os.path.relpath(syslib_path, plc_json_dir).replace("\\", "/")

        return (
            json.dumps(
                {
                    "name": project_id,
                    "description": project_name,
                    "version": version,
                    "libraries": [libraries_path],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )

    @staticmethod
    def _minimal_pm_session(project_id: str, project_name: str, project_root: str) -> str:
        """生成最小 PM_SESSION 内容"""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""# PM_SESSION_{project_id}

## 0. Meta
- project_id: {project_id}
- project_name: {project_name}
- project_root: {project_root}
- last_updated: {today}
- owners: 待填写

## 1. Positioning（项目定位）
- one_liner: 待填写
- users: 待填写
- non_goals: 待填写

## 2. Current Focus（当前焦点）
- current_focus: 项目初始化
- milestone: V1.0.0
- acceptance: 待定义

## 3. Status Summary（当前状态摘要）
- in_progress:
  - 项目骨架搭建
- next_up:
  - 需求分析
- open_questions:
  - 待整理
- risks_dependencies:
  - 待评估
- spec_compliance:
  - last_check: {today}
  - result: 待检查

## 4. Artifacts Index（文档索引）
- req: {PRD_DIR}/需求分析文档_REQ.md
- int: {PRD_DIR}/接口文档_INT.md
- dsn: {PRD_DIR}/详细设计说明书_DSN.md
- tec: {PRD_DIR}/技术方案文档_TEC.md

## 5. Logs（按事件沉淀）
- change_log:
  - {today} 项目初始化，骨架创建

## 6. Implementation Log
- {today} | skill=auto-pm | mode=自动修复
  - goal: 补全缺失的 PM_SESSION
  - changed_files: PM_SESSION_{project_id}.md
  - impact: 项目管理会话文件就绪
  - risks: 无
"""

    @staticmethod
    def _minimal_prd_doc(doc_name: str, project_id: str, project_name: str) -> str:
        """生成最小 PRD 文档内容"""
        today = datetime.now().strftime("%Y-%m-%d")
        doc_type = doc_name.replace(".md", "")
        return f"""# {doc_type} - {project_id} {project_name}

> 项目编号: {project_id}
> 项目名称: {project_name}
> 创建日期: {today}

## 1. 概述
待补充

## 2. 变更记录
| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| {today} | V1.0.0 | 初始版本 | auto-pm |
"""
