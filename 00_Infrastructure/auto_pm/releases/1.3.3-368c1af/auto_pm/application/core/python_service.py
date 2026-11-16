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
import re
import shutil
import time
import tomllib
from pathlib import Path
from typing import Any

import jinja2
import yaml

from auto_pm.application.core.paths import PG_INITIATING_DIR, PYTHON_REQUIRED_DIRS

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

# 合法包名：与 templates/python-tool/copier.yml 的 package_name 校验一致
_PACKAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def derive_package_name(project_name: str, project_id: str) -> str:
    """未显式给包名时推导默认 Python 包名

    项目名能直接当包名（如 "Data Tool" → data_tool）时沿用项目名；
    否则（中文名等）与 project create 一致，按模板默认值取项目号（SW-2026-901 → sw_2026_901）。
    """
    candidate = project_name.strip().replace(" ", "_").replace("-", "_").lower()
    if _PACKAGE_NAME_RE.match(candidate):
        return candidate
    return project_id.replace("-", "_").lower()


# 没渲染的 Jinja 占位符（TD-SW008-566）：`{{ 变量 }}` 或 `{% 语句 %}`。`{{.变量}}` 是 go-task 自己的写法，不算。
_UNRENDERED_RE = re.compile(r"\{\{-?\s*(?!\.)[^{}\n]*\}\}|\{%.*?%\}")
# repair 会写、check 要查内容的文本文件
_RENDERED_FILES = ("pyproject.toml", "README.md", "Taskfile.yml", ".copier-answers.yml", "tests/conftest.py")
# 找现成包目录时跳过的目录
_NOT_A_PACKAGE = {"tests", "test", "docs", "build", "dist", "venv", "env", "node_modules"}
# 模板里没有 copier.yml 时用的默认值（与 templates/python-tool/copier.yml 一致）
_FALLBACK_DEFAULTS = {"author": "fubai", "version": "0.1.0", "stack": "python", "mode": "", "business_line": ""}


def find_unrendered(text: str) -> list[str]:
    """文本里没渲染的模板占位符（原样返回，最多前几处由调用方截）"""
    return _UNRENDERED_RE.findall(text)


def declared_packages(pyproject_text: str) -> list[str]:
    """pyproject 里 hatch wheel 声明的包目录；读不出来时返回空列表"""
    try:
        data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError:
        return []
    wheel = data.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {})
    packages = wheel.get("packages", []) if isinstance(wheel, dict) else []
    return [str(p) for p in packages if isinstance(p, str)]


def _existing_package(project_path: str) -> str:
    """项目根下唯一一个现成的 Python 包目录（有 __init__.py、名字合法）；没有或不止一个时返回空串"""
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        return ""
    found = [
        e for e in entries
        if e not in _NOT_A_PACKAGE and not e.startswith((".", "_")) and _PACKAGE_NAME_RE.match(e)
        and os.path.isfile(os.path.join(project_path, e, "__init__.py"))
    ]
    return found[0] if len(found) == 1 else ""


def _jinja_env() -> jinja2.Environment:
    """和 copier 一样的少量过滤器；变量缺了直接报错，不留半渲染的文件"""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    env.filters["strftime"] = lambda fmt: time.strftime(fmt)
    env.filters["to_nice_yaml"] = lambda value: yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    return env


