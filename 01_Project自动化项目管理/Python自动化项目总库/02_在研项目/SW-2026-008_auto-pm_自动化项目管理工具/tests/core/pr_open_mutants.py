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
# The PR description is built in its own module (D-85: three anchors still pointed at pr_open_service.py after the split).
BODY_SOURCE = PROJECT / "auto_pm" / "application" / "core" / "pr_body_builder.py"
SOURCES = (SOURCE, BODY_SOURCE)
TESTS = ("tests/core/test_pr_open_service.py", "tests/core/test_pr_body_builder.py")

# (名字, 原文, 变异后)：每条都是“去掉一道拒绝条件”或“放开一个动作”。
MUTANTS: tuple[tuple[str, str, str], ...] = (
    ("名册外的 agent 也开", "        if prefix is None:\n", "        if False:\n"),
    ("认不出调用方时放行", "        if caller == UNKNOWN_CALLER:\n", "        if False:\n"),
    (
        "可以替别的 agent 开 PR",
        "        if not acts_for(caller, agent) and not self._stations.lent_to_caller(agent):\n",
        "        if False:\n",
    ),
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
        '            if "chg" in leftover.casefold():\n',
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
    (
        "推送失败强推",
        '"push", "origin", f"{head_sha}:refs/heads/{branch}")',
        '"push", "-f", "origin", f"{head_sha}:refs/heads/{branch}")',
    ),
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
        'out += ["## 可改范围", "", f"任务卡: {task_card}", ""]\n',
        'out += ["## 可改范围", "", ""]\n',
    ),
    (
        "PLC 改动不声明也放行",
        "        if touches_plc and declared is None:\n",
        "        if False:\n",
    ),
    (
        "声明值不检查",
        "        if declared is not None and declared not in SAFETY_ANSWERS:\n",
        "        if False:\n",
    ),
    ("声明不进描述", 'f"安全回路: {safety_circuit}", ""]', '"安全回路: 否", ""]'),
    (
        "推送不用显式 refspec",
        'self._git(station, "push", "origin", f"{head_sha}:refs/heads/{branch}")',
        'self._git(station, "push", "origin", branch)',
    ),
    (
        "占位检查不做全角归一",
        'unicodedata.normalize("NFKC", CHG_NUMBER.sub("", message))',
        'CHG_NUMBER.sub("", message)',
    ),
    (
        "CHG 号认全角数字",
        're.compile(r"CHG-[A-Z]+-[0-9]{4}-[0-9]{3,}", re.ASCII)',
        're.compile(r"CHG-[A-Z]+-\\d{4}-\\d{3,}")',
    ),
    ("gh pr create 带无关参数", '"--body-file", "-",', '"--body-file", "-", "--fill",'),
    ("查已有 PR 失败也往下走", "        if existing.returncode != 0:\n", "        if False:\n"),
    ("pr create 失败只看网址", "if created.returncode != 0 or match is None:", "if match is None:"),
    ("没有证据时假装有", 'or [f"- {UNPROVIDED}"]', 'or ["- 已验证"]'),
)


def _locate(before: str, originals: dict[Path, str]) -> Path | None:
    """The one source file that holds ``before`` exactly once and no other file holds it; None otherwise."""

    holders = [path for path, text in originals.items() if text.count(before) >= 1]
    if len(holders) != 1 or originals[holders[0]].count(before) != 1:
        return None
    return holders[0]


def main() -> int:
    originals = {path: path.read_text(encoding="utf-8") for path in SOURCES}
    # D-85: check every anchor before running anything, and list ALL stale ones (not just the first), so a refactor
    # that moves code cannot hide behind an early exit.
    stale = [name for name, before, _after in MUTANTS if _locate(before, originals) is None]
    if stale:
        for name in stale:
            print(f"[错误] 变异“{name}”的原文在源文件里不是恰好一处，脚本需要更新")
        print(f"{len(stale)}/{len(MUTANTS)} 个变异的锚点失效；不运行任何变异")
        return 2
    signal.signal(
        signal.SIGTERM, lambda *_: sys.exit(3)
    )  # a killed run still restores the sources in finally
    survivors: list[str] = []
    try:
        for name, before, after in MUTANTS:
            target = _locate(before, originals)
            assert target is not None  # checked above
            target.write_text(originals[target].replace(before, after), encoding="utf-8")
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
                    *TESTS,
                ],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            target.write_text(originals[target], encoding="utf-8")
            caught = result.returncode != 0
            print(f"[{'抓住' if caught else '漏网'}] {name}")
            if not caught:
                survivors.append(name)
    finally:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} 个变异被测试抓住")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
