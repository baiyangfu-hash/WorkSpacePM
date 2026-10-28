"""TD-SW008-056：短路径（auto_pm.core.x）和分层路径（auto_pm.application.core.x）必须是同一个模块对象。"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT = Path(__file__).resolve().parents[1]

PAIRS = [
    ("auto_pm.core", "auto_pm.application.core"),
    ("auto_pm.core.pr_open_service", "auto_pm.application.core.pr_open_service"),
    ("auto_pm.change", "auto_pm.domain.change"),
    ("auto_pm.plc.doc_consistency", "auto_pm.domain.plc.doc_consistency"),
    ("auto_pm.db", "auto_pm.infrastructure.db"),
    ("auto_pm.cli", "auto_pm.ui.cli"),
]


@pytest.mark.parametrize(("short", "layered"), PAIRS)
def test_a01_short_and_layered_paths_are_one_module_object(short: str, layered: str) -> None:
    assert importlib.import_module(short) is importlib.import_module(layered)


def test_a02_a_patch_through_one_path_is_seen_through_the_other() -> None:
    short: Any = importlib.import_module("auto_pm.core.pr_open_service")
    layered: Any = importlib.import_module("auto_pm.application.core.pr_open_service")
    sentinel = object()
    original = layered.JUDGE_RELATIVE
    try:
        short.JUDGE_RELATIVE = sentinel
        assert layered.JUDGE_RELATIVE is sentinel
    finally:
        layered.JUDGE_RELATIVE = original


def _import_order(first: str, second: str) -> str:
    code = (
        f"import importlib; a = importlib.import_module({first!r}); b = importlib.import_module({second!r}); "
        "print(a is b, a.__name__ == b.__name__)"
    )
    done = subprocess.run(  # noqa: S603 - fixed interpreter and literal code
        [sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.mark.parametrize("order", [("auto_pm.core.doc_services", "auto_pm.application.core.doc_services"),
                                   ("auto_pm.application.core.doc_services", "auto_pm.core.doc_services")])
def test_a03_the_import_order_does_not_matter(order: tuple[str, str]) -> None:
    assert _import_order(*order) == "True True"


def test_a04_modules_directly_under_the_package_are_not_aliased() -> None:
    assert importlib.import_module("auto_pm.app_context").__name__ == "auto_pm.app_context"
    assert importlib.import_module("auto_pm.application.core").__name__ == "auto_pm.application.core"


@pytest.mark.parametrize(("short", "layered"), PAIRS)
def test_a05_the_module_keeps_its_own_spec_after_an_alias_import(short: str, layered: str) -> None:
    module = importlib.import_module(short)
    assert module.__spec__ is not None and module.__spec__.name == layered
    assert module.__name__ == layered


def test_a06_relative_imports_inside_an_aliased_package_raise_no_spec_warning() -> None:
    code = (
        "import warnings; warnings.simplefilter('error'); "
        "import auto_pm.spec.core.registry as r; import auto_pm.domain.spec.core.registry as s; "
        "print(r is s)"
    )
    done = subprocess.run(  # noqa: S603 - fixed interpreter and literal code
        [sys.executable, "-c", code], cwd=PROJECT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "True"
