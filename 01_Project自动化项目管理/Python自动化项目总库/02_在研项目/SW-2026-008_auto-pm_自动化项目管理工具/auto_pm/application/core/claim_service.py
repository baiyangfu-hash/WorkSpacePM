"""auto_pm.application.core.claim_service - cross-machine card claims on GitHub (D-39, steps 1 and 2).

Several computers, cloud sessions and agents work on one repository, yet only GitHub is visible to all of them.  A *claim*
is the remote branch ``claims/<card>`` that points at an orphan commit (empty tree) whose message says who holds the card,
from which computer, which paths it will change and what for.

Creating the branch is atomic on the server (``--force-with-lease=<ref>:`` means "only if it does not exist"), so two
parties racing for one card number cannot both win; the loser is told who did.  Everything here needs only Git and
``origin`` -- no ledger -- so a cloud session in its own clone can use it.  Nothing is ever deleted unasked: ``release`` is an
explicit call by the holder.  Cloud proxies refuse branch deletion, so nothing here depends on it: ``release`` pushes a new
commit on top that marks the claim released, and every claim carries a lease (``expires_at``).  Released and expired
claims count as free -- they block nobody and their card can be taken over -- while deleting the branch stays a tidy-up for a
computer that is allowed to (a person decides; never automatic).
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.infrastructure.control_root_guard import authority_path_covered, clean_git_environment
from auto_pm.infrastructure.git_timeout import run_git_bounded

CLAIM_PREFIX = "claims/"
_CLAIM_REF = "refs/heads/claims/"
_LOCAL_REF = "refs/remotes/origin/claims/"
_CARD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_CARD_FILE = re.compile(r"/02_规划/(\d{3})_[^/]+_PM\.md$")
GIT_TIMEOUT_SECONDS = 120.0
LEASE_DAYS = 7
STALE_DAYS = LEASE_DAYS
AUTO_RETRIES = 8


class ClaimError(RuntimeError):
    """The claim cannot be made or read; the message says why and what to do next."""


@dataclass(frozen=True)
class Claim:
    card: str
    owner: str
    machine: str
    paths: tuple[str, ...]
    goal: str
    claimed_at: str
    commit: str
    status: str = "active"
    expires_at: str = ""

    @property
    def free(self) -> bool:
        """Released, or past its lease: blocks nobody and its card may be taken over."""

        if self.status != "active":
            return True
        try:
            return datetime.fromisoformat(self.expires_at) <= datetime.now(UTC)
        except ValueError:
            return True  # a claim with no readable lease cannot hold anything

    def age_days(self, now: datetime | None = None) -> int | None:
        try:
            then = datetime.fromisoformat(self.claimed_at)
        except ValueError:
            return None
        return max(0, ((now or datetime.now(UTC)) - then).days)

    @property
    def stale(self) -> bool:
        return (self.age_days() or 0) > STALE_DAYS

    def label(self) -> str:
        return f"卡 {self.card}（{self.owner}@{self.machine}：{self.goal or '无说明'}）"

    def as_json(self) -> dict[str, object]:
        return {
            "card": self.card,
            "owner": self.owner,
            "machine": self.machine,
            "paths": list(self.paths),
            "goal": self.goal,
            "claimed_at": self.claimed_at,
            "age_days": self.age_days(),
            "stale": self.stale,
            "commit": self.commit,
            "status": self.status,
            "expires_at": self.expires_at,
            "free": self.free,
        }


def claim_overlap(first: Sequence[str], second: Sequence[str]) -> tuple[str, ...]:
    """Paths of ``first`` that sit inside or contain a path of ``second`` (a directory claim covers its files)."""

    hit: list[str] = []
    for path in first:
        if any(authority_path_covered(path, (other,)) or authority_path_covered(other, (path,)) for other in second):
            hit.append(path)
    return tuple(hit)


REQUIRE_CLAIM_ENV = "AUTO_PM_REQUIRE_CLAIM"


def claim_required() -> bool:
    """Whether ``pr open`` insists on a claim.  Opt-in (``AUTO_PM_REQUIRE_CLAIM=1``) until the user flips the default."""

    return os.environ.get(REQUIRE_CLAIM_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def claim_refusal(repo_root: str | Path, card: str, owner: str) -> str:
    """Why ``owner`` may not open a PR for ``card`` (no active claim of theirs); "" when allowed or not required.

    Offline is "not verified", never a pretended pass or a hard stop on the network: the reason says so and refuses, because an
    unverified claim is exactly the collision this guards against.
    """

    if not claim_required():
        return ""
    try:
        claims = ClaimService(repo_root).all_claims()
    except ClaimError as error:
        return f"领卡占位未核实（{error}）；联网后再开 PR，或请用户决定"
    mine = next((claim for claim in claims if claim.card == card and not claim.free), None)
    if mine is None:
        return f"卡 {card} 没有有效的领卡占位；先 `main.py claim open {card} --paths … --goal …`（占位过期或已放下的也要重领）"
    if mine.owner != owner:
        return f"卡 {card} 的占位是 {mine.label()} 领的，不是 {owner}；不能替别人的卡开 PR"
    return ""


class ClaimService:
    def __init__(self, repo_root: str | Path, *, remote: str = "origin") -> None:
        self._root = Path(repo_root).resolve()
        self._remote = remote

    # ── read ──────────────────────────────────────────────────────────

    def all_claims(self, *, fetch: bool = True) -> list[Claim]:
        """Every claim on the remote; with ``fetch`` False, the ones this clone already knows."""

        if fetch:
            self._fetch()
        refs = self._git(["for-each-ref", "--format=%(refname)%09%(objectname)", _LOCAL_REF]).decode("utf-8", "replace")
        claims: list[Claim] = []
        for line in refs.splitlines():
            ref, _, commit = line.partition("\t")
            card = ref[len(_LOCAL_REF):]
            body = self._git(["show", "-s", "--format=%B", commit]).decode("utf-8", "replace")
            claims.append(self._parse(card, commit, body))
        return sorted(claims, key=lambda claim: claim.card)

    @staticmethod
    def _parse(card: str, commit: str, body: str) -> Claim:
        try:
            data = json.loads(body.split("\n", 1)[1]) if "\n" in body else {}
        except json.JSONDecodeError:
            data = {}
        return Claim(
            card=card,
            owner=str(data.get("owner", "?")),
            machine=str(data.get("machine", "?")),
            paths=tuple(str(item) for item in data.get("paths", ())),
            goal=str(data.get("goal", "")),
            claimed_at=str(data.get("claimed_at", "")),
            commit=commit,
            status=str(data.get("status", "active")),
            expires_at=str(data.get("expires_at", "")),
        )

    # ── claim ─────────────────────────────────────────────────────────

    def open(
        self, card: str, *, paths: Sequence[str], goal: str, owner: str, machine: str | None = None
    ) -> Claim:
        """Claim ``card`` (a name, or ``auto`` for the next free number); refuses when taken or when paths overlap a claim."""

        if not paths:
            raise ClaimError("领卡必须写明要改的路径（--paths），否则无法判断两边会不会改同一批文件")
        if card != "auto" and not _CARD.match(card):
            raise ClaimError(f"卡号 `{card}` 不能用：只允许字母、数字、点、横线、下划线")
        if not owner.strip():
            raise ClaimError("领卡必须写明是谁（--as）")
        existing = self.all_claims()
        for other in existing:
            if other.free:
                continue
            if card != "auto" and other.card == card:
                raise ClaimError(f"卡 {card} 已被领走：{other.label()}，{other.claimed_at}；换一个卡号或找他确认")
            clash = claim_overlap(paths, other.paths)
            if clash:
                raise ClaimError(
                    f"要改的路径和别人的占位重叠：{'、'.join(clash[:5])} ↔ {other.label()}。"
                    "两边不能同时改同一批文件；等对方放下，或请用户决定"
                )
        attempts = AUTO_RETRIES if card == "auto" else 1
        taken = {claim.card for claim in existing}
        for _ in range(attempts):
            name = self._next_number(taken) if card == "auto" else card
            claim = self._create(name, paths, goal, owner, machine or socket.gethostname(), previous=self._tip(existing, name))
            if claim is not None:
                return claim
            taken.add(name)
            if card != "auto":
                break
            existing = self.all_claims()
            taken |= {item.card for item in existing}
        raise ClaimError(f"卡 {card} 刚被别人领走（服务器拒绝了同名占位）；`claim list` 看是谁")

    @staticmethod
    def _tip(existing: Sequence[Claim], card: str) -> str:
        """The commit a free claim of the same name stands at (taken over on top of it); "" when the name is new."""

        return next((claim.commit for claim in existing if claim.card == card), "")

    def _commit(self, card: str, payload: dict[str, object], parent: str) -> str:
        tree = self._git(["mktree"], stdin=b"").decode().strip()
        message = f"claim {card}\n" + json.dumps(payload, ensure_ascii=False)
        arguments = ["-c", "user.name=claim", "-c", "user.email=claim@example.invalid", "commit-tree", tree, "-m", message]
        if parent:
            arguments += ["-p", parent]
        return self._git(arguments).decode().strip()

    def _create(
        self, card: str, paths: Sequence[str], goal: str, owner: str, machine: str, *, previous: str = ""
    ) -> Claim | None:
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "owner": owner,
            "machine": machine,
            "paths": list(paths),
            "goal": goal,
            "status": "active",
            "claimed_at": now.isoformat(timespec="seconds"),
            "expires_at": (now + timedelta(days=LEASE_DAYS)).isoformat(timespec="seconds"),
        }
        commit = self._commit(card, payload, previous)
        message = f"claim {card}\n" + json.dumps(payload, ensure_ascii=False)
        ref = f"{_CLAIM_REF}{card}"
        # Compare-and-swap: create only if absent (previous == ""), or take over only if the branch still stands at the free tip we saw.
        result = self._run(["push", f"--force-with-lease={ref}:{previous}", self._remote, f"{commit}:{ref}"])
        if result.returncode == 0:
            self._fetch()
            return self._parse(card, commit, message)
        text = result.stderr.decode("utf-8", "replace")
        if "stale info" in text or "rejected" in text or "already exists" in text:
            return None
        raise ClaimError(f"推占位分支失败，未领到卡：{text.strip() or '未知错误'}。离线时不能领卡（未核实就不当作领到）")

    def _next_number(self, taken: set[str]) -> str:
        numbers = [int(card) for card in taken if card.isdigit()]
        self._run(["fetch", self._remote, "main"])  # a stale origin/main would hand out a number main already uses
        listing = self._git(["ls-tree", "-r", "-z", "--name-only", f"refs/remotes/{self._remote}/main"], allow_failure=True)
        for line in (listing or b"").decode("utf-8", "replace").split("\0"):
            found = _CARD_FILE.search(line)
            if found:
                numbers.append(int(found.group(1)))
        return f"{max(numbers, default=0) + 1:03d}"

    # ── release ───────────────────────────────────────────────────────

    def release(self, card: str, *, owner: str) -> None:
        """Mark the holder's own claim released by pushing a commit on top of it (works where deleting a branch is refused)."""

        for claim in self.all_claims():
            if claim.card == card:
                if claim.owner != owner:
                    raise ClaimError(f"卡 {card} 是 {claim.owner} 领的，不是 {owner}；别人的占位只由用户决定放不放")
                if claim.free:
                    return  # already released or expired: nothing to do
                payload: dict[str, object] = {
                    "owner": claim.owner,
                    "machine": claim.machine,
                    "paths": list(claim.paths),
                    "goal": claim.goal,
                    "status": "released",
                    "claimed_at": claim.claimed_at,
                    "expires_at": claim.expires_at,
                    "released_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                commit = self._commit(card, payload, claim.commit)
                ref = f"{_CLAIM_REF}{card}"
                result = self._run(["push", f"--force-with-lease={ref}:{claim.commit}", self._remote, f"{commit}:{ref}"])
                if result.returncode != 0:
                    raise ClaimError("放下占位没推成功：" + result.stderr.decode("utf-8", "replace").strip())
                return
        raise ClaimError(f"没有叫 {card} 的占位")

    # ── git plumbing ──────────────────────────────────────────────────

    def _fetch(self) -> None:
        result = self._run(["fetch", "--prune", self._remote, f"+{_CLAIM_REF}*:{_LOCAL_REF}*"])
        if result.returncode != 0:
            raise ClaimError(f"无法读取远程占位（离线或没有 {self._remote}）：{result.stderr.decode('utf-8', 'replace').strip()}")

    def _run(self, arguments: list[str], *, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
        return run_git_bounded(
            ["git", "-C", str(self._root), *arguments],
            default_timeout=GIT_TIMEOUT_SECONDS,
            error_cls=ClaimError,
            where=self._root,
            capture_output=True,
            check=False,
            input=stdin,
            env=clean_git_environment(),
        )

    def _git(self, arguments: list[str], *, allow_failure: bool = False, stdin: bytes | None = None) -> bytes:
        result = self._run(arguments, stdin=stdin)
        if result.returncode != 0:
            if allow_failure:
                return b""
            raise ClaimError("git " + " ".join(arguments[:2]) + " 失败：" + result.stderr.decode("utf-8", "replace").strip())
        return result.stdout
