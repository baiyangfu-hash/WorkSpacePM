"""变异反证：把工位命令的每一道拒绝条件逐个拿掉，``test_agent_worktree_service.py`` 都必须变红。

用法（在 SW-2026-008 项目目录）：``python -B tests/core/agent_worktree_mutants.py``。
每个变异只改内存里的一份副本写回源文件、跑完立即还原；退出码 0＝全部变异都被测试抓住。
"""

from __future__ import annotations

import signal
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
    ("可以收别的 agent 的工位", "        if not (acts_for(caller, agent) or caller == self.borrower(agent)):\n            raise StationRefusedError(\n                f\"你是 {caller_alias() or caller}，不能收", "        if False:\n            raise StationRefusedError(\n                f\"你是 {caller_alias() or caller}，不能收"),
    (
        "认不出调用方时放行（close）",
        "        if caller == _UNKNOWN_CALLER:\n",
        "        if False:\n",
    ),
    (
        "认不出调用方时放行（sweep）",
        "        if apply and caller == _UNKNOWN_CALLER:\n",
        "        if False:\n",
    ),
    (
        "互相矛盾的标记当成认得出",
        "if len(found) > 1 or not found <= set(AGENT_ROSTER):",
        "if not found <= set(AGENT_ROSTER):",
    ),
    (
        "agent 会话 sweep 可清别人的",
        "            if agent is not None and not acts_for(caller, agent):\n",
        "            if False:\n",
    ),
    ("agent 会话 sweep 不限定到自己", "            agent = agent or caller\n", "            pass\n"),
    ("agent 会话可清 run-plan", 'if station.kind == "run-plan" and caller_agent():', "if False:"),
    (
        "名册外前缀的孤儿分支也删",
        "if not branch.startswith(tuple(AGENT_ROSTER.values())):",
        "if False:",
    ),
    (
        "删前复查丢了 locked",
        "head=info.head, locked=info.locked\n            ),\n            idle_seconds",
        "head=info.head\n            ),\n            idle_seconds",
    ),
    (
        "删前不再核对是否并进 main",
        "        if require_merged and not fresh.merged:\n",
        "        if False:\n",
    ),
    ("分支上有独有提交也删", "        if self._unique_commits(branch):\n", "        if False:\n"),
    (
        "git status 失败按干净处理",
        "            if status.returncode != 0:\n",
        "            if False:\n",
    ),
    (
        "工位里是别人的分支也收",
        "if station.branch and not station.branch.startswith(prefix):",
        "if False:",
    ),
    (
        "--agent 限定不生效",
        'station.kind == "agent" and agent is not None and not _in_sweep_scope(station.name, agent)',
        "False",
    ),
    ("刚开的空工位也清", "        if station.untouched:\n", "        if False:\n"),
    (
        "没并进 main 的工位也清",
        '        if not station.merged:\n            return SweepItem(target, "station"',
        '        if False:\n            return SweepItem(target, "station"',
    ),
    ("名册外的目录也清", '        if station.kind == "other":\n', "        if False:\n"),
    (
        "分支前缀不符的工位也清",
        "if not station.branch.startswith(self._prefix(station.name)):",
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
        "if agent is not None and not branch.startswith(self._prefix(agent)):",
        "if False:",
    ),
    ("没并进 main 也删本地分支", "        elif fresh.merged:\n", "        elif True:\n"),
    (
        "agent 会话可清名册外的目录",
        '        if caller_agent():\n            return SweepItem(\n                target, "other", False, "不在',
        '        if False:\n            return SweepItem(\n                target, "other", False, "不在',
    ),
    ("名册外的目录有未提交也清", "        refusal = self._refusal(station)\n        if refusal:\n            return SweepItem(target, \"other\", False, refusal)\n", ""),
    ("名册外没有自己提交的新目录也清", "        if station.untouched and not station.stale:\n", "        if False:\n"),
    ("名册外没并进 main 的目录也清", "        if not station.merged:\n            return SweepItem(target, \"other\"", "        if False:\n            return SweepItem(target, \"other\""),
    ("时间在未来不钳成 0", "return max(0, int(time.time() - max(stamps)))", "return int(time.time() - max(stamps))"),
    (
        "名册外有被忽略的文件也清",
        "        if station.ignored_paths:\n            shown",
        "        if False:\n            shown",
    ),
    (
        "列表不说工位会带走忽略文件",
        "    if not station.ignored_paths:\n        return \"\"\n    shown",
        "    if True:\n        return \"\"\n    shown",
    ),
    (
        ".mypy_cache 不算缓存",
        'frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})',
        'frozenset({"__pycache__", ".pytest_cache", ".ruff_cache"})',
    ),
    (
        ".ruff_cache 不算缓存",
        'frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})',
        'frozenset({"__pycache__", ".pytest_cache", ".mypy_cache"})',
    ),
    (
        "缓存目录也算被忽略的文件",
        "if entry and not _is_tool_cache(entry)",
        "if entry",
    ),
    (
        "__pycache__ 里的非 pyc 文件也当缓存",
        'folder in CACHE_DIRS and (folder != "__pycache__" or name.endswith(".pyc"))',
        "folder in CACHE_DIRS",
    ),
    (
        "任何目录里的文件都当缓存",
        'folder in CACHE_DIRS and (folder != "__pycache__" or name.endswith(".pyc"))',
        "True",
    ),
    (
        "删前复查不看被忽略的文件和闲置",
        '        if fresh.kind == "other":\n            hold = self._other_hold(fresh)',
        '        if False:\n            hold = self._other_hold(fresh)',
    ),
    (
        "读不到被忽略的文件按没有处理",
        "            if hidden.returncode != 0:\n",
        "            if False:\n",
    ),
    (
        "--only 找不到目录不报错",
        "if only is not None and not listed_stations:",
        "if False:",
    ),
    (
        "--only 不限定目录",
        "self.stations(only=only, progress=progress)",
        "self.stations(progress=progress)",
    ),
    (
        "--only 时仍处理孤儿分支",
        "for branch in [] if only is not None else self._gone_branches():",
        "for branch in self._gone_branches():",
    ),
    (
        "保留名单不生效",
        "if item.remove and station.name.lower() in RESERVED_STATIONS:",
        "if False:",
    ),
    ("工位满了也能开", "        if count >= MAX_STATIONS:\n", "        if False:\n"),
    ("同一 agent 可开第二个工位", "if path.exists() or self._registered(path):", "if False:"),
    (
        "远程已有同名分支也开",
        'for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):',
        "for ref in ():",
    ),
    ("卡号可占用 control-root/run-plan", " or card.lower().startswith(RESERVED_CARD_PREFIXES)", ""),
    (
        "工位目录可以经过 symlink",
        'require_safe_workspace_path(self._root, path, label="工位目录")',
        "path.resolve()",
    ),
    (
        "删除时不查工位目录是否经过链接",
        "        self._require_inside(station.path)\n        info = self._worktrees()",
        "        info = self._worktrees()",
    ),
    (
        "删前不核对分支是否被换",
        "        if info.branch != station.branch:\n",
        "        if False:\n",
    ),
    (
        "新分支把 origin/main 设成上游",
        '"worktree", "add", "--no-track",',
        '"worktree", "add", "--track",',
    ),
)


def bad_anchors(original: str) -> list[str]:
    """Mutants whose original text is not in the source exactly once (or that change nothing).

    A mutant that cannot be applied would otherwise abort the whole run; ``test_agent_worktree_mutant_anchors.py``
    runs this on every test run, so a source edit that breaks an anchor is caught long before the (slow) mutation run.
    """

    return [
        name
        for name, before, after in MUTANTS
        if original.count(before) != 1 or before == after
    ]


def main() -> int:
    original = SOURCE.read_text(encoding="utf-8")
    broken = bad_anchors(original)
    if broken:
        for name in broken:
            print(f"[错误] 变异“{name}”的原文在源文件里不是恰好一处，脚本需要更新")
        return 2
    signal.signal(
        signal.SIGTERM, lambda *_: sys.exit(3)
    )  # a killed run still restores the source in finally
    survivors: list[str] = []
    try:
        for name, before, after in MUTANTS:
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
                text=True, encoding="utf-8", errors="replace",
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
