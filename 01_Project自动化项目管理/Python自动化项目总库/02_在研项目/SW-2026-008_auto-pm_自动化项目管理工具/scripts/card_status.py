"""实施卡状态的公共算法（WBS 8.8 第一版）：只认 Git 里查得到的事实，不认任何手写的状态。

谁用：``scripts/plan_status.py``（项目计划表）现在用；交接契约的“状态单”以后也调这一份，不许各算各的。

一张卡的状态只由四样事实决定（都从 Git 远程读，云端和本机算出来一样）：

1. 占位：远程有没有 ``claims/<卡号>``，它最新一次提交写的是不是“有效且没过期”。
2. 分支：远程有没有名字是 ``<前缀>/<卡号>``、还没并进 main 的分支（PR 开着时分支在）。
3. 合并：main 上能不能找到“认这张卡”的提交。认法只有两种，随口提到卡号的提交不算：
   a. GitHub 默认的合并提交，标题是 ``Merge pull request #N from <谁>/<前缀>/<卡号>``（分支名就是卡号）；
   b. 提交说明里单独一行 ``领卡占位: <卡号>``（和 PR 正文那一行同一个写法；合并标题被改写时靠这一行）。
4. 证据：计划表给的证据文件在 main 上存在、不是空的、里面写着这个卡号。

判法（从上往下，先中先得）：

- 已合并，证据齐 → 已完成
- 已合并，证据不齐或没列证据 → 已合并未验证
- 占位有效，或有没并进 main 的分支 → 在干
- 其余 → 未开始
- 远程读不到（断网、没有远程）→ 没查到。绝不把“没查到”显示成“未开始”或“没完成”。

规矩：

- 本模块只读。唯一会动本机仓库的动作是 ``git fetch``（更新本机的远程跟踪引用，和 ``claim list`` 一样）；
  ``offline=True`` 时连这一步也不做，只用本机上次取回的数据，并在结果里写明。
- 不读占位里的交接记录文字（``note``），不读实施卡文件里手写的“状态”行，不读台账。
- 只用标准库和 ``git``，不依赖 ``auto_pm`` 包：脚本不进发布载荷，现役发布版本新旧都能跑。
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GIT_TIMEOUT = 120
CLAIM_HEADS = "refs/heads/claims/"
CLAIM_LOCAL = "refs/remotes/{remote}/claims/"

# 四级状态，加“没查到”。文字就是显示给人看的文字。
NOT_STARTED = "未开始"
IN_PROGRESS = "在干"
MERGED = "已合并未验证"
DONE = "已完成"
UNKNOWN = "没查到"
CARD_STATUSES = (NOT_STARTED, IN_PROGRESS, MERGED, DONE, UNKNOWN)

# 卡号里允许的字符同 auto_pm/application/core/claim_service.py 的 _CARD。
CARD_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

Runner = Callable[..., Any]


MARKER = re.compile(
    r"^\s*领卡占位\s*[:：]\s*`?([A-Za-z0-9][A-Za-z0-9._-]{0,62})`?\s*$", re.MULTILINE
)
MERGE_SUBJECT = re.compile(r"^Merge pull request #\d+ from \S+?/(\S+)$")


def commit_names_card(message: str, card: str) -> bool:
    """这个提交认不认这张卡：默认合并标题里的分支名以卡号结尾，或说明里有一行“领卡占位: <卡号>”。"""
    if any(found == card for found in MARKER.findall(message)):
        return True
    subject = message.split("\n", 1)[0].strip()
    match = MERGE_SUBJECT.match(subject)
    if match is None:
        return False
    branch = match.group(1)
    return branch == card or branch.endswith("/" + card)


def card_in(text: str, card: str) -> bool:
    """文字里有没有这个卡号。前后不能紧挨着字母、数字或连字符：``…-001`` 不会被 ``…-0012`` 或 ``X…-001`` 冒认。"""
    return (
        re.search(rf"(?<![A-Za-z0-9-]){re.escape(card)}(?![A-Za-z0-9]|-[A-Za-z0-9])", text)
        is not None
    )


@dataclass(frozen=True)
class ClaimFact:
    """``claims/<卡号>`` 最新一次提交里写的占位。"""

    commit: str
    status: str
    owner: str
    expires_at: str

    def live(self, now: datetime) -> bool:
        """有效且没过期。读不出租期的占位不算有效（和 ClaimService.free 同一口径）。"""
        if self.status != "active":
            return False
        try:
            return datetime.fromisoformat(self.expires_at) > now
        except (ValueError, TypeError):
            return False


@dataclass(frozen=True)
class CardFacts:
    """一张卡查到的事实。``known`` 为 False 表示远程没读到，别的栏都不可信。"""

    card: str
    known: bool
    claim: ClaimFact | None = None
    open_branches: tuple[str, ...] = ()
    merged_commits: tuple[str, ...] = ()
    evidence_ok: tuple[str, ...] = ()
    evidence_bad: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CardStatus:
    card: str
    status: str
    reasons: tuple[str, ...]
    facts: CardFacts

    def as_json(self) -> dict[str, Any]:
        claim = self.facts.claim
        return {
            "card": self.card,
            "status": self.status,
            "reasons": list(self.reasons),
            "claim": None
            if claim is None
            else {
                "commit": claim.commit,
                "status": claim.status,
                "owner": claim.owner,
                "expires_at": claim.expires_at,
            },
            "open_branches": list(self.facts.open_branches),
            "merged_commits": list(self.facts.merged_commits),
            "evidence_ok": list(self.facts.evidence_ok),
            "evidence_bad": [list(item) for item in self.facts.evidence_bad],
        }


def judge(facts: CardFacts, now: datetime | None = None) -> CardStatus:
    """按事实判一张卡的状态。纯函数，不碰 Git。"""
    moment = now or datetime.now(UTC)
    if not facts.known:
        return CardStatus(facts.card, UNKNOWN, ("远程没读到，没法判断",), facts)
    reasons: list[str] = []
    claim = facts.claim
    if claim is None:
        reasons.append("没有占位")
    elif claim.live(moment):
        reasons.append(f"占位有效（{claim.owner}，到 {claim.expires_at}）")
    elif claim.status != "active":
        reasons.append(f"占位已{'收回' if claim.status == 'reclaimed' else '释放'}")
    else:
        reasons.append("占位已过期")
    if facts.open_branches:
        reasons.append("有没并进 main 的分支：" + "、".join(facts.open_branches))
    if facts.merged_commits:
        reasons.append(
            "main 上有认这张卡的提交：" + "、".join(c[:9] for c in facts.merged_commits[:3])
        )
        if facts.evidence_ok and not facts.evidence_bad:
            reasons.append("证据齐：" + "、".join(facts.evidence_ok))
            return CardStatus(facts.card, DONE, tuple(reasons), facts)
        if facts.evidence_bad:
            reasons.extend(f"证据不算数：{path}（{why}）" for path, why in facts.evidence_bad)
        else:
            reasons.append("计划表没给这个任务列证据")
        return CardStatus(facts.card, MERGED, tuple(reasons), facts)
    if (claim is not None and claim.live(moment)) or facts.open_branches:
        return CardStatus(facts.card, IN_PROGRESS, tuple(reasons), facts)
    return CardStatus(facts.card, NOT_STARTED, tuple(reasons), facts)


@dataclass
class Snapshot:
    """一次取数的结果：按哪个提交、什么时候的数据算的。"""

    ok: bool
    offline: bool
    ref: str = ""
    commit: str = ""
    commit_time: str = ""
    taken_at: str = ""
    problem: str = ""
    branches: dict[str, str] = field(
        default_factory=dict
    )  # 分支名（不带远程名）→ 提交号；不含 claims/ 和 main
    claims: dict[str, ClaimFact] = field(default_factory=dict)

    def describe(self) -> str:
        if not self.ok:
            return f"远程没读到：{self.problem}"
        source = "本机上次取回的数据（没有联网取新）" if self.offline else "刚从远程取回的数据"
        return f"按 {self.ref} {self.commit[:9]}（{self.commit_time}）算，用的是{source}，取数时间 {self.taken_at}"


class GitFacts:
    """从一个 Git 仓库读实施卡的事实。所有 git 调用都走列表参数，不经过 shell。"""

    def __init__(
        self,
        repo: str | Path,
        *,
        remote: str = "origin",
        main: str = "main",
        runner: Runner = subprocess.run,
    ) -> None:
        self._repo = Path(repo)
        self._remote = remote
        self._main = main
        self._runner = runner
        self._ref = f"refs/remotes/{remote}/{main}"
        self.snapshot = Snapshot(ok=False, offline=False, problem="还没取数")

    # ── git ───────────────────────────────────────────────────────────

    def _git(self, *arguments: str) -> tuple[int, str]:
        try:
            done = self._runner(
                ["git", "-C", str(self._repo), "-c", "core.quotepath=off", *arguments],
                capture_output=True,
                timeout=GIT_TIMEOUT,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, f"{type(error).__name__}: {error}"
        out = (
            done.stdout if isinstance(done.stdout, str) else done.stdout.decode("utf-8", "replace")
        )
        err = (
            done.stderr if isinstance(done.stderr, str) else done.stderr.decode("utf-8", "replace")
        )
        return int(done.returncode), out if done.returncode == 0 else (err or out)

    # ── 取数 ──────────────────────────────────────────────────────────

    def refresh(self, *, offline: bool = False) -> Snapshot:
        """取一次数。联网时：取回 main 和全部占位，并列出远程分支；断网取不到就整体记“没读到”，不拿旧数据充数。"""
        taken = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        snapshot = Snapshot(
            ok=False, offline=offline, ref=f"{self._remote}/{self._main}", taken_at=taken
        )
        local_claims = CLAIM_LOCAL.format(remote=self._remote)
        if not offline:
            code, text = self._git(
                "fetch",
                "--prune",
                self._remote,
                f"+refs/heads/{self._main}:{self._ref}",
                f"+{CLAIM_HEADS}*:{local_claims}*",
            )
            if code != 0:
                snapshot.problem = (
                    f"git fetch 没成功（断网或没有远程 {self._remote}）：{text.strip()[:300]}"
                )
                self.snapshot = snapshot
                return snapshot
            code, text = self._git("ls-remote", "--heads", self._remote)
            if code != 0:
                snapshot.problem = f"git ls-remote 没成功：{text.strip()[:300]}"
                self.snapshot = snapshot
                return snapshot
            for line in text.splitlines():
                commit, _, ref = line.partition("\t")
                name = ref.removeprefix("refs/heads/")
                if name != self._main and not name.startswith("claims/"):
                    snapshot.branches[name] = commit.strip()
        else:
            code, text = self._git(
                "for-each-ref",
                "--format=%(objectname)%09%(refname)",
                f"refs/remotes/{self._remote}/",
            )
            if code != 0:
                snapshot.problem = f"读本机的远程跟踪引用没成功：{text.strip()[:300]}"
                self.snapshot = snapshot
                return snapshot
            prefix = f"refs/remotes/{self._remote}/"
            for line in text.splitlines():
                commit, _, ref = line.partition("\t")
                name = ref.removeprefix(prefix)
                if name not in (self._main, "HEAD") and not name.startswith("claims/"):
                    snapshot.branches[name] = commit.strip()
        code, text = self._git("log", "-1", "--format=%H%x09%cI", self._ref)
        if code != 0 or "\t" not in text:
            snapshot.problem = f"本机没有 {snapshot.ref}（没取回过 main）：{text.strip()[:300]}"
            self.snapshot = snapshot
            return snapshot
        snapshot.commit, _, when = text.strip().partition("\t")
        snapshot.commit_time = when
        code, text = self._git("for-each-ref", "--format=%(objectname)%09%(refname)", local_claims)
        if code != 0:
            snapshot.problem = f"读占位没成功：{text.strip()[:300]}"
            self.snapshot = snapshot
            return snapshot
        for line in text.splitlines():
            commit, _, ref = line.partition("\t")
            card = ref.removeprefix(local_claims)
            code, body = self._git("show", "-s", "--format=%B", commit)
            if code != 0:
                continue
            snapshot.claims[card] = _claim_of(commit, body)
        snapshot.ok = True
        self.snapshot = snapshot
        return snapshot

    # ── 单项事实 ──────────────────────────────────────────────────────

    def merged_commits(self, card: str) -> tuple[str, ...]:
        """main 上认这张卡的提交（见 commit_names_card），新的在前。"""
        code, text = self._git(
            "log", self._ref, "--fixed-strings", f"--grep={card}", "--format=%H%x1f%B%x1e"
        )
        if code != 0:
            return ()
        found: list[str] = []
        for record in text.split("\x1e"):
            commit, _, message = record.strip().partition("\x1f")
            if commit and commit_names_card(message, card):
                found.append(commit)
        return tuple(found)

    def open_branches(self, card: str) -> tuple[str, ...]:
        """名字是 ``<前缀>/<卡号>``（或就是卡号）、提交还没并进 main 的远程分支。"""
        names: list[str] = []
        for name, commit in sorted(self.snapshot.branches.items()):
            if name != card and not name.endswith("/" + card):
                continue
            code, _ = self._git("merge-base", "--is-ancestor", commit, self._ref)
            if code != 0:  # 没并进去；本机没有这个提交也算没并进去（只取了 main 和占位）
                names.append(name)
        return tuple(names)

    def file_text(self, path: str) -> str | None:
        """main 上这个文件的内容；不存在返回 None。"""
        code, text = self._git("show", f"{self._ref}:{path}")
        return text if code == 0 else None

    def path_exists(self, path: str) -> bool:
        code, _ = self._git("cat-file", "-e", f"{self._ref}:{path}")
        return code == 0

    def list_paths(self, prefix: str) -> tuple[str, ...]:
        """main 上某个目录下的全部文件路径（相对仓库根）。"""
        code, text = self._git("ls-tree", "-r", "--name-only", self._ref, "--", prefix)
        return tuple(line for line in text.splitlines() if line) if code == 0 else ()

    # ── 汇总 ──────────────────────────────────────────────────────────

    def card_facts(self, card: str, evidence: Sequence[str] = ()) -> CardFacts:
        """一张卡的全部事实。``evidence`` 是相对仓库根的路径。"""
        if not CARD_PATTERN.match(card):
            raise ValueError(f"卡号格式不对：{card!r}")
        if not self.snapshot.ok:
            return CardFacts(card, known=False)
        good: list[str] = []
        bad: list[tuple[str, str]] = []
        for path in evidence:
            text = self.file_text(path)
            if text is None:
                bad.append((path, "main 上没有这个文件"))
            elif not text.strip():
                bad.append((path, "文件是空的"))
            elif not card_in(text, card):
                bad.append((path, "文件里没写这张卡的卡号"))
            else:
                good.append(path)
        return CardFacts(
            card,
            known=True,
            claim=self.snapshot.claims.get(card),
            open_branches=self.open_branches(card),
            merged_commits=self.merged_commits(card),
            evidence_ok=tuple(good),
            evidence_bad=tuple(bad),
        )

    def card_status(
        self, card: str, evidence: Sequence[str] = (), now: datetime | None = None
    ) -> CardStatus:
        return judge(self.card_facts(card, evidence), now)


def _claim_of(commit: str, body: str) -> ClaimFact:
    """占位提交的说明：第一行 ``claim <卡号>``，后面是一段 JSON（同 ClaimService._parse；只读已知的几栏）。"""
    try:
        data = json.loads(body.split("\n", 1)[1]) if "\n" in body else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return ClaimFact(
        commit=commit,
        status=str(data.get("status", "active")),
        owner=str(data.get("owner", "?")),
        expires_at=str(data.get("expires_at", "")),
    )
