"""Isolated real-file tests for fail-closed decision disposition consumption."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from auto_pm.contracts.decision_package import DecisionPackageDTO, DecisionPackageValidationError
from auto_pm.domain.change.decision_service import (
    DecisionNotFoundError,
    DecisionService,
    DecisionValidationError,
)

DECISION_ID = "DEC-20260904-3362BFFF"


def _decision_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "decision_package.v1",
        "decision_id": DECISION_ID,
        "project_id": "SW-2026-008",
        "change_id": "CHG-SCPT-2026-005",
        "approved_scope": "MODULE",
        "approved_files": ["auto_pm/domain/change/decision_service.py"],
        "approver": "fubai",
        "approved_at": "2026-09-05T04:39:55+00:00",
        "decision_conclusion": "approved",
        "conditions": ["candidate only"],
        "metadata": {},
    }
    payload.update(overrides)
    return payload


def _disposition_payload(target_sha: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "decision_disposition.v1",
        "record_id": "DISP-20260904-3362BFFF-01",
        "target_decision_id": DECISION_ID,
        "target_decision_sha256": target_sha,
        "disposition": "BLOCKED_SEMANTIC_CONFLICT",
        "effect": "NOT_AUTHORITY_FOR_FUTURE_RECOVERY_COMMIT_DEPLOY_OR_RELEASE",
        "preserves_original": True,
        "retroactive_mutation": False,
        "approver": "fubai",
        "approved_at": "2026-09-04T22:05:08+00:00",
        "supersession_status": "DEFERRED_UNTIL_NEW_INDEPENDENTLY_APPROVED_DECISION",
        "superseding_decision_id": None,
        "authority_semantics": {
            "future_consumption_only": True,
            "rewrites_target_decision": False,
            "grants_recovery_or_release_authority": False,
        },
    }
    payload.update(overrides)
    return payload


def _write_decision(
    workspace: Path, payload: dict[str, Any], *, file_decision_id: str | None = None
) -> bytes:
    target_id = file_decision_id or payload["decision_id"]
    target = workspace / ".auto-pm" / "decisions" / f"{target_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    target.write_bytes(encoded)
    return encoded


def _write_disposition(workspace: Path, payload: dict[str, Any], name: str = "record.json") -> None:
    target = workspace / ".auto-pm" / "decisions" / "dispositions" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_valid_current_decision_can_authorize_its_exact_files(tmp_path: Path) -> None:
    _write_decision(tmp_path, _decision_payload())

    decision = DecisionService(tmp_path).get_decision(
        DECISION_ID, target_files=["auto_pm/domain/change/decision_service.py"]
    )

    assert decision.decision_id == DECISION_ID


def test_blocked_historical_decision_is_never_consumed(tmp_path: Path) -> None:
    decision_bytes = _write_decision(tmp_path, _decision_payload())
    _write_disposition(tmp_path, _disposition_payload(hashlib.sha256(decision_bytes).hexdigest()))

    with pytest.raises(DecisionValidationError, match="blocked.*拒绝消费"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_superseded_decision_is_never_consumed(tmp_path: Path) -> None:
    decision_bytes = _write_decision(tmp_path, _decision_payload())
    _write_disposition(
        tmp_path,
        _disposition_payload(
            hashlib.sha256(decision_bytes).hexdigest(),
            disposition="SUPERSEDED",
            supersession_status="SUPERSEDED",
            superseding_decision_id="DEC-20260905-NEW00001",
        ),
    )

    with pytest.raises(DecisionValidationError, match="superseded.*拒绝消费"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_disposition_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    _write_decision(tmp_path, _decision_payload())
    _write_disposition(tmp_path, _disposition_payload("0" * 64))

    with pytest.raises(DecisionValidationError, match="SHA-256.*不匹配"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_missing_target_decision_fails_closed(tmp_path: Path) -> None:
    _write_disposition(tmp_path, _disposition_payload("0" * 64))

    with pytest.raises(DecisionNotFoundError, match="未找到决策包"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_damaged_decision_json_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / ".auto-pm" / "decisions" / f"{DECISION_ID}.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ damaged", encoding="utf-8")

    with pytest.raises(DecisionValidationError, match="JSON 损坏"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_damaged_disposition_json_fails_closed(tmp_path: Path) -> None:
    _write_decision(tmp_path, _decision_payload())
    target = tmp_path / ".auto-pm" / "decisions" / "dispositions" / "broken.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ broken", encoding="utf-8")

    with pytest.raises(DecisionValidationError, match="JSON 损坏"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "decision_package.v0", "schema"),
        ("decision_id", "DEC-INVALID", "decision_id"),
        ("approver", "", "approver"),
        ("approved_at", "2026-09-05", "approved_at"),
        ("approved_files", ["../escape.py"], "安全相对路径"),
    ],
)
def test_authority_bearing_decision_fields_are_strict(
    tmp_path: Path, field: str, value: Any, message: str
) -> None:
    _write_decision(
        tmp_path,
        _decision_payload(**{field: value}),
        file_decision_id=DECISION_ID,
    )

    with pytest.raises(DecisionValidationError, match=message):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_exact_allow_list_rejects_unapproved_target_and_duplicate_request(tmp_path: Path) -> None:
    _write_decision(tmp_path, _decision_payload())
    service = DecisionService(tmp_path)

    with pytest.raises(DecisionValidationError, match="未获精确批准"):
        service.get_decision(DECISION_ID, target_files=["auto_pm/contracts/decision_package.py"])
    with pytest.raises(DecisionValidationError, match="重复路径"):
        service.get_decision(
            DECISION_ID,
            target_files=[
                "auto_pm/domain/change/decision_service.py",
                "auto_pm/domain/change/decision_service.py",
            ],
        )


def test_conflicting_disposition_state_fails_closed(tmp_path: Path) -> None:
    decision_bytes = _write_decision(tmp_path, _decision_payload())
    _write_disposition(
        tmp_path,
        _disposition_payload(
            hashlib.sha256(decision_bytes).hexdigest(),
            supersession_status="SUPERSEDED",
            superseding_decision_id="DEC-20260905-NEW00001",
        ),
    )

    with pytest.raises(DecisionValidationError, match="状态冲突"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_multiple_dispositions_for_one_target_fail_closed(tmp_path: Path) -> None:
    decision_bytes = _write_decision(tmp_path, _decision_payload())
    record = _disposition_payload(hashlib.sha256(decision_bytes).hexdigest())
    _write_disposition(tmp_path, record, "first.json")
    _write_disposition(tmp_path, record, "second.json")

    with pytest.raises(DecisionValidationError, match="多个处置记录"):
        DecisionService(tmp_path).get_decision(DECISION_ID)


def test_dto_rejects_ambiguous_path_before_serialization() -> None:
    dto = DecisionPackageDTO(
        decision_id=DECISION_ID,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-005",
        approved_scope="MODULE",
        approved_files=["auto_pm\\domain\\change\\decision_service.py"],
        approver="fubai",
        approved_at="2026-09-05T04:39:55+00:00",
    )

    with pytest.raises(DecisionPackageValidationError, match="精确路径"):
        dto.to_dict()
