"""统一测试运行脚本

提供多种测试模式：
- smoke: 冒烟测试（核心功能快速验证，< 30s）
- unit: 单元测试（非 GUI 测试）
- gui: GUI 全功能测试
- all: 全量测试
- coverage: 生成覆盖率报告

用法：
    python scripts/run_tests.py smoke           # 冒烟测试
    python scripts/run_tests.py unit            # 单元测试
    python scripts/run_tests.py gui             # GUI 测试
    python scripts/run_tests.py all             # 全量测试
    python scripts/run_tests.py coverage        # 覆盖率报告
    python scripts/run_tests.py --help          # 帮助

M4-Iter6：测试脚本工具更新（冒烟/GUI 测试前）
"""

# ruff: noqa: T201
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ── 配置 ──────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT = 600  # 10 分钟


# ── 测试模式定义 ──────────────────────────────────────────


TEST_MODES: dict[str, dict[str, Any]] = {
    "smoke": {
        "desc": "冒烟测试（核心功能快速验证）",
        "cmd": [
            sys.executable, "-m", "pytest",
            "-m", "smoke",
            "--tb=short", "-q",
            "--no-cov",
            "--ignore=tests/gui",
        ],
        "timeout": 120,
    },
    "unit": {
        "desc": "单元测试（非 GUI 测试）",
        "cmd": [
            sys.executable, "-m", "pytest",
            "--tb=short", "-q",
            "--no-cov",
            "--ignore=tests/gui",
        ],
        "timeout": 600,
    },
    "gui": {
        "desc": "GUI 全功能测试",
        "cmd": [
            sys.executable, "-m", "pytest",
            "tests/gui",
            "--tb=short", "-q",
            "--no-cov",
            "-m", "gui",
        ],
        "timeout": 1800,
    },
    "ui": {
        "desc": "UI 组件测试（非 GUI 全流程）",
        "cmd": [
            sys.executable, "-m", "pytest",
            "tests/ui",
            "--tb=short", "-q",
            "--no-cov",
        ],
        "timeout": 600,
    },
    "change": {
        "desc": "变更管理测试",
        "cmd": [
            sys.executable, "-m", "pytest",
            "tests/change",
            "--tb=short", "-q",
            "--no-cov",
        ],
        "timeout": 300,
    },
    "core": {
        "desc": "核心服务测试",
        "cmd": [
            sys.executable, "-m", "pytest",
            "tests/core",
            "--tb=short", "-q",
            "--no-cov",
        ],
        "timeout": 300,
    },
    "plc": {
        "desc": "PLC 服务测试",
        "cmd": [
            sys.executable, "-m", "pytest",
            "tests/plc",
            "--tb=short", "-q",
            "--no-cov",
        ],
        "timeout": 300,
    },
    "cli": {
        "desc": "CLI 命令测试（tests/cli/ + tests/spec/test_cli.py）",
        "cmd": [
            sys.executable, "-m", "pytest",
            "tests/cli/",
            "tests/spec/test_cli.py",
            "--tb=short", "-q",
            "--no-cov",
        ],
        "timeout": 300,
    },
    "all": {
        "desc": "全量测试（含 GUI）",
        "cmd": [
            sys.executable, "-m", "pytest",
            "--tb=short", "-q",
            "--no-cov",
        ],
        "timeout": 1800,
    },
    "coverage": {
        "desc": "生成覆盖率报告",
        "cmd": [
            sys.executable, "-m", "pytest",
            "--tb=short", "-q",
            "--cov=auto_pm/",
            "--cov-report=term",
            "--cov-report=html:coverage/html",
            "--cov-report=xml:coverage/coverage.xml",
            "--ignore=tests/gui",
        ],
        "timeout": 600,
    },
}


# ── 主函数 ────────────────────────────────────────────────


def main() -> int:
    """主入口"""
    parser = argparse.ArgumentParser(
        description="auto-pm 统一测试运行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="可用测试模式:\n" + "\n".join(
            f"  {name:10s} - {mode['desc']}"
            for name, mode in TEST_MODES.items()
        ),
    )
    parser.add_argument(
        "mode",
        choices=list(TEST_MODES.keys()),
        help="测试模式",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出",
    )
    parser.add_argument(
        "--no-timeout",
        action="store_true",
        help="禁用超时（用于调试）",
    )

    args = parser.parse_args()
    mode = TEST_MODES[args.mode]

    print(f"\n{'=' * 60}")
    print(f"测试模式: {args.mode} - {mode['desc']}")
    print(f"{'=' * 60}\n")

    cmd = mode["cmd"]
    if args.verbose:
        cmd = [c for c in cmd if c not in ("-q",)]
        cmd.append("-v")

    timeout = None if args.no_timeout else mode["timeout"]

    print(f"执行命令: {' '.join(cmd)}")
    print(f"超时: {timeout or '无'}s\n")

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            timeout=timeout,
        )
        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"测试完成 - 耗时 {elapsed:.1f}s - 退出码 {result.returncode}")
        print(f"{'=' * 60}\n")
        return result.returncode
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"测试超时 - 耗时 {elapsed:.1f}s - 超时 {timeout}s")
        print(f"{'=' * 60}\n")
        return 2
    except KeyboardInterrupt:
        print(f"\n{'=' * 60}")
        print("测试被用户中断")
        print(f"{'=' * 60}\n")
        return 130


if __name__ == "__main__":
    sys.exit(main())
