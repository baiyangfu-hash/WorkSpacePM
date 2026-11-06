"""Cross-machine card claims (D-39 steps 1-2): a bare ``origin`` and two clones play two computers / cloud sessions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.claim_service import ClaimError, ClaimService
from tests.git_support import git_do, git_out

IDENTITY = ("user.email=t@example.invalid", "user.name=tester")


def _git(root: Path, *args: str) -> None:
    git_do(root, *args, config=IDENTITY)


class Pair:
    def __init__(self, base: Path) -> None:
        self.origin = base / "origin.git"
        self.a = base / "laptop"
        self.b = base / "cloud"
        _git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        _git(base, "clone", "-q", str(self.origin), str(self.a))
        planning = self.a / "p" / "02_规划"
        planning.mkdir(parents=True)
        (planning / "241_登记卡_PM.md").write_text("x\n", encoding="utf-8")
        _git(self.a, "add", ".")
        _git(self.a, "commit", "-q", "-m", "seed")
        _git(self.a, "push", "-q", "origin", "HEAD:main")
        _git(base, "clone", "-q", str(self.origin), str(self.b))
        self.laptop = ClaimService(self.a)
        self.cloud = ClaimService(self.b)


@pytest.fixture
def pair(tmp_path: Path) -> Pair:
    return Pair(tmp_path)


def test_two_computers_cannot_both_claim_the_same_card(pair: Pair) -> None:
    pair.laptop.open("250", paths=["p/a"], goal="laptop work", owner="claude", machine="laptop")

    with pytest.raises(ClaimError, match=r"卡 250 已被领走.*laptop"):
        pair.cloud.open("250", paths=["p/other"], goal="cloud work", owner="claude", machine="cloud")


def test_a_race_where_the_loser_has_not_seen_the_claim_is_still_refused_by_the_server(pair: Pair) -> None:
    """The cloud listed before the laptop pushed: the server's create-only push is what stops it."""

    stale = pair.cloud.all_claims()
    assert stale == []
    pair.laptop.open("251", paths=["p/a"], goal="first", owner="claude", machine="laptop")
    pair.cloud.all_claims = lambda **_: []  # type: ignore[method-assign]  # the cloud still believes there is nothing

    with pytest.raises(ClaimError, match="刚被别人领走"):
        pair.cloud.open("251", paths=["p/b"], goal="second", owner="claude", machine="cloud")


def test_auto_gives_each_computer_a_different_number_above_main_and_claims(pair: Pair) -> None:
    first = pair.laptop.open("auto", paths=["p/a"], goal="a", owner="claude", machine="laptop")
    second = pair.cloud.open("auto", paths=["p/b"], goal="b", owner="claude", machine="cloud")

    assert first.card == "242", "main 上最大的卡文件是 241"
    assert second.card == "243"


def test_overlapping_paths_are_refused_and_name_the_holder(pair: Pair) -> None:
    pair.laptop.open("260", paths=["p/module"], goal="refactor", owner="claude", machine="laptop")

    with pytest.raises(ClaimError, match=r"路径.*重叠.*laptop"):
        pair.cloud.open("261", paths=["p/module/inner.py"], goal="fix", owner="trae", machine="cloud")
    pair.cloud.open("262", paths=["p/elsewhere"], goal="fine", owner="trae", machine="cloud")  # no overlap: fine


def test_release_frees_the_card_and_paths_without_deleting_the_branch(pair: Pair) -> None:
    pair.laptop.open("270", paths=["p/a"], goal="x", owner="claude", machine="laptop")

    pair.laptop.release("270", owner="claude")

    remote = git_out(pair.origin, "for-each-ref", "refs/heads/claims/")
    assert "claims/270" in remote, "云端删不了分支，释放不能靠删除"
    assert pair.cloud.all_claims()[0].free
    taken_over = pair.cloud.open("270", paths=["p/a"], goal="cloud takes over", owner="trae", machine="cloud")
    assert taken_over.owner == "trae" and not taken_over.free


def test_only_the_holder_releases(pair: Pair) -> None:
    pair.laptop.open("271", paths=["p/a"], goal="x", owner="claude", machine="laptop")

    with pytest.raises(ClaimError, match="不是 trae"):
        pair.cloud.release("271", owner="trae")


def test_an_expired_lease_counts_as_free(pair: Pair) -> None:
    pair.laptop.open("280", paths=["p/a"], goal="forgotten", owner="claude", machine="laptop")
    ref = "refs/heads/claims/280"
    tip = git_out(pair.origin, "rev-parse", ref)
    body = git_out(pair.origin, "show", "-s", "--format=%B", tip).split("\n", 1)[1].strip()
    data = json.loads(body)
    data["expires_at"] = "2020-01-01T00:00:00+00:00"
    tree = git_out(pair.origin, "rev-parse", f"{tip}^{{tree}}")
    expired = git_out(pair.origin, "-c", "user.name=t", "-c", "user.email=t@x", "commit-tree", tree, "-p", tip, "-m", "claim 280\n" + json.dumps(data))
    _git(pair.origin, "update-ref", ref, expired)

    claims = pair.cloud.all_claims()
    assert claims[0].free
    pair.cloud.open("281", paths=["p/a"], goal="the paths are free now", owner="trae", machine="cloud")


def test_offline_is_reported_not_pretended(pair: Pair, tmp_path: Path) -> None:
    _git(pair.a, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    with pytest.raises(ClaimError, match="无法读取远程占位"):
        pair.laptop.open("290", paths=["p/a"], goal="x", owner="claude")


def test_paths_and_owner_are_required(pair: Pair) -> None:
    with pytest.raises(ClaimError, match="路径"):
        pair.laptop.open("300", paths=[], goal="x", owner="claude")
    with pytest.raises(ClaimError, match="不能用"):
        pair.laptop.open("../x", paths=["p"], goal="x", owner="claude")
