"""TD-SW008-163：模板生成的 PM_SESSION §4 文档索引必须指向模板真会生成的文件。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
TEMPLATES = PROJECT / "templates"
INDEX_LINE = re.compile(r"^- (req|int|dsn|tec): (.+)$", re.MULTILINE)
PM_SESSION_TEMPLATES = sorted(TEMPLATES.glob("*/template/PM_SESSION_*.md.jinja"))


def _generated(template_root: Path, relative: str) -> bool:
    """模板里有这个文件（Copier 会去掉 .jinja 后缀）。"""
    target = template_root / relative
    return target.is_file() or target.with_name(target.name + ".jinja").is_file()


def test_pm_session_templates_are_found() -> None:
    assert PM_SESSION_TEMPLATES, "没找到任何 PM_SESSION 模板，这条守卫已失效"


@pytest.mark.parametrize("template", PM_SESSION_TEMPLATES, ids=lambda p: p.parent.parent.name)
def test_artifacts_index_points_at_generated_files(template: Path) -> None:
    text = template.read_text(encoding="utf-8", errors="replace")
    if "Artifacts Index" not in text:
        pytest.skip("该模板的 PM_SESSION 没有文档索引一节")
    entries = INDEX_LINE.findall(text)
    assert entries, f"{template.name} 有文档索引一节却没有 req/int/dsn/tec 条目"
    missing = [
        f"{key}: {path}"
        for key, path in entries
        if path.strip() != "待补充" and not _generated(template.parent, path.strip())
    ]
    assert missing == []


def test_python_tool_docs_do_not_describe_the_old_initiating_directory() -> None:
    """python-tool 的启动文档目录已统一为 01_启动（CHG-SCPT-2026-146），说明文字不能再写旧名。"""
    root = TEMPLATES / "python-tool"
    stale = [
        path.relative_to(root).as_posix()
        for path in [root / "README.md", *(root / "template").rglob("*.md.jinja")]
        if "00_项目基础信息" in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert stale == []
