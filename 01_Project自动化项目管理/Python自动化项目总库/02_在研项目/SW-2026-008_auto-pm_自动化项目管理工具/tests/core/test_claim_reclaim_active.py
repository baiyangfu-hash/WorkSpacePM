"""没到期、有动静的占位谁都不能收（G 工位止血第 2 条，卡 280；试车九条第 4 条）。

试车里一个对话自己写了一句格式合格的 ``user-confirmation:…``，就把另一个对话刚领、没到期的占位收走了：``reclaim`` 只查凭据的格式，
不看占位还在不在租期里。现在租期里的占位一律拒，带不带凭据都一样；过期的照旧走原来的凭据路径（TD-SW008-485）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.claim_note_service import ClaimNoteService
from auto_pm.application.core.claim_service import ClaimError, ClaimService
from tests.git_support import git_do, git_out

IDENTITY = ("user.email=t@example.invalid", "user.name=tester")
WORD = "user-confirmation:cmsg_0123456789"


def _git(root: Path, *args: str) -> None:
    git_do(root, *args, config=IDENTITY)


class Pair:
    def __init__(self, base: Path) -> None:
        self.origin = base / "origin.git"
        self.a, self.b = base / "laptop", base / "cloud"
        _git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        _git(base, "clone", "-q", str(self.origin), str(self.a))
        (self.a / "p").mkdir()
        (self.a / "p" / "a.md").write_text("a\n", encoding="utf-8")
        _git(self.a, "add", ".")
        _git(self.a, "commit", "-q", "-m", "seed")
        _git(self.a, "push", "-q", "origin", "HEAD:main")
        _git(base, "clone", "-q", str(self.origin), str(self.b))
        self.holder = ClaimNoteService(self.a, machine="laptop")
        self.other = ClaimService(self.b, machine="cloud")

    def remote(self, card: str) -> dict[str, object]:
        body = git_out(self.origin, "show", "-s", "--format=%B", f"refs/heads/claims/{card}")
        data: dict[str, object] = json.loads(body.split("\n", 1)[1])
        return data

    def expire(self, card: str) -> None:
        ref = f"refs/heads/claims/{card}"
        tip = git_out(self.origin, "rev-parse", ref)
        data = self.remote(card)
        data["expires_at"] = "2020-01-01T00:00:00+00:00"
        tree = git_out(self.origin, "rev-parse", f"{tip}^{{tree}}")
        aged = git_out(self.origin, "-c", "user.name=t", "-c", "user.email=t@x", "commit-tree", tree, "-p", tip, "-m",
                       f"claim {card}\n" + json.dumps(data))
        _git(self.origin, "update-ref", ref, aged)


@pytest.fixture
def pair(tmp_path: Path) -> Pair:
    return Pair(tmp_path)


@pytest.mark.parametrize("word", [WORD, "user-confirmation:drill-W4-reclaim"])
def test_a_claim_inside_its_lease_is_refused_even_with_a_well_formed_word(pair: Pair, word: str) -> None:
    pair.holder.open("880", paths=["p"], goal="刚领", owner="claude-aaaaaa", machine="laptop")
    with pytest.raises(ClaimError, match="没到期") as caught:
        pair.other.reclaim("880", by="claude-bbbbbb", reason="对方没动静", approval_ref=word)
    assert "带不带用户原话都一样" in str(caught.value) and "claude-aaaaaa" in str(caught.value), "说清是谁的、为什么不能收"
    assert pair.remote("880")["status"] == "active" and pair.remote("880")["owner"] == "claude-aaaaaa", "被拒就什么都没写"


def test_a_claim_renewed_and_noted_just_now_is_refused(pair: Pair) -> None:
    pair.holder.open("881", paths=["p"], goal="在干", owner="claude-aaaaaa", machine="laptop")
    pair.holder.renew("881", owner="claude-aaaaaa")
    pair.holder.add("881", kind="draft", sender="claude-aaaaaa", to="audit", next_step="还在干")
    with pytest.raises(ClaimError, match="没到期"):
        pair.other.reclaim("881", by="claude-bbbbbb", reason="对方没动静", approval_ref=WORD)
    assert pair.remote("881")["status"] == "active" and "note" in pair.remote("881"), "被拒就什么都没写，交接记录还在顶上"


def test_an_expired_claim_still_goes_through_the_users_word(pair: Pair) -> None:
    pair.holder.open("882", paths=["p"], goal="早停了", owner="claude-aaaaaa", machine="laptop")
    pair.expire("882")
    with pytest.raises(ClaimError, match="只听用户的"):
        pair.other.reclaim("882", by="claude-bbbbbb", reason="过期没动静", approval_ref="")
    taken = pair.other.reclaim("882", by="claude-bbbbbb", reason="过期没动静", approval_ref=WORD)
    assert taken.written and pair.remote("882")["status"] == "reclaimed"
