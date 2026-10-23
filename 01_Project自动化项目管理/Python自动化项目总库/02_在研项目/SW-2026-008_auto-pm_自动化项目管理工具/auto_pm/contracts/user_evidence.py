"""The one definition of "the user's own words" that every approval path shares.

Before this module the planning approval (``DecisionService``) and the Mission park/unpark/switch/admission rules
(``contracts.mission``) each kept their own copy of the evidence pattern and of the agent-name list, so a change to one
could miss the other (TD-071 card 2 audit 75, low).  Both now read from here.
"""

from __future__ import annotations

import re
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


def is_user_confirmation(evidence_ref: str) -> bool:
    """Whether ``evidence_ref`` has the ``user-confirmation:<reference>`` form."""

    return USER_CONFIRMATION.fullmatch(evidence_ref) is not None


def names_an_agent(text: str) -> bool:
    """Whether ``text`` names an agent, a model or an AI tool as a whole word."""

    return AGENT_MARKER.search(text) is not None


def user_evidence_problem(evidence_ref: str) -> str:
    """Why ``evidence_ref`` is not the user's own words; empty when it is acceptable."""

    if not is_user_confirmation(evidence_ref):
        return "用户原话凭据必须写成 user-confirmation:<用户消息的时间或编号>（至少 8 个字符）"
    if names_an_agent(evidence_ref.removeprefix(USER_CONFIRMATION_PREFIX)):
        return "用户原话凭据不能是 agent 或模型自己写的"
    return ""
