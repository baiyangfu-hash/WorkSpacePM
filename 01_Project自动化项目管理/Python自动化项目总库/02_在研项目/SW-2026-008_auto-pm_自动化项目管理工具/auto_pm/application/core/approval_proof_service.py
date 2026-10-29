"""The user's approval PIN: evidence of a human approval that an agent cannot produce (gap 9).

Before this, every command-line approval only checked the *format* of its evidence (``user-confirmation:`` plus 8
characters) and that the approver name had no "agent"/"model" in it; an agent typing the user's name and an invented
reference was accepted.  A terminal check (``pm sign-risk``) does not close that either: an agent can open a pseudo
terminal and clear its own environment markers.  What an agent does not have is a secret only the user knows.

- The user sets an approval PIN once (``pm approver-pin init``, in their own terminal).  Only a salted scrypt verifier is
  written, to ``SYS-2026-001_WorkspaceGovernance/approvers.json``.
- The verifier counts only once it is **committed**: it is always read from Git ``HEAD`` of the control root, never from
  the working tree.  An agent that edits or replaces the file changes nothing until a commit, and that commit is a visible
  change of the approver key (audit item).
- With a committed verifier, a scope approval and a final acceptance need the PIN, on every entrance (``pm approve``,
  ``pm accept``, the cockpit buttons, the thin SDK).  The approver name and the evidence reference then come from the
  verified key, not from the caller.  A wrong PIN writes nothing; five wrong PINs in a row lock approvals for 15 minutes.
- Without a committed verifier the old format check still applies (rollout: the user's first commit switches it on),
  but only when that is provably so; anything unreadable refuses (see ``committed_state``).

The PIN is read from an interactive terminal only (hidden input).  It is never an option, an environment variable or a
file, so an agent has no channel to pass one it was told; it must never ask the user for it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.infrastructure.git_timeout import run_git_bounded

REGISTRY_RELATIVE_PATH = "SYS-2026-001_WorkspaceGovernance/approvers.json"
SCHEMA_VERSION = "approvers.v1"
MIN_PIN_LENGTH = 10
MAX_FAILURES = 5
LOCKOUT = timedelta(minutes=15)
# scrypt cost for a new verifier: about 64 MiB and a fraction of a second, so a guessed PIN costs the same for anyone.
SCRYPT_N = 2**16
SCRYPT_R = 8
SCRYPT_P = 1
_MIN_SCRYPT_N = 2**10
_FAILURES_RELATIVE_PATH = ".auto-pm/cache/approval-pin-failures.json"  # ignored by Git, like every runtime cache


class ApprovalProofError(RuntimeError):
    """The approval carries no valid user PIN; nothing was written."""


@dataclass(frozen=True)
class ApproverKey:
    approver: str
    salt: str
    verifier: str
    n: int
    r: int
    p: int
    created_at: str

    @property
    def key_id(self) -> str:
        return hashlib.sha256(f"{self.salt}:{self.verifier}".encode()).hexdigest()[:12]

    def to_json(self) -> dict[str, object]:
        return {
            "approver": self.approver,
            "key_id": self.key_id,
            "salt": self.salt,
            "verifier": self.verifier,
            "n": self.n,
            "r": self.r,
            "p": self.p,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ApprovalProof:
    """What a verified PIN yields: the approver it belongs to and a reference that names the key and the subject."""

    approver: str
    key_id: str
    evidence_ref: str


def pin_problem(pin: str) -> str:
    """Why a new PIN is too weak ('' when it is acceptable)."""

    if len(pin) < MIN_PIN_LENGTH:
        return f"批准口令至少 {MIN_PIN_LENGTH} 位"
    if pin.isdigit():
        return "批准口令不能全是数字（加几个字母）"
    if pin != pin.strip():
        return "批准口令首尾不能有空格"
    return ""


def _derive(pin: str, salt: str, n: int, r: int, p: int) -> str:
    return hashlib.scrypt(
        pin.encode("utf-8"), salt=bytes.fromhex(salt), n=n, r=r, p=p, dklen=32, maxmem=256 * n * r + 2**24
    ).hex()


def make_key(approver: str, pin: str, *, n: int = SCRYPT_N, now: datetime | None = None) -> ApproverKey:
    """A new verifier for ``approver``; the PIN itself is not kept."""

    approver = approver.strip()
    if not approver:
        raise ApprovalProofError("批准人名字不能为空")
    problem = pin_problem(pin)
    if problem:
        raise ApprovalProofError(problem)
    salt = secrets.token_hex(16)
    return ApproverKey(
        approver=approver,
        salt=salt,
        verifier=_derive(pin, salt, n, SCRYPT_R, SCRYPT_P),
        n=n,
        r=SCRYPT_R,
        p=SCRYPT_P,
        created_at=(now or datetime.now(UTC)).isoformat(),
    )


def registry_text(keys: list[ApproverKey]) -> str:
    payload = {"schema_version": SCHEMA_VERSION, "approvers": [key.to_json() for key in keys]}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def parse_registry(text: str) -> list[ApproverKey]:
    try:
        payload = json.loads(text)
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("schema_version")
        keys = []
        for item in payload["approvers"]:
            key = ApproverKey(
                approver=str(item["approver"]).strip(),
                salt=str(item["salt"]),
                verifier=str(item["verifier"]),
                n=int(item["n"]),
                r=int(item["r"]),
                p=int(item["p"]),
                created_at=str(item.get("created_at", "")),
            )
            bytes.fromhex(key.salt)
            bytes.fromhex(key.verifier)
            if not key.approver or key.n < _MIN_SCRYPT_N or key.n & (key.n - 1) or key.r < 1 or key.p < 1:
                raise ValueError("key")
            keys.append(key)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise ApprovalProofError(f"批准人登记文件 {REGISTRY_RELATIVE_PATH} 格式无效，所有批准一律拒绝") from error
    if not keys:
        raise ApprovalProofError(f"批准人登记文件 {REGISTRY_RELATIVE_PATH} 里没有批准人，所有批准一律拒绝")
    return keys


class ApprovalProofService:
    """Reads the committed approver verifiers of one control root and turns a typed PIN into approval evidence."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._root = Path(workspace_root).resolve()

    @property
    def registry_path(self) -> Path:
        return self._root / REGISTRY_RELATIVE_PATH

    def committed_keys(self) -> list[ApproverKey] | None:
        """The verifiers in Git HEAD, or None only when the PIN was provably never set up (the old format check).

        Fails closed (audit 72, high-1): anything that keeps the committed file from being read - an inherited
        ``GIT_DIR``, no ``git`` on PATH, a HEAD that points nowhere, a repository that is not this root - refuses every
        approval instead of falling back.  So does a registry that exists in the working tree but not in HEAD, or one
        that ever existed in the history but is gone from HEAD: once switched on, the PIN cannot be switched off by
        moving HEAD or deleting the file.
        """

        keys, problem = self.committed_state()
        if problem:
            raise ApprovalProofError(problem)
        return keys

    def committed_state(self) -> tuple[list[ApproverKey] | None, str]:
        """(keys or None, '') when the state is clear; (None, reason) when approvals must be refused."""

        enclosing = next((parent for parent in self._root.parents if (parent / ".git").exists()), None)
        if enclosing is not None:
            # A folder below a repository (e.g. ``-w <control root>/0100_PLC自动化``) must not shed the PIN that
            # repository enforces, whether or not the folder has a .git of its own (a planted ``git init`` or gitlink
            # file would otherwise stop the search; audit 72 re-reviews).  Found on the file system, so a missing git
            # cannot hide it; the enclosing repository's own check walks further up in turn.
            keys, problem = ApprovalProofService(enclosing).committed_state()
            if keys is not None or problem:
                return None, (
                    f"批准口令由上级仓库 {enclosing} 管着，这一步必须在控制根运行（-w/--control-root 指向它），"
                    "不能用它的子目录当工作区"
                    + (f"；{problem}" if problem else "")
                )
        if not (self._root / ".git").exists():
            # Not inside any PIN-enforcing Git working tree (a scratch workspace): there is no committed file to read.
            return None, ""
        refuse = f"读不到 Git 里已提交的批准人登记文件（{REGISTRY_RELATIVE_PATH}），为安全起见所有批准一律拒绝："
        try:
            top = self._git("rev-parse", "--show-toplevel")
            if top.returncode != 0 or Path(top.stdout.decode("utf-8").strip()).resolve() != self._root:
                return None, refuse + "Git 仓库不是这个控制根"
            head = self._git("rev-parse", "--verify", "-q", "HEAD^{commit}")
            if head.returncode != 0:
                refs = self._git("for-each-ref", "--count=1")
                if refs.returncode == 0 and not refs.stdout.strip() and not self.registry_path.exists():
                    return None, ""  # a brand-new repository with no commit yet
                return None, refuse + "HEAD 不指向任何提交"
            listed = self._git("ls-tree", "--name-only", "HEAD", "--", REGISTRY_RELATIVE_PATH)
            if listed.returncode != 0:
                return None, refuse + "git ls-tree 出错"
            if not listed.stdout.strip():
                if self.registry_path.exists():
                    return None, (
                        f"批准人登记文件 {REGISTRY_RELATIVE_PATH} 还没提交（或已被移出 HEAD）；"
                        "请先提交它，提交前所有批准一律拒绝"
                    )
                ever = self._git("rev-list", "-n", "1", "--all", "--", REGISTRY_RELATIVE_PATH)
                if ever.returncode != 0:
                    return None, refuse + "git rev-list 出错"
                if ever.stdout.strip():
                    return None, refuse + "批准口令曾经启用过，现在 HEAD 里却没有登记文件"
                return None, ""
            shown = self._git("show", f"HEAD:{REGISTRY_RELATIVE_PATH}")
            if shown.returncode != 0:
                return None, refuse + "git show 出错"
        except ApprovalProofError as error:
            return None, refuse + str(error)
        except (OSError, subprocess.SubprocessError) as error:
            return None, refuse + f"无法运行 git（{type(error).__name__}）"
        except UnicodeDecodeError:
            return None, refuse + "Git 输出的路径不是合法 UTF-8"
        try:
            return parse_registry(shown.stdout.decode("utf-8")), ""
        except ApprovalProofError as error:
            return None, str(error)
        except UnicodeDecodeError:
            return None, refuse + "登记文件不是合法 UTF-8"

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        """git in this root only: inherited GIT_* variables (GIT_DIR, GIT_WORK_TREE, ...) could point it elsewhere."""

        environment = {name: value for name, value in os.environ.items() if not name.upper().startswith("GIT_")}
        return run_git_bounded(
            ["git", "-C", str(self._root), *arguments],
            default_timeout=30.0,
            error_cls=ApprovalProofError,
            where=self._root,
            capture_output=True,
            check=False,
            env=environment,
        )

    def enforced(self) -> bool:
        return self.committed_keys() is not None

    def working_keys(self) -> list[ApproverKey]:
        """The verifiers in the working tree file (what ``init`` edits before the user commits it)."""

        if not self.registry_path.is_file():
            return []
        return parse_registry(self.registry_path.read_text(encoding="utf-8"))

    def write_working_keys(self, keys: list[ApproverKey]) -> Path:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(registry_text(keys), encoding="utf-8", newline="\n")
        return self.registry_path

    # ------------------------------------------------------------------ verification
    def attest(self, pin: str, *, purpose: str, subject: str, now: datetime | None = None) -> ApprovalProof:
        """Verify ``pin`` against the committed verifiers; refuse when none is committed (callers decide that case)."""

        keys = self.committed_keys()
        if keys is None:
            raise ApprovalProofError("还没有提交批准口令（pm approver-pin init 后要提交登记文件）")
        moment = now or datetime.now(UTC)
        self._refuse_when_locked(moment)
        if not pin:
            raise ApprovalProofError(
                "已启用批准口令：这一步必须由用户本人在终端输入批准口令"
                "（批准范围用 main.py pm approve，最终验收用 main.py pm accept，命令会提示输入；驾驶舱界面暂不能输入口令）。"
                "agent 不得索要或代填口令"
            )
        for key in keys:
            if hmac.compare_digest(_derive(pin, key.salt, key.n, key.r, key.p), key.verifier):
                self._clear_failures()
                digest = hashlib.sha256(f"{purpose}\n{subject}".encode()).hexdigest()[:16]
                return ApprovalProof(
                    approver=key.approver,
                    key_id=key.key_id,
                    evidence_ref=f"user-confirmation:pin-{key.key_id}-{purpose}-{digest}",
                )
        left = self._record_failure(moment)
        if left <= 0:
            raise ApprovalProofError(f"批准口令错误；已连续错 {MAX_FAILURES} 次，批准锁定 15 分钟")
        raise ApprovalProofError(f"批准口令错误（再错 {left} 次锁定 15 分钟）；未写入任何内容")

    def resolve(
        self, *, pin: str, approver: str, evidence_ref: str, purpose: str, subject: str
    ) -> tuple[str, str]:
        """(approver, evidence reference) to record for one human approval.

        Without a committed verifier: the caller's values, unchanged (they still go through the old format check).
        With one: the verified key's approver and a PIN reference; a caller-supplied approver must be that same person.
        """

        if self.committed_keys() is None:
            return approver, evidence_ref
        proof = self.attest(pin, purpose=purpose, subject=subject)
        if approver.strip() and approver.strip() != proof.approver:
            raise ApprovalProofError(f"批准口令属于 {proof.approver}，与填写的批准人 {approver.strip()} 不一致")
        return proof.approver, proof.evidence_ref

    def require(self, *, pin: str, purpose: str, subject: str) -> ApprovalProof | None:
        """A proof when a verifier is committed (refusing without a valid PIN), None otherwise."""

        if self.committed_keys() is None:
            return None
        return self.attest(pin, purpose=purpose, subject=subject)

    # ------------------------------------------------------------------ wrong-PIN lockout
    @property
    def _failures_path(self) -> Path:
        return self._root / _FAILURES_RELATIVE_PATH

    def _failures(self) -> dict[str, object]:
        try:
            data = json.loads(self._failures_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _refuse_when_locked(self, now: datetime) -> None:
        until = str(self._failures().get("locked_until", ""))
        if until:
            try:
                locked_until = datetime.fromisoformat(until)
            except ValueError:
                return
            if now < locked_until:
                raise ApprovalProofError(
                    f"批准口令连续输错 {MAX_FAILURES} 次，锁定到 {locked_until.astimezone().strftime('%H:%M')}（本机时间）"
                )

    def _record_failure(self, now: datetime) -> int:
        data = self._failures()
        raw = data.get("count", 0)
        count = (raw if isinstance(raw, int) else 0) + 1
        record: dict[str, object] = {"count": count, "last_failure": now.isoformat()}
        if count >= MAX_FAILURES:
            record = {"count": 0, "locked_until": (now + LOCKOUT).isoformat(), "last_failure": now.isoformat()}
        try:
            self._failures_path.parent.mkdir(parents=True, exist_ok=True)
            self._failures_path.write_text(json.dumps(record), encoding="utf-8")
        except OSError:
            pass
        return MAX_FAILURES - count

    def _clear_failures(self) -> None:
        try:
            self._failures_path.unlink(missing_ok=True)
        except OSError:
            pass
