"""D-357：带待整理记录（``intake_notes`` 表）的账本，交给老发布版读，会怎样。

用新代码建一本账（一条待整理、一条已转正），再用仓库里发布目录的代码在子进程里跑三条只读命令。
“老版本”不跟着发布指针走（指针一切换到带这个功能的版本，前提就不成立了；#840 切到 368c1af 时就红了）：
从 deployment_manifest.json 里按 built_at 从新到旧找第一个“有入箱、没有待整理记录”的发布
（``auto_pm/infrastructure/intake_store.py`` 在、但里面没有 ``intake_notes``）。老版本不认识这张表：
命令照常返回、看不见记录、不动账本；记录不丢。两个发布指针指向的版本按它自己有没有这个功能来断言：
没有的照老版本断言，有的要看得见待整理记录、同样不动账本。
发布目录找不到、或者一个老版本都找不到时，本文件报失败并写明原因，不跳过。
"""

from __future__ import annotations

import atexit
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
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
OLDER = "older"  # the newest release in the manifest that has the inbox but not the notes table
INTAKE_STORE = Path("auto_pm") / "infrastructure" / "intake_store.py"
NOTES_TABLE = "intake_notes"
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


_PROJECT_PACKAGE_PREFIX = (
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/"
    "SW-2026-008_auto-pm_自动化项目管理工具/auto_pm"
)
_MATERIALIZED_ROOT: Path | None = None
_MATERIALIZED_CACHE: dict[tuple[str, str], Path] = {}


