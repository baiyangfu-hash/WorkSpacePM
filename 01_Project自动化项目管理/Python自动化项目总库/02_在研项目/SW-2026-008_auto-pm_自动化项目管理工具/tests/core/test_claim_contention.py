"""交接记录并发写不丢（G 工位止血第 1 条，卡 280；试车九条第 2 条）。

根因：同一个控制根里两个对话同时 ``claim note``，两边都 ``git fetch`` 远程占位，抢同一个本机引用锁
（``cannot lock ref 'refs/remotes/origin/claims/…'``），输的一方被当成“离线”报“这一笔没有记上”。不是断网，是本机抢锁。

这里在同一个克隆里并发记 50 轮（每轮两笔同时记），一笔不许丢；真断网（origin 不存在）照旧说断网；本机抢锁说清是
“别人刚记了一笔”，不说断网；推上去以后刷新本机引用失败不算没记上。
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from auto_pm.application.core import claim_service
from auto_pm.application.core.claim_note_service import ClaimNoteService
from auto_pm.application.core.claim_service import ClaimContentionError, ClaimError, ClaimService
from tests.git_support import git_do, git_out

IDENTITY = ("user.email=t@example.invalid", "user.name=tester")
CARD = "CARD-T-280"
ROUNDS = 50


def _git(root: Path, *args: str) -> None:
    git_do(root, *args, config=IDENTITY)


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    root = tmp_path / "root"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(root))
    (root / "p").mkdir()
    (root / "p" / "a.md").write_text("a\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "push", "-q", "origin", "HEAD:main")
    ClaimService(root, machine="vm").open(CARD, paths=["p"], goal="并发记交接记录", owner="claude", machine="vm")
    return root


def _held_lock(root: Path) -> Path:
    """别的命令正在改这张卡的本机远程引用：origin 上已经是新的一笔，本机副本还是旧值，锁文件还在（git 写引用先建 <ref>.lock）。"""

    ref = f"refs/remotes/origin/claims/{CARD}"
    before = git_out(root, "rev-parse", ref)
    ClaimNoteService(root, machine="vm").add(CARD, kind="draft", sender="other", to="audit", next_step="别人刚推的一笔")
    git_do(root, "update-ref", ref, before)
    lock = root / ".git" / (ref + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(before + "\n", encoding="utf-8")
    return lock


def _note(root: Path, who: str) -> None:
    ClaimNoteService(root, machine="vm").add(CARD, kind="draft", sender=who, to="audit", next_step=f"{who} 的下一步")


def test_fifty_rounds_of_two_notes_at_once_in_one_clone_lose_nothing(clone: Path) -> None:
    failures: list[str] = []

    def write(who: str, start: threading.Barrier) -> None:
        start.wait()
        try:
            _note(clone, who)
        except ClaimError as error:  # 一笔没记上就是丢了
            failures.append(f"{who}: {error}")

    for round_no in range(ROUNDS):
        start = threading.Barrier(2)
        threads = [threading.Thread(target=write, args=(f"r{round_no}-{side}", start)) for side in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert failures == [], failures[:5]
    senders = [note.text("from") for note in ClaimNoteService(clone, machine="vm").log(CARD)]
    assert len(senders) == 2 * ROUNDS and len(set(senders)) == 2 * ROUNDS, "并发 50 轮必须 100 笔都在、一笔不重"


def test_a_lock_race_on_the_local_ref_is_retried_and_never_called_offline(clone: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = _held_lock(clone)
    released: list[float] = []
    real_sleep = claim_service._sleep

    def sleep(seconds: float) -> None:
        released.append(seconds)
        if len(released) == 2:
            lock.unlink()  # 别人记完放锁
        real_sleep(0)

    monkeypatch.setattr(claim_service, "_sleep", sleep)
    ClaimService(clone, machine="vm").all_claims()  # 默认会先取远程占位
    assert len(released) >= 2, "抢锁时要等一下再取，不能直接报错"


def test_a_lock_that_never_frees_says_someone_else_is_writing_not_offline(clone: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _held_lock(clone)
    monkeypatch.setattr(claim_service, "_sleep", lambda seconds: None)
    with pytest.raises(ClaimContentionError) as caught:
        _note(clone, "late")
    text = str(caught.value)
    assert "别人刚记了一笔" in text and "已重试" in text, text
    assert "离线" not in text and "不是断网" in text, text


def test_a_missing_origin_still_says_offline(clone: Path) -> None:
    _git(clone, "remote", "set-url", "origin", str(clone.parent / "gone.git"))
    with pytest.raises(ClaimError) as caught:
        _note(clone, "offline")
    assert not isinstance(caught.value, ClaimContentionError)
    assert "离线" in str(caught.value)


def test_a_note_that_reached_origin_is_recorded_even_if_refreshing_the_local_ref_fails(
    clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ClaimNoteService(clone, machine="vm")
    real_fetch = service._fetch
    calls: list[int] = []

    def fetch(*, timeout: float | None = None, card: str = "") -> None:
        calls.append(1)
        if len(calls) > 1:  # 推送之后那一次刷新失败
            raise ClaimContentionError("别人刚记了一笔（本机占位引用正被别的命令更新），已重试仍没读到")
        real_fetch(timeout=timeout, card=card)

    monkeypatch.setattr(service, "_fetch", fetch)
    note = service.add(CARD, kind="draft", sender="push-then-refresh-fails", to="audit", next_step="无")
    origin_tip = git_out(clone, "ls-remote", "origin", f"refs/heads/claims/{CARD}").split()[0]
    assert note.commit == origin_tip, "推上去了就是记上了，刷新本机引用失败不能报“没有记上”"


def test_a_lock_held_on_another_cards_ref_does_not_stop_a_note_on_this_card(clone: Path) -> None:
    """试车第 2 条 2b 的真因：别的对话正改卡甲的本机引用（锁还在），给卡乙记一笔不该被拖下水。"""
    ClaimService(clone, machine="vm").open("CARD-OTHER", paths=["q"], goal="别人的卡", owner="claude-bbbbbb", machine="vm")
    ref = "refs/remotes/origin/claims/CARD-OTHER"
    before = git_out(clone, "rev-parse", ref)
    ClaimNoteService(clone, machine="vm").add("CARD-OTHER", kind="draft", sender="other", to="audit", next_step="别人刚推的")
    git_do(clone, "update-ref", ref, before)
    lock = clone / ".git" / (ref + ".lock")
    lock.write_text(before + "\n", encoding="utf-8")  # 一直不放
    note = ClaimNoteService(clone, machine="vm").add(CARD, kind="draft", sender="mine", to="audit", next_step="我的这一笔")
    assert note.commit == git_out(clone, "ls-remote", "origin", f"refs/heads/claims/{CARD}").split()[0]
    lock.unlink()


def test_a_push_that_landed_although_git_reported_a_local_error_is_recorded_once(clone: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ClaimNoteService(clone, machine="vm")
    real_run = service._run

    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        result = real_run(arguments, **kwargs)  # type: ignore[arg-type]
        if arguments[:1] == ["push"] and result.returncode == 0:  # origin 收下了，只是本机跟踪引用没更新成
            return subprocess.CompletedProcess(result.args, 1, result.stdout, b"error: cannot lock ref 'refs/remotes/origin/claims/x'")
        return result

    monkeypatch.setattr(service, "_run", run)
    note = service.add(CARD, kind="draft", sender="landed", to="audit", next_step="无")
    senders = [item.text("from") for item in ClaimNoteService(clone, machine="vm").log(CARD)]
    assert senders == ["landed"], "推上去了就是记上了，不能当没记上再推一遍"
    assert note.retries == 0


def test_the_cli_says_someone_else_just_wrote_not_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    from auto_pm.ui.cli import claim as claim_cli

    class Busy:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def add(self, *args: object, **kwargs: object) -> None:
            raise ClaimContentionError("交接记录没推成功：别人刚记了一笔，已重试 8 次都被抢先")

        def log(self, *args: object, **kwargs: object) -> None:
            raise ClaimContentionError("别人刚记了一笔（本机的占位引用正被另一条命令更新），已重试 6 次仍没读到；不是断网")

    monkeypatch.setattr(claim_cli, "ClaimNoteService", Busy)
    obj = type("Ctx", (), {"control_root": "/x", "workspace_root": ""})()
    noted = CliRunner().invoke(claim_cli.claim_group, ["note", CARD, "--kind", "draft", "--to", "audit", "--next", "无", "--as", "claude"], obj=obj)
    assert noted.exit_code == 2 and "别人刚记了一笔、已重试" in noted.output and "联网后" not in noted.output, noted.output
    logged = CliRunner().invoke(claim_cli.claim_group, ["log", CARD], obj=obj)
    assert logged.exit_code == 2 and "离线或连不上" not in logged.output, logged.output
