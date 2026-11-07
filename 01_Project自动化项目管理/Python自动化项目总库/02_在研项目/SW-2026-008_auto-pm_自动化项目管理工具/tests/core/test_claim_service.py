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
        self.laptop = ClaimService(self.a, machine="laptop")
        self.cloud = ClaimService(self.b, machine="cloud")


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


# ── step 3: orient reads claims; step 4: pr open needs a claim ──────────────────────────────────────────────────────


def test_pr_open_gate_is_on_by_default_and_off_only_when_asked(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.claim_service import claim_refusal

    monkeypatch.delenv("AUTO_PM_REQUIRE_CLAIM", raising=False)
    assert "没有有效的领卡占位" in claim_refusal(pair.a, "310", "claude"), "default is on (user, 2026-11-07)"

    for off in ("0", "false", "No", "OFF"):
        monkeypatch.setenv("AUTO_PM_REQUIRE_CLAIM", off)
        assert claim_refusal(pair.a, "310", "claude") == "", off
    monkeypatch.setenv("AUTO_PM_REQUIRE_CLAIM", "banana")
    assert "没有有效的领卡占位" in claim_refusal(pair.a, "310", "claude"), "an unreadable value does not switch the guard off"


def test_pr_open_gate_refuses_without_a_claim_and_passes_with_one(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.claim_service import claim_refusal

    monkeypatch.setenv("AUTO_PM_REQUIRE_CLAIM", "1")
    assert "没有有效的领卡占位" in claim_refusal(pair.a, "310", "claude")

    pair.laptop.open("310", paths=["p/a"], goal="x", owner="claude", machine="laptop")

    assert claim_refusal(pair.a, "310", "claude", "laptop") == ""
    assert "不是 trae" in claim_refusal(pair.b, "310", "trae"), "别人的卡不能替他开 PR"


def test_pr_open_gate_refuses_a_released_claim(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.claim_service import claim_refusal

    monkeypatch.setenv("AUTO_PM_REQUIRE_CLAIM", "1")
    pair.laptop.open("311", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    pair.laptop.release("311", owner="claude")

    assert "没有有效的领卡占位" in claim_refusal(pair.a, "311", "claude")


def test_pr_open_gate_does_not_pretend_when_offline(pair: Pair, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.claim_service import claim_refusal

    monkeypatch.setenv("AUTO_PM_REQUIRE_CLAIM", "1")
    _git(pair.a, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    assert "未核实" in claim_refusal(pair.a, "312", "claude")


def test_orient_notice_lists_other_claims_and_flags_scope_overlap(
    pair: Pair, capsys: pytest.CaptureFixture[str]
) -> None:
    from auto_pm.ui.cli.pm import _claims_notice

    pair.laptop.open("320", paths=["p/module"], goal="refactor", owner="claude", machine="laptop")
    pair.cloud.all_claims()  # a fetch, as any earlier command would have done

    found = _claims_notice(str(pair.b), ("p",))

    err = capsys.readouterr().err
    assert "[领卡占位]" in err and "laptop" in err and "重叠" in err
    assert found[0]["card"] == "320" and found[0]["overlaps_scope"] == ["p"]
    assert _claims_notice(str(pair.b), ("elsewhere",))[0]["overlaps_scope"] == []


def test_renew_pushes_the_lease_forward_and_only_the_holder_may(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core import claim_service

    opened = pair.laptop.open("330", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    monkeypatch.setattr(claim_service, "LEASE_HOURS", claim_service.LEASE_HOURS + 3)  # a later "now + lease" must show in expires_at

    renewed = pair.laptop.renew("330", owner="claude")

    assert renewed.expires_at > opened.expires_at and not renewed.free
    assert next(c for c in pair.laptop.all_claims() if c.card == "330").expires_at == renewed.expires_at, "it is on the server, not only returned"
    with pytest.raises(ClaimError, match="只有持有者能续租"):
        pair.cloud.renew("330", owner="trae")


def test_a_released_or_expired_claim_cannot_be_renewed(pair: Pair) -> None:
    pair.laptop.open("331", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    pair.laptop.release("331", owner="claude")
    with pytest.raises(ClaimError, match="不能续租"):
        pair.laptop.renew("331", owner="claude")


def test_reclaim_needs_the_users_word_and_frees_the_card_without_deleting_it(pair: Pair) -> None:
    pair.laptop.open("332", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    pair.cloud.all_claims()

    with pytest.raises(ClaimError, match="只听用户的"):
        pair.cloud.reclaim("332", by="trae", reason="没动静", approval_ref="")
    with pytest.raises(ClaimError, match="只听用户的"):
        pair.cloud.reclaim("332", by="trae", reason="没动静", approval_ref="I said so")
    with pytest.raises(ClaimError, match="必须写明原因"):
        pair.cloud.reclaim("332", by="trae", reason=" ", approval_ref="user-confirmation:cmsg_0123456789")
    assert not next(c for c in pair.cloud.all_claims() if c.card == "332").free, "refused calls changed nothing"

    taken = pair.cloud.reclaim("332", by="trae", reason="没动静", approval_ref="user-confirmation:cmsg_0123456789")

    assert taken.status == "reclaimed" and taken.free
    again = pair.cloud.open("332", paths=["p/a"], goal="接手", owner="trae", machine="cloud")
    assert again.owner == "trae", "a reclaimed card can be claimed again, on top of the old history"
    assert pair.cloud.reclaim("332", by="trae", reason="再收", approval_ref="user-confirmation:cmsg_0123456789").status == "reclaimed"


def test_the_lease_is_four_hours_and_a_renewal_never_shortens_it(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime, timedelta

    from auto_pm.application.core import claim_service

    opened = pair.laptop.open("333", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    ahead = datetime.fromisoformat(opened.expires_at) - datetime.now(UTC)
    assert timedelta(hours=3, minutes=58) < ahead <= timedelta(hours=4), "the default lease is 4 hours"

    monkeypatch.setattr(claim_service, "LEASE_HOURS", 100)
    long_lease = pair.laptop.open("334", paths=["p/b"], goal="x", owner="claude", machine="laptop")
    monkeypatch.setattr(claim_service, "LEASE_HOURS", 4)

    renewed = pair.laptop.renew("334", owner="claude")

    assert renewed.expires_at == long_lease.expires_at, "renewing with a shorter lease keeps the later expiry"


def test_reclaim_refuses_a_reference_that_is_only_the_prefix_and_records_who_why_and_on_whose_word(pair: Pair) -> None:
    pair.laptop.open("335", paths=["p/a"], goal="x", owner="claude", machine="laptop")
    pair.cloud.all_claims()

    with pytest.raises(ClaimError, match="只听用户的"):
        pair.cloud.reclaim("335", by="trae", reason="没动静", approval_ref="user-confirmation:ab")

    taken = pair.cloud.reclaim("335", by="trae", reason="没动静", approval_ref="user-confirmation:cmsg_0123456789")

    record = git_out(pair.b, "show", "-s", "--format=%B", taken.commit)
    for expected in ("reclaimed_by", "trae", "没动静", "user-confirmation:cmsg_0123456789", "reclaimed_at"):
        assert expected in record, expected

def test_control_root_status_json_carries_other_claims_and_stays_pure_json(
    pair: Pair, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-39 follow-up: other threads and scripts read the claims from ``pm control-root-status --json`` (stdout is only JSON)."""

    import inspect
    from types import SimpleNamespace

    from auto_pm.ui.cli import pm as pm_cli

    pair.laptop.open("321", paths=["p/module"], goal="refactor", owner="claude", machine="laptop")
    pair.cloud.all_claims()  # a fetch, as any earlier command would have done
    root = SimpleNamespace(obj=SimpleNamespace(control_root=pair.b, workspace_root=str(pair.b)))
    ctx = SimpleNamespace(find_root=lambda: root)

    callback = pm_cli.control_root_status.callback
    assert callback is not None
    inspect.unwrap(callback)(ctx, "", True)

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert [claim["card"] for claim in data["claims"]] == ["321"]
    assert "[领卡占位]" not in captured.err, "JSON mode must not also print the human hint"
    assert "branch" in data and "on_main" in data, "the existing fields are untouched"


def _set_expiry(pair: Pair, card: str, expires_at: str) -> None:
    """Rewrite a claim's ``expires_at`` on the server (a commit on top), to age it without waiting."""

    ref = f"refs/heads/claims/{card}"
    tip = git_out(pair.origin, "rev-parse", ref)
    body = git_out(pair.origin, "show", "-s", "--format=%B", tip).split("\n", 1)[1].strip()
    data = json.loads(body)
    data["expires_at"] = expires_at
    tree = git_out(pair.origin, "rev-parse", f"{tip}^{{tree}}")
    aged = git_out(pair.origin, "-c", "user.name=t", "-c", "user.email=t@x", "commit-tree", tree, "-p", tip, "-m", f"claim {card}\n" + json.dumps(data))
    _git(pair.origin, "update-ref", ref, aged)


def test_renew_held_only_pushes_when_less_than_half_the_lease_is_left_and_only_for_my_claims(pair: Pair) -> None:
    from datetime import UTC, datetime, timedelta

    pair.laptop.open("340", paths=["p/a"], goal="fresh", owner="claude", machine="laptop")
    pair.laptop.open("341", paths=["p/b"], goal="running low", owner="claude", machine="laptop")
    pair.laptop.open("342", paths=["p/c"], goal="somebody else's", owner="trae", machine="laptop")
    low = (datetime.now(UTC) + timedelta(minutes=30)).isoformat(timespec="seconds")
    _set_expiry(pair, "341", low)
    _set_expiry(pair, "342", low)
    fresh_tip = git_out(pair.origin, "rev-parse", "refs/heads/claims/340")
    other_tip = git_out(pair.origin, "rev-parse", "refs/heads/claims/342")

    renewed = pair.laptop.renew_held("claude")

    assert [claim.card for claim in renewed] == ["341"], "only my claim that was running low"
    assert git_out(pair.origin, "rev-parse", "refs/heads/claims/340") == fresh_tip, "a fresh lease is not pushed again"
    assert git_out(pair.origin, "rev-parse", "refs/heads/claims/342") == other_tip, "somebody else's claim is never touched"
    after = next(c for c in pair.laptop.all_claims() if c.card == "341")
    assert datetime.fromisoformat(after.expires_at) > datetime.now(UTC) + timedelta(hours=3), "back to about a full lease on the server"


def test_renew_held_skips_free_claims_and_never_raises_when_git_cannot_answer(pair: Pair, tmp_path: Path) -> None:
    pair.laptop.open("343", paths=["p/a"], goal="done", owner="claude", machine="laptop")
    pair.laptop.release("343", owner="claude")
    assert pair.laptop.renew_held("claude") == [], "a released claim is not brought back to life"

    not_a_repo = ClaimService(tmp_path / "nowhere")
    assert not_a_repo.renew_held("claude") == []


# ── D-39 / D-73 / D-102 follow-ups ────────────────────────────────────────────────────────────────


def test_the_lease_can_be_shortened_for_drills_and_a_bad_value_is_refused(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    monkeypatch.setenv("AUTO_PM_CLAIM_LEASE_SECONDS", "120")
    claim = pair.laptop.open("360", paths=["p/a"], goal="short lease", owner="claude")
    left = (datetime.fromisoformat(claim.expires_at) - datetime.now(UTC)).total_seconds()
    assert 60 < left <= 120, left

    for bad in ("0", "-5", "abc", str(24 * 3600 + 1)):
        monkeypatch.setenv("AUTO_PM_CLAIM_LEASE_SECONDS", bad)
        with pytest.raises(ClaimError, match="AUTO_PM_CLAIM_LEASE_SECONDS"):
            pair.laptop.open("361", paths=["p/b"], goal="x", owner="claude")


def test_a_claim_with_a_short_lease_really_expires_and_another_clone_takes_the_card_over(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    """The drill the live test repeats on GitHub: open, let the lease run out, a second computer takes the same card."""

    monkeypatch.setenv("AUTO_PM_CLAIM_LEASE_SECONDS", "1")
    pair.laptop.open("362", paths=["p/a"], goal="will expire", owner="claude")
    import time

    time.sleep(1.5)
    monkeypatch.delenv("AUTO_PM_CLAIM_LEASE_SECONDS")

    taken = pair.cloud.open("362", paths=["p/a"], goal="took over", owner="trae")

    assert taken.owner == "trae" and not taken.free
    with pytest.raises(ClaimError, match="不是 claude"):
        pair.laptop.renew("362", owner="claude")


def test_the_loser_of_a_same_name_race_is_told_who_won(pair: Pair) -> None:
    pair.laptop.open("363", paths=["p/a"], goal="the winner's goal", owner="claude", machine="laptop")
    original = pair.cloud.all_claims
    calls = {"count": 0}

    def stale_first(**kwargs: object):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return [] if calls["count"] == 1 else original(**kwargs)  # type: ignore[arg-type]

    pair.cloud.all_claims = stale_first  # type: ignore[method-assign]

    with pytest.raises(ClaimError, match=r"刚被别人领走：卡 363（claude@laptop：the winner's goal）"):
        pair.cloud.open("363", paths=["p/b"], goal="second", owner="trae")


def test_the_same_owner_name_on_another_computer_is_not_the_holder(pair: Pair) -> None:
    pair.laptop.open("364", paths=["p/a"], goal="x", owner="claude")

    with pytest.raises(ClaimError, match="在另一台机器 laptop"):
        pair.cloud.renew("364", owner="claude")
    with pytest.raises(ClaimError, match="在另一台机器 laptop"):
        pair.cloud.release("364", owner="claude")
    assert pair.laptop.renew("364", owner="claude").owner == "claude"
    pair.laptop.release("364", owner="claude")


def test_the_pr_gate_does_not_accept_the_same_owner_name_from_another_computer(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.claim_service import claim_refusal

    monkeypatch.setenv("AUTO_PM_REQUIRE_CLAIM", "1")
    pair.laptop.open("365", paths=["p/a"], goal="x", owner="claude")

    assert claim_refusal(pair.a, "365", "claude", "laptop") == ""
    assert "在另一台机器 laptop" in claim_refusal(pair.b, "365", "claude", "cloud")


def test_a_claim_without_a_machine_is_compared_by_owner_alone(pair: Pair) -> None:
    from auto_pm.application.core.claim_service import Claim, holder_problem

    old = Claim(card="9", owner="claude", machine="?", paths=("p",), goal="", claimed_at="2026-11-07T00:00:00+00:00", commit="c")

    assert holder_problem(old, "claude", "anything") == ""
    assert "不是 trae" in holder_problem(old, "trae", "anything")


def test_renew_held_leaves_the_same_owner_name_on_another_computer_alone(pair: Pair) -> None:
    from datetime import UTC, datetime, timedelta

    pair.laptop.open("366", paths=["p/a"], goal="laptop's", owner="claude")
    _set_expiry(pair, "366", (datetime.now(UTC) + timedelta(minutes=30)).isoformat(timespec="seconds"))
    tip = git_out(pair.origin, "rev-parse", "refs/heads/claims/366")

    assert pair.cloud.renew_held("claude") == [], "the cloud session is also called claude, but it is not the holder"
    assert git_out(pair.origin, "rev-parse", "refs/heads/claims/366") == tip
