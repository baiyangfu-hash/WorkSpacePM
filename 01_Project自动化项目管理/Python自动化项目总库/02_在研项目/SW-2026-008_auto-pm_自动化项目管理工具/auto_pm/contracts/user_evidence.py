"""The one definition of "the user's own words" that every approval path shares.

Before this module the planning approval (``DecisionService``) and the Mission park/unpark/switch/admission rules
(``contracts.mission``) each kept their own copy of the evidence pattern and of the agent-name list, so a change to one
could miss the other (TD-071 card 2 audit 75, low).  Both now read from here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Final

USER_CONFIRMATION_PREFIX: Final = "user-confirmation:"

# ``user-confirmation:`` and a reference to the user's message (its time or id) of at least 8 characters.
USER_CONFIRMATION = re.compile(r"user-confirmation:[A-Za-z0-9][A-Za-z0-9._:/-]{7,}\Z")

# Agent, model and tool names, matched as whole words; an approver or a reference that names one was not written by
# the user.  Separators include ``:`` and ``/`` so that ``codex/auto-ok`` or ``x:claude`` are caught too.
AGENT_NAMES: Final = (
    "ai",
    "agent",
    "codex",
    "gpt",
    "model",
    "claude",
    "anthropic",
    "opus",
    "sonnet",
    "haiku",
    "fable",
    "gemini",
    "copilot",
    "llm",
    "bot",
    "assistant",
    "trae",
    "cursor",
)
AGENT_MARKER = re.compile(
    r"(?:^|[-_. (:/])(?:" + "|".join(AGENT_NAMES) + r")(?:$|[-_. ):/])",
    re.IGNORECASE,
)


# The fixed words of the user's own evidence formats, which the cockpit writes itself (audit 865 §3.1): the prefix
# ``user-confirmation``, the board click ``board-click:<time>:<session>``, the GUI click ``gui-click-<time>-<digest>``, the cockpit
# click ``cockpit-<hash>-<who>``, the PIN proof ``pin-<key>-<purpose>-<digest>`` with every ``purpose=`` the code passes, and the
# message id ``cmsg_…`` an agent quotes the user by.  An AI may never be registered under one of these (``agent_registry`` reserves
# them), or the user's own approvals would read as agent-written.  ``tests/core/test_agent_registry.py`` scans the code for new
# formats and purposes, so this list cannot fall behind.
EVIDENCE_FORMAT_WORDS: Final = frozenset(
    {
        "user", "confirmation", "board", "click", "gui", "cockpit", "pin", "cmsg",
        # ApprovalProofService.attest(purpose=...): every purpose, split at "-"
        "accept", "admission", "release", "approve", "scope", "card", "change", "decision", "lease", "extend", "hold",
        "rotate", "project", "archive", "delete", "import", "force", "reactivate", "restore", "retire", "sign", "risk",
    }
)

# CHG-SCPT-2026-712: the AIs the user registered on this machine (and the built-in roster names) count as agent names too.
# This module is pure data and cannot read the ledger, so the application layer hands in a source
# (``agent_registry.use_ledger_roster``); it is asked lazily, each time a text is judged.  No source: the built-in words only.
# A source that raises (the registry exists but cannot be read) fails closed: no text is accepted as the user's words.
_EXTRA_NAME = re.compile(r"[a-z][a-z0-9]{1,19}")
_extra_source: list[Callable[[], Iterable[str]]] = []
REGISTRY_UNREADABLE: Final = "本机 AI 登记表读不出来，判不了凭据里有没有写着登记的 AI 名字，先不收（失败关闭）；先修好账本再来"


def use_extra_agent_names(source: Callable[[], Iterable[str]] | None) -> None:
    """Also treat the names ``source`` returns as agent names (``None``: only ``AGENT_NAMES``)."""

    _extra_source[:] = [] if source is None else [source]


def _extra_names() -> tuple[str, ...] | None:
    """The extra agent names; ``None`` when the source cannot answer (fail closed: the caller treats every text as agent-written)."""

    if not _extra_source:
        return ()
    try:
        names = tuple(_extra_source[0]())
    except Exception:  # noqa: BLE001 - any failure to read the registry is "cannot tell", never "nobody registered"
        return None
    return tuple(
        sorted(
            {
                name
                for name in names
                if _EXTRA_NAME.fullmatch(name) and name not in AGENT_NAMES and name not in EVIDENCE_FORMAT_WORDS
            }
        )
    )


def is_user_confirmation(evidence_ref: str) -> bool:
    """Whether ``evidence_ref`` has the ``user-confirmation:<reference>`` form."""

    return USER_CONFIRMATION.fullmatch(evidence_ref) is not None


def names_an_agent(text: str) -> bool:
    """Whether ``text`` names an agent, a model or an AI tool as a whole word."""

    if AGENT_MARKER.search(text) is not None:
        return True
    extra = _extra_names()
    if extra is None:
        return True  # the registry cannot be read: cannot tell, so not the user's words (fail closed)
    if not extra:
        return False
    marker = re.compile(r"(?:^|[-_. (:/])(?:" + "|".join(extra) + r")(?:$|[-_. ):/])", re.IGNORECASE)
    return marker.search(text) is not None


def user_evidence_problem(evidence_ref: str) -> str:
    """Why ``evidence_ref`` is not the user's own words; empty when it is acceptable."""

    if not is_user_confirmation(evidence_ref):
        return "用户原话凭据必须写成 user-confirmation:<用户消息的时间或编号>（至少 8 个字符）"
    if AGENT_MARKER.search(evidence_ref.removeprefix(USER_CONFIRMATION_PREFIX)) is None and _extra_names() is None:
        return REGISTRY_UNREADABLE
    if names_an_agent(evidence_ref.removeprefix(USER_CONFIRMATION_PREFIX)):
        return "用户原话凭据不能是 agent 或模型自己写的"
    return ""
