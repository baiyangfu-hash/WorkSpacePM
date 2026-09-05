"""Temporary AI execution handoff inbox.

Handoffs are short-lived messages for pm-workflow, not a second project ledger.
Only pm-workflow may turn a handoff into PM_SESSION or cockpit feedback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AiHandoffService:
    """Read and validate pending execution handoffs under ``.auto-pm/handoffs``."""

    REQUIRED_FIELDS = ("request_id", "project_id", "executor_skill", "summary")
    DEFAULT_VERIFICATION = {
        "lint_result": "",
        "test_result": "",
        "other_checks": [],
        "not_run": [],
    }
    DEFAULT_PRODUCT_IMPACT = {
        "hypothesis_id": "",
        "impact_type": "general",
        "engineering_signal": "",
        "verification_mode": "code_static",
        "validation_stage": "",
        "needs_user_validation": False,
        "assumption_affected": "",
        "observable_signal": "",
    }
    DEFAULT_PM_CLOSURE = {
        "required": True,
        "suggested_event": "iteration",
        "suggested_status": "pending_review",
    }

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root)

    @property
    def inbox_dir(self) -> Path:
        return self._workspace_root / ".auto-pm" / "handoffs"

    def list_pending(self, project_id: str = "") -> list[dict[str, Any]]:
        """Return valid pending handoffs, newest first, optionally for one project."""
        if not self.inbox_dir.is_dir():
            return []

        handoffs: list[dict[str, Any]] = []
        for path in self.inbox_dir.glob("*.json"):
            payload = self._read_valid(path)
            if payload is None or payload.get("status", "pending") != "pending":
                continue
            if project_id and payload["project_id"] != project_id:
                continue
            payload["file"] = str(path)
            handoffs.append(payload)
        return sorted(handoffs, key=lambda item: str(item.get("generated_at", "")), reverse=True)

    def get_pending(self, request_id: str) -> dict[str, Any] | None:
        """Return one valid pending handoff by request id."""
        for handoff in self.list_pending():
            if handoff["request_id"] == request_id:
                return handoff
        return None

    def _read_valid(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if any(not str(payload.get(field, "")).strip() for field in self.REQUIRED_FIELDS):
            return None
        return self._normalize_payload(payload)

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["status"] = str(payload.get("status", "pending") or "pending")
        normalized["changed_files"] = self._normalize_list(payload.get("changed_files"))
        normalized["risks"] = self._normalize_list(payload.get("risks"))
        normalized["next_actions"] = self._normalize_list(payload.get("next_actions"))
        normalized["watchouts"] = self._normalize_list(payload.get("watchouts"))
        normalized["read_first"] = self._normalize_list(payload.get("read_first"))
        normalized["artifacts"] = self._normalize_list(payload.get("artifacts"))
        normalized["chg_updates"] = self._normalize_list(payload.get("chg_updates"))
        normalized["verification"] = self._normalize_mapping(
            payload.get("verification"), self.DEFAULT_VERIFICATION
        )

        pi = self._normalize_mapping(payload.get("product_impact"), self.DEFAULT_PRODUCT_IMPACT)
        # Bidirectional sync for backward compatibility
        if not pi["hypothesis_id"] and pi.get("assumption_affected"):
            pi["hypothesis_id"] = str(pi["assumption_affected"])
        if not pi.get("assumption_affected") and pi["hypothesis_id"]:
            pi["assumption_affected"] = pi["hypothesis_id"]
        if not pi["engineering_signal"] and pi.get("observable_signal"):
            pi["engineering_signal"] = str(pi["observable_signal"])
        if not pi.get("observable_signal") and pi["engineering_signal"]:
            pi["observable_signal"] = pi["engineering_signal"]

        normalized["product_impact"] = pi
        normalized["pm_closure"] = self._normalize_mapping(
            payload.get("pm_closure"), self.DEFAULT_PM_CLOSURE
        )
        return normalized

    def validate_product_impact(self, product_impact: dict[str, Any]) -> dict[str, Any]:
        """Validate product_impact against anti-emptiness and anti-platitude rules."""
        hypothesis_id = str(product_impact.get("hypothesis_id", "")).strip()
        signal = str(product_impact.get("engineering_signal", "")).strip()

        warnings: list[str] = []
        if not hypothesis_id:
            warnings.append("缺少 hypothesis_id（未关联产品假设）")
        if not signal:
            warnings.append("缺少 engineering_signal（未描述具体工程/物理可观测信号）")
        elif len(signal) < 8 and any(
            kw in signal for kw in ("优化", "完成", "修改", "修复", "改进")
        ):
            warnings.append("engineering_signal 过于泛化（缺乏具体物理量/交互量）")

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
        }

    def _normalize_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        return []

    def _normalize_mapping(self, value: Any, defaults: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(defaults)
        if isinstance(value, dict):
            for key in defaults:
                if key in value:
                    normalized[key] = value[key]
        return normalized
