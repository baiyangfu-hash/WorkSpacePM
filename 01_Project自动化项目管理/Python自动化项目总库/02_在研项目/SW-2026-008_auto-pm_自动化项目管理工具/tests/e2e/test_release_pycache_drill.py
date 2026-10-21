"""Misconduct drill: a Python cache directory appears inside the active release.

Field report (D08, Trae CN): running plain ``python`` against ``releases/<id>`` leaves ``__pycache__`` there; the stable
launcher's exact-tree check then rejects the active slot and quietly runs the previous release.  This drill builds a real
two-slot container from the current source and the real stable launcher, and records what a user or agent can notice.
Passing tests pin today's behaviour; strict xfails name what should happen and wait for a card.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import auto_pm

ACTIVE, PREVIOUS = "9.9.9-active", "9.9.8-previous"
PROJECT_ID = "DJ-2026-011"
PROJECT = "0100_PLC自动化/DJ-2026-011_驾驶舱A6PLC续作验证套件"
SILENT_FALLBACK = (
    "现象（技术债候选，未开卡）：活动槽被拒、退回上一版时，启动器退出码 0、stderr 为空，只在 stdout 打一行“verified via "
    "previous_release.json”，被拒的原因（未登记目录 __pycache__）被丢掉；用户和 agent 都不会注意到"
)
WRITES_DESPITE_DIVERGENCE = (
    "现象（技术债候选，未开卡）：运行身份分歧（RUNTIME_IDENTITY_DIVERGENCE）时，pm orient 会报冲突，"
    "但命令行写命令（如 pm inbox add）照样写库；只有薄 SDK 会拒绝"
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _container(tmp_path: Path) -> tuple[Path, Path]:
    """A workspace whose 00_Infrastructure/auto_pm holds two releases built from the current source."""

    repository = _repository_root()
    workspace = tmp_path / "ws"
    container = workspace / "00_Infrastructure" / "auto_pm"
    shutil.copytree(repository / "00_Infrastructure" / "auto_pm" / "launcher", container / "launcher")
    source = Path(auto_pm.__file__).resolve().parent
    releases: dict[str, dict[str, dict[str, str]]] = {}
    for release in (ACTIVE, PREVIOUS):
        target = container / "releases" / release / "auto_pm"
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        root = target.parent
        releases[release] = {
            "files": {
                path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }
        }
    (container / "deployment_manifest.json").write_text(
        json.dumps({"schema_version": "deployment_manifest.v1", "releases": releases}), encoding="utf-8"
    )
    for slot, release in (("active_release.json", ACTIVE), ("previous_release.json", PREVIOUS)):
        (container / slot).write_text(
            json.dumps({"schema_version": "release_pointer.v1", "slot": slot, "release_id": release, "release_path": release}),
            encoding="utf-8",
        )
    governance = workspace / "SYS-2026-001_WorkspaceGovernance"
    governance.mkdir()
    for name in ("workspace_registry.json", "PM_SESSION_SYS-2026-001.md"):
        shutil.copy2(repository / "SYS-2026-001_WorkspaceGovernance" / name, governance / name)
    project = workspace / PROJECT
    project.mkdir(parents=True)
    shutil.copy2(repository / PROJECT / f"PM_SESSION_{PROJECT_ID}.md", project / f"PM_SESSION_{PROJECT_ID}.md")
    (project / ".plc.json").write_text(json.dumps({"name": PROJECT_ID, "version": "V1.0.0", "description": "drill"}), encoding="utf-8")
    shutil.copy2(repository / ".gitignore", workspace / ".gitignore")
    _git(workspace, "init", "-q")
    _git(workspace, "add", "-A")
    _git(workspace, "-c", "user.name=Drill", "-c", "user.email=drill@example.invalid", "commit", "-q", "-m", "baseline")

    from datetime import UTC, datetime

    from auto_pm.infrastructure.continuity_store import ContinuityStore

    ContinuityStore(workspace).initialize(datetime.now(UTC).isoformat(), "pycache-drill")
    return workspace, container


def _launch(container: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-B", str(container / "launcher" / "launch.py"), *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment, timeout=300,
    )


def _orient(container: Path) -> dict[str, object]:
    result = _launch(container, "pm", "orient", PROJECT_ID, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, object] = json.loads(result.stdout[result.stdout.index("{") :])
    return payload


def _pollute(container: Path) -> None:
    """What a plain ``python`` run from inside the release leaves behind."""

    cache = container / "releases" / ACTIVE / "auto_pm" / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-312.pyc").write_bytes(b"\x00")


def test_c01_a_clean_container_runs_the_active_release_without_conflicts(tmp_path: Path) -> None:
    _, container = _container(tmp_path)

    resolved = _launch(container, "--resolve-only")
    oriented = _orient(container)

    assert resolved.returncode == 0 and "active_release.json" in resolved.stdout
    assert oriented["conflicts"] == []


def test_c02_today_a_cache_folder_switches_to_the_previous_release_and_git_cannot_see_it(tmp_path: Path) -> None:
    workspace, container = _container(tmp_path)
    _pollute(container)

    resolved = _launch(container, "--resolve-only")
    oriented = _orient(container)

    assert resolved.returncode == 0
    assert "previous_release.json" in resolved.stdout
    assert _git(workspace, "status", "--porcelain") == ""  # the root .gitignore hides __pycache__
    context = oriented["context"]
    assert isinstance(context, dict)
    assert context["configured_release_id"] == ACTIVE and context["effective_release_id"] == PREVIOUS
    assert oriented["conflicts"] == ["RUNTIME_IDENTITY_DIVERGENCE"]
    assert context["runtime_fallback_reason"] == ""  # the read-only view does not say why


@pytest.mark.xfail(strict=True, reason=SILENT_FALLBACK)
def test_c03_falling_back_to_the_previous_release_is_reported_loudly_with_its_reason(tmp_path: Path) -> None:
    _, container = _container(tmp_path)
    _pollute(container)

    resolved = _launch(container, "--resolve-only")

    assert "__pycache__" in resolved.stderr


@pytest.mark.xfail(strict=True, reason=WRITES_DESPITE_DIVERGENCE)
def test_c04_a_write_command_refuses_while_the_runtime_identity_diverges(tmp_path: Path) -> None:
    workspace, container = _container(tmp_path)
    _pollute(container)

    written = _launch(
        container, "pm", "inbox", "add", "--project-id", PROJECT_ID, "--request-id", "REQ-PYC", "--title", "退回旧版时写入",
        "--kind", "iteration", "--original-words", "演练", "--affects", "无", "--duplicate-check", "无",
        "--evidence", f"file:{PROJECT}/.plc.json", "--disposition", "after_current", "--rationale", "演练",
        "--alternative", "不做", "--cost-risk", "低",
    )

    assert written.returncode != 0, written.stdout
