"""D-361（TD-SW008-626）、D-127（TD-SW008-393）：试跑记录里的改动文件名照原字记，不写成八进制转义码。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from auto_pm.application.core.dogfood_runner import DogfoodRunner


def _git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


def test_changed_files_keep_chinese_names(tmp_path: Path) -> None:
    repo = tmp_path / "candidate"
    (repo / "00_Infrastructure" / "auto_pm").mkdir(parents=True)
    (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "i")
    (repo / "00_Infrastructure" / "auto_pm" / "说明.md").write_text("新\n", encoding="utf-8")
    (repo / "中文目录").mkdir()
    (repo / "中文目录" / "a.txt").write_text("a\n", encoding="utf-8")

    _root, _sha, changed = DogfoodRunner(tmp_path)._git_state(repo)

    assert sorted(changed) == ["00_Infrastructure/auto_pm/说明.md", "中文目录/a.txt"]
    assert not any("\\" in path or '"' in path for path in changed)
