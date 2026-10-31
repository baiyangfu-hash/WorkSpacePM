"""Pure codecs of the continuity store: no I/O, no clock, no connection, no Qt.

Extracted from ``continuity_store.py`` by card CARD-SW008-M3-B1 (WBS task M2-B1) without changing a byte of what they produce. The store keeps its private static
methods as thin delegates, so every caller, every patch target and every hash already written into an event stay exactly as before.
"""

from __future__ import annotations

import hashlib
import json

_LEASE_TOKEN_DOMAIN = b"auto-pm/run-lease-token/v1\0"


def run_creation_request_hash(request: dict[str, object]) -> str:
    """SHA-256 of the canonical JSON (sorted keys, compact separators, non-ASCII kept) of a Run creation request."""

    return hashlib.sha256(
        json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def settlement_request_hash(request: dict[str, object]) -> str:
    """SHA-256 of the canonical JSON of a recovery settlement request (same canonical form as the Run creation request)."""

    canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def lease_token_fingerprint(lease_token: str) -> str:
    """Domain-separated SHA-256 of a lease token; the token itself is never part of the output."""

    return hashlib.sha256(_LEASE_TOKEN_DOMAIN + lease_token.encode("utf-8")).hexdigest()
