"""auto_pm.application.core.claim_note_service - the hand-over record of one card, kept on its claim branch.

A card changes hands many times between drafting and closing (draft -> pre-check -> change order -> PR -> audit -> merge).  The
draft hash, the change-order number, the PR number, the verdict and "who does what next" used to live only in chat threads, so a
new conversation or another vendor's agent could not pick the card up.  A *note* is one more commit on ``claims/<card>``:

* its message carries the claim payload of the commit below it **unchanged** plus one extra key, ``note``.  Every reader of a claim
  (``ClaimService._parse`` and ``reviews/tools/pr_overlap_check.py``) reads only the tip commit and only the keys it knows, so the
  claim (holder, paths, lease, status) reads exactly as before;
* the hand-over record of a card is the first-parent history of its claim branch, filtered to the commits that carry ``note``.
  ``renew``/``release``/``add-paths`` rebuild the payload without ``note``, which is correct: they are not notes;
* a note holds references and the next step only, never a state.  States are computed from the ledger, GitHub and the files.
  Whatever is written here is never read to decide a state, so a wrong word in a note cannot change one.

Like claims, this needs only Git and ``origin`` -- no ledger -- so a cloud session can read and write it, and it pushes only to
the ``claims/`` branches such a session already writes.  Nothing is deleted or rewritten: a push lands only on top of the commit
that was read (``--force-with-lease``); the loser of a race reads again and retries.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from auto_pm.application.core.claim_service import (
    _CARD,
    _CLAIM_REF,
    _LOCAL_REF,
    AUTO_RETRIES,
    ClaimError,
    ClaimService,
    _decode,
)
from auto_pm.infrastructure.control_root_guard import authority_path_covered

# kind -> the Chinese name shown to people.  The order is the usual order of a card's life.
KINDS: dict[str, str] = {
    "draft": "起草",
    "precheck": "预核",
    "order": "建单",
    "compare": "比对",
    "ask-user": "请用户",
    "pr": "开PR",
    "deliver": "交卷",
    "audit": "审计",
    "merge": "合并",
    "park": "搁置",
    "takeover": "接手",
    "return": "退回",
    "void": "作废",
}
VERDICTS = ("pass", "fail", "fix")
VERIFICATIONS = ("lint", "test", "other", "none")
VERDICT_KINDS = frozenset({"precheck", "compare", "audit"})
MAX_NOTE_BYTES = 8 * 1024
MAX_TEXT_CHARS = 500
# Words that state a status.  Only free-text fields are checked (never paths or ids), and Latin words only as whole words.
_STATE_WORDS_CN = ("已批准", "已完成", "已验收", "已合并")
_STATE_WORDS_EN = re.compile(r"\b(?:approved|completed|accepted|merged)\b", re.IGNORECASE)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


class ClaimNoteRefusedError(ClaimError):
    """The note breaks a rule (exit code 1); nothing was pushed.  A plain ``ClaimError`` means Git or the network failed (2)."""


@dataclass(frozen=True)
class Note:
    """One hand-over entry as read back from the claim branch."""

    sequence: int
    commit: str
    card: str
    data: dict[str, object]

    @property
    def kind(self) -> str:
        return str(self.data.get("kind", ""))

    def text(self, key: str) -> str:
        return str(self.data.get(key, "") or "")

    def items(self, key: str) -> tuple[str, ...]:
        value = self.data.get(key, ())
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    def as_json(self) -> dict[str, object]:
        return {"sequence": self.sequence, "commit": self.commit, "card": self.card, **self.data}


class ClaimNoteService(ClaimService):
    """Append and read hand-over notes; the claim itself is left exactly as it was."""

    # ── read ──────────────────────────────────────────────────────────

    def log(self, card: str, *, fetch: bool = True) -> list[Note]:
        """Every note of ``card``, oldest first.  Raises ``ClaimNoteRefusedError`` when the card has no claim at all."""

        self._check_card(card)
        if fetch:
            self._fetch()
        tip = self._tip_commit(card)
        if not tip:
            raise ClaimNoteRefusedError(f"没有这张卡的占位：{card}（先 `claim number` 领号或 `claim open` 订卡，同一个号用到底）")
        return self._notes(card, tip)

    def _tip_commit(self, card: str) -> str:
        return _decode(self._git(["rev-parse", "--verify", "--quiet", f"{_LOCAL_REF}{card}"], allow_failure=True)).strip()

    def _notes(self, card: str, tip: str) -> list[Note]:
        raw = _decode(self._git(["log", "--first-parent", "--reverse", "--format=%H%x00%B%x01", tip]))
        notes: list[Note] = []
        for chunk in raw.split("\x01"):
            commit, _, body = chunk.strip("\n").partition("\x00")
            data = self._payload_of(body).get("note")
            if commit and isinstance(data, dict):
                notes.append(Note(sequence=len(notes) + 1, commit=commit, card=card, data=data))
        return notes

    @staticmethod
    def _payload_of(body: str) -> dict[str, object]:
        try:
            data = json.loads(body.split("\n", 1)[1]) if "\n" in body else {}
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}

    # ── write ─────────────────────────────────────────────────────────

    def add(
        self,
        card: str,
        *,
        kind: str,
        sender: str,
        to: str,
        next_step: str,
        git_head: str = "",
        refs: Sequence[str] = (),
        refs_outside: Sequence[str] = (),
        chg: str = "",
        pr: int | None = None,
        verdict: str = "",
        verify: str = "",
        changed: Sequence[str] = (),
        risk: str = "",
        caution: str = "",
        ask_user: str = "",
        read_first: Sequence[str] = (),
    ) -> Note:
        """Check the note (rules N1-N10 of the card), then push it on top of the claim.  Refusals push nothing."""

        self._check_card(card)
        note = self._shape(
            kind=kind, sender=sender, to=to, next_step=next_step, chg=chg, pr=pr, verdict=verdict, verify=verify,
            changed=changed, risk=risk, caution=caution, ask_user=ask_user, read_first=read_first, refs_outside=refs_outside,
        )
        self._fetch()  # offline -> ClaimError: a note that cannot reach origin is not recorded anywhere (no local queue)
        head = self._resolve_head(git_head, pr)
        note["git_head"] = head
        note["refs"] = [{"path": path, "sha256": self._blob_sha256(head, path, "--ref")} for path in self._clean_paths(refs)]
        for path in self._clean_paths(read_first):
            self._blob_sha256(head, path, "--read-first")
        if pr is not None and not self._pull_head(pr):
            raise ClaimNoteRefusedError(f"查不到 PR #{pr}（origin 上没有 refs/pull/{pr}/head）")
        for attempt in range(AUTO_RETRIES):
            tip = self._tip_commit(card)
            if not tip:
                raise ClaimNoteRefusedError(f"没有这张卡的占位：{card}（先 `claim number` 领号或 `claim open` 订卡，同一个号用到底）")
            payload = self._payload_of(_decode(self._git(["show", "-s", "--format=%B", tip])))
            existing = self._notes(card, tip)
            self._check_against_claim(card, payload, existing, note)
            payload["note"] = note
            if len(json.dumps(note, ensure_ascii=False).encode("utf-8")) > MAX_NOTE_BYTES:
                raise ClaimNoteRefusedError(f"这一笔超过 {MAX_NOTE_BYTES // 1024} KB：只记引用和下一步，长内容放进文件再用 --ref 引用")
            commit = self._commit(card, payload, tip)
            ref = f"{_CLAIM_REF}{card}"
            result = self._run(["push", f"--force-with-lease={ref}:{tip}", self._remote, f"{commit}:{ref}"])
            if result.returncode == 0:
                self._fetch()
                return Note(sequence=len(existing) + 1, commit=commit, card=card, data=note)
            self._fetch()  # someone else wrote first (a renewal or another note): read again and put this one on top
            if attempt == AUTO_RETRIES - 1:
                raise ClaimError("交接记录没推成功：" + _decode(result.stderr).strip())
        raise ClaimError("交接记录没推成功")  # pragma: no cover - the loop always returns or raises

    # ── rules ─────────────────────────────────────────────────────────

    @staticmethod
    def _check_card(card: str) -> None:
        if not _CARD.fullmatch(card):
            raise ClaimNoteRefusedError(f"卡号 {card!r} 不合法：字母数字开头，可含 . _ -")

    def _shape(
        self,
        *,
        kind: str,
        sender: str,
        to: str,
        next_step: str,
        chg: str,
        pr: int | None,
        verdict: str,
        verify: str,
        changed: Sequence[str],
        risk: str,
        caution: str,
        ask_user: str,
        read_first: Sequence[str],
        refs_outside: Sequence[str],
    ) -> dict[str, object]:
        if kind not in KINDS:
            raise ClaimNoteRefusedError(f"--kind {kind!r} 不在表里：" + "、".join(f"{key}（{name}）" for key, name in KINDS.items()))
        texts = {"--as": sender.strip(), "--to": to.strip(), "--next": next_step.strip()}
        for option, value in texts.items():
            if not value:
                raise ClaimNoteRefusedError(f"{option} 不能为空" + ("；真的没有下一步就写“无”，不要编" if option == "--next" else ""))
        if verdict and verdict not in VERDICTS:
            raise ClaimNoteRefusedError(f"--verdict 只能是 {'、'.join(VERDICTS)}")
        if verify and verify not in VERIFICATIONS:
            raise ClaimNoteRefusedError(f"--verify 只能是 {'、'.join(VERIFICATIONS)}")
        if kind in VERDICT_KINDS and not verdict:
            raise ClaimNoteRefusedError(f"{KINDS[kind]}这一笔要写结论：--verdict {'|'.join(VERDICTS)}")
        if kind == "deliver" and not verify:
            raise ClaimNoteRefusedError(f"交卷这一笔要写怎么验证的：--verify {'|'.join(VERIFICATIONS)}（没跑就写 none，不要不写）")
        clean_changed = self._clean_paths(changed)
        if kind == "deliver" and not clean_changed:
            raise ClaimNoteRefusedError("交卷这一笔要写改了哪些文件：--changed <路径>，可重复")
        if kind == "ask-user" and not ask_user.strip():
            raise ClaimNoteRefusedError("请用户这一笔要写清请用户说的那句完整的话：--ask-user")
        if pr is not None and pr <= 0:
            raise ClaimNoteRefusedError("--pr 要写正整数")
        if chg and not _CHG.fullmatch(chg.strip()):
            raise ClaimNoteRefusedError(f"--chg {chg!r} 不像变更单号")
        free_text = {"--to": to, "--next": next_step, "--risk": risk, "--caution": caution, "--ask-user": ask_user}
        for option, value in free_text.items():
            if len(value) > MAX_TEXT_CHARS:
                raise ClaimNoteRefusedError(f"{option} 超过 {MAX_TEXT_CHARS} 字：长内容放进文件再用 --ref 引用")
            word = self._state_word(value)
            if word:
                raise ClaimNoteRefusedError(f"{option} 里写了状态词“{word}”：交接记录只记引用和下一步，状态去状态单里看")
        outside: list[dict[str, str]] = []
        for item in refs_outside:
            path, _, digest = item.strip().rpartition("#")
            if not path or not _SHA256.fullmatch(digest.lower()):
                raise ClaimNoteRefusedError(f"--ref-outside {item!r} 要写成 路径#sha256（64 位十六进制）")
            outside.append({"path": path, "sha256": digest.lower(), "checked": "no"})
        note: dict[str, object] = {
            "kind": kind,
            "from": sender.strip(),
            "to": to.strip(),
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "next": next_step.strip(),
            "read_first": self._clean_paths(read_first),
        }
        optional: dict[str, object] = {
            "refs_outside": outside, "chg": chg.strip(), "pr": pr, "verdict": verdict, "verify": verify, "changed": clean_changed,
            "risk": risk.strip(), "caution": caution.strip(), "ask_user": ask_user.strip(),
        }
        note.update({key: value for key, value in optional.items() if value not in ("", None, [])})
        return note

    @staticmethod
    def _state_word(text: str) -> str:
        for word in _STATE_WORDS_CN:
            if word in text:
                return word
        match = _STATE_WORDS_EN.search(text)
        return match.group(0) if match else ""

    @staticmethod
    def _clean_paths(paths: Sequence[str]) -> list[str]:
        result: list[str] = []
        for raw in paths:
            text = raw.strip().replace("\\", "/").removeprefix("./")
            if not text or text.startswith("/") or ".." in text.split("/") or ":" in text:
                raise ClaimNoteRefusedError(f"路径 {raw!r} 要写成仓库根起的相对路径")
            if text not in result:
                result.append(text)
        return result

    def _resolve_head(self, git_head: str, pr: int | None) -> str:
        """The full commit id of ``git_head`` (default ``HEAD``); it must be a commit that ``origin`` has (N3)."""

        name = git_head.strip() or "HEAD"
        if name.startswith("-"):
            raise ClaimNoteRefusedError(f"--git-head {git_head!r} 不是提交号")
        head = _decode(self._git(["rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"], allow_failure=True)).strip()
        if not head:
            raise ClaimNoteRefusedError(f"--git-head {name} 在本机查不到这个提交")
        if self._on_remote_branch(head):
            return head
        self._run(["fetch", self._remote])  # the remote-tracking branches may be older than what was just pushed
        if self._on_remote_branch(head):
            return head
        # A merged PR's branch is deleted, so its commits hang only under refs/pull/<n>/head; ask origin for that one ref.
        pull_head = self._pull_head(pr) if pr is not None else ""
        if pull_head:
            self._run(["fetch", self._remote, f"refs/pull/{pr}/head"])
            if self._run(["merge-base", "--is-ancestor", head, pull_head]).returncode == 0:
                return head
        raise ClaimNoteRefusedError(
            f"提交 {head[:12]} 不在 origin 上（只在这台电脑里）：先推上去再记，别人才核得到；"
            "PR 分支合并后已删的，带上 --pr <号>"
        )

    def _on_remote_branch(self, head: str) -> bool:
        return bool(_decode(self._git(["branch", "-r", "--contains", head], allow_failure=True)).strip())

    def _pull_head(self, pr: int) -> str:
        result = self._run(["ls-remote", self._remote, f"refs/pull/{pr}/head"])
        if result.returncode != 0:
            raise ClaimError(f"查不了 PR #{pr}（离线或连不上 {self._remote}）：" + _decode(result.stderr).strip())
        return _decode(result.stdout).split("\t", 1)[0].strip()

    def _blob_sha256(self, head: str, path: str, option: str) -> str:
        """sha256 of ``path`` as it is in commit ``head`` -- never the working tree, so every computer gets the same answer (N4)."""

        result = self._run(["cat-file", "blob", f"{head}:{path}"])
        if result.returncode != 0:
            raise ClaimNoteRefusedError(f"{option} {path} 在提交 {head[:12]} 里不存在（按提交判断，和工作目录里有没有无关）")
        return hashlib.sha256(result.stdout).hexdigest()

    @staticmethod
    def _check_against_claim(card: str, payload: dict[str, object], existing: Sequence[Note], note: dict[str, object]) -> None:
        if existing and existing[-1].kind == "void" and note["kind"] != "takeover":
            raise ClaimNoteRefusedError(f"卡 {card} 上一笔是作废：之后只收“接手”（--kind takeover）")
        changed = note.get("changed")
        if isinstance(changed, list) and changed:
            held = payload.get("paths", [])
            roots = [str(item) for item in held] if isinstance(held, list) else []
            outside = [path for path in changed if not authority_path_covered(str(path), roots, windows=False)]
            if outside:
                raise ClaimNoteRefusedError(
                    f"交卷的文件不在卡 {card} 占位登记的路径里：{'、'.join(str(path) for path in outside[:8])}"
                    f"（先 `claim add-paths {card} --paths …` 补路径）"
                )
