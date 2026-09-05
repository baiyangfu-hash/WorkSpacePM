"""PLC-HMI 概念映射：SFB 库函数（Python 项目服务（扫描/创建/管理 Python 项目））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

Python 项目管理服务 - V2.5 交付

提供 Python 项目的规范检查与自动修复功能。
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

import yaml
from auto_pm.core.paths import PG_INITIATING_DIR, PYTHON_REQUIRED_DIRS

log = logging.getLogger(__name__)

# Python 项目规范必需文件（210 规范）
_REQUIRED_FILES = [
    "pyproject.toml",
    "README.md",
    ".copier-answers.yml",
    ".ruff.toml",
    ".pre-commit-config.yaml",
    "Taskfile.yml",
]

# Python 项目规范必需目录（CHG-SCPT-2026-144: 引用集中常量）
_REQUIRED_DIRS = PYTHON_REQUIRED_DIRS


class PythonProjectService:
    """Python 项目规范检查与修复服务"""

    def __init__(self, workspace_root: str, templates_dir: str | None = None) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        if templates_dir:
            self.templates_dir = os.path.abspath(templates_dir)
        else:
            # 动态向上查找包含 templates 目录的根路径
            curr = Path(__file__).resolve()
            found_tpl = ""
            for parent in curr.parents:
                tpl_candidate = parent / "templates"
                if tpl_candidate.is_dir() and (tpl_candidate / "python-tool").is_dir():
                    found_tpl = str(tpl_candidate)
                    break
            self.templates_dir = found_tpl or os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                ),
                "templates",
            )

    def check_project_spec(self, project_path: str, project_id: str) -> dict[str, Any]:
        """检查单个 Python 项目规范 (CODE-210/211/220)"""
        checks: list[dict[str, Any]] = []

        # 1. 必需文件检查
        for fname in _REQUIRED_FILES:
            fpath = os.path.join(project_path, fname)
            ok = os.path.isfile(fpath)
            checks.append(
                {
                    "name": f"文件: {fname}",
                    "ok": ok,
                    "detail": "" if ok else "文件不存在",
                }
            )

        # 2. 必需目录检查
        for dname in _REQUIRED_DIRS:
            dpath = os.path.join(project_path, dname)
            ok = os.path.isdir(dpath)
            checks.append(
                {
                    "name": f"目录: {dname}",
                    "ok": ok,
                    "detail": "" if ok else "目录不存在",
                }
            )

        # 3. pyproject.toml 基本字段检查
        pyproject_path = os.path.join(project_path, "pyproject.toml")
        if os.path.isfile(pyproject_path):
            try:
                with open(pyproject_path, encoding="utf-8") as f:
                    content = f.read()
                has_name = "name" in content
                has_version = "version" in content
                has_python = "requires-python" in content
                checks.append(
                    {
                        "name": "pyproject.toml: name 字段",
                        "ok": has_name,
                        "detail": "" if has_name else "缺少 name 字段",
                    }
                )
                checks.append(
                    {
                        "name": "pyproject.toml: version 字段",
                        "ok": has_version,
                        "detail": "" if has_version else "缺少 version 字段",
                    }
                )
                checks.append(
                    {
                        "name": "pyproject.toml: requires-python 字段",
                        "ok": has_python,
                        "detail": "" if has_python else "缺少 requires-python 字段",
                    }
                )
            except OSError:
                checks.append(
                    {
                        "name": "pyproject.toml 读取",
                        "ok": False,
                        "detail": "读取失败",
                    }
                )

        # 4. tests/conftest.py 检查
        tests_dir = os.path.join(project_path, "tests")
        if os.path.isdir(tests_dir):
            has_conftest = os.path.isfile(os.path.join(tests_dir, "conftest.py"))
            checks.append(
                {
                    "name": "tests/conftest.py",
                    "ok": has_conftest,
                    "detail": "" if has_conftest else "缺少 conftest.py",
                }
            )

        # 5. PM_SESSION 文件检查
        pm_session_found = False
        try:
            for entry in os.listdir(project_path):
                if entry.startswith("PM_SESSION_") and entry.endswith(".md"):
                    pm_session_found = True
                    break
        except OSError:
            pass
        checks.append(
            {
                "name": "PM_SESSION 文件",
                "ok": pm_session_found,
                "detail": "" if pm_session_found else "缺少 PM_SESSION_*.md",
            }
        )

        passed = sum(1 for c in checks if c["ok"])
        total = len(checks)

        return {
            "project_id": project_id,
            "path": project_path,
            "passed": passed,
            "total": total,
            "all_ok": passed == total,
            "checks": checks,
        }

    def repair_project_spec(
        self, project_path: str, project_id: str, dry_run: bool = False
    ) -> list[str]:
        """修复单个 Python 项目规范问题"""
        repaired_items: list[str] = []
        tpl_path = os.path.join(self.templates_dir, "python-tool", "template")

        # 确定元数据
        project_name = os.path.basename(project_path)
        if "_" in project_name:
            # 类似 "SW-2026-008_auto-pm_自动化项目管理工具"
            parts = project_name.split("_", 1)
            project_name = parts[1]
        package_name = project_name.replace(" ", "_").lower()
        cli_command = package_name.replace("_", "-")

        # 读取现有的 copier answers 或其他元数据以尽可能还原
        answers_path = os.path.join(project_path, ".copier-answers.yml")
        if os.path.isfile(answers_path):
            try:
                with open(answers_path, encoding="utf-8") as f:
                    answers = yaml.safe_load(f) or {}
                project_id = answers.get("project_id", project_id)
                project_name = answers.get("project_name", project_name)
                package_name = answers.get("package_name", package_name)
                cli_command = answers.get("cli_command", cli_command)
            except Exception:
                pass

        if not os.path.exists(tpl_path):
            # 向上回溯查找工程根目录下的 templates/python-tool/template
            for parent in Path(__file__).resolve().parents:
                candidate = parent / "templates" / "python-tool" / "template"
                if candidate.is_dir():
                    tpl_path = str(candidate)
                    break

        if not os.path.exists(tpl_path):
            log.warning("Python 模板不存在，跳过物理修复: %s", tpl_path)
            return repaired_items

        # 修复逻辑
        def copy_static_file(src_name: str, dst_name: str) -> None:
            src = os.path.join(tpl_path, src_name)
            dst = os.path.join(project_path, dst_name)
            if os.path.isfile(src) and not os.path.exists(dst):
                if not dry_run:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                repaired_items.append(f"Restored file {dst_name}")

        def render_jinja_file(src_name: str, dst_name: str) -> None:
            src = os.path.join(tpl_path, src_name)
            dst = os.path.join(project_path, dst_name)
            if os.path.isfile(src) and not os.path.exists(dst):
                if not dry_run:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(src, encoding="utf-8") as sf:
                        content = sf.read()
                    # 简单占位符替换以模拟 jinja 渲染
                    content = content.replace("{{ project_id }}", project_id)
                    content = content.replace("{{ project_name }}", project_name)
                    content = content.replace("{{ package_name }}", package_name)
                    content = content.replace("{{ cli_command }}", cli_command)
                    with open(dst, "w", encoding="utf-8") as df:
                        df.write(content)
                repaired_items.append(f"Restored rendered file {dst_name}")

        # 1. 修复必须文件
        copy_static_file(".pre-commit-config.yaml", ".pre-commit-config.yaml")
        copy_static_file(".ruff.toml", ".ruff.toml")
        render_jinja_file(".copier-answers.yml.jinja", ".copier-answers.yml")
        render_jinja_file("Taskfile.yml.jinja", "Taskfile.yml")
        render_jinja_file("README.md.jinja", "README.md")
        render_jinja_file("pyproject.toml.jinja", "pyproject.toml")

        # 2. 修复目录和里面的文件
        # tests/
        tests_dir = os.path.join(project_path, "tests")
        if not os.path.exists(tests_dir):
            if not dry_run:
                os.makedirs(tests_dir, exist_ok=True)
            repaired_items.append("Created directory tests")

        # tests/conftest.py
        conftest = os.path.join(tests_dir, "conftest.py")
        if not os.path.exists(conftest):
            if not dry_run:
                with open(conftest, "w", encoding="utf-8") as f:
                    f.write("# conftest for pytest\n")
            repaired_items.append("Restored tests/conftest.py")

        # 01_启动（CHG-SCPT-2026-146: 5大过程组统一路径，原 00_项目基础信息）
        info_dir = os.path.join(project_path, PG_INITIATING_DIR)
        if not os.path.exists(info_dir):
            if not dry_run:
                os.makedirs(info_dir, exist_ok=True)
            repaired_items.append(f"Created directory {PG_INITIATING_DIR}")

        # PM_SESSION 文件
        # 扫描是否存在 PM_SESSION_*.md
        pm_session_found = False
        try:
            for entry in os.listdir(project_path):
                if entry.startswith("PM_SESSION_") and entry.endswith(".md"):
                    pm_session_found = True
                    break
        except OSError:
            pass
        if not pm_session_found:
            render_jinja_file("PM_SESSION_{{ project_id }}.md.jinja", f"PM_SESSION_{project_id}.md")

        return repaired_items
