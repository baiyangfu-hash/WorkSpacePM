"""版本库策略守护（AGENTS.md「版本库策略」一节的机器卡点）。

规矩原文：`.cursor/` 下除 `rules/`、`commands/` 外的本地状态、`.trae/tmp_*` 等临时文件不纳入 Git；跨 AI 适配入口只有 `.agent/rules/`。
以前只靠 `.gitignore`，有人 `git add -f` 就绕过了，CI 仍是绿的。本测试只读：用 `git ls-files` 看已入库的，用
`git check-ignore --no-index` 看规则，不依赖磁盘上有没有这些文件。每个 PR 和 main 推送都由 root-tests 跑。
"""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]

# 目录 -> 允许入库的子路径前缀（规矩写明的纳入范围）；目录里的其他入库文件都是本地状态
ALLOWED_PREFIXES = {
    ".cursor": (".cursor/rules/", ".cursor/commands/"),
    ".agent": (".agent/rules/",),
}
TEMP_PATTERNS = {".trae": ".trae/tmp_*"}

MUST_IGNORE = [
    ".cursor/mcp.json",
    ".cursor/chat/session.json",
    ".cursor/state/cache.db",
    ".trae/tmp_probe.json",
    ".trae/tmp_notes/a.md",
]
MUST_TRACK = [
    ".cursor/rules/example.mdc",
    ".cursor/commands/example.md",
    ".trae/rules/project-rule.md",
    ".trae/skills/x/SKILL.md",
]

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (WORKSPACE_ROOT / ".git").exists(),
    reason="需要 git 和仓库检出",
)


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        check=False,
        timeout=120,
    )


def _tracked(*pathspec: str) -> list[str]:
    done = _git("ls-files", "-z", "--", *pathspec)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return [name for name in done.stdout.decode("utf-8").split("\0") if name]


def _ignored(path: str) -> bool:
    proc = _git("check-ignore", "--no-index", "-q", path)
    assert proc.returncode in (0, 1), proc.stderr.decode("utf-8", "replace")
    return proc.returncode == 0


def outside_policy(tracked: list[str]) -> list[str]:
    """Tracked files in a policy directory that are outside its allowed sub-paths."""

    found: list[str] = []
    for name in tracked:
        for directory, prefixes in ALLOWED_PREFIXES.items():
            if name.startswith(directory + "/") and not name.startswith(prefixes):
                found.append(name)
    return sorted(found)


def tracked_temporary_files(tracked: list[str]) -> list[str]:
    return sorted(
        name
        for name in tracked
        if any(fnmatch.fnmatch(name, pattern) for pattern in TEMP_PATTERNS.values())
    )


@pytest.mark.parametrize("directory", sorted(ALLOWED_PREFIXES))
def test_only_the_policys_sub_directories_are_tracked(directory: str) -> None:
    extra = outside_policy(_tracked(directory))
    allowed = "、".join(ALLOWED_PREFIXES[directory])
    assert not extra, (
        f"{directory}/ 里只有 {allowed} 可以入库，其余是本地状态（版本库策略）；请 `git rm --cached`："
        + "、".join(extra)
    )


def test_no_trae_temporary_file_is_tracked() -> None:
    temp = tracked_temporary_files(_tracked(".trae"))
    assert not temp, ".trae/tmp_* 是临时文件，不得入库（版本库策略）：" + "、".join(
        temp
    )


@pytest.mark.parametrize("path", MUST_IGNORE)
def test_local_state_stays_ignored(path: str) -> None:
    assert _ignored(path), (
        f"{path} 没被 .gitignore 挡住：本地状态/临时文件必须被忽略（版本库策略）"
    )


@pytest.mark.parametrize("path", MUST_TRACK)
def test_the_tracked_rule_files_are_not_ignored(path: str) -> None:
    assert not _ignored(path), f"{path} 被 .gitignore 挡住了：规则/技能文件必须能入库"


def test_the_detectors_catch_planted_files_and_leave_the_policy_paths_alone() -> None:
    planted = [
        ".cursor/mcp.json",
        ".cursor/rules/a.mdc",
        ".cursor/commands/b.md",
        ".agent/state.json",
        ".agent/rules/p.md",
        ".trae/tmp_x.json",
    ]
    assert outside_policy(planted) == [".agent/state.json", ".cursor/mcp.json"]
    assert tracked_temporary_files(planted) == [".trae/tmp_x.json"]
    assert (
        outside_policy([".cursorrules", "x/.cursor/a.json"]) == []
    )  # only the top-level directories are the policy's subject
