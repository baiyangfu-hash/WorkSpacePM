"""PLC-HMI 概念映射：SFB 库函数（模板引擎（Copier 模板管理/项目模板应用））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

Copier 模板调度 Service

封装 copier 的 copy/update API，提供项目初始化和模板增量更新能力。
模板存放在项目根目录的 templates/ 下。
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


class TemplateService:
    """Copier 模板调度 Service"""

    def __init__(self, templates_dir: str) -> None:
        """初始化

        Args:
            templates_dir: 模板根目录（含 plc-standard/ 等子目录）
        """
        self.templates_dir = os.path.abspath(templates_dir)

    # ── 模板列表 ──────────────────────────────────────────

    def list_templates(self) -> list[str]:
        """列出所有可用模板

        Returns:
            模板名称列表（templates/ 下的子目录名，含 copier.yml 的）
        """
        if not os.path.isdir(self.templates_dir):
            return []

        templates: list[str] = []
        try:
            for entry in os.listdir(self.templates_dir):
                entry_path = os.path.join(self.templates_dir, entry)
                if os.path.isdir(entry_path) and os.path.isfile(
                    os.path.join(entry_path, "copier.yml")
                ):
                    templates.append(entry)
        except OSError as e:
            log.warning("扫描模板目录失败: %s", e)

        templates.sort()
        return templates

    def get_template_path(self, template_name: str) -> str:
        """获取模板路径

        Args:
            template_name: 模板名称，如 plc-standard

        Returns:
            模板绝对路径

        Raises:
            FileNotFoundError: 模板不存在
        """
        template_path = os.path.join(self.templates_dir, template_name)
        if not os.path.isdir(template_path) or not os.path.isfile(
            os.path.join(template_path, "copier.yml")
        ):
            raise FileNotFoundError(f"模板不存在: {template_name} (路径: {template_path})")
        return template_path

    # ── 项目初始化 ────────────────────────────────────────

    def copy_template(
        self,
        template_name: str,
        dest_path: str,
        data: dict[str, Any],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """使用 Copier 模板生成项目

        Args:
            template_name: 模板名称，如 plc-standard
            dest_path: 目标路径（项目目录）
            data: 模板变量，如 {"project_id": "DJ-2026-010", "project_name": "边框缓存机"}
            overwrite: 是否覆盖已存在的目标

        Returns:
            Copier copy 操作结果

        Raises:
            FileNotFoundError: 模板不存在
            FileExistsError: 目标已存在且 overwrite=False
        """
        # 延迟导入 copier，避免未安装时影响其他功能
        import copier

        template_path = self.get_template_path(template_name)

        if os.path.exists(dest_path) and not overwrite:
            raise FileExistsError(f"目标路径已存在: {dest_path}（使用 overwrite=True 覆盖）")

        log.info(
            "Copier copy: template=%s, dest=%s, data=%s",
            template_name,
            dest_path,
            {k: v for k, v in data.items() if k != "description"},
        )

        copier.run_copy(
            src_path=template_path,
            dst_path=dest_path,
            data=data,
            defaults=True,
            overwrite=overwrite,
            unsafe=True,
        )

        log.info("项目生成完成: %s", dest_path)
        return {"dest_path": dest_path, "template": template_name, "data": data}

    # ── 模板更新 ──────────────────────────────────────────

    def update_template(
        self,
        project_path: str,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """对已有项目执行 Copier 模板增量更新

        Args:
            project_path: 项目目录（需含 .copier-answers.yml）
            overwrite: 是否覆盖冲突文件
            dry_run: 仅预览不实际执行更新，返回模板信息

        Returns:
            Copier update 操作结果；dry_run=True 时返回预览信息

        Raises:
            FileNotFoundError: 项目缺少 .copier-answers.yml
        """
        answers_path = os.path.join(project_path, ".copier-answers.yml")
        if not os.path.isfile(answers_path):
            raise FileNotFoundError(f"项目缺少 .copier-answers.yml，无法更新: {project_path}")

        # 预览模式：仅读取模板信息，不实际执行更新
        if dry_run:
            info = self._read_template_info(project_path)
            log.info(
                "Copier update 预览: project=%s, template=%s", project_path, info.get("template")
            )
            return {"project_path": project_path, "updated": False, "dry_run": True, "info": info}

        import copier

        log.info("Copier update: project=%s, overwrite=%s", project_path, overwrite)

        copier.run_update(
            dst_path=project_path,
            defaults=True,
            overwrite=overwrite,
            unsafe=True,
        )

        log.info("模板更新完成: %s", project_path)
        return {"project_path": project_path, "updated": True}

    def _read_template_info(self, project_path: str) -> dict[str, Any]:
        """从 .copier-answers.yml 读取模板信息（名称/版本/上次更新时间）"""
        import yaml

        answers_path = os.path.join(project_path, ".copier-answers.yml")
        info: dict[str, Any] = {
            "template": "",
            "commit": "",
            "last_updated": "",
        }
        try:
            with open(answers_path, encoding="utf-8") as f:
                answers = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as e:
            log.warning("读取 .copier-answers.yml 失败: %s: %s", project_path, e)
            return info

        src_path = answers.get("_src_path", "")
        # 从 _src_path 提取模板名（如 templates/plc-standard → plc-standard）
        info["template"] = os.path.basename(src_path) if src_path else ""
        info["commit"] = str(answers.get("_commit", ""))
        try:
            mtime = os.path.getmtime(answers_path)
            from datetime import datetime

            info["last_updated"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            info["last_updated"] = ""
        return info
