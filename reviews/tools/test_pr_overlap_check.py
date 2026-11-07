"""D-101：PR 撞车与领卡检查（假 GitHub，不联网）。验收：两个范围重叠的 PR，第二个被拦下并点名；没订卡的 PR 被拦下。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_overlap_check as check_module
from pr_overlap_check import ApiError, NotFound, check, overlap

REPO = "o/r"
EARLY = "2026-11-07T10:00:00Z"
LATE = "2026-11-07T12:00:00Z"
BEFORE_ENFORCE = "2026-11-01T00:00:00Z"
ENFORCE_FROM = "2026-11-05T00:00:00Z"


def body(*scope: str, claim: str = "", waiver: str = "") -> str:
    lines = ["## 可改范围", *[f"- {path}" for path in scope], ""]
    if claim:
        lines.append(f"领卡占位: {claim}")
    if waiver:
        lines.append(f"重叠放行: {waiver}")
    return "\n".join(lines)


class FakeGitHub:
    """Just enough of the REST API: PRs (body, files, commits), claim refs."""

    def __init__(self) -> None:
        self.prs: dict[int, dict[str, object]] = {}
        self.files: dict[int, list[str]] = {}
        self.commit_times: dict[int, list[str]] = {}
        self.claims: dict[str, dict[str, object]] = {}
        self.fail = False

    def add_pr(self, number: int, pr_body: str, files: list[str], *, created: str = LATE, draft: bool = False, commit: str = LATE) -> None:
        self.prs[number] = {"number": number, "title": f"pr {number}", "body": pr_body, "draft": draft, "created_at": created}
        self.files[number] = files
        self.commit_times[number] = [commit]

    def claim(
        self, card: str, paths: list[str], *, claimed_at: str = EARLY, status: str = "active", expires_at: str = "2099-01-01T00:00:00Z", released_at: str = ""
    ) -> None:
        self.claims[card] = {
            "paths": paths, "claimed_at": claimed_at, "status": status, "owner": "claude", "expires_at": expires_at, "released_at": released_at,
        }

    def __call__(self, path: str) -> object:
        if self.fail:
            raise ApiError("down")
        route, _, query = path.partition("?")
        page = int(dict(item.split("=") for item in query.split("&")).get("page", "1")) if query else 1
        parts = route.strip("/").split("/")[3:]  # drop repos/<owner>/<name>
        if parts[0] == "pulls" and len(parts) == 1:
            return list(self.prs.values()) if page == 1 else []
        if parts[0] == "pulls" and len(parts) == 2:
            return self.prs[int(parts[1])]
        if parts[0] == "pulls" and parts[2] == "files":
            return [{"filename": name} for name in self.files[int(parts[1])]] if page == 1 else []
        if parts[0] == "pulls" and parts[2] == "commits":
            return [{"commit": {"committer": {"date": date}}} for date in self.commit_times[int(parts[1])]] if page == 1 else []
        if parts[:3] == ["git", "ref", "heads"]:
            card = "/".join(parts[3:])[len("claims/"):]
            if card not in self.claims:
                raise NotFound(route)
            return {"object": {"sha": f"sha-{card}"}}
        if parts[:2] == ["git", "commits"]:
            card = parts[2][len("sha-"):]
            return {"message": f"claim {card}\n" + json.dumps(self.claims[card])}
        raise AssertionError(f"unexpected request {path}")


@pytest.fixture
def github() -> FakeGitHub:
    return FakeGitHub()


def run(github: FakeGitHub, number: int, enforce_from: str = ENFORCE_FROM) -> check_module.Result:
    return check(github, REPO, number, str(github.prs[number]["body"]), enforce_from)


def test_overlap_means_equal_or_inside_a_directory() -> None:
    assert overlap(["a/b.py"], ["a/b.py"]) == ["a/b.py"]
    assert overlap(["a"], ["a/b.py", "c.py"]) == ["a/b.py"]
    assert overlap(["a/b.py"], ["a"]) == ["a/b.py"]
    assert overlap(["a/b.py"], ["a/bc.py"]) == [], "a shared name prefix is not a directory"


def test_the_second_pr_on_the_same_file_is_stopped_and_names_the_first(github: FakeGitHub) -> None:
    github.claim("c2", ["pkg"])
    github.add_pr(10, body("pkg/mod.py", claim="c1"), ["pkg/mod.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, body("pkg/mod.py", claim="c2"), ["pkg/mod.py"], created=LATE)

    first = run(github, 10)
    second = run(github, 11)

    assert first.passed, "the earlier PR is not blocked by the later one"
    assert not second.passed
    assert any("#10" in error and "pkg/mod.py" in error for error in second.errors)


def test_a_draft_still_holds_its_files(github: FakeGitHub) -> None:
    github.add_pr(10, body("pkg/"), ["pkg/a.py"], created=BEFORE_ENFORCE, draft=True)
    github.add_pr(11, body("pkg/b.py"), ["pkg/b.py"], created=LATE)

    result = run(github, 11)

    assert any("#10（草稿）" in error for error in result.errors)


def test_the_actual_changed_files_count_even_when_the_declared_scope_is_narrow(github: FakeGitHub) -> None:
    github.add_pr(10, body("docs/x.md"), ["docs/x.md", "pkg/sneaky.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, body("pkg/sneaky.py"), ["pkg/sneaky.py"], created=LATE)

    assert not run(github, 11).passed


def test_disjoint_prs_do_not_collide(github: FakeGitHub) -> None:
    github.claim("cb", ["b"])
    github.add_pr(10, body("a/x.py"), ["a/x.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, body("b/y.py", claim="cb"), ["b/y.py"], created=LATE)

    assert run(github, 11).passed


def test_a_written_waiver_turns_the_error_into_a_named_note(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"])
    github.add_pr(10, body("pkg/mod.py"), ["pkg/mod.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, body("pkg/mod.py", claim="c1", waiver="#10 两边改不同函数，先合 10"), ["pkg/mod.py"], created=LATE)

    result = run(github, 11)

    assert result.passed
    assert any("#10" in note and "已按描述放行" in note for note in result.notes)


def test_a_waiver_for_another_pr_does_not_cover_this_one(github: FakeGitHub) -> None:
    github.add_pr(10, body("pkg/mod.py"), ["pkg/mod.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, body("pkg/mod.py", waiver="#99 无关"), ["pkg/mod.py"], created=LATE)

    assert not run(github, 11).passed


def test_a_pr_with_a_claim_made_before_its_first_commit_passes(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"])
    github.add_pr(11, body("pkg/mod.py", claim="c1"), ["pkg/mod.py"], commit=LATE)

    assert run(github, 11).passed


def test_no_claim_line_stops_a_new_pr_but_only_warns_an_old_one(github: FakeGitHub) -> None:
    github.add_pr(11, body("pkg/mod.py"), ["pkg/mod.py"], created=LATE)
    github.add_pr(5, body("other.py"), ["other.py"], created=BEFORE_ENFORCE)

    new = run(github, 11)
    old = run(github, 5)

    assert any("领卡占位" in error for error in new.errors)
    assert old.passed and any("只提示" in note for note in old.notes)


def test_a_claim_branch_that_does_not_exist_is_refused(github: FakeGitHub) -> None:
    github.add_pr(11, body("pkg/mod.py", claim="ghost"), ["pkg/mod.py"])

    assert any("远程没有 `claims/ghost`" in error for error in run(github, 11).errors)


def test_code_before_the_claim_is_refused(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"], claimed_at="2026-11-07T13:00:00Z")
    github.add_pr(11, body("pkg/mod.py", claim="c1"), ["pkg/mod.py"], commit="2026-11-07T11:00:00Z")

    assert any("先改代码后订卡" in error for error in run(github, 11).errors)


def test_a_reclaimed_claim_is_refused(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"], status="reclaimed")
    github.add_pr(11, body("pkg/mod.py", claim="c1"), ["pkg/mod.py"])

    assert any("已被收回" in error for error in run(github, 11).errors)


def test_a_scope_entry_outside_the_claimed_paths_is_refused(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.add_pr(11, body("pkg/a/x.py", "elsewhere/y.py", claim="c1"), ["pkg/a/x.py"])

    errors = run(github, 11).errors

    assert any("elsewhere/y.py" in error and "不在卡 c1 订的路径里" in error for error in errors)
    assert not any("pkg/a/x.py" in error for error in errors), "a path under a claimed directory is covered"


def test_a_github_that_does_not_answer_is_not_a_pass(github: FakeGitHub) -> None:
    github.add_pr(11, body("pkg/mod.py"), ["pkg/mod.py"])
    github.fail = True

    with pytest.raises(ApiError):
        run(github, 11)


def test_a_pr_created_before_the_enforcement_date_is_only_told_about_an_overlap(github: FakeGitHub) -> None:
    github.add_pr(10, body("pkg/mod.py"), ["pkg/mod.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, body("pkg/mod.py"), ["pkg/mod.py"], created=BEFORE_ENFORCE)

    result = run(github, 11)

    assert result.passed
    assert any("#10" in note and "只提示" in note for note in result.notes)


def test_a_claim_released_before_the_first_commit_is_refused_but_one_released_after_is_fine(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"], status="released", released_at="2026-11-07T11:00:00Z")
    github.add_pr(11, body("pkg/mod.py", claim="c1"), ["pkg/mod.py"], commit=LATE)
    assert any("之前就已放下" in error for error in run(github, 11).errors)

    github.claim("c2", ["other"], status="released", released_at="2026-11-07T13:00:00Z")
    github.add_pr(12, body("other/mod.py", claim="c2"), ["other/mod.py"], commit=LATE)
    assert run(github, 12).passed, "work finished and released afterwards"


def test_a_claim_that_had_already_expired_when_the_first_commit_was_made_is_refused(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"], expires_at="2026-11-07T11:00:00Z")
    github.add_pr(11, body("pkg/mod.py", claim="c1"), ["pkg/mod.py"], commit=LATE)

    assert any("占位无效时改了代码" in error for error in run(github, 11).errors)


def test_a_file_actually_changed_outside_the_claimed_paths_is_refused_even_if_the_scope_text_is_clean(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.add_pr(11, body("pkg/a/x.py", claim="c1"), ["pkg/a/x.py", "elsewhere/sneaky.py"])

    errors = run(github, 11).errors

    assert any("实际改到的 `elsewhere/sneaky.py`" in error for error in errors)
    assert not any("pkg/a/x.py" in error for error in errors)


def test_one_card_cannot_back_two_open_prs(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"])
    github.add_pr(10, body("pkg/a.py", claim="c1"), ["pkg/a.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, body("pkg/b.py", claim="c1"), ["pkg/b.py"], created=LATE)

    assert any("卡 c1 已被更早开着的 PR #10 引用" in error for error in run(github, 11).errors)


def multi_body(*scope: str, cards: tuple[str, ...]) -> str:
    return body(*scope, claim=cards[0]) + "".join(f"\n领卡占位: {card}" for card in cards[1:])


def test_a_pr_that_names_two_cards_is_covered_by_both_cards_paths(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.claim("c2", ["pkg/b"])
    github.add_pr(11, multi_body("pkg/a/x.py", "pkg/b/y.py", cards=("c1", "c2")), ["pkg/a/x.py", "pkg/b/y.py"])

    result = run(github, 11)

    assert result.passed, result.errors


def test_a_path_covered_by_none_of_the_named_cards_is_still_refused(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.claim("c2", ["pkg/b"])
    github.add_pr(11, multi_body("pkg/a/x.py", "elsewhere/z.py", cards=("c1", "c2")), ["pkg/a/x.py", "elsewhere/z.py"])

    errors = run(github, 11).errors

    assert any("elsewhere/z.py" in error and "c1" in error and "c2" in error for error in errors)
    assert not any("pkg/a/x.py" in error for error in errors)


def test_every_named_card_is_checked_on_its_own(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.claim("c2", ["pkg/b"], status="reclaimed")
    github.add_pr(11, multi_body("pkg/a/x.py", "pkg/b/y.py", cards=("c1", "c2")), ["pkg/a/x.py", "pkg/b/y.py"])

    errors = run(github, 11).errors

    assert any("卡 c2 的占位已被收回" in error for error in errors)
    assert not any("卡 c1 的占位已被收回" in error for error in errors)


def test_a_missing_card_among_several_is_named(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.add_pr(11, multi_body("pkg/a/x.py", cards=("c1", "ghost")), ["pkg/a/x.py"])

    assert any("远程没有 `claims/ghost`" in error for error in run(github, 11).errors)


def test_each_named_card_cannot_back_an_earlier_open_pr(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.claim("c2", ["pkg/b"])
    github.add_pr(10, body("pkg/b/old.py", claim="c2"), ["pkg/b/old.py"], created=BEFORE_ENFORCE)
    github.add_pr(11, multi_body("pkg/a/x.py", "pkg/b/y.py", cards=("c1", "c2")), ["pkg/a/x.py", "pkg/b/y.py"])

    assert any("卡 c2 已被更早开着的 PR #10 引用" in error for error in run(github, 11).errors)


def test_cards_may_share_one_line_separated_by_commas(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.claim("c2", ["pkg/b"])
    github.add_pr(11, body("pkg/a/x.py", "pkg/b/y.py", claim="c1, c2"), ["pkg/a/x.py", "pkg/b/y.py"])

    assert run(github, 11).passed


def test_an_unrelated_broad_card_cannot_ride_along_to_widen_the_union(github: FakeGitHub) -> None:
    github.claim("narrow", ["pkg/a"])
    github.claim("broad", ["pkg"])
    github.add_pr(11, multi_body("pkg/a/x.py", cards=("narrow", "broad")), ["pkg/a/x.py"])

    errors = run(github, 11).errors

    assert any("卡 broad 是多余的" in error for error in errors), errors
    assert not any("卡 narrow 是多余的" in error for error in errors)


def test_a_broad_card_that_is_really_needed_is_fine_when_the_other_one_is_the_redundant_one(github: FakeGitHub) -> None:
    github.claim("narrow", ["pkg/a"])
    github.claim("broad", ["pkg"])
    github.add_pr(11, multi_body("pkg/a/x.py", "pkg/b/y.py", cards=("narrow", "broad")), ["pkg/a/x.py", "pkg/b/y.py"])

    errors = run(github, 11).errors

    assert any("卡 narrow 是多余的" in error for error in errors), errors
    assert not any("卡 broad 是多余的" in error for error in errors)


def test_two_cards_that_each_cover_a_path_the_other_does_not_both_pass(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg/a"])
    github.claim("c2", ["pkg/b"])
    github.add_pr(11, multi_body("pkg/a/x.py", "pkg/b/y.py", cards=("c1", "c2")), ["pkg/a/x.py", "pkg/b/y.py"])

    assert run(github, 11).passed


def test_two_identical_cards_keep_only_the_first(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg"])
    github.claim("c2", ["pkg"])
    github.add_pr(11, multi_body("pkg/x.py", cards=("c1", "c2")), ["pkg/x.py"])

    errors = run(github, 11).errors

    assert any("卡 c2 是多余的" in error for error in errors)
    assert not any("卡 c1 是多余的" in error for error in errors)


def test_a_single_card_is_never_called_redundant(github: FakeGitHub) -> None:
    github.claim("c1", ["pkg", "other"])
    github.add_pr(11, body("pkg/x.py", claim="c1"), ["pkg/x.py"])

    assert run(github, 11).passed
