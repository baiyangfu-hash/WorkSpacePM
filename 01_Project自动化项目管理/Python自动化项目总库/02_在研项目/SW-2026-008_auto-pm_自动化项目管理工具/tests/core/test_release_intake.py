"""D-146 card 5: a release travels into main as slices that fit GitHub's limit, payload first, pointers last, drafts only."""

from __future__ import annotations

import pytest

from auto_pm.application.core import release_intake as ri

RID = "1.3.3-abcdef0"
BASE = f"{ri.RELEASE_ROOT}/releases/{RID}"


def _paths(count: int, width: int = 60) -> list[str]:
    return [f"{BASE}/auto_pm/{'d' * width}/file_{i:05d}.py" for i in range(count)]


class FakePort:
    def __init__(self) -> None:
        self.prs: dict[str, int] = {}
        self.merged: set[str] = set()
        self.calls: list[str] = []
        self.bodies: dict[str, str] = {}

    def existing_pr(self, branch: str) -> int | None:
        return self.prs.get(branch)

    def pr_merged(self, branch: str) -> bool:
        return branch in self.merged

    def open_branch(self, branch: str) -> None:
        self.calls.append(f"branch {branch}")

    def commit(self, branch: str, paths: tuple[str, ...], message: str) -> None:
        self.calls.append(f"commit {branch} {len(paths)}")

    def open_draft_pr(self, branch: str, title: str, body: str) -> int:
        self.calls.append(f"draft {branch}")
        self.bodies[branch] = body
        self.prs[branch] = 100 + len(self.prs)
        return self.prs[branch]


def _plan(count: int = 1800) -> tuple[ri.Chunk, ...]:
    return ri.plan_intake(RID, _paths(count), change_id="CHG-SCPT-2026-999", card_id="intake")


def test_eighteen_hundred_files_are_cut_into_slices_that_each_fit_the_github_limit() -> None:
    chunks = _plan()

    assert len(chunks) > 2
    for chunk in chunks:
        body = ri.render_body(chunk, release_id=RID, change_id="CHG-SCPT-2026-999", card_id="intake", total=len(chunks))
        assert len(body) <= ri.DEFAULT_BUDGET + 200 and len(body) < ri.GITHUB_BODY_LIMIT
    payload = [p for c in chunks if c.kind == "payload" for p in c.paths]
    assert sorted(payload) == sorted(_paths(1800)) and len(payload) == len(set(payload)), "every file exactly once"


def test_the_pointer_slice_is_last_and_is_exactly_the_three_pointer_files() -> None:
    chunks = _plan(50)

    assert chunks[-1].kind == "pointers" and chunks[-1].paths == ri.POINTER_FILES
    assert all(c.kind == "payload" for c in chunks[:-1])


@pytest.mark.parametrize("bad", ["1.3.3", "1.3.3-ABCDEF0", "../1.3.3-abcdef0", "1.3.3-abcdef0/x"])
def test_a_malformed_release_id_is_refused(bad: str) -> None:
    with pytest.raises(ri.IntakeError, match="发布号"):
        ri.plan_intake(bad, _paths(3))


@pytest.mark.parametrize(
    "bad", [f"{ri.RELEASE_ROOT}/releases/1.3.3-1111111/x.py", f"{BASE}/../x.py", "/abs/x.py", f"{BASE}\\x.py", f"{ri.RELEASE_ROOT}/active_release.json"],
)
def test_a_payload_path_outside_the_release_folder_is_refused(bad: str) -> None:
    with pytest.raises(ri.IntakeError, match="之内"):
        ri.plan_intake(RID, [*_paths(2), bad])


def test_an_empty_payload_and_duplicates_are_refused() -> None:
    with pytest.raises(ri.IntakeError, match="没有载荷"):
        ri.plan_intake(RID, [])
    with pytest.raises(ri.IntakeError, match="重复"):
        ri.plan_intake(RID, [*_paths(2), *_paths(1)])


@pytest.mark.parametrize("budget", [100, 70000])
def test_an_unreasonable_budget_is_refused(budget: int) -> None:
    with pytest.raises(ri.IntakeError, match="预算"):
        ri.plan_intake(RID, _paths(3), budget=budget)


def test_payload_slices_open_first_and_the_pointer_slice_waits_for_every_merge() -> None:
    chunks, port = _plan(400), FakePort()

    steps = ri.open_intake(chunks, port, release_id=RID, change_id="CHG-SCPT-2026-999", card_id="intake")

    payload = [c for c in chunks if c.kind == "payload"]
    assert len([c for c in port.calls if c.startswith("draft")]) == len(payload)
    assert chunks[-1].branch not in port.prs and steps[-1].startswith("等待")
    port.merged.update(c.branch for c in payload[:-1])  # one still unmerged
    assert ri.open_intake(chunks, port, release_id=RID, change_id="CHG-SCPT-2026-999", card_id="intake")[-1].startswith("等待")
    assert chunks[-1].branch not in port.prs


def test_when_all_payload_slices_are_merged_the_pointer_slice_opens_as_a_draft() -> None:
    chunks, port = _plan(400), FakePort()
    ri.open_intake(chunks, port, release_id=RID, change_id="CHG-SCPT-2026-999", card_id="intake")
    port.merged.update(c.branch for c in chunks[:-1])

    steps = ri.open_intake(chunks, port, release_id=RID, change_id="CHG-SCPT-2026-999", card_id="intake")

    assert chunks[-1].branch in port.prs and steps[-1].startswith("开草稿")
    body = port.bodies[chunks[-1].branch]
    assert "领卡占位: intake" in body and "变更单: CHG-SCPT-2026-999" in body and "规则批准" in body and "只开草稿，不自动合并" in body


def test_a_second_run_opens_nothing_twice() -> None:
    chunks, port = _plan(400), FakePort()
    ri.open_intake(chunks, port, release_id=RID, change_id="C", card_id="k")
    done = list(port.calls)

    again = ri.open_intake(chunks, port, release_id=RID, change_id="C", card_id="k")

    assert port.calls == done and all(s.startswith(("已有", "等待")) for s in again)


def test_the_port_cannot_merge_anything() -> None:
    assert not any("merge" in name and name != "pr_merged" for name in dir(ri.IntakePort))


def test_slices_must_be_payload_then_exactly_one_pointer_slice() -> None:
    chunks = _plan(10)
    for bad in ((), chunks[:-1], (chunks[-1], chunks[0])):
        with pytest.raises(ri.IntakeError, match="分片"):
            ri.open_intake(tuple(bad), FakePort(), release_id=RID, change_id="C", card_id="k")
