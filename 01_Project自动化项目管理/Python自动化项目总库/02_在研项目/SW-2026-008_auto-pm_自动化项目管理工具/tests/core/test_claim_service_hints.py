"""D-152 (#653 audit suggestions): the refusal texts and the goal rule of ``claim number``.

Kept apart from ``test_claim_service.py`` (another card holds that file); it builds the same two-computer ``Pair`` as that file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.claim_service import ClaimError
from tests.core.test_claim_service import Pair, _set_expiry
from tests.git_support import git_out


@pytest.fixture
def pair(tmp_path: Path) -> Pair:
    return Pair(tmp_path)


def test_d152_exhausted_auto_retries_do_not_blame_a_card_called_auto(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pair.cloud, "_create", lambda *a, **k: None)  # every push is refused

    with pytest.raises(ClaimError) as raised:
        pair.cloud.reserve_number(goal="一直输", owner="claude", machine="cloud")

    assert "卡 auto" not in str(raised.value)
    assert "连续 8 次" in str(raised.value) and "再运行一次" in str(raised.value)


def test_d152_a_named_card_that_lost_the_race_still_names_the_card(pair: Pair) -> None:
    pair.laptop.open("252", paths=["p/a"], goal="first", owner="claude", machine="laptop")
    pair.cloud.all_claims = lambda **_: []  # type: ignore[method-assign]

    with pytest.raises(ClaimError, match="卡 252 刚被别人领走"):
        pair.cloud.open("252", paths=["p/b"], goal="second", owner="claude", machine="cloud")


@pytest.mark.parametrize("goal", ["", "   "])
def test_d152_reserve_number_refuses_an_empty_goal_and_pushes_nothing(pair: Pair, goal: str) -> None:
    with pytest.raises(ClaimError, match="--goal"):
        pair.laptop.reserve_number(goal=goal, owner="claude", machine="laptop")

    assert pair.laptop.all_claims() == []


def _remote(pair: Pair, card: str) -> dict[str, object]:
    """What the server itself says about ``card`` now."""

    tip = git_out(pair.origin, "rev-parse", f"refs/heads/claims/{card}")
    data: dict[str, object] = json.loads(git_out(pair.origin, "show", "-s", "--format=%B", tip).split("\n", 1)[1].strip())
    return data


def test_td397_releasing_an_expired_active_claim_writes_released_on_the_server(pair: Pair) -> None:
    pair.laptop.open("397", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    _set_expiry(pair, "397", "2020-01-01T00:00:00+00:00")
    assert _remote(pair, "397")["status"] == "active"

    assert pair.laptop.release("397", owner="claude") is True
    assert _remote(pair, "397")["status"] == "released", "an expired lease is not the same as letting go: it is written down"
    assert pair.laptop.release("397", owner="claude") is False, "a second release writes nothing and says so"


def test_td397_releasing_someone_elses_expired_claim_is_still_refused(pair: Pair) -> None:
    pair.laptop.open("398", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    _set_expiry(pair, "398", "2020-01-01T00:00:00+00:00")

    with pytest.raises(ClaimError, match="别人的占位只由用户决定"):
        pair.cloud.release("398", owner="trae")
    assert _remote(pair, "398")["status"] == "active"


def test_td485_reclaiming_an_expired_active_claim_records_who_why_and_on_whose_word(pair: Pair) -> None:
    pair.laptop.open("485", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    _set_expiry(pair, "485", "2020-01-01T00:00:00+00:00")

    taken = pair.cloud.reclaim("485", by="trae", reason="过期没动静", approval_ref="user-confirmation:cmsg_0123456789")

    assert taken.written and taken.status == "reclaimed"
    on_server = _remote(pair, "485")
    assert on_server["status"] == "reclaimed" and on_server["reclaimed_on"] == "user-confirmation:cmsg_0123456789"
    assert on_server["reclaimed_by"] == "trae" and on_server["reclaimed_reason"] == "过期没动静"
    again = pair.cloud.reclaim("485", by="trae", reason="再收", approval_ref="user-confirmation:cmsg_0123456789")
    assert not again.written and again.status == "reclaimed", "an already reclaimed claim is returned as it is"
    assert _remote(pair, "485")["reclaimed_reason"] == "过期没动静", "and nothing new is written"


def test_td578_the_orient_notice_says_it_is_the_last_fetch_and_points_to_claim_list(
    pair: Pair, capsys: pytest.CaptureFixture[str]
) -> None:
    from auto_pm.ui.cli.pm import _claims_notice

    pair.laptop.open("578", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    pair.cloud.all_claims()  # the cloud fetched while the claim was held
    pair.laptop.release("578", owner="claude")  # released since; the cloud has not fetched again

    assert [claim["card"] for claim in _claims_notice(str(pair.b), ())] == ["578"]
    err = capsys.readouterr().err
    assert "本机上次抓到的占位里，有人领着 卡 578" in err
    assert "以 `main.py claim list`（联网）为准" in err
    assert not any(claim.card == "578" and not claim.free for claim in pair.cloud.all_claims()), "claim list (fetching) calls it free"
    assert _claims_notice(str(pair.b), ()) == [] and "[领卡占位]" not in capsys.readouterr().err, "after a fetch the notice agrees"
