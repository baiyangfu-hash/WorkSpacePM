"""Putting a deployed release into the repository as draft pull requests (D-146 card 5).

A deployed release lives in the control root's ``releases/<id>`` folder, two pointers and a manifest.  To get it into ``main`` it has to
travel as pull requests, and two things went wrong when this was done by hand:

* a release is ~1800 files and the pull-request description lists every one, so a single description (185k characters) was over GitHub's
  65536 limit and could not be opened.  The payload is therefore cut into slices whose rendered description stays under a budget;
* ``main`` must never point at a release folder that is not in ``main`` yet.  So the payload slices go first and the **pointer slice**
  (active, previous, manifest) is only opened after every payload slice is merged.

Everything with a side effect goes through :class:`IntakePort`.  The port has no merge method on purpose: this module only opens *draft*
pull requests and never merges anything.  Re-running is safe: a slice whose pull request already exists is left alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

RELEASE_ROOT = "00_Infrastructure/auto_pm"
POINTER_FILES = (
    f"{RELEASE_ROOT}/active_release.json",
    f"{RELEASE_ROOT}/previous_release.json",
    f"{RELEASE_ROOT}/deployment_manifest.json",
)
GITHUB_BODY_LIMIT = 65536
DEFAULT_BUDGET = 60000
_RELEASE_ID = re.compile(r"^\d+\.\d+\.\d+-[0-9a-f]{7}$")


class IntakeError(RuntimeError):
    """The slicing or the sequence cannot proceed; the message says why."""


@dataclass(frozen=True)
class Chunk:
    index: int
    kind: str  # "payload" or "pointers"
    paths: tuple[str, ...]
    branch: str
    title: str


class IntakePort(Protocol):
    def existing_pr(self, branch: str) -> int | None: ...
    def pr_merged(self, branch: str) -> bool: ...
    def open_branch(self, branch: str) -> None: ...
    def commit(self, branch: str, paths: tuple[str, ...], message: str) -> None: ...
    def open_draft_pr(self, branch: str, title: str, body: str) -> int: ...


def _check_release_id(release_id: str) -> None:
    if not _RELEASE_ID.match(release_id):
        raise IntakeError(f"发布号格式不对：{release_id!r}")


def _check_payload(release_id: str, paths: list[str]) -> None:
    prefix = f"{RELEASE_ROOT}/releases/{release_id}/"
    if not paths:
        raise IntakeError(f"发布 {release_id} 没有载荷文件，不能入库")
    for path in paths:
        parts = PurePosixPath(path).parts
        if not path.startswith(prefix) or ".." in parts or path.startswith("/") or "\\" in path:
            raise IntakeError(f"载荷路径不在 releases/{release_id}/ 之内：{path}")
    if len(set(paths)) != len(paths):
        raise IntakeError("载荷路径有重复")


def _row(release_id: str, path: str, kind: str) -> str:
    use = f"发布 {release_id} 的载荷文件" if kind == "payload" else "发布指针/清单（需要用户规则批准）"
    return f"| `{path}` | 计划新增 | {use} |\n"


def render_body(chunk: Chunk, *, release_id: str, change_id: str, card_id: str, total: int) -> str:
    """The pull-request description of one slice: claim line, change order, and the table of files it may change."""

    head = (
        f"领卡占位: {card_id}\n变更单: {change_id}\n\n"
        f"发布 {release_id} 入库，第 {chunk.index + 1}/{total} 片（{'指针与清单，须等前面各片合并后才开' if chunk.kind == 'pointers' else '载荷文件'}）。\n"
        "只开草稿，不自动合并。\n\n## 可改范围\n\n| 路径 | 基线状态 | 用途 |\n|---|---|---|\n"
    )
    return head + "".join(_row(release_id, path, chunk.kind) for path in chunk.paths)


def plan_intake(
    release_id: str, payload_paths: list[str], *, branch_prefix: str = "claude/release-intake", change_id: str = "CHG-X", card_id: str = "card", budget: int = DEFAULT_BUDGET,
) -> tuple[Chunk, ...]:
    """Cut the payload into slices whose rendered description fits ``budget`` characters; the pointer slice is last."""

    _check_release_id(release_id)
    if not 5000 <= budget <= GITHUB_BODY_LIMIT:
        raise IntakeError(f"预算 {budget} 不合理（5000 到 {GITHUB_BODY_LIMIT}）")
    _check_payload(release_id, payload_paths)
    ordered = sorted(payload_paths)
    slices: list[list[str]] = [[]]
    used = len(render_body(Chunk(0, "payload", (), "b", "t"), release_id=release_id, change_id=change_id, card_id=card_id, total=99))
    for path in ordered:
        cost = len(_row(release_id, path, "payload"))
        if cost > budget - used and slices[-1]:
            slices.append([])
            used = len(render_body(Chunk(0, "payload", (), "b", "t"), release_id=release_id, change_id=change_id, card_id=card_id, total=99))
        slices[-1].append(path)
        used += cost
    chunks = [
        Chunk(i, "payload", tuple(paths), f"{branch_prefix}-{release_id}-{i + 1}", f"chore(release): 入库发布 {release_id}（载荷 {i + 1}/{len(slices) + 1}）")
        for i, paths in enumerate(slices)
    ]
    chunks.append(Chunk(len(slices), "pointers", POINTER_FILES, f"{branch_prefix}-{release_id}-pointers", f"chore(release): 入库发布 {release_id}（指针与清单 {len(slices) + 1}/{len(slices) + 1}）"))
    for chunk in chunks:
        body = render_body(chunk, release_id=release_id, change_id=change_id, card_id=card_id, total=len(chunks))
        if len(body) > GITHUB_BODY_LIMIT:
            raise IntakeError(f"第 {chunk.index + 1} 片的描述 {len(body)} 字符，超过 GitHub 上限")
    return tuple(chunks)


def open_intake(chunks: tuple[Chunk, ...], port: IntakePort, *, release_id: str, change_id: str, card_id: str) -> list[str]:
    """Open the draft pull requests in order; stops (without error) at the pointer slice until every payload slice is merged."""

    if not chunks or chunks[-1].kind != "pointers" or any(c.kind != "payload" for c in chunks[:-1]):
        raise IntakeError("分片必须是若干载荷片加最后一个指针片")
    steps: list[str] = []
    for chunk in chunks:
        if chunk.kind == "pointers":
            waiting = [c.branch for c in chunks[:-1] if not port.pr_merged(c.branch)]
            if waiting:
                steps.append(f"等待：{len(waiting)} 个载荷片还没合并，指针片不开（{waiting[0]} 等）")
                return steps
        existing = port.existing_pr(chunk.branch)
        if existing is not None:
            steps.append(f"已有 PR #{existing}：{chunk.branch}")
            continue
        port.open_branch(chunk.branch)
        port.commit(chunk.branch, chunk.paths, chunk.title)
        body = render_body(chunk, release_id=release_id, change_id=change_id, card_id=card_id, total=len(chunks))
        number = port.open_draft_pr(chunk.branch, chunk.title, body)
        steps.append(f"开草稿 PR #{number}：{chunk.branch}")
    return steps
