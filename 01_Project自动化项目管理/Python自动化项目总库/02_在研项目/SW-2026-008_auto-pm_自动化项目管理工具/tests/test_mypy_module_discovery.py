"""TD-SW008-122：`mypy .` 的模块发现不能被模板里的 `logging` 目录遮蔽标准库。

根因：`templates/python-tool/template/{{ package_name }}/logging/` 的上级目录名不是合法标识符，
mypy 不把它当包，就把里面的 `logging` 当成顶层模块，于是全仓每个 `import logging` 都被遮蔽
（`Module has no attribute "getLogger"`）。修法：`[tool.mypy] exclude` 整个模板目录。
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
SHADOWED = "import logging\nlog = logging.getLogger(__name__)\n"


def _mypy_exclude() -> list[str]:
    data = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8", errors="replace"))
    return list(data["tool"]["mypy"]["exclude"])


def test_every_template_directory_with_a_jinja_name_is_excluded_from_mypy() -> None:
    patterns = [re.compile(item) for item in _mypy_exclude()]
    templated = [
        path.relative_to(PROJECT).as_posix() + "/"
        for path in (PROJECT / "templates").rglob("*")
        if path.is_dir() and "{{" in path.name
    ]
    assert templated, "模板里应当还有 {{ package_name }} 这类目录，否则这条守卫已经没有对象"
    unexcluded = [item for item in templated if not any(p.search(item) for p in patterns)]
    assert unexcluded == []


def _run_mypy(root: Path, exclude: str) -> str:
    (root / "mypy.ini").write_text(
        f"[mypy]\nexclude = {exclude}\nignore_missing_imports = True\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental", "--cache-dir", str(root / ".cache"), "."],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root, check=False,
    )
    return result.stdout


@pytest.mark.needs_quality_tools
def test_a_jinja_named_logging_directory_shadows_the_stdlib_unless_excluded(tmp_path: Path) -> None:
    """复现根因，并证明 exclude 能除掉它。"""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "service.py").write_text(SHADOWED, encoding="utf-8")
    shadow = tmp_path / "templates" / "{{ package_name }}" / "logging"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text("", encoding="utf-8")

    assert 'Module has no attribute "getLogger"' in _run_mypy(tmp_path, "^$")
    assert "getLogger" not in _run_mypy(tmp_path, "^templates/")
