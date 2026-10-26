"""真实质量门测试对 ruff/mypy 的依赖判定（默认缺依赖即红，显式环境变量才允许跳过）。"""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping

ALLOW_SKIP_ENV = "AUTO_PM_ALLOW_SKIP_QUALITY_TOOLS"
REQUIRED_MODULES = ("ruff", "mypy")


def missing_quality_modules() -> list[str]:
    """当前解释器里找不到的质量门模块。"""
    return [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]


def skip_reason(missing: list[str], env: Mapping[str, str]) -> str | None:
    """只有缺依赖且显式设了 AUTO_PM_ALLOW_SKIP_QUALITY_TOOLS=1 才返回跳过原因；否则 None（测试照跑，缺依赖就红）。"""
    if not missing or env.get(ALLOW_SKIP_ENV) != "1":
        return None
    return f"当前解释器缺 {'/'.join(missing)}，已按 {ALLOW_SKIP_ENV}=1 跳过真实质量门测试"