def _materialize_release_from_git(infrastructure: Path, release_path: str) -> Path | None:
    """Materialize ``auto_pm/`` from the release's Git ``source_commit`` when an untracked release folder is absent (TD-SW008-019)."""

    global _MATERIALIZED_ROOT
    manifest_path = infrastructure / "deployment_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        releases = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace")).get("releases", {})
    except (OSError, ValueError):
        return None
    entry = releases.get(release_path) if isinstance(releases, dict) else None
    source_commit = str(entry.get("source_commit", "")).strip() if isinstance(entry, dict) else ""
    if len(source_commit) < 7:
        return None
    repo_root = infrastructure.parent.parent
    if not (repo_root / ".git").exists():
        return None
    resolved = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-c", "core.fsmonitor=false", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"{source_commit}^{{commit}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    full_commit = resolved.stdout.strip() if resolved.returncode == 0 else ""
    if not full_commit:
        return None
    cache_key = (str(repo_root.resolve()), full_commit)
    cached = _MATERIALIZED_CACHE.get(cache_key)
    if cached is not None and (cached / "auto_pm" / "__main__.py").is_file():
        return cached
    archived = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-c", "core.fsmonitor=false", "-C", str(repo_root), "archive", "--format=tar", full_commit, "--", _PROJECT_PACKAGE_PREFIX],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if archived.returncode != 0 or not archived.stdout:
        return None
    if _MATERIALIZED_ROOT is None:
        _MATERIALIZED_ROOT = Path(tempfile.mkdtemp(prefix="auto-pm-release-intake-"))
        atexit.register(shutil.rmtree, _MATERIALIZED_ROOT, ignore_errors=True)
    dest = _MATERIALIZED_ROOT / f"{release_path}-{full_commit[:12]}"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    prefix = f"{_PROJECT_PACKAGE_PREFIX}/"
    with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            name = member.name.replace("\\", "/")
            if not name.startswith(prefix):
                continue
            rel = Path(name.removeprefix(prefix))
            if rel.is_absolute() or ".." in rel.parts:
                continue
            target = dest / "auto_pm" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is not None:
                target.write_bytes(extracted.read())
    if not (dest / "auto_pm" / "__main__.py").is_file():
        return None
    _MATERIALIZED_CACHE[cache_key] = dest
    return dest


def _release_dir(pointer: str) -> Path:
    infrastructure = _infrastructure()
    pointer_path = infrastructure / pointer
    if not pointer_path.is_file():
        pytest.fail(f"发布指针 {pointer} 不存在：{pointer_path}", pytrace=False)
    release_path = str(json.loads(pointer_path.read_text(encoding="utf-8", errors="replace")).get("release_path", ""))
    release = infrastructure / "releases" / release_path
    if release_path and (release / "auto_pm" / "__main__.py").is_file():
        return release
    if release_path:
        materialized = _materialize_release_from_git(infrastructure, release_path)
        if materialized is not None:
            return materialized
    pytest.fail(f"发布指针 {pointer} 指向的发布目录不在或不完整：{release}", pytrace=False)


def _has_notes(release: Path) -> bool:
    """Whether a release's code knows the notes table (D-357); a release without the inbox at all does not."""

    store = release / INTAKE_STORE
    return store.is_file() and NOTES_TABLE in store.read_text(encoding="utf-8", errors="replace")


def _older_release() -> Path:
    """The newest release in the manifest that has the inbox (``intake_store.py``) but not the notes table.

    Picked by what the code holds, not by a pointer, so switching the pointers to a release with notes leaves the
    premise true.  A release without the inbox at all cannot run ``pm inbox list`` and is not an older reader.
    """

    infrastructure = _infrastructure()
    manifest_path = infrastructure / "deployment_manifest.json"
    if not manifest_path.is_file():
        pytest.fail(f"发布清单不存在：{manifest_path}", pytrace=False)
    releases = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace")).get("releases", {})
    built: list[tuple[datetime, str]] = []
    for release_id, entry in releases.items():
        stamp = str(entry.get("built_at", "")) if isinstance(entry, dict) else ""
        if stamp:
            built.append((datetime.fromisoformat(stamp), str(release_id)))
    for _stamp, release_id in sorted(built, reverse=True):
        release = infrastructure / "releases" / release_id
        if (release / "auto_pm" / "__main__.py").is_file() and (release / INTAKE_STORE).is_file() and not _has_notes(release):
            return release
    pytest.fail(
        f"{manifest_path} 里找不到有入箱、没有待整理记录（{INTAKE_STORE.as_posix()} 里没有 {NOTES_TABLE}）的发布目录",
        pytrace=False,
    )


def _reader(name: str) -> Path:
    return _older_release() if name == OLDER else _release_dir(name)


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


def test_an_older_release_reads_a_ledger_with_notes_sees_none_and_changes_nothing(tmp_path: Path) -> None:
    release = _older_release()
    assert not _has_notes(release)
    _assert_sees_none_and_changes_nothing(release, tmp_path, OLDER)


@pytest.mark.parametrize("pointer", POINTERS)
def test_a_pointed_release_reads_a_ledger_with_notes_as_its_code_says(tmp_path: Path, pointer: str) -> None:
    """Each pointed release is held to what its own code holds: without the table it is an older reader; with it
    the waiting note is listed, and neither kind changes the ledger."""

    release = _release_dir(pointer)
    if not _has_notes(release):
        _assert_sees_none_and_changes_nothing(release, tmp_path, pointer)
        return
    raw_id, turned_id, _item_id = _ledger(tmp_path)
    before = _digest(tmp_path)
    for command in READ_COMMANDS:
        result = _old(release, tmp_path, "-m", "auto_pm", "-w", str(tmp_path), *command)
        assert result.returncode == 0, f"{pointer} {' '.join(command)}\n{result.stdout}\n{result.stderr}"
        assert _digest(tmp_path) == before, f"{pointer} {' '.join(command)} 动了账本"
    listed = _old(release, tmp_path, "-m", "auto_pm", "-w", str(tmp_path), *READ_COMMANDS[0])
    assert raw_id in listed.stdout, f"{pointer} 有待整理记录功能，pm inbox list 却没列出 {raw_id}\n{listed.stdout}"
    assert _digest(tmp_path) == before
    store = IntakeStore(tmp_path)
    assert [note.note_id for note in store.list_notes(PROJECT)] == [raw_id]
    assert [note.note_id for note in store.list_notes(PROJECT, (NoteStatus.TRIAGED,))] == [turned_id]


def _assert_sees_none_and_changes_nothing(release: Path, tmp_path: Path, pointer: str) -> None:
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


@pytest.mark.parametrize("pointer", (OLDER, *POINTERS))
def test_an_older_release_accepts_the_new_orient_answer(tmp_path: Path, pointer: str) -> None:
    release = _reader(pointer)
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


def _manifest(infrastructure: Path, releases: dict[str, str]) -> None:
    (infrastructure / "deployment_manifest.json").write_text(
        json.dumps({"releases": {release: {"built_at": stamp} for release, stamp in releases.items()}}),
        encoding="utf-8",
        errors="replace",
    )


def _payload(infrastructure: Path, release: str, store: str | None) -> None:
    package = infrastructure / "releases" / release / "auto_pm"
    (package / "infrastructure").mkdir(parents=True)
    (package / "__main__.py").write_text("", encoding="utf-8", errors="replace")
    if store is not None:
        (package / "infrastructure" / "intake_store.py").write_text(store, encoding="utf-8", errors="replace")


def test_the_older_release_is_the_newest_with_the_inbox_and_without_notes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    infrastructure = tmp_path / "00_Infrastructure" / "auto_pm"
    _payload(infrastructure, "1.0.0-noinbox", None)
    _payload(infrastructure, "1.1.0-inbox-old", "CREATE TABLE intake_items\n")
    _payload(infrastructure, "1.1.1-inbox", "CREATE TABLE intake_items\n")
    _payload(infrastructure, "1.1.2-noinbox", None)  # newer than 1.1.1 but without the inbox: cannot run pm inbox list
    _payload(infrastructure, "1.2.0-notes", "CREATE TABLE intake_items\nCREATE TABLE intake_notes\n")
    _manifest(
        infrastructure,
        {
            "1.0.0-noinbox": "2026-09-06T13:29:39.4500876Z",
            "1.1.0-inbox-old": "2026-11-01T00:00:00+00:00",
            "1.1.1-inbox": "2026-11-02T00:00:00+00:00",
            "1.1.2-noinbox": "2026-11-02T12:00:00+00:00",
            "1.2.0-notes": "2026-11-03T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(sys.modules[__name__], "_infrastructure", lambda: infrastructure)
    assert _older_release().name == "1.1.1-inbox"  # newest without notes; the release with notes and the newer one with no inbox are passed over


def test_no_older_release_in_the_manifest_fails_with_the_reason_instead_of_skipping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    infrastructure = tmp_path / "00_Infrastructure" / "auto_pm"
    _payload(infrastructure, "1.0.0-noinbox", None)
    _payload(infrastructure, "1.2.0-notes", "CREATE TABLE intake_notes\n")
    _manifest(infrastructure, {"1.0.0-noinbox": "2026-09-06T00:00:00+00:00", "1.2.0-notes": "2026-11-03T00:00:00+00:00"})
    monkeypatch.setattr(sys.modules[__name__], "_infrastructure", lambda: infrastructure)
    with pytest.raises(pytest.fail.Exception, match="找不到有入箱、没有待整理记录"):
        _older_release()


def test_an_untracked_pointed_release_is_materialized_from_git_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _git(tmp_path, "init")
    pkg = tmp_path / _PROJECT_PACKAGE_PREFIX
    pkg.mkdir(parents=True)
    (pkg / "__main__.py").write_text("print('ok')\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "release source")
    head = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    release_id = f"1.3.3-{head[:7]}"
    infrastructure = tmp_path / "00_Infrastructure" / "auto_pm"
    infrastructure.mkdir(parents=True)
    (infrastructure / "active_release.json").write_text(
        json.dumps({"release_path": release_id}), encoding="utf-8"
    )
    (infrastructure / "previous_release.json").write_text(
        json.dumps({"release_path": "1.3.3-deadbee"}), encoding="utf-8"
    )
    (infrastructure / "deployment_manifest.json").write_text(
        json.dumps(
            {
                "releases": {
                    release_id: {"source_commit": head},
                    "1.3.3-deadbee": {"source_commit": "deadbee" + "0" * 33},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "_infrastructure", lambda: infrastructure)

    resolved = _release_dir("active_release.json")
    assert (resolved / "auto_pm" / "__main__.py").is_file()
    with pytest.raises(pytest.fail.Exception, match="发布目录不在或不完整"):
        _release_dir("previous_release.json")
