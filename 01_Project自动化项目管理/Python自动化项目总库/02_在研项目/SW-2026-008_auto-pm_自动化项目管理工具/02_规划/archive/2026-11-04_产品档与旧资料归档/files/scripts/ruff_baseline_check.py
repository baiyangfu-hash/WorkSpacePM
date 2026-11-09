"""Ruff 扩展规则增量检测脚本

用途：检测 RUF/SIM/PLR 扩展规则违规是否超过基线阈值。
     基线是当前快照，不要求立即修复，但新代码不得增加违规（增量门禁）。

运行方式：
    python scripts/ruff_baseline_check.py --baseline reports/ruff_extended_baseline.json --threshold 0.05

退出码：
    0 = 未超阈值（当前 count ≤ 基线 * (1 + threshold)）
    1 = 超过阈值，须创建治理 CHG
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def get_current_count(workspace: str) -> int:
    """运行 ruff check --select RUF,SIM,PLR 并返回违规数。"""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--select", "RUF,SIM,PLR", "--output-format=json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=workspace,
        shell=False,
    )
    if result.returncode not in (0, 1):
        print(f"ruff 执行失败（exit={result.returncode}）: {result.stderr}", file=sys.stderr)
        sys.exit(2)
    data = json.loads(result.stdout)
    return len(data)


def get_baseline_count(baseline_path: str) -> int:
    """读取基线 JSON 文件中的违规数。"""
    with open(baseline_path, encoding="utf-8-sig") as f:
        data = json.load(f)
    return len(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ruff 扩展规则增量检测")
    parser.add_argument(
        "--baseline",
        required=True,
        help="基线 JSON 文件路径（reports/ruff_extended_baseline.json）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="允许的增长比例（默认 0.05 = 5%%）",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="工作空间根目录（默认当前目录）",
    )
    args = parser.parse_args()

    baseline_count = get_baseline_count(args.baseline)
    current_count = get_current_count(args.workspace)
    max_allowed = int(baseline_count * (1 + args.threshold))

    print(f"基线违规数: {baseline_count}")
    print(f"当前违规数: {current_count}")
    print(f"允许上限（基线 × {1 + args.threshold:.0%}）: {max_allowed}")

    if current_count > max_allowed:
        print(
            f"\n❌ 扩展规则违规增长超 {args.threshold:.0%} 阈值！"
            f"（{current_count} > {max_allowed}）"
            f"\n   须创建治理 CHG，按规则类别分批治理（RUF 优先 → SIM → PLR，每批 ≤500 errors）"
        )
        return 1

    print(f"\n✅ 未超阈值（{current_count} ≤ {max_allowed}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
