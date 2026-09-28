from __future__ import annotations

import re
from pathlib import Path


def _prototype_path() -> Path:
    workspace = Path(__file__).resolve().parents[6]
    return workspace / "SYS-2026-001_WorkspaceGovernance/01_项目文档/prototypes/pm-flow-v2.html"


def _prototype_html() -> str:
    return _prototype_path().read_text(encoding="utf-8", errors="replace")


def test_u01_prototype_declares_demo_data_and_five_reachable_states() -> None:
    html = _prototype_html()

    assert 'data-demo="true"' in html
    assert "演示数据" in html
    for state in ("new-goal", "confirm", "executing", "recovery", "acceptance"):
        assert f'id="page-{state}"' in html


def test_u01_prototype_has_no_navigation_or_inline_function_dead_links() -> None:
    html = _prototype_html()
    pages = set(re.findall(r'id=["\']page-([a-z-]+)["\']', html))
    navigation_targets = set(re.findall(r"goPage\(['\"]([a-z-]+)['\"]\)", html))
    assert navigation_targets <= pages

    defined_functions = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", html))
    called_functions = set(re.findall(r'onclick=["\']\s*([A-Za-z_$][\w$]*)\s*\(', html))
    assert called_functions <= defined_functions
