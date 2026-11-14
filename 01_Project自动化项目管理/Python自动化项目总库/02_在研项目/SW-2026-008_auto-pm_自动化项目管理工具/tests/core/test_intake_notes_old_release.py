"""D-357：带待整理记录（``intake_notes`` 表）的账本，交给老发布版读，会怎样。

用新代码建一本账（一条待整理、一条已转正），再用仓库里两个发布指针（现役、上一版）指向的发布目录里的代码，
在子进程里各跑三条只读命令。老版本不认识这张表：命令照常返回、看不见记录、不动账本；记录不丢。
发布目录找不到时本文件报失败并写明原因，不跳过。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.contracts.intake import (
    Disposition,
    IntakeClassification,
    IntakeKind,
    NoteStatus,
    TriageTicket,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.intake_store import IntakeStore
from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.external_reads  # D-200: reads the release pointers and release directories outside the project

PROJECT = "SW-2026-008"
POINTERS = ("active_release.json", "previous_release.json")
READ_COMMANDS = (
    ("pm", "inbox", "list", "--project-id", PROJECT),
    ("pm", "orient", PROJECT, "--json"),
    ("pm", "resume", PROJECT, "--json"),
)
VALIDATE = (
    "import json, sys\n"
    "from auto_pm.contracts.continuity_resume import validate_query_resume\n"
    "checked = validate_query_resume(json.load(sys.stdin), require_query=True)\n"
    "import auto_pm\n"
    "print(auto_pm.__file__)\n"
)


def _infrastructure() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "00_Infrastructure" / "auto_pm"
        if (candidate / "active_release.json").is_file():
            return candidate
    pytest.fail("找不到 00_Infrastructure/auto_pm/active_release.json：这条测试要用仓库里的发布目录，不能跳过", pytrace=False)


def _release_dir(pointer: str) -> Path:
    infrastructure = _infrastructure()
    pointer_path = infrastructure / pointer
    if not pointer_path.is_file():
        pytest.fail(f"发布指针 {pointer} 不存在：{pointer_path}", pytrace=False)
    release_path = str(json.loads(pointer_path.read_text(encoding="utf-8", errors="replace")).get("release_path", ""))
    release = infrastructure / "releases" / release_path
    if not release_path or not (release / "auto_pm" / "__main__.py").is_file():
        pytest.fail(f"发布指针 {pointer} 指向的发布目录不在或不完整：{release}", pytrace=False)
    return release


def _git(root: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(root), "-c", "user.name=Old Release Test", "-c", "user.email=old-release@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def _ledger(root: Path) -> tuple[str, str, str]:
    """A workspace whose ledger holds one raw note and one triaged note; returns (raw id, triaged id, item id)."""

    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8", errors="replace")
    project = root / PROJECT
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        f"project_id: {PROJECT}\nproject_name: Old Release Test\nstack: python\n", encoding="utf-8", errors="replace"
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [{"project_id": PROJECT, "project_root": PROJECT, "development_root": PROJECT}],
            }
        ),
        encoding="utf-8",
        errors="replace",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "baseline")
    ContinuityStore(root).initialize("2026-11-13T00:00:00+00:00", "test")
    store = IntakeStore(root)
    turned, _ = store.add_note(
        request_id="REQ-NOTE-1", project_id=PROJECT, title="导出按钮没反应", original_words="点了导出没反应",
        kind_hint=IntakeKind.BUG, recorded_by="trae",
    )
    item, _ = store.add_item(
        request_id="REQ-ITEM-1", project_id=PROJECT, title="导出按钮没反应",
        classification=IntakeClassification(kind=IntakeKind.BUG, domain="SCPT"),
        ticket=TriageTicket(
            original_words="点了导出没反应", affects=PROJECT, duplicate_check="查过，没有同类条目", evidence=("file:README.md",),
            disposition=Disposition.INBOX_WAIT, rationale="不急", alternatives=("下个迭代",), cost_risk="半天；低",
        ),
        proposed_by="pm-test", from_note=turned.note_id, triaged_by="claude",
    )
    raw, _ = store.add_note(
        request_id="REQ-NOTE-2", project_id=PROJECT, title="看板字太小", original_words="字太小了，看不清",
        kind_hint=IntakeKind.ITERATION, recorded_by="no-agent-marker",
    )
    return raw.note_id, turned.note_id, item.item_id


def _old(release: Path, root: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update({"PYTHONPATH": str(release), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "AUTO_PM_AUDIT_DIR": "off"})
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, *args],
        cwd=root,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def _digest(root: Path) -> str:
    return hashlib.sha256((root / ".auto-pm" / "continuity.db").read_bytes()).hexdigest()


@pytest.mark.parametrize("pointer", POINTERS)
def test_an_older_release_reads_a_ledger_with_notes_sees_none_and_changes_nothing(tmp_path: Path, pointer: str) -> None:
    release = _release_dir(pointer)
    raw_id, turned_id, item_id = _ledger(tmp_path)
    before = _digest(tmp_path)

    for command in READ_COMMANDS:
        result = _old(release, tmp_path, "-m", "auto_pm", "-w", str(tmp_path), *command)
        assert result.returncode == 0, f"{pointer} {' '.join(command)}\n{result.stdout}\n{result.stderr}"
        assert "NOTE-" not in result.stdout, f"{pointer} {' '.join(command)} 看见了待整理记录"
        assert _digest(tmp_path) == before, f"{pointer} {' '.join(command)} 动了账本"
    listed = _old(release, tmp_path, "-m", "auto_pm", "-w", str(tmp_path), *READ_COMMANDS[0])
    assert item_id in listed.stdout  # the formal item made from the note is an ordinary item to the older release

    assert _digest(tmp_path) == before
    store = IntakeStore(tmp_path)  # the records are still there for the new code
    assert [note.note_id for note in store.list_notes(PROJECT)] == [raw_id]
    assert [note.note_id for note in store.list_notes(PROJECT, (NoteStatus.TRIAGED,))] == [turned_id]


@pytest.mark.parametrize("pointer", POINTERS)
def test_an_older_release_accepts_the_new_orient_answer(tmp_path: Path, pointer: str) -> None:
    release = _release_dir(pointer)
    raw_id, _turned_id, _item_id = _ledger(tmp_path)
    answer = CliRunner().invoke(cli, ["-w", str(tmp_path), "pm", "orient", PROJECT, "--json"])
    assert answer.exit_code == 0, answer.output
    text = answer.output[answer.output.index("{") :]
    payload = json.JSONDecoder().raw_decode(text)[0]
    assert payload["notes"]["waiting"] == 1 and payload["notes"]["oldest_note_id"] == raw_id

    accepted = _old(release, tmp_path, "-c", VALIDATE, stdin=json.dumps(payload))
    assert accepted.returncode == 0, f"{pointer} 拒收了新版本的回答\n{accepted.stdout}\n{accepted.stderr}"
    assert Path(accepted.stdout.strip()).resolve().is_relative_to(release.resolve())  # it really was the older release's code

    payload["intake"]["notes_waiting"] = 1  # why the block is top-level: an extra field inside ``intake`` is refused
    refused = _old(release, tmp_path, "-c", VALIDATE, stdin=json.dumps(payload))
    assert refused.returncode != 0 and "intake.notes_waiting" in refused.stderr


def test_a_missing_release_directory_fails_with_the_reason_instead_of_skipping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    infrastructure = tmp_path / "00_Infrastructure" / "auto_pm"
    infrastructure.mkdir(parents=True)
    (infrastructure / "active_release.json").write_text(json.dumps({"release_path": "9.9.9-missing"}), encoding="utf-8", errors="replace")
    monkeypatch.setattr(sys.modules[__name__], "_infrastructure", lambda: infrastructure)
    with pytest.raises(pytest.fail.Exception, match="发布目录不在或不完整"):
        _release_dir("active_release.json")
    with pytest.raises(pytest.fail.Exception, match="previous_release.json 不存在"):
        _release_dir("previous_release.json")
