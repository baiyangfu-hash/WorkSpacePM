"""Hand-over notes on a claim branch: a bare ``origin`` and two clones play two computers / two agents.

Every rule has a case written wrong on purpose that must be refused with nothing pushed, and the claim itself must read exactly as
it did before a note was added (the note carries the claim payload unchanged).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from auto_pm.application.core.claim_note_service import (
    KINDS,
    ClaimNoteRefusedError,
    ClaimNoteService,
)
from auto_pm.application.core.claim_service import ClaimError, ClaimService
from tests.git_support import git_do, git_out

IDENTITY = ("user.email=t@example.invalid", "user.name=tester")
CARD = "CARD-T-001"


def _git(root: Path, *args: str) -> None:
    git_do(root, *args, config=IDENTITY)


class Pair:
    def __init__(self, base: Path) -> None:
        self.origin = base / "origin.git"
        self.a = base / "laptop"
        self.b = base / "cloud"
        _git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        _git(base, "clone", "-q", str(self.origin), str(self.a))
        (self.a / "p").mkdir()
        (self.a / "p" / "draft.md").write_text("draft v1\n", encoding="utf-8")
        (self.a / "p" / "code.py").write_text("x = 1\n", encoding="utf-8")
        _git(self.a, "add", ".")
        _git(self.a, "commit", "-q", "-m", "seed")
        _git(self.a, "push", "-q", "origin", "HEAD:main")
        _git(base, "clone", "-q", str(self.origin), str(self.b))
        self.head = git_out(self.a, "rev-parse", "HEAD").strip()
        self.laptop = ClaimNoteService(self.a, machine="laptop")
        self.cloud = ClaimNoteService(self.b, machine="cloud")
        self.laptop.open(CARD, paths=["p"], goal="work", owner="claude", machine="laptop")

    def tip(self) -> str:
        return git_out(self.origin, "rev-parse", f"refs/heads/claims/{CARD}").strip()


@pytest.fixture
def pair(tmp_path: Path) -> Pair:
    return Pair(tmp_path)


def _add(service: ClaimNoteService, **overrides: object) -> object:
    arguments: dict[str, object] = {"kind": "draft", "sender": "claude", "to": "audit", "next_step": "预核草稿"}
    arguments.update(overrides)
    return service.add(CARD, **arguments)  # type: ignore[arg-type]


def _refused(pair: Pair, match: str, **overrides: object) -> None:
    before = pair.tip()
    with pytest.raises(ClaimNoteRefusedError, match=match):
        _add(pair.laptop, **overrides)
    assert pair.tip() == before, "被拒的一笔不能推上去"


# ── the claim is untouched ────────────────────────────────────────────


def test_notes_are_read_back_in_order_and_the_claim_reads_exactly_as_before(pair: Pair) -> None:
    before = [claim.as_json() | {"commit": "", "age_days": 0} for claim in ClaimService(pair.b).all_claims()]

    _add(pair.laptop, refs=["p/draft.md"], read_first=["p/draft.md"])
    _add(pair.cloud, kind="precheck", sender="audit", to="local", next_step="本机建单", verdict="fix")
    _add(pair.laptop, kind="order", sender="local", to="audit", next_step="逐字比对", chg="CHG-SCPT-2026-900")

    notes = pair.cloud.log(CARD)
    assert [(note.sequence, note.kind, note.text("from"), note.text("to")) for note in notes] == [
        (1, "draft", "claude", "audit"),
        (2, "precheck", "audit", "local"),
        (3, "order", "local", "audit"),
    ]
    assert notes[0].data["refs"] == [{"path": "p/draft.md", "sha256": hashlib.sha256(b"draft v1\n").hexdigest()}]
    assert notes[0].data["git_head"] == pair.head
    assert notes[2].commit == pair.tip()
    after = [claim.as_json() | {"commit": "", "age_days": 0} for claim in ClaimService(pair.b).all_claims()]
    assert after == before, "占位（谁、哪台机器、路径、租期、状态）不能因为记了交接记录而变"


def test_the_tip_payload_keeps_every_claim_key_so_the_gate_check_reads_the_same(pair: Pair) -> None:
    def payload() -> dict[str, dict[str, object]]:
        body = git_out(pair.origin, "show", "-s", "--format=%B", f"refs/heads/claims/{CARD}")
        loaded: dict[str, dict[str, object]] = json.loads(body.split("\n", 1)[1])  # the way pr_overlap_check.py reads it
        return loaded

    before = payload()
    _add(pair.laptop)
    after = payload()
    assert {key: value for key, value in after.items() if key != "note"} == before
    assert after["note"]["kind"] == "draft"


def test_a_renewal_after_a_note_keeps_the_record_and_the_holder(pair: Pair) -> None:
    _add(pair.laptop)
    pair.laptop.renew(CARD, owner="claude")
    _add(pair.laptop, kind="pr", to="audit", next_step="审计")

    assert [note.kind for note in pair.cloud.log(CARD)] == ["draft", "pr"]
    assert pair.cloud.all_claims()[0].owner == "claude"


def test_a_released_claim_still_takes_the_merge_note_and_stays_released(pair: Pair) -> None:
    pair.laptop.release(CARD, owner="claude")
    _add(pair.laptop, kind="merge", sender="audit", to="user", next_step="本机推到完成")

    claim = pair.cloud.all_claims()[0]
    assert claim.status == "released" and claim.free
    assert pair.cloud.log(CARD)[-1].kind == "merge"


def test_a_card_reopened_by_someone_else_continues_the_same_record(pair: Pair) -> None:
    _add(pair.laptop)
    pair.laptop.release(CARD, owner="claude")
    pair.cloud.open(CARD, paths=["p"], goal="again", owner="trae", machine="cloud")
    _add(pair.cloud, kind="takeover", sender="trae", to="trae", next_step="接着改")

    assert [note.kind for note in pair.laptop.log(CARD)] == ["draft", "takeover"]


# ── rules, each with a wrong case ─────────────────────────────────────


def test_n1_a_card_without_a_claim_cannot_be_noted_or_read(pair: Pair) -> None:
    with pytest.raises(ClaimNoteRefusedError, match="没有这张卡的占位"):
        pair.laptop.add("CARD-T-404", kind="draft", sender="claude", to="audit", next_step="x")
    with pytest.raises(ClaimNoteRefusedError, match="没有这张卡的占位"):
        pair.laptop.log("CARD-T-404")
    with pytest.raises(ClaimNoteRefusedError, match="不合法"):
        pair.laptop.log("../x")


def test_a_number_only_claim_takes_notes_before_work_starts(pair: Pair) -> None:
    number = pair.cloud.reserve_number(goal="draft first", owner="claude", machine="cloud")
    pair.cloud.add(number.card, kind="draft", sender="claude", to="audit", next_step="预核")

    assert [note.kind for note in pair.laptop.log(number.card)] == ["draft"]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"kind": "done"}, "不在表里"),
        ({"to": " "}, "--to 不能为空"),
        ({"next_step": ""}, "--next 不能为空"),
        ({"sender": ""}, "--as 不能为空"),
        ({"kind": "precheck"}, "要写结论"),
        ({"kind": "audit", "verdict": "ok"}, "--verdict 只能是"),
        ({"kind": "deliver", "changed": ["p/code.py"]}, "怎么验证的"),
        ({"kind": "deliver", "verify": "test"}, "改了哪些文件"),
        ({"kind": "deliver", "verify": "passed", "changed": ["p/code.py"]}, "--verify 只能是"),
        ({"kind": "ask-user"}, "完整的话"),
        ({"pr": 0}, "正整数"),
        ({"chg": "CHG 900"}, "不像变更单号"),
    ],
)
def test_n2_kind_and_required_fields(pair: Pair, overrides: dict[str, object], match: str) -> None:
    _refused(pair, match, **overrides)


def test_n3_a_commit_that_origin_does_not_have_is_refused(pair: Pair) -> None:
    (pair.a / "p" / "local.md").write_text("only here\n", encoding="utf-8")
    _git(pair.a, "add", ".")
    _git(pair.a, "commit", "-q", "-m", "local only")

    _refused(pair, "不在 origin 上")
    _refused(pair, "查不到这个提交", git_head="0" * 40)
    _refused(pair, "不是提交号", git_head="--all")

    _git(pair.a, "push", "-q", "origin", "HEAD:refs/heads/claude/work")
    _add(pair.laptop, refs=["p/local.md"])  # pushed: the remote-tracking branch is refreshed and the note is taken


def test_n3_a_merged_pr_whose_branch_is_gone_is_found_under_refs_pull(pair: Pair) -> None:
    (pair.a / "p" / "pr.md").write_text("pr\n", encoding="utf-8")
    _git(pair.a, "add", ".")
    _git(pair.a, "commit", "-q", "-m", "pr work")
    _git(pair.a, "push", "-q", "origin", "HEAD:refs/pull/7/head")  # what GitHub keeps after the branch is deleted

    _refused(pair, "不在 origin 上")
    _add(pair.laptop, kind="audit", verdict="pass", pr=7, sender="audit", to="user", next_step="合并")


def test_n4_files_are_judged_by_the_commit_not_by_the_working_tree(pair: Pair) -> None:
    (pair.a / "p" / "untracked.md").write_text("not committed\n", encoding="utf-8")
    _refused(pair, "在提交 .* 里不存在", refs=["p/untracked.md"])
    _refused(pair, "在提交 .* 里不存在", read_first=["p/untracked.md"])
    _refused(pair, "仓库根起的相对路径", refs=["../outside.md"])
    _refused(pair, "仓库根起的相对路径", read_first=["/etc/passwd"])

    (pair.a / "p" / "draft.md").unlink()  # gone from the working tree, still in the commit
    (pair.a / "p" / "code.py").write_text("x = 2  # edited, not committed\n", encoding="utf-8")
    note = _add(pair.laptop, refs=["p/draft.md", "p/code.py"], read_first=["p/draft.md"])
    assert [ref["sha256"] for ref in note.data["refs"]] == [  # type: ignore[attr-defined]
        hashlib.sha256(b"draft v1\n").hexdigest(),
        hashlib.sha256(b"x = 1\n").hexdigest(),
    ]


def test_n5_a_pr_number_origin_does_not_know_is_refused(pair: Pair) -> None:
    _refused(pair, "查不到 PR #99", pr=99)


def test_n6_delivered_files_must_be_inside_the_claimed_paths(pair: Pair) -> None:
    _refused(pair, "不在卡 .* 占位登记的路径里：other/x.py", kind="deliver", verify="test", changed=["p/code.py", "other/x.py"])
    _refused(pair, "不在卡 .* 占位登记的路径里", kind="deliver", verify="test", changed=["px/code.py"])
    _add(pair.laptop, kind="deliver", verify="none", changed=["p/code.py"])


@pytest.mark.parametrize("word", ["已批准", "已完成", "已验收", "已合并", "approved", "Completed", "ACCEPTED", "merged"])
@pytest.mark.parametrize("field", ["next_step", "risk", "caution", "ask_user", "to"])
def test_n7_state_words_are_refused_in_free_text(pair: Pair, word: str, field: str) -> None:
    _refused(pair, "状态词", **{field: f"用户 {word} 了"})


def test_n7_does_not_hit_ordinary_sentences_paths_or_ids(pair: Pair) -> None:
    (pair.a / "p" / "merged_approved.md").write_text("m\n", encoding="utf-8")
    _git(pair.a, "add", ".")
    _git(pair.a, "commit", "-q", "-m", "name with words")
    _git(pair.a, "push", "-q", "origin", "HEAD:main")

    _add(
        pair.laptop,
        kind="ask-user",
        next_step="等用户批准后合并；unmerged 的分支先留着",
        ask_user="请在本机说：批准 CHG-SCPT-2026-900",
        refs=["p/merged_approved.md"],
        read_first=["p/merged_approved.md"],
        chg="CHG-merged-1",
        refs_outside=["plans/已完成的草稿.md#" + "a" * 64],
    )


def test_n8_after_void_only_a_takeover_is_taken(pair: Pair) -> None:
    _add(pair.laptop, kind="void", to="nobody", next_step="无")
    _refused(pair, "上一笔是作废", kind="deliver", verify="test", changed=["p/code.py"])
    _add(pair.laptop, kind="takeover", to="trae", next_step="重新做")
    _add(pair.laptop, kind="pr", to="audit", next_step="审计")


def test_n9_offline_records_nothing_anywhere(pair: Pair, tmp_path: Path) -> None:
    _git(pair.a, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    refs_before = git_out(pair.a, "for-each-ref")

    with pytest.raises(ClaimError) as caught:
        _add(pair.laptop)
    assert not isinstance(caught.value, ClaimNoteRefusedError), "离线是 Git 错（退出码 2），不是规则拒绝"
    assert git_out(pair.a, "for-each-ref") == refs_before, "本机也不暂存"


def test_n10_long_text_and_bad_outside_references_are_refused(pair: Pair) -> None:
    _refused(pair, "超过 500 字", next_step="长" * 501)
    _refused(pair, "路径#sha256", refs_outside=["plans/x.md"])
    _refused(pair, "路径#sha256", refs_outside=["plans/x.md#abc"])
    _refused(pair, "超过 8 KB", refs_outside=[f"plans/{'很长的名字' * 20}{index}.md#" + "b" * 64 for index in range(40)])

    note = _add(pair.laptop, refs_outside=["plans/x.md#" + "C" * 64])
    assert note.data["refs_outside"] == [{"path": "plans/x.md", "sha256": "c" * 64, "checked": "no"}]  # type: ignore[attr-defined]


# ── two writers ───────────────────────────────────────────────────────


def test_a_writer_that_lost_the_race_reads_again_and_both_notes_stay(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    """The cloud reads the tip, then the laptop pushes first: the cloud's first push is refused by the server and it retries."""

    real_commit = pair.cloud._commit
    raced: list[str] = []

    def commit_after_the_other_side_wrote(card: str, payload: dict[str, object], parent: str) -> str:
        if not raced:
            raced.append(parent)
            _add(pair.laptop, kind="draft", next_step="laptop first")
        return real_commit(card, payload, parent)

    monkeypatch.setattr(pair.cloud, "_commit", commit_after_the_other_side_wrote)
    second = _add(pair.cloud, kind="precheck", verdict="pass", sender="audit", to="local", next_step="cloud second")

    notes = pair.laptop.log(CARD)
    assert [note.text("next") for note in notes] == ["laptop first", "cloud second"]
    assert second.sequence == 2  # type: ignore[attr-defined]
    assert git_out(pair.origin, "rev-parse", f"{notes[1].commit}^").strip() == notes[0].commit, "后写的接在先写的上面，谁也没被盖掉"


