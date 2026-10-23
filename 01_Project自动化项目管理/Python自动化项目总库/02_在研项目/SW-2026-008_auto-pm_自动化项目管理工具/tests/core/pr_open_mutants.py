"""变异反证：把 ``pr open`` 的每一道拒绝条件逐个拿掉，``test_pr_open_service.py`` 都必须变红。

用法（在 SW-2026-008 项目目录）：``python -B tests/core/pr_open_mutants.py``。
每个变异只改内存里的一份副本写回源文件、跑完立即还原；退出码 0＝全部变异都被测试抓住。
"""

from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT / "auto_pm" / "application" / "core" / "pr_open_service.py"
TESTS = "tests/core/test_pr_open_service.py"

# (名字, 原文, 变异后)：每条都是“去掉一道拒绝条件”或“放开一个动作”。
MUTANTS: tuple[tuple[str, str, str], ...] = (
    ("名册外的 agent 也开", "        if prefix is None:\n", "        if False:\n"),
    ("认不出调用方时放行", "        if caller == UNKNOWN_CALLER:\n", "        if False:\n"),
    ("可以替别的 agent 开 PR", "        if caller and caller != agent:\n", "        if False:\n"),
    (
        "没有工位也往下走",
        '        if station is None or station.kind != "agent":\n',
        "        if False:\n",
    ),
    ("分支名不符也开", "        if station.branch != branch:\n", "        if False:\n"),
    ("有未提交改动也开", "        if station.dirty_paths:\n", "        if False:\n"),
    ("没有新提交也开", "        if not commits:\n", "        if False:\n"),
    (
        "任务卡不在 main 上也开",
        "        if shown.returncode != 0:\n",
        "        if False:\n",
    ),
    (
        "任务卡路径可以跳出仓库",
        '        if not path or path.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", path):\n',
        "        if False:\n",
    ),
    (
        "CHG 占位也放行",
        "            if CHG_PLACEHOLDER.search(message):\n",
        "            if False:\n",
    ),
    ("没有 CHG 号也放行", "        if not found:\n", "        if False:\n"),
    ("越界检查不过也开", "        if code != 0:\n", "        if False:\n"),
    (
        "越界脚本找不到时当通过",
        '            return 2, f"找不到越界检查脚本',
        '            return 0, f"找不到越界检查脚本',
    ),
    ("gh 没登录也推送", "        if auth.returncode != 0:\n", "        if False:\n"),
    ("已有 PR 也再开", "        if '\"number\"' in existing.stdout:\n", "        if False:\n"),
    (
        "推送被拒也当网络问题重试",
        "            if not NETWORK_FAILURE.search(detail):\n",
        "            if False:\n",
    ),
    ("推送失败强推", '"push", "-u", "origin", branch)', '"push", "-f", "-u", "origin", branch)'),
    (
        "退避不等待",
        "                self._sleep(PUSH_BACKOFF_SECONDS[attempt])\n",
        "                pass\n",
    ),
    (
        "开 PR 时顺手自动合并",
        '"--title", plan.title, "--body-file", "-",',
        '"--title", plan.title, "--body-file", "-", "--auto-merge",',
    ),
    (
        "PR 描述丢了任务卡行",
        'lines = [f"任务卡: {task_card}", "", "## 变更单", ""]',
        'lines = ["## 变更单", ""]',
    ),
    ("没有证据时假装有", '["- 未提供（由审计者自行核验）"]', '["- 已验证"]'),
)


def main() -> int:
    original = SOURCE.read_text(encoding="utf-8")
    signal.signal(
        signal.SIGTERM, lambda *_: sys.exit(3)
    )  # a killed run still restores the source in finally
    survivors: list[str] = []
    try:
        for name, before, after in MUTANTS:
            if original.count(before) != 1:
                print(f"[错误] 变异“{name}”的原文在源文件里不是恰好一处，脚本需要更新")
                return 2
            SOURCE.write_text(original.replace(before, after), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "pytest",
                    "-q",
                    "-x",
                    "-p",
                    "no:cacheprovider",
                    "-o",
                    "addopts=",
                    TESTS,
                ],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            caught = result.returncode != 0
            print(f"[{'抓住' if caught else '漏网'}] {name}")
            if not caught:
                survivors.append(name)
    finally:
        SOURCE.write_text(original, encoding="utf-8")
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} 个变异被测试抓住")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
