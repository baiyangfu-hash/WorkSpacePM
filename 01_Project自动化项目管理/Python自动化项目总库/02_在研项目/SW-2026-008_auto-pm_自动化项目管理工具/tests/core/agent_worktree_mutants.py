"""变异反证：把工位命令的每一道拒绝条件逐个拿掉，``test_agent_worktree_service.py`` 都必须变红。

用法（在 SW-2026-008 项目目录）：``python -B tests/core/agent_worktree_mutants.py``。
每个变异只改内存里的一份副本写回源文件、跑完立即还原；退出码 0＝全部变异都被测试抓住。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT / "auto_pm" / "application" / "core" / "agent_worktree_service.py"
TESTS = "tests/core/test_agent_worktree_service.py"

# (名字, 原文, 变异后)：每条都是“去掉一道拒绝条件”。
MUTANTS: tuple[tuple[str, str, str], ...] = (
    ("有未提交改动也删", "        if station.dirty_paths:\n", "        if False:\n"),
    ("有没推送的提交也删", "        if station.unpushed:\n", "        if False:\n"),
    ("锁住的工位也删", "        if station.locked:\n", "        if False:\n"),
    ("detached 工位也删", "        if not station.branch:\n", "        if False:\n"),
    ("可以收别的 agent 的工位", "if caller in AGENT_ROSTER and caller != agent:", "if False:"),
    (
        "工位里是别人的分支也收",
        "if station.branch and not station.branch.startswith(prefix):",
        "if False:",
    ),
    (
        "--agent 限定不生效",
        'station.kind == "agent" and agent is not None and station.name != agent',
        "False",
    ),
    ("刚开的空工位也清", "        if station.untouched:\n", "        if False:\n"),
    ("没并进 main 的工位也清", "        if not station.merged:\n", "        if False:\n"),
    ("名册外的目录也清", '        if station.kind == "other":\n', "        if False:\n"),
    (
        "分支前缀不符的工位也清",
        "if not station.branch.startswith(AGENT_ROSTER[station.name]):",
        "if False:",
    ),
    ("Run 没结束也清 run-plan", "if state not in TERMINAL_RUN_STATES:", "if False:"),
    ("账本查不到也清 run-plan", "            if state is None:\n", "            if False:\n"),
    (
        "控制根自己的分支也删",
        'branch == "main" or branch.startswith("codex/control-root")',
        "False",
    ),
    (
        "远程已删但没并进 main 的分支也删",
        'if not self._is_ancestor(f"refs/heads/{branch}", MAIN_REF):',
        "if False:",
    ),
    (
        "工位正签出的分支当孤儿分支删",
        "            if branch in checked_out:\n",
        "            if False:\n",
    ),
    (
        "--agent 限定对孤儿分支不生效",
        "if agent is not None and not branch.startswith(AGENT_ROSTER[agent]):",
        "if False:",
    ),
    ("没并进 main 也删本地分支", "        elif fresh.merged:\n", "        elif True:\n"),
    ("同一 agent 可开第二个工位", "if path.exists() or self._registered(path):", "if False:"),
    (
        "远程已有同名分支也开",
        'for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):',
        "for ref in ():",
    ),
    ("卡号可占用 control-root/run-plan", " or card.lower().startswith(RESERVED_CARD_PREFIXES)", ""),
    (
        "新分支把 origin/main 设成上游",
        '"worktree", "add", "--no-track",',
        '"worktree", "add", "--track",',
    ),
)


def main() -> int:
    original = SOURCE.read_text(encoding="utf-8")
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
