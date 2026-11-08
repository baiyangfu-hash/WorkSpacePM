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
LEASE_HOURS = 4  # short on purpose: a holder that is still working renews (``claim renew``); one that went silent frees the card by itself
LEASE_SECONDS_ENV = "AUTO_PM_CLAIM_LEASE_SECONDS"  # a shorter lease for tests and live drills (e.g. 120 = two minutes); never longer than a day
MAX_LEASE_SECONDS = 4 * 3600  # not silently clamped: a longer value is refused
AUTO_RENEW_CAP = timedelta(hours=12)  # keep-alive never carries a claim past 12 h from the last explicit open/renew
AUTO_RENEW_FETCH_SECONDS = 10.0  # the keep-alive may not hold a checkpoint up
STALE_DAYS = 2
AUTO_RETRIES = 8


class ClaimError(RuntimeError):
    """The claim cannot be made or read; the message says why and what to do next."""


def lease_duration() -> timedelta:
    """How long a claim or a renewal holds: ``LEASE_HOURS``, or ``AUTO_PM_CLAIM_LEASE_SECONDS`` when that is set (1 second to four hours)."""

    raw = os.environ.get(LEASE_SECONDS_ENV, "").strip()
    if not raw:
        return timedelta(hours=LEASE_HOURS)
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 0
    if not 1 <= seconds <= MAX_LEASE_SECONDS:
        raise ClaimError(f"{LEASE_SECONDS_ENV}={raw!r} 不能用：写成 1～{MAX_LEASE_SECONDS} 之间的整数秒")
    return timedelta(seconds=seconds)


def holder_problem(claim: Claim, owner: str, machine: str | None = None) -> str:
    """Why ``owner`` on ``machine`` is not the holder of ``claim`` ("" when they are).

    The owner name is what tells two agents apart; the machine name tells two computers apart when both run an agent of the
    same name (D-73).  Old claims that carry no machine (``?``) compare by owner alone, and so do cloud sessions, whose
    machine names are not unique but whose owner aliases are.
    """

    here = machine if machine is not None else socket.gethostname()
    if claim.owner != owner:
        return f"卡 {claim.card} 是 {claim.owner}@{claim.machine} 领的，不是 {owner}@{here}"
    if claim.machine not in {"", "?"} and claim.machine != here:
        return f"卡 {claim.card} 是 {claim.owner} 在另一台机器 {claim.machine} 上领的，这里是 {here}"
    return ""


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
    renewed_at: str = ""  # the last *explicit* renewal; the keep-alive never writes it, so it cannot extend its own cap

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


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")  # lenient-decode: Git output only labels hints; one bad byte must not hide the other claims


def claim_overlap(first: Sequence[str], second: Sequence[str]) -> tuple[str, ...]:
    """Paths of ``first`` that sit inside or contain a path of ``second`` (a directory claim covers its files)."""

    hit: list[str] = []
    for path in first:
        if any(authority_path_covered(path, (other,)) or authority_path_covered(other, (path,)) for other in second):
            hit.append(path)
    return tuple(hit)


REQUIRE_CLAIM_ENV = "AUTO_PM_REQUIRE_CLAIM"


def claim_required() -> bool:
    """Whether ``pr open`` insists on a claim.  On by default (user, 2026-11-07); ``AUTO_PM_REQUIRE_CLAIM=0`` (or false/no/off) turns it off."""

    return os.environ.get(REQUIRE_CLAIM_ENV, "").strip().lower() not in {"0", "false", "no", "off"}