def test_a_writer_that_keeps_losing_gives_up_with_a_git_error(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    real_commit = pair.cloud._commit

    def always_late(card: str, payload: dict[str, object], parent: str) -> str:
        pair.laptop.renew(CARD, owner="claude")
        return real_commit(card, payload, parent)

    monkeypatch.setattr(pair.cloud, "_commit", always_late)
    with pytest.raises(ClaimError, match="没推成功") as caught:
        _add(pair.cloud)
    assert not isinstance(caught.value, ClaimNoteRefusedError)
    assert pair.laptop.log(CARD) == []


# ── reading writes nothing ────────────────────────────────────────────


def test_log_changes_nothing_on_origin_or_in_the_working_tree(pair: Pair) -> None:
    _add(pair.laptop)
    origin_before = git_out(pair.origin, "for-each-ref")
    status_before = git_out(pair.b, "status", "--porcelain")

    pair.cloud.log(CARD)
    pair.cloud.log(CARD, fetch=False)

    assert git_out(pair.origin, "for-each-ref") == origin_before
    assert git_out(pair.b, "status", "--porcelain") == status_before == ""


def test_a_claim_without_notes_reads_as_an_empty_record(pair: Pair) -> None:
    assert pair.cloud.log(CARD) == []


def test_every_kind_has_a_chinese_name() -> None:
    assert len(KINDS) == 13 and all(name for name in KINDS.values())