def _template_context(tpl_path: str, answers: dict[str, Any]) -> dict[str, Any]:
    """模板变量：已知答案优先，其余按模板 copier.yml 的默认值依次渲染（与 copier 建项目时同一套值）"""
    context: dict[str, Any] = dict(answers)
    copier_yml = os.path.join(os.path.dirname(tpl_path), "copier.yml")
    questions: dict[str, Any] = {}
    try:
        with open(copier_yml, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        if isinstance(loaded, dict):
            questions = loaded
    except (OSError, yaml.YAMLError):
        questions = {}
    env = _jinja_env()
    for name, spec in questions.items():
        if name.startswith("_") or name in context or not isinstance(spec, dict) or "default" not in spec:
            continue
        default = spec["default"]
        if isinstance(default, str):
            try:
                default = env.from_string(default).render(context)
            except jinja2.TemplateError:
                continue
        context[name] = default
    for name, value in _FALLBACK_DEFAULTS.items():
        context.setdefault(name, value)
    context.setdefault("description", context.get("project_name", ""))
    context["_copier_answers"] = {k: v for k, v in context.items() if not k.startswith("_")} | {"_src_path": "templates/python-tool"}
    return context


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
            self.templates_dir = found_tpl or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "templates")

    def check_project_spec(self, project_path: str, project_id: str) -> dict[str, Any]:
        """检查单个 Python 项目规范 (CODE-210/211/220)"""
        checks: list[dict[str, Any]] = []

        # 1. 必需文件检查
        for fname in _REQUIRED_FILES:
            fpath = os.path.join(project_path, fname)
            ok = os.path.isfile(fpath)
            checks.append({
                "name": f"文件: {fname}",
                "ok": ok,
                "detail": "" if ok else "文件不存在",
            })

        # 2. 必需目录检查
        for dname in _REQUIRED_DIRS:
            dpath = os.path.join(project_path, dname)
            ok = os.path.isdir(dpath)
            checks.append({
                "name": f"目录: {dname}",
                "ok": ok,
                "detail": "" if ok else "目录不存在",
            })

        # 3. pyproject.toml 基本字段检查
        pyproject_path = os.path.join(project_path, "pyproject.toml")
        if os.path.isfile(pyproject_path):
            try:
                with open(pyproject_path, encoding="utf-8") as f:
                    content = f.read()
                has_name = "name" in content
                has_version = "version" in content
                has_python = "requires-python" in content
                checks.append({
                    "name": "pyproject.toml: name 字段",
                    "ok": has_name,
                    "detail": "" if has_name else "缺少 name 字段",
                })
                checks.append({
                    "name": "pyproject.toml: version 字段",
                    "ok": has_version,
                    "detail": "" if has_version else "缺少 version 字段",
                })
                checks.append({
                    "name": "pyproject.toml: requires-python 字段",
                    "ok": has_python,
                    "detail": "" if has_python else "缺少 requires-python 字段",
                })
            except OSError:
                checks.append({
                    "name": "pyproject.toml 读取",
                    "ok": False,
                    "detail": "读取失败",
                })

        # 4. tests/conftest.py 检查
        tests_dir = os.path.join(project_path, "tests")
        if os.path.isdir(tests_dir):
            has_conftest = os.path.isfile(os.path.join(tests_dir, "conftest.py"))
            checks.append({
                "name": "tests/conftest.py",
                "ok": has_conftest,
                "detail": "" if has_conftest else "缺少 conftest.py",
            })

        # 5. PM_SESSION 文件检查
        pm_session_found = False
        try:
            for entry in os.listdir(project_path):
                if entry.startswith("PM_SESSION_") and entry.endswith(".md"):
                    pm_session_found = True
                    break
        except OSError:
            pass
        checks.append({
            "name": "PM_SESSION 文件",
            "ok": pm_session_found,
            "detail": "" if pm_session_found else "缺少 PM_SESSION_*.md",
        })

        # 6. 内容检查（TD-SW008-566）：只查文件在不在会把留着占位符的半成品判成合格
        checks.extend(self._content_checks(project_path))

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

    @staticmethod
    def _content_checks(project_path: str) -> list[dict[str, Any]]:
        """没渲染的模板占位符、pyproject 声明的包目录是否真的存在"""
        names = list(_RENDERED_FILES)
        try:
            names += sorted(e for e in os.listdir(project_path) if e.startswith("PM_SESSION_") and e.endswith(".md"))
        except OSError:
            pass
        leftovers: list[str] = []
        for name in names:
            path = os.path.join(project_path, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    found = find_unrendered(f.read())
            except (OSError, UnicodeDecodeError):
                continue
            if found:
                leftovers.append(f"{name} {len(found)} 处（如 {found[0]}）")
        result = [{
            "name": "没渲染的模板占位符",
            "ok": not leftovers,
            "detail": "；".join(leftovers),
        }]
        pyproject_path = os.path.join(project_path, "pyproject.toml")
        if os.path.isfile(pyproject_path):
            try:
                with open(pyproject_path, encoding="utf-8") as f:
                    packages = declared_packages(f.read())
            except (OSError, UnicodeDecodeError):
                packages = []
            if packages:
                missing = [p for p in packages if not os.path.isdir(os.path.join(project_path, p))]
                result.append({
                    "name": "pyproject.toml: 声明的包目录存在",
                    "ok": not missing,
                    "detail": f"声明了不存在的包目录: {'、'.join(missing)}" if missing else "",
                })
        return result

    def repair_project_spec(self, project_path: str, project_id: str, dry_run: bool = False) -> list[str]:
        """修复单个 Python 项目规范问题"""
        repaired_items: list[str] = []
        tpl_path = os.path.join(self.templates_dir, "python-tool", "template")

        # 确定元数据
        project_name = os.path.basename(project_path)
        if "_" in project_name:
            # 类似 "SW-2026-008_auto-pm_自动化项目管理工具"
            parts = project_name.split("_", 1)
            project_name = parts[1]
        # 读取现有的 copier answers 或其他元数据以尽可能还原
        answers: dict[str, Any] = {}
        answers_path = os.path.join(project_path, ".copier-answers.yml")
        if os.path.isfile(answers_path):
            try:
                with open(answers_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                if isinstance(loaded, dict):
                    answers = {k: v for k, v in loaded.items() if isinstance(k, str) and not k.startswith("_")}
            except (OSError, yaml.YAMLError) as e:
                log.warning("读取 .copier-answers.yml 失败: %s: %s", answers_path, e)
        project_id = str(answers.get("project_id") or project_id)
        project_name = str(answers.get("project_name") or project_name)
        # 包名：答案里有就用；没有时先认项目里唯一的现成包，再按项目名推导（TD-SW008-566：不声明不存在的包）
        package_name = str(answers.get("package_name") or _existing_package(project_path)
                           or derive_package_name(project_name, project_id))
        cli_command = str(answers.get("cli_command") or package_name.replace("_", "-"))
        known = answers | {"project_id": project_id, "project_name": project_name,
                           "package_name": package_name, "cli_command": cli_command}

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

        context = _template_context(tpl_path, known)
        env = _jinja_env()

        def render_jinja_file(src_name: str, dst_name: str) -> None:
            # TD-SW008-566：真用 Jinja 渲染（以前只替换 4 个变量，version 等 5 处原样留下还报“修好了”）。
            # 渲染不了（变量缺失、语法错）就不写，如实报“没修”。
            src = os.path.join(tpl_path, src_name)
            dst = os.path.join(project_path, dst_name)
            if not os.path.isfile(src) or os.path.exists(dst):
                return
            try:
                with open(src, encoding="utf-8") as sf:
                    content = env.from_string(sf.read()).render(context)
            except (OSError, jinja2.TemplateError) as e:
                log.warning("渲染模板失败: %s: %s", src, e)
                repaired_items.append(f"Not repaired {dst_name}: 模板渲染失败（{e}）")
                return
            leftover = find_unrendered(content)
            if leftover:
                repaired_items.append(f"Not repaired {dst_name}: 渲染后还有占位符 {leftover[0]}")
                return
            if not dry_run:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
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
            render_jinja_file(
                "PM_SESSION_{{ project_id }}.md.jinja",
                f"PM_SESSION_{project_id}.md"
            )

        # pyproject 声明的包目录（TD-SW008-566）：不存在就照模板建一个只有 __init__.py 的包，不声明空包
        pyproject_path = os.path.join(project_path, "pyproject.toml")
        if os.path.isfile(pyproject_path):
            with open(pyproject_path, encoding="utf-8") as f:
                packages = declared_packages(f.read())
        else:
            packages = [package_name] if any(i == "Restored rendered file pyproject.toml" for i in repaired_items) else []
        for package in packages:
            if not os.path.isdir(os.path.join(project_path, package)):
                render_jinja_file(os.path.join("{{ package_name }}", "__init__.py.jinja"), os.path.join(package, "__init__.py"))
                if not os.path.isfile(os.path.join(tpl_path, "{{ package_name }}", "__init__.py.jinja")):
                    if not dry_run:
                        os.makedirs(os.path.join(project_path, package), exist_ok=True)
                        with open(os.path.join(project_path, package, "__init__.py"), "w", encoding="utf-8") as f:
                            f.write(f'"""{project_name}"""\n')
                    repaired_items.append(f"Created package {package}/__init__.py")

        return repaired_items
