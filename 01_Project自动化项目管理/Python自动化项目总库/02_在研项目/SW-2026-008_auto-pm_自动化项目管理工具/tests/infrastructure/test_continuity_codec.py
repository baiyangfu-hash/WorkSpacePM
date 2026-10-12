"""The codecs extracted from the continuity store produce exactly the bytes the store produced before (card CARD-SW008-M3-B1, WBS task M2-B1).

The expected digests below were computed ONCE from the original static methods of ``ContinuityStore`` at the baseline commit and are written down as literals, so a change of the
canonical form, the encoding or the lease-token domain prefix is caught even if the store and the codec were changed together. The store's private static methods must stay
callable on the class and on an instance and must agree with the codec.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any

import pytest

from auto_pm.infrastructure.continuity_internal import codec
from auto_pm.infrastructure.continuity_store import ContinuityStore

REQUESTS: dict[str, dict[str, Any]] = {'empty': {},
 'ordered': {'a': 1, 'b': 2},
 'reordered': {'b': 2, 'a': 1},
 'unicode': {'目标': '运行-中文', '路径': ['01_项目/文件.md', 'tests/测试.py']},
 'nested': {'run': {'id': 'RUN-1', 'owned': ['x', 'y'], 'n': 3}, 'flags': [True, False, None], 'ratio': 0.5}}
TOKENS: dict[str, str] = {'ascii': 'tok-ABC-123', 'empty': '', 'unicode': '令牌-тест-🔑'}
RUN_DIGESTS: dict[str, str] = {
    "empty": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    "ordered": "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
    "reordered": "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
    "unicode": "293e30ab33c79fdad6caea85fcf53744695c901b1f54db6b5ac0f55b166bcc5c",
    "nested": "785ae3cd3bb4a41e31b72db248d8014308194625efccecd45ea8b82137fc14d4"
}
SETTLEMENT_DIGESTS: dict[str, str] = {
    "empty": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    "ordered": "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
    "reordered": "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
    "unicode": "293e30ab33c79fdad6caea85fcf53744695c901b1f54db6b5ac0f55b166bcc5c",
    "nested": "785ae3cd3bb4a41e31b72db248d8014308194625efccecd45ea8b82137fc14d4"
}
FINGERPRINTS: dict[str, str] = {
    "ascii": "3725f9b26b7cc5aa6926fb4a41553a9f1b93030a8d0fd2d501b6ba7de59399c7",
    "empty": "fd8cbbc02ec5b85ab8d1678e4a219a4d22db17bc407b86839b86fc8b079c0b90",
    "unicode": "2548a4df130765308ea3fd919a660d64448b6f578f705f5324eb5ffac30050f1"
}


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_cd01_the_run_creation_hash_is_the_digest_the_original_code_produced(name: str) -> None:
    assert codec.run_creation_request_hash(REQUESTS[name]) == RUN_DIGESTS[name]
    assert ContinuityStore._run_creation_request_hash(REQUESTS[name]) == RUN_DIGESTS[name]


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_cd02_the_settlement_hash_is_the_digest_the_original_code_produced(name: str) -> None:
    assert codec.settlement_request_hash(REQUESTS[name]) == SETTLEMENT_DIGESTS[name]
    assert ContinuityStore._settlement_request_hash(REQUESTS[name]) == SETTLEMENT_DIGESTS[name]


@pytest.mark.parametrize("name", sorted(TOKENS))
def test_cd03_the_lease_token_fingerprint_is_the_digest_the_original_code_produced(name: str) -> None:
    token = TOKENS[name]
    assert codec.lease_token_fingerprint(token) == FINGERPRINTS[name]
    assert ContinuityStore._lease_token_fingerprint(token) == FINGERPRINTS[name]
    assert FINGERPRINTS[name] != hashlib.sha256(token.encode("utf-8")).hexdigest(), "the domain prefix must separate the fingerprint from a plain digest"
    if token:
        assert token not in FINGERPRINTS[name]


def test_cd04_key_order_does_not_change_a_hash_and_unicode_is_not_escaped() -> None:
    assert RUN_DIGESTS["ordered"] == RUN_DIGESTS["reordered"]
    assert codec.run_creation_request_hash({"b": 2, "a": 1}) == codec.run_creation_request_hash({"a": 1, "b": 2})
    unescaped = hashlib.sha256(json.dumps({"目标": "x"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert codec.run_creation_request_hash({"目标": "x"}) == unescaped
    escaped = hashlib.sha256(json.dumps({"目标": "x"}, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert unescaped != escaped


def test_cd05_the_original_error_semantics_are_kept_for_a_request_that_is_not_json() -> None:
    with pytest.raises(TypeError):
        codec.run_creation_request_hash({"x": object()})
    with pytest.raises(TypeError):
        codec.settlement_request_hash({"x": object()})
    with pytest.raises(TypeError):
        ContinuityStore._run_creation_request_hash({"x": object()})


def test_cd06_the_store_keeps_the_three_private_static_methods_as_delegates() -> None:
    for name in ("_run_creation_request_hash", "_settlement_request_hash", "_lease_token_fingerprint"):
        raw = inspect.getattr_static(ContinuityStore, name)
        assert isinstance(raw, staticmethod), f"{name} must stay a staticmethod so every existing call site and patch target keeps working"
        assert len(inspect.getsource(raw.__func__).splitlines()) <= 8, f"{name} must stay a thin delegate to the codec"
