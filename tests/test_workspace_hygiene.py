"""工作空间洁净守护（AGENTS.md DEV-TMP-001 的机器卡点）。

规矩原文：临时文件、测试产物不得残留在工作空间根目录；`.agents/` 是临时运行态，除 `skills.json` 外的过程文件不得纳入 Git。
以前这两条只靠 `.gitignore` 和自觉。本测试只读：用 `git ls-files` 看已入库的，用 `git check-ignore --no-index` 看规则，
不依赖磁盘上有没有这些文件。每个 PR 和 main 推送都由 root-tests 跑。
"""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]

# 根目录下允许入库的"文件"（目录不限）。新增根文件要来改这张表，改动会出现在 PR 的受保护路径里被点名。
ROOT_FILES_ALLOWED = frozenset(
    {
        ".dockerignore",
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "LICENSE",
        "README.md",
        "main.py",
        "requirements.txt",
        "setup_env.bat",
        "双击启动驾驶舱.bat",
    }
)
# 不管在不在允许表里，这些名字出现在根目录就是残留的临时产物
ROOT_TEMP_PATTERNS = (
    "tmp_*",
    ".coverage*",
    "htmlcov",
    "*.log",
    "*.pyc",
    "__pycache__",
    "handoff.md",
    "progress.md",
    "*.tmp",
    "*.bak",
)

# 这些必须被 .gitignore 挡住（临时测试产物、agent 过程文件）
MUST_IGNORE = [
    "tmp_scratch.py",
    ".coverage",
    "htmlcov/index.html",
    "run.log",
    ".agents/handoff.md",
    ".agents/progress.md",
    ".agents/teamwork/notes.md",
    ".trae/tmp_probe.json",
]
# 这个必须能入库（技能注册表）
MUST_TRACK = [".agents/skills.json"]

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


def test_only_the_skill_registry_of_dot_agents_is_tracked() -> None:
    extra = [name for name in _tracked(".agents") if name != ".agents/skills.json"]
    assert not extra, (
        ".agents/ 是临时运行态，除 skills.json 外的过程文件不得入库（DEV-TMP-001）；请 `git rm --cached` 后保持 .gitignore 的 `.agents/*` 规则："
        + "、".join(extra)
    )


@pytest.mark.parametrize("path", MUST_IGNORE)
def test_temporary_artifacts_stay_ignored(path: str) -> None:
    assert _ignored(path), (
        f"{path} 没被 .gitignore 挡住：临时测试产物与 agent 过程文件必须被忽略（DEV-TMP-001）"
    )


@pytest.mark.parametrize("path", MUST_TRACK)
def test_the_skill_registry_is_not_ignored(path: str) -> None:
    assert not _ignored(path), f"{path} 被 .gitignore 挡住了：技能注册表必须能入库"


def temp_root_entries(tracked: list[str]) -> list[str]:
    """Top-level names among ``tracked`` that look like leftover temporary output."""

    root_entries = {name.split("/", 1)[0] for name in tracked}
    return sorted(
        name
        for name in root_entries
        if any(fnmatch.fnmatch(name, pattern) for pattern in ROOT_TEMP_PATTERNS)
    )


def unknown_root_files(tracked: list[str]) -> list[str]:
    """Tracked files directly in the workspace root that are not on the allowed list."""

    return sorted(
        name for name in tracked if "/" not in name and name not in ROOT_FILES_ALLOWED
    )


def test_no_temporary_artifact_is_tracked_at_the_workspace_root() -> None:
    temp = temp_root_entries(_tracked())
    assert not temp, (
        "根目录入库了临时产物（DEV-TMP-001：根目录必须保持纯净）：" + "、".join(temp)
    )


def test_every_tracked_root_file_is_on_the_allowed_list() -> None:
    root_files = sorted(name for name in _tracked() if "/" not in name)
    unknown = unknown_root_files(root_files)
    assert not unknown, (
        "根目录新增了不在允许表里的文件（DEV-TMP-001）。确属需要就把它加进 tests/test_workspace_hygiene.py 的 ROOT_FILES_ALLOWED，"
        "否则挪到合适的子目录或删掉：" + "、".join(unknown)
    )
    stale = sorted(ROOT_FILES_ALLOWED - set(root_files))
    assert not stale, (
        "允许表里有根目录已不存在的文件，请从 ROOT_FILES_ALLOWED 删掉："
        + "、".join(stale)
    )


def test_the_detectors_catch_planted_leftovers_and_ignore_normal_files() -> None:
    planted = [
        "tmp_scratch.py",
        ".coverage",
        ".coverage.host.123",
        "htmlcov/index.html",
        "debug.log",
        "handoff.md",
        "notes.bak",
        "stray.txt",
    ]
    assert temp_root_entries(planted) == [
        ".coverage",
        ".coverage.host.123",
        "debug.log",
        "handoff.md",
        "htmlcov",
        "notes.bak",
        "tmp_scratch.py",
    ]
    unknown = unknown_root_files(planted)
    assert "stray.txt" in unknown and "htmlcov/index.html" not in unknown
    normal = ["AGENTS.md", "main.py", "tests/test_x.py", "docs/handover/a.md", "00_Infrastructure/tmp_keep/a.py"]
    assert temp_root_entries(normal) == []
    assert unknown_root_files(normal) == []
