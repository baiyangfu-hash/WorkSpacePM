"""Admission of a new card into a project that already has open cards (TD-071 card 3, decisions 2 and 3).

- Soft limit: a project may hold ``OPEN_MISSION_SOFT_LIMIT`` open cards; the next one needs the user's word.
- Collision check: a new card whose paths overlap an open card's paths is stopped and the overlap listed;
  the user's word releases it, and the overlap is recorded so that picking either card back up reminds
  the agent to sync first.

Pure functions over already-read facts; nothing here reads or writes the store.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from auto_pm.contracts.mission import (
    OPEN_MISSION_SOFT_LIMIT,
    Mission,
    MissionState,
    user_evidence_problem,
)
from auto_pm.infrastructure.control_root_guard import authority_path_parts

ADMISSION_RELEASE_HINT = "（命令行加 --admission-release-ref 写明用户原话的位置）"
_CLOSED_STATES = frozenset({MissionState.ACCEPTED, MissionState.CLOSED, MissionState.CANCELLED})


@dataclass(frozen=True)
class ScopeOverlap:
    mission_id: str
    title: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class AdmissionVerdict:
    open_count: int
    limit: int
    overlaps: tuple[ScopeOverlap, ...]
    # The open cards this verdict was made over; creating the new card re-reads them inside its write transaction and
    # refuses when another card was opened in between, so two approvals cannot both pass a stale check (audit 77, 6).
    open_ids: tuple[str, ...] = ()

    @property
    def over_limit(self) -> bool:
        return self.open_count >= self.limit

    @property
    def needs_user_release(self) -> bool:
        return self.over_limit or bool(self.overlaps)

    def reason(self) -> str:
        parts: list[str] = []
        if self.over_limit:
            parts.append(
                f"项目开着的卡已有 {self.open_count} 张（上限 {self.limit} 张），再开一张要你一句话放行"
            )
        for overlap in self.overlaps:
            parts.append(
                f"和开着的卡“{overlap.title}”（{overlap.mission_id}）要改同一批文件："
                + "、".join(overlap.paths)
                + "，要你一句话放行"
            )
        return "；".join(parts)


def _overlapping(left: str, right: str, windows: bool | None) -> bool:
    a, b = authority_path_parts(left, windows=windows), authority_path_parts(right, windows=windows)
    shorter = min(len(a), len(b))
    return a[:shorter] == b[:shorter]


def scope_overlaps(
    new_paths: Iterable[str], other: Mission, *, windows: bool | None = None
) -> tuple[str, ...]:
    """The new card's paths that overlap ``other``'s authorized paths (a folder covers what is inside it).

    Paths are compared by whole parts with the host's casing rule (case-insensitive on Windows), as the Run guard does.
    """

    others = other.authority.scope_paths
    return tuple(
        sorted(
            {
                path
                for path in new_paths
                if any(_overlapping(path, mine, windows) for mine in others)
            }
        )
    )


def admission_verdict(
    open_missions: Iterable[Mission],
    new_scope_paths: Iterable[str],
    *,
    limit: int = OPEN_MISSION_SOFT_LIMIT,
) -> AdmissionVerdict:
    paths = tuple(new_scope_paths)
    live = [mission for mission in open_missions if mission.state not in _CLOSED_STATES]
    overlaps = []
    for mission in sorted(live, key=lambda item: item.mission_id):
        hit = scope_overlaps(paths, mission)
        if hit:
            overlaps.append(ScopeOverlap(mission.mission_id, mission.title, hit))
    return AdmissionVerdict(
        open_count=len(live),
        limit=limit,
        overlaps=tuple(overlaps),
        open_ids=tuple(sorted(mission.mission_id for mission in live)),
    )


def release_problem(verdict: AdmissionVerdict, admission_release_ref: str) -> str:
    """Why a new card cannot be admitted: no release where one is needed, or words that are not the user's own."""

    if not verdict.needs_user_release:
        return ""
    release = admission_release_ref.strip()
    if not release:
        return verdict.reason() + ADMISSION_RELEASE_HINT
    problem = user_evidence_problem(release)
    return f"{verdict.reason()}；放行凭据不合格：{problem}" if problem else ""
