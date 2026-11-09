"""D-152 (#653 audit suggestions): the refusal texts and the goal rule of ``claim number``.

Kept apart from ``test_claim_service.py`` (another card holds that file); it builds the same two-computer ``Pair`` as that file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.claim_service import ClaimError
from tests.core.test_claim_service import Pair


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
