"""Every ``AUTO_PM_*`` environment variable the product reads must be documented in the README table."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIABLE = re.compile(r"AUTO_PM_[A-Z0-9_]+")


def _documented() -> set[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace")
    return {match.group(1) for match in re.finditer(r"^\| `(AUTO_PM_[A-Z0-9_]+)` \|", readme, re.MULTILINE)}


def _read_by_the_product() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted((ROOT / "auto_pm").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in VARIABLE.findall(text):
            found.setdefault(name, path.relative_to(ROOT).as_posix())
    return found


def test_every_variable_the_product_reads_is_in_the_readme_table() -> None:
    documented = _documented()
    missing = {name: where for name, where in _read_by_the_product().items() if name not in documented}

    assert not missing, f"README 的环境变量表缺这些变量: {missing}"


def test_the_readme_table_lists_no_variable_the_product_no_longer_reads() -> None:
    stale = sorted(_documented() - set(_read_by_the_product()) - {"AUTO_PM_START_WATCHDOG_SCALE", "AUTO_PM_ALLOW_SKIP_QUALITY_TOOLS"})

    assert not stale, f"README 列了但代码里已不读取: {stale}"