def claim_refusal(repo_root: str | Path, card: str, owner: str, machine: str | None = None) -> str:
    """Why ``owner`` may not open a PR for ``card`` (no active claim of theirs); "" when allowed or not required.

    Offline is "not verified", never a pretended pass or a hard stop on the network: the reason says so and refuses, because an
    unverified claim is exactly the collision this guards against.
    """

    if not claim_required():
        return ""
    try:
        claims = ClaimService(repo_root, machine=machine).all_claims()
    except ClaimError as error:
        return f"领卡占位未核实（{error}）；联网后再开 PR，或请用户决定"
    mine = next((claim for claim in claims if claim.card == card and not claim.free), None)
    if mine is None:
        return f"卡 {card} 没有有效的领卡占位；先 `main.py claim open {card} --paths … --goal …`（占位过期或已放下的也要重领）"
    problem = holder_problem(mine, owner, machine)
    if problem:
        return f"{problem}；不能替别人的卡开 PR"
    return ""


class ClaimService:
    def __init__(self, repo_root: str | Path, *, remote: str = "origin", machine: str | None = None) -> None:
        self._root = Path(repo_root).resolve()
        self._remote = remote
        self.keepalive_warnings: list[str] = []
        self._machine = machine or socket.gethostname()  # who "I" am as a computer: opens write it, release/renew compare it (D-73)

    # ── read ──────────────────────────────────────────────────────────

    def all_claims(self, *, fetch: bool = True) -> list[Claim]:
        """Every claim on the remote; with ``fetch`` False, the ones this clone already knows."""

        if fetch:
            self._fetch()
        refs = _decode(self._git(["for-each-ref", "--format=%(refname)%09%(objectname)", _LOCAL_REF]))
        claims: list[Claim] = []
        for line in refs.splitlines():
            ref, _, commit = line.partition("\t")
            card = ref[len(_LOCAL_REF):]
            body = _decode(self._git(["show", "-s", "--format=%B", commit]))
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
            renewed_at=str(data.get("renewed_at", "")),
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
            claim = self._create(name, paths, goal, owner, machine or self._machine, previous=self._tip(existing, name))
            if claim is not None:
                return claim
            taken.add(name)
            if card != "auto":
                break
            existing = self.all_claims()
            taken |= {item.card for item in existing}
        raise ClaimError(self._lost_race_message(card))

    def _lost_race_message(self, card: str) -> str:
        """The refusal for a lost same-name race: names the winner when the claim list can be read again, else says to look."""

        try:
            winner = next((claim for claim in self.all_claims() if claim.card == card and not claim.free), None)
        except ClaimError:
            winner = None
        if winner is None:
            return f"卡 {card} 刚被别人领走（服务器拒绝了同名占位）；`claim list` 看是谁"
        return f"卡 {card} 刚被别人领走：{winner.label()}，{winner.claimed_at}；换一个卡号或找他确认"

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
            "expires_at": (now + lease_duration()).isoformat(timespec="seconds"),
        }
        commit = self._commit(card, payload, previous)
        message = f"claim {card}\n" + json.dumps(payload, ensure_ascii=False)
        ref = f"{_CLAIM_REF}{card}"
        # Compare-and-swap: create only if absent (previous == ""), or take over only if the branch still stands at the free tip we saw.
        result = self._run(["push", f"--force-with-lease={ref}:{previous}", self._remote, f"{commit}:{ref}"])
        if result.returncode == 0:
            self._fetch()
            return self._parse(card, commit, message)
        text = _decode(result.stderr)
        if "stale info" in text or "rejected" in text or "already exists" in text:
            return None
        raise ClaimError(f"推占位分支失败，未领到卡：{text.strip() or '未知错误'}。离线时不能领卡（未核实就不当作领到）")

    def _next_number(self, taken: set[str]) -> str:
        numbers = [int(card) for card in taken if card.isdigit()]
        self._run(["fetch", self._remote, "main"])  # a stale origin/main would hand out a number main already uses
        listing = self._git(["ls-tree", "-r", "-z", "--name-only", f"refs/remotes/{self._remote}/main"], allow_failure=True)
        for line in _decode(listing or b"").split("\0"):
            found = _CARD_FILE.search(line)
            if found:
                numbers.append(int(found.group(1)))
        return f"{max(numbers, default=0) + 1:03d}"

    # ── release ───────────────────────────────────────────────────────

    def release(self, card: str, *, owner: str) -> None:
        """Mark the holder's own claim released by pushing a commit on top of it (works where deleting a branch is refused)."""

        for claim in self.all_claims():
            if claim.card == card:
                problem = holder_problem(claim, owner, self._machine)
                if problem:
                    raise ClaimError(f"{problem}；别人的占位只由用户决定放不放")
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
                    raise ClaimError("放下占位没推成功：" + _decode(result.stderr).strip())
                return
        raise ClaimError(f"没有叫 {card} 的占位")

    # ── renew / reclaim ───────────────────────────────────────────────

    def renew(self, card: str, *, owner: str) -> Claim:
        """The holder says "still working": push a commit that moves ``expires_at`` to now + ``LEASE_HOURS`` (never shortens it)."""

        claim = self._find(card)
        problem = holder_problem(claim, owner, self._machine)
        if problem:
            raise ClaimError(f"{problem}；只有持有者能续租")
        if claim.free:
            raise ClaimError(f"卡 {card} 的占位已放下、被收回或已到期，不能续租；重新 `claim open {card} --paths … --goal …`")
        now = datetime.now(UTC)
        payload = self._payload(claim, "active")
        payload["expires_at"] = max(claim.expires_at, (now + lease_duration()).isoformat(timespec="seconds"))
        payload["renewed_at"] = now.isoformat(timespec="seconds")
        return self._push_on_top(claim, payload, "续租没推成功")

    def renew_held(self, owner: str, *, paths: Sequence[str]) -> list[Claim]:
        """Keep alive the live claims ``owner`` holds **that cover ``paths``** (the checkpointing Run's owned paths), as a side effect
        of work the agent does anyway (D-39 follow-up).

        Scoped on purpose: a checkpoint proves its own Run is alive, not every card the same owner name holds, so an
        empty ``paths`` renews nothing.  Capped: never past 12 h after the last explicit open or ``claim renew``
        (``renewed_at``); after that only an explicit renew keeps the claim.  Bounded: the fetch and the push give up
        after ``AUTO_RENEW_FETCH_SECONDS``.  A claim is only pushed again once less than half of the lease is left.
        Failures are recorded in ``keepalive_warnings`` and never raised -- this must not stop the command it rides on.
        Returns the claims that were actually renewed.
        """

        self.keepalive_warnings = []
        renewed: list[Claim] = []
        if not paths:
            return renewed
        failure: Exception | None = None
        try:
            self._fetch(timeout=AUTO_RENEW_FETCH_SECONDS)
        except Exception as error:  # noqa: BLE001 - keep-alive must never stop the command it rides on
            failure = error
        try:
            now = datetime.now(UTC)
            lease = lease_duration()
            mine = [
                claim
                for claim in self.all_claims(fetch=False)
                if not claim.free and not holder_problem(claim, owner, self._machine) and claim_overlap(claim.paths, paths)
            ]
        except Exception as error:  # noqa: BLE001 - same reason
            if failure is None:  # the fetch worked but the claims could not be read; with the fetch also down there is nothing known to warn about
                self.keepalive_warnings.append(f"领卡续租没做（{error}）；占位到期前请手动 `claim renew`")
            return renewed
        if failure is not None:
            # Say so only when there is something this checkpoint would have kept alive: a clone with no origin or no claims stays quiet.
            if mine:
                self.keepalive_warnings.append(f"领卡续租没做（读不到远程占位：{failure}）；占位到期前请手动 `claim renew`")
            return renewed
        for claim in mine:
            try:
                anchor = max(filter(None, (claim.claimed_at, claim.renewed_at)))
                ceiling = datetime.fromisoformat(anchor) + AUTO_RENEW_CAP
                if now >= ceiling:
                    self.keepalive_warnings.append(f"{claim.label()} 已满 12 小时自动续租上限，需要显式 `claim renew {claim.card}`")
                    continue
                if datetime.fromisoformat(claim.expires_at) > now + lease / 2:
                    continue
                payload = self._payload(claim, "active")
                payload["expires_at"] = max(claim.expires_at, min(now + lease, ceiling).isoformat(timespec="seconds"))
                payload["auto_renewed_at"] = now.isoformat(timespec="seconds")
                renewed.append(self._push_on_top(claim, payload, "自动续租没推成功", timeout=AUTO_RENEW_FETCH_SECONDS))
            except Exception as error:  # noqa: BLE001 - same reason; the explicit `claim renew` still reports errors
                self.keepalive_warnings.append(f"{claim.label()} 自动续租没成功（{error}）；请手动 `claim renew {claim.card}`")
        return renewed

    def reclaim(self, card: str, *, by: str, reason: str, approval_ref: str) -> Claim:
        """Take a card back from a holder that went silent (D-39).  Only on the user's word: ``approval_ref`` must be ``user-confirmation:<where>``.

        Nothing is deleted: a commit marked ``reclaimed`` (who, why, when, on whose word) goes on top, so the history stays and the card is free.
        """

        if not reason.strip():
            raise ClaimError("收回占位必须写明原因（--reason）")
        prefix = "user-confirmation:"
        if not approval_ref.startswith(prefix) or len(approval_ref[len(prefix):].strip()) < 6:
            raise ClaimError("收回别人的占位只听用户的：--approval-evidence-ref 写成 user-confirmation:<用户那条消息的时间或编号>")
        claim = self._find(card)
        if claim.free:
            return claim  # already released, reclaimed or expired: nothing to do
        payload = self._payload(claim, "reclaimed")
        payload.update(
            {
                "reclaimed_by": by,
                "reclaimed_reason": reason.strip(),
                "reclaimed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "reclaimed_on": approval_ref,
            }
        )
        return self._push_on_top(claim, payload, "收回占位没推成功")

    def _find(self, card: str) -> Claim:
        for claim in self.all_claims():
            if claim.card == card:
                return claim
        raise ClaimError(f"没有叫 {card} 的占位")

    @staticmethod
    def _payload(claim: Claim, status: str) -> dict[str, object]:
        return {
            "owner": claim.owner,
            "machine": claim.machine,
            "paths": list(claim.paths),
            "goal": claim.goal,
            "status": status,
            "claimed_at": claim.claimed_at,
            "expires_at": claim.expires_at,
            **({"renewed_at": claim.renewed_at} if claim.renewed_at else {}),
        }

    def _push_on_top(self, claim: Claim, payload: dict[str, object], failure: str, *, timeout: float | None = None) -> Claim:
        commit = self._commit(claim.card, payload, claim.commit)
        ref = f"{_CLAIM_REF}{claim.card}"
        result = self._run(["push", f"--force-with-lease={ref}:{claim.commit}", self._remote, f"{commit}:{ref}"], timeout=timeout)
        if result.returncode != 0:
            raise ClaimError(f"{failure}：" + _decode(result.stderr).strip())
        self._fetch(timeout=timeout)
        return self._parse(claim.card, commit, f"claim {claim.card}\n" + json.dumps(payload, ensure_ascii=False))

    # ── git plumbing ──────────────────────────────────────────────────

    def _fetch(self, *, timeout: float | None = None) -> None:
        result = self._run(["fetch", "--prune", self._remote, f"+{_CLAIM_REF}*:{_LOCAL_REF}*"], timeout=timeout)
        if result.returncode != 0:
            raise ClaimError(f"无法读取远程占位（离线或没有 {self._remote}）：{_decode(result.stderr).strip()}")

    def _run(self, arguments: list[str], *, stdin: bytes | None = None, timeout: float | None = None) -> subprocess.CompletedProcess[bytes]:
        return run_git_bounded(
            ["git", "-C", str(self._root), *arguments],
            default_timeout=timeout or GIT_TIMEOUT_SECONDS,
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
            raise ClaimError("git " + " ".join(arguments[:2]) + " 失败：" + _decode(result.stderr).strip())
        return result.stdout
