from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.quality_tools_gate import ALLOW_SKIP_ENV, skip_reason


def test_missing_tools_without_the_opt_in_variable_is_not_skipped() -> None:
    assert skip_reason(["ruff"], {}) is None
    assert skip_reason(["mypy"], {"CI": "true"}) is None
    assert skip_reason(["ruff", "mypy"], {ALLOW_SKIP_ENV: "0"}) is None


def test_skip_needs_both_missing_tools_and_the_opt_in_variable() -> None:
    assert skip_reason([], {ALLOW_SKIP_ENV: "1"}) is None
    reason = skip_reason(["ruff"], {ALLOW_SKIP_ENV: "1"})
    assert reason is not None and "ruff" in reason


def test_quality_gate_tests_fail_when_tools_are_missing_and_not_opted_in(tmp_path: Path) -> None:
    """端到端钉住：缺依赖又没设变量时，被标记的测试结果是失败而不是跳过。"""
    project = Path(__file__).resolve().parents[1]
    # 一个把 ruff/mypy 都"藏"起来的解释器环境：用 sitecustomize 让 find_spec 找不到它们
    (tmp_path / "sitecustomize.py").write_text(
        "import importlib.machinery as m, importlib.util as u\n"
        "_orig = u.find_spec\n"
        "def find_spec(name, package=None):\n"
        "    if name in ('ruff', 'mypy'):\n"
        "        return None\n"
        "    return _orig(name, package)\n"
        "u.find_spec = find_spec\n",
        encoding="utf-8",
    )
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import pytest\n\n"
        "@pytest.mark.needs_quality_tools\n"
        "def test_probe():\n"
        "    raise AssertionError('quality gate ran')\n",
        encoding="utf-8",
    )
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        "import os\nimport pytest\n"
        "from tests.quality_tools_gate import missing_quality_modules, skip_reason\n\n"
        "def pytest_collection_modifyitems(items):\n"
        "    reason = skip_reason(missing_quality_modules(), os.environ)\n"
        "    if reason:\n"
        "        for item in items:\n"
        "            if 'needs_quality_tools' in item.keywords:\n"
        "                item.add_marker(pytest.mark.skip(reason=reason))\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k not in (ALLOW_SKIP_ENV, "PYTEST_ADDOPTS")}
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(project)])

    def run(extra: dict[str, str]) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-p", "no:cacheprovider",
             "-c", str(tmp_path / "pytest.ini"), "--rootdir", str(tmp_path), "-q"],
            capture_output=True, text=True, env={**env, **extra}, cwd=tmp_path, check=False,
        )
        return result.stdout

    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    needs_quality_tools: x\n", encoding="utf-8")
    assert "1 failed" in run({})
    assert "1 skipped" in run({ALLOW_SKIP_ENV: "1"})
