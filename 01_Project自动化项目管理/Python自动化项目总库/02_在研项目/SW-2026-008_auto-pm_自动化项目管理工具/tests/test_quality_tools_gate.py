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


def test_real_conftest_fails_marked_tests_without_tools_and_skips_them_with_the_opt_in(
    tmp_path: Path,
) -> None:
    """端到端钉住真正的 tests/conftest.py：藏起 ruff/mypy 后，默认失败，设变量才跳过。

    起子进程对真实 tests 目录跑一个被标记的测试和一个没标记的测试；sitecustomize 同时让 find_spec 和
    import 都找不到 ruff/mypy（质量门子进程继承 PYTHONPATH，所以 `python -m ruff` 也报缺模块）。
    """
    project = Path(__file__).resolve().parents[1]
    (tmp_path / "sitecustomize.py").write_text(
        "import importlib.abc, importlib.util, sys\n"
        "_HIDDEN = ('ruff', 'mypy')\n"
        "_orig = importlib.util.find_spec\n"
        "def find_spec(name, package=None):\n"
        "    if name.split('.')[0] in _HIDDEN:\n"
        "        return None\n"
        "    return _orig(name, package)\n"
        "importlib.util.find_spec = find_spec\n"
        "class _Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in _HIDDEN:\n"
        "            raise ModuleNotFoundError(name)\n"
        "sys.meta_path.insert(0, _Block())\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k not in (ALLOW_SKIP_ENV, "PYTEST_ADDOPTS", "CI")}
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(project)])

    def run(extra: dict[str, str]) -> str:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest", "tests/core/test_pm_facade_service.py",
                "-k", "rechecks_generic_owned_paths_after_rehash or confirm_start_uses_the_mission_bound",
                "--no-cov", "-p", "no:cacheprovider", "-q", "--color=no",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**env, **extra}, cwd=project, check=False,
        )
        return result.stdout

    # 被标记的 1 个测试 + 同文件里没标记的 1 个（后者任何情况下都必须照常通过）
    default = run({})
    assert "1 failed" in default and "1 passed" in default and "skipped" not in default
    opted_in = run({ALLOW_SKIP_ENV: "1"})
    assert "1 skipped" in opted_in and "1 passed" in opted_in and "failed" not in opted_in
