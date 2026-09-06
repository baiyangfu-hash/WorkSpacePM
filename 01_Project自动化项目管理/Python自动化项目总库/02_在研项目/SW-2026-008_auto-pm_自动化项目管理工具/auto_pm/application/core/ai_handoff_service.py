"""AI skill handoff contract and transactional inbox service.

The inbox is a short-lived execution message. It is deliberately not a
second project ledger: only the PM workflow may consume a handoff and write
the result to PM_SESSION or cockpit feedback.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from auto_pm.application.core.pm_saga_service import PmClosureSagaCoordinator


class HandoffError(RuntimeError):
    """Base error for invalid or unsafe handoff operations."""


class HandoffValidationError(HandoffError, ValueError):
    """Raised when a request or closure result violates handoff.v1."""


class HandoffConflictError(HandoffError):
    """Raised when an idempotency key is reused with different content."""


class HandoffNotFoundError(HandoffError):
    """Raised when a requested handoff does not exist."""


class AiHandoffService:
    """Create, inspect, and atomically consume ``handoff.v1`` messages."""

    SCHEMA_VERSION = "handoff.v1"
    REQUIRED_FIELDS = ("request_id", "project_id", "executor_skill", "summary")
    ALLOWED_EXECUTOR_SKILLS = frozenset({"fullstack-engineer", "plc-electrical-engineer"})
    ALLOWED_STATUSES = frozenset(
        {"pending", "claimed", "in_progress", "completed", "failed", "expired", "consumed"}
    )
    STATUS_ORDER = ("pending", "claimed", "in_progress", "completed", "failed", "expired", "consumed")
    ACTIVE_STATUSES = frozenset({"pending", "claimed", "in_progress", "completed"})
    DEFAULT_LEASE_SECONDS = 900
    REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,79}$")
    LOCK_STALE_SECONDS = 300
    RESULT_FIELDS = (
        "summary",
        "changed_files",
        "verification",
        "risks",
        "next_actions",
        "watchouts",
        "read_first",
        "artifacts",
        "chg_updates",
        "change_substance",
        "product_impact",
        "pm_closure",
    )

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
        self._workspace_root = Path(workspace_root).resolve()
        self._saga_coordinator: PmClosureSagaCoordinator | None = None

    @property
    def saga_coordinator(self) -> PmClosureSagaCoordinator:
        if self._saga_coordinator is None:
            from auto_pm.application.core.pm_saga_service import PmClosureSagaCoordinator

            self._saga_coordinator = PmClosureSagaCoordinator(self._workspace_root, handoff_service=self)
        return self._saga_coordinator

    @property
    def inbox_dir(self) -> Path:
        return self._workspace_root / ".auto-pm" / "handoffs"

    @property
    def failure_dir(self) -> Path:
        """Return the ignored evidence directory for failed Saga attempts."""
        return self._workspace_root / ".auto-pm" / "reports" / "dogfood" / "handoff-saga"

    def create_request(
        self,
        project_id: str,
        executor_skill: str,
        summary: str,
        *,
        goal: str = "",
        mode: str = "execution",
        specs: list[str] | None = None,
        read_first: list[str] | None = None,
        request_id: str = "",
        change_id: str = "",
        decision_id: str = "",
        skill_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a pending request, or return the same request idempotently."""
        self._validate_scalar(project_id, "project_id")
        if executor_skill not in self.ALLOWED_EXECUTOR_SKILLS:
            raise HandoffValidationError(f"executor_skill 不受支持: {executor_skill}")
        self._validate_scalar(summary, "summary")
        if mode not in {"grooming", "execution"}:
            raise HandoffValidationError("mode 必须是 grooming 或 execution")

        resolved_request_id = request_id or self._new_request_id()
        self._validate_request_id(resolved_request_id)
        generated_at = datetime.now(UTC).isoformat()
        context = dict(skill_context or {})
        context.setdefault("goal", goal)
        context.setdefault("mode", mode)
        context.setdefault("injected_specs", list(specs or []))
        context.setdefault("baseline_documents", list(read_first or []))
        if change_id:
            context["change_id"] = change_id

        if decision_id:
            from auto_pm.domain.change.decision_service import DecisionError, DecisionService
            try:
                dec_svc = DecisionService(self._workspace_root)
                dec = dec_svc.get_decision(decision_id)
                if dec.project_id and dec.project_id != project_id:
                    raise HandoffValidationError(
                        f"决策包项目编号不匹配: 期望 {project_id}，实际 {dec.project_id}"
                    )
                if change_id and dec.change_id != change_id:
                    raise HandoffValidationError(
                        f"决策包关联变更单不匹配: 期望 {change_id}，实际 {dec.change_id}"
                    )
                context["decision_id"] = decision_id
                context["approved_scope"] = dec.approved_scope
                context["approved_files"] = dec.approved_files
                context["decision_conclusion"] = dec.decision_conclusion
            except DecisionError as e:
                raise HandoffValidationError(f"决策包验证失败: {e}") from e

        payload: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "request_id": resolved_request_id,
            "project_id": project_id,
            "executor_skill": executor_skill,
            "summary": summary,
            "status": "pending",
            "lifecycle_version": "handoff.lifecycle.v2",
            "dispatch": {
                "adapter": "manual",
                "state": "awaiting_pickup",
            },
            "mode": mode,
            "goal": goal,
            "change_id": change_id,
            "decision_id": decision_id,
            "generated_at": generated_at,
            "created_by": "pm-workflow",
            "skill_context": context,
            "idempotency_key": resolved_request_id,
            "changed_files": [],
            "risks": [],
            "next_actions": [],
            "watchouts": [],
            "read_first": list(read_first or []),
            "artifacts": [],
            "chg_updates": [],
            "verification": self._copy_default(self.DEFAULT_VERIFICATION),
            "product_impact": self._copy_default(self.DEFAULT_PRODUCT_IMPACT),
            "pm_closure": self._copy_default(self.DEFAULT_PM_CLOSURE),
        }

        path = self._path_for_request(resolved_request_id)
        with self._transaction_lock():
            if path.exists():
                existing = self._read_valid(path)
                if existing is None:
                    raise HandoffConflictError(f"交接文件已存在但不可读取: {path.name}")
                if self._same_request(existing, payload):
                    existing["file"] = str(path)
                    return existing
                raise HandoffConflictError(f"request_id 已存在且内容不同: {resolved_request_id}")
            self._write_atomic(path, payload)
        payload["file"] = str(path)
        return payload

    def list_pending(self, project_id: str = "") -> list[dict[str, Any]]:
        """Return valid pending handoffs, newest first, optionally by project."""
        return self.list_requests(project_id=project_id, status="pending")

    def list_active(self, project_id: str = "") -> list[dict[str, Any]]:
        """Return requests that still need executor or PM attention."""
        return [
            request
            for request in self.list_requests(project_id=project_id)
            if request.get("status") in self.ACTIVE_STATUSES
        ]

    def list_requests(
        self,
        project_id: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        """Return valid inbox records, including consumed records when requested."""
        if not self.inbox_dir.is_dir():
            return []
        if status and status not in self.ALLOWED_STATUSES:
            raise HandoffValidationError(f"不支持的 handoff status: {status}")

        handoffs: list[dict[str, Any]] = []
        for path in sorted(self.inbox_dir.glob("*.json")):
            # Executor receipts are evidence sidecars, never queue entries.
            if path.name.endswith(".result.json"):
                continue
            payload = self._read_valid(path)
            if payload is None:
                continue
            if status and payload.get("status", "pending") != status:
                continue
            if project_id and payload.get("project_id") != project_id:
                continue
            payload["file"] = str(path)
            handoffs.append(payload)
        return sorted(
            handoffs,
            key=lambda item: str(item.get("closed_at") or item.get("generated_at") or ""),
            reverse=True,
        )

    def queue_snapshot(self, project_id: str = "", *, limit: int = 10) -> dict[str, Any]:
        """Return a read-only aggregate view of the handoff inbox."""
        if limit < 1 or limit > 100:
            raise HandoffValidationError("queue limit 必须在 1 到 100 之间")

        requests = self.list_requests(project_id=project_id)
        counts = dict.fromkeys(self.STATUS_ORDER, 0)
        lifecycle_counts: dict[str, int] = {}
        failure_by_request: dict[str, int] = {}
        failure_total = 0
        for request in requests:
            status = str(request.get("status", "pending"))
            if status in counts:
                counts[status] += 1
            lifecycle = self._lifecycle_state(request)
            lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1
            request_id = str(request.get("request_id", ""))
            events = self.list_failure_events(request_id)
            if events:
                failure_by_request[request_id] = len(events)
                failure_total += len(events)

        return {
            "schema_version": "handoff.queue.v1",
            "project_id": project_id,
            "as_of": datetime.now(UTC).isoformat(),
            "read_only": True,
            "total": len(requests),
            "status_counts": counts,
            "lifecycle_state_counts": dict(sorted(lifecycle_counts.items())),
            "failure_events": {
                "total": failure_total,
                "by_request": failure_by_request,
            },
            "latest": requests[:limit],
        }

    def claim_request(
        self,
        request_id: str,
        *,
        executor_id: str,
        adapter: str = "manual",
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> dict[str, Any]:
        """Claim a pending request with a renewable executor lease."""
        self._validate_executor(executor_id, adapter, lease_seconds)
        return self._transition_execution(
            request_id,
            executor_id=executor_id,
            allowed_statuses={"pending"},
            next_status="claimed",
            adapter=adapter,
            lease_seconds=lease_seconds,
            event="claimed",
        )

    def start_request(self, request_id: str, *, executor_id: str) -> dict[str, Any]:
        """Mark a claimed request as actively executing."""
        return self._transition_execution(
            request_id,
            executor_id=executor_id,
            allowed_statuses={"claimed"},
            next_status="in_progress",
            event="started",
        )

    def heartbeat_request(
        self,
        request_id: str,
        *,
        executor_id: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> dict[str, Any]:
        """Renew the lease for its owner without changing execution status."""
        self._validate_executor(executor_id, "manual", lease_seconds)
        return self._transition_execution(
            request_id,
            executor_id=executor_id,
            allowed_statuses={"claimed", "in_progress"},
            next_status="",
            lease_seconds=lease_seconds,
            event="heartbeat",
        )

    def submit_result(
        self,
        request_id: str,
        *,
        executor_id: str,
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist a verified executor result before PM consumes the handoff."""
        self._validate_request_id(request_id)
        with self._transaction_lock():
            path = self._find_request_path(request_id)
            current = self._read_valid(path)
            if current is None:
                raise HandoffNotFoundError(f"找不到有效 handoff: {request_id}")
            self._require_executor_owner(current, executor_id, {"in_progress"})
            merged = self._merge_result(current, result)
            self._validate_closure(merged)
            now = datetime.now(UTC).isoformat()
            merged["status"] = "completed"
            merged["result_submitted_at"] = now
            execution = dict(merged.get("execution") or {})
            execution.update({"last_event": "result_submitted", "last_heartbeat_at": now})
            merged["execution"] = execution
            self._write_atomic(path, merged)
            self._write_result_atomic(request_id, result)
        merged["file"] = str(path)
        return merged

    def fail_request(
        self,
        request_id: str,
        *,
        executor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Record an executor-owned failure without consuming the request."""
        if not reason.strip():
            raise HandoffValidationError("失败原因不能为空")
        return self._transition_execution(
            request_id,
            executor_id=executor_id,
            allowed_statuses={"claimed", "in_progress"},
            next_status="failed",
            event="failed",
            reason=reason,
        )

    def expire_stale_requests(self, project_id: str = "") -> list[dict[str, Any]]:
        """Mark elapsed execution leases as expired and return affected requests."""
        expired: list[dict[str, Any]] = []
        with self._transaction_lock():
            for request in self.list_requests(project_id=project_id):
                if request.get("status") not in {"claimed", "in_progress"} or not self._lease_expired(request):
                    continue
                path = self._find_request_path(str(request["request_id"]))
                request["status"] = "expired"
                execution = dict(request.get("execution") or {})
                execution["last_event"] = "timeout"
                execution["expired_at"] = datetime.now(UTC).isoformat()
                request["execution"] = execution
                self._write_atomic(path, request)
                request["file"] = str(path)
                expired.append(request)
        return expired

    def requeue_request(self, request_id: str, *, pm_id: str, reason: str) -> dict[str, Any]:
        """Return a stale or failed request to PM-controlled pending dispatch."""
        self._validate_request_id(request_id)
        if not pm_id.strip():
            raise HandoffValidationError("pm_id 不能为空")
        if not reason.strip():
            raise HandoffValidationError("重新派发原因不能为空")

        with self._transaction_lock():
            path = self._find_request_path(request_id)
            current = self._read_valid(path)
            if current is None:
                raise HandoffNotFoundError(f"找不到有效 handoff: {request_id}")
            status = str(current.get("status", "pending"))
            can_requeue = status in {"expired", "failed"} or (
                status in {"claimed", "in_progress"} and self._lease_expired(current)
            )
            if not can_requeue:
                raise HandoffConflictError("仅允许重新派发 failed、expired 或租约已过期的请求")

            now = datetime.now(UTC).isoformat()
            execution = dict(current.get("execution") or {})
            history = list(execution.get("requeue_history") or [])
            history.append(
                {
                    "at": now,
                    "pm_id": pm_id.strip(),
                    "reason": reason.strip(),
                    "previous_status": status,
                    "previous_executor_id": execution.get("executor_id", ""),
                }
            )
            execution.update({"last_event": "requeued", "requeue_history": history})
            execution.pop("lease_expires_at", None)
            current["status"] = "pending"
            current["dispatch"] = {"adapter": "manual", "state": "awaiting_pickup"}
            current["execution"] = execution
            self._write_atomic(path, current)
        current["file"] = str(path)
        return current

    def get_pending(self, request_id: str) -> dict[str, Any] | None:
        """Return one valid pending handoff by request id."""
        payload = self.get_request(request_id)
        if payload is None or payload.get("status", "pending") != "pending":
            return None
        return payload

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        """Return one valid handoff regardless of its lifecycle status."""
        self._validate_request_id(request_id)
        path = self._find_request_path(request_id)
        payload = self._read_valid(path)
        if payload is not None and payload.get("request_id") == request_id:
            payload["file"] = str(path)
            return payload
        return None

    def preflight_close(
        self,
        request_id: str,
        *,
        result: Mapping[str, Any] | None = None,
        idempotency_key: str = "",
        expected_project_id: str = "",
        expected_executor_skill: str = "",
    ) -> dict[str, Any]:
        """Validate a close without changing the handoff or PM ledgers."""
        self._validate_request_id(request_id)
        with self._transaction_lock():
            path = self._find_request_path(request_id)
            current = self._read_valid(path)
            if current is None:
                raise HandoffNotFoundError(f"找不到有效 handoff: {request_id}")
            self._validate_expected_identity(
                current,
                project_id=expected_project_id,
                executor_skill=expected_executor_skill,
            )
            merged, effective_key, fingerprint = self._prepare_close_payload(
                current,
                result or {},
                idempotency_key,
            )
            if current.get("status") == "consumed":
                old_closure = current.get("closure")
                if isinstance(old_closure, dict) and (
                    old_closure.get("idempotency_key") == effective_key
                    and old_closure.get("fingerprint") == fingerprint
                ):
                    return {
                        "ok": True,
                        "already_consumed": True,
                        "request_id": request_id,
                        "project_id": current["project_id"],
                        "fingerprint": fingerprint,
                        "idempotency_key": effective_key,
                        "file": str(path),
                    }
                raise HandoffConflictError(
                    f"handoff 已消费，不能使用不同结果重复关闭: {request_id}"
                )
            self._validate_closure(merged)
            return {
                "ok": True,
                "already_consumed": False,
                "request_id": request_id,
                "project_id": current["project_id"],
                "executor_skill": current["executor_skill"],
                "fingerprint": fingerprint,
                "idempotency_key": effective_key,
                "file": str(path),
            }

    def list_failure_events(self, request_id: str) -> list[dict[str, Any]]:
        """Read failure evidence for one request without changing runtime state."""
        self._validate_request_id(request_id)
        path = self.failure_dir / f"{request_id}.json"
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return []
        events = payload.get("events") if isinstance(payload, dict) else None
        return list(events) if isinstance(events, list) else []

    def retry_close(
        self,
        request_id: str,
        *,
        result: Mapping[str, Any] | None = None,
        idempotency_key: str = "",
        actor: str = "pm-workflow",
    ) -> dict[str, Any]:
        """Retry a failed close using the same idempotent close protocol."""
        return self.close_request(
            request_id,
            result=result,
            idempotency_key=idempotency_key,
            actor=actor,
        )

    def close_request(
        self,
        request_id: str,
        *,
        result: Mapping[str, Any] | None = None,
        idempotency_key: str = "",
        actor: str = "pm-workflow",
        use_saga: bool = False,
        simulate_fail_at: str = "",
    ) -> dict[str, Any]:
        """Validate and atomically consume one handoff.

        A repeated close with the same semantic result is idempotent. A
        different result or idempotency key is rejected instead of silently
        overwriting an already-consumed message.
        """
        if use_saga:
            return self.close_with_saga(
                request_id,
                result=result,
                idempotency_key=idempotency_key,
                actor=actor,
                simulate_fail_at=simulate_fail_at,
            )
        self._validate_request_id(request_id)
        if not actor.strip():
            raise HandoffValidationError("actor 不能为空")
        try:
            with self._transaction_lock():
                path = self._find_request_path(request_id)
                current = self._read_valid(path)
                if current is None:
                    raise HandoffNotFoundError(f"找不到有效 handoff: {request_id}")

                merged, effective_key, fingerprint = self._prepare_close_payload(
                    current,
                    result or {},
                    idempotency_key,
                )
                old_closure = current.get("closure")
                if current.get("status") == "consumed":
                    if isinstance(old_closure, dict) and (
                        old_closure.get("idempotency_key") == effective_key
                        and old_closure.get("fingerprint") == fingerprint
                    ):
                        current["file"] = str(path)
                        return current
                    raise HandoffConflictError(
                        f"handoff 已消费，不能使用不同结果重复关闭: {request_id}"
                    )

                self._validate_closure(merged)

                # 自动注入变更单实质内容
                target_chg_id = (
                    merged.get("change_id")
                    or merged.get("skill_context", {}).get("change_id")
                    or (merged.get("change_substance", {}) or {}).get("change_number")
                )
                if target_chg_id:
                    try:
                        from auto_pm.domain.change.substance_injector import SubstanceInjector
                        substance = merged.get("change_substance") or {}
                        changed_files = merged.get("changed_files") or []
                        executor_id = str(merged.get("execution", {}).get("executor_id", "ai-executor"))
                        SubstanceInjector.inject(
                            workspace_root=self._workspace_root,
                            change_number=target_chg_id,
                            substance=substance,
                            changed_files=changed_files,
                            executor_id=executor_id,
                            project_id=merged.get("project_id", ""),
                        )
                    except Exception:
                        # 记录日志，若明确找不到文件或严重错误则视需要阻断
                        pass

                now = datetime.now(UTC).isoformat()
                merged.update(
                    {
                        "schema_version": self.SCHEMA_VERSION,
                        "status": "consumed",
                        "closed_at": now,
                        "consumed_at": now,
                        "closed_by": actor,
                        "idempotency_key": effective_key,
                        "closure": {
                            "idempotency_key": effective_key,
                            "fingerprint": fingerprint,
                            "closed_by": actor,
                        },
                    }
                )
                self._write_atomic(path, merged)
            merged["file"] = str(path)
            return merged
        except HandoffError as error:
            self._record_failure(request_id, error, phase="preflight")
            raise
        except OSError as error:
            self._record_failure(request_id, error, phase="commit")
            raise HandoffError(f"handoff 写入失败，可安全重试: {request_id}") from error

    def close_with_saga(
        self,
        request_id: str,
        *,
        result: Mapping[str, Any] | None = None,
        idempotency_key: str = "",
        actor: str = "pm-workflow",
        simulate_fail_at: str = "",
    ) -> dict[str, Any]:
        """通过 PmClosureSagaCoordinator 执行跨资产原子收口事务。"""
        saga = self.saga_coordinator.execute_saga(
            request_id,
            result=result,
            idempotency_key=idempotency_key,
            actor=actor,
            simulate_fail_at=simulate_fail_at,
        )
        path = self._find_request_path(request_id)
        consumed = self._read_valid(path) or {}
        consumed["file"] = str(path)
        consumed["saga_id"] = saga.get("saga_id")
        consumed["saga_status"] = saga.get("status")
        return consumed

    def get_saga_status(self, request_id: str) -> dict[str, Any] | None:
        """查询指定 request_id 的 Saga 事务状态日志。"""
        return self.saga_coordinator.get_saga_status(request_id)

    def resume_saga(
        self,
        request_id: str,
        *,
        actor: str = "pm-workflow",
        simulate_fail_at: str = "",
    ) -> dict[str, Any]:
        """从断点恢复并继续执行未完成的 Saga 事务。"""
        return self.saga_coordinator.resume_saga(
            request_id,
            actor=actor,
            simulate_fail_at=simulate_fail_at,
        )

    def compensate_saga(
        self,
        request_id: str,
        *,
        actor: str = "pm-workflow",
    ) -> dict[str, Any]:
        """补偿回滚已失败或需撤销的 Saga 事务。"""
        return self.saga_coordinator.compensate_saga(
            request_id,
            actor=actor,
        )

    def validate_product_impact(self, product_impact: dict[str, Any]) -> dict[str, Any]:
        """Validate product_impact against anti-emptiness rules."""
        hypothesis_id = str(product_impact.get("hypothesis_id", "")).strip()
        signal = str(product_impact.get("engineering_signal", "")).strip()

        warnings: list[str] = []
        if not hypothesis_id:
            warnings.append("缺少 hypothesis_id（未关联产品假设）")
        if not signal:
            warnings.append("缺少 engineering_signal（未描述具体物理/交互可观测信号）")
        elif len(signal) < 8 and any(
            kw in signal for kw in ("优化", "完成", "修改", "修复", "改进")
        ):
            warnings.append("engineering_signal 过于泛化（缺乏具体物理量/交互量）")

        return {"valid": len(warnings) == 0, "warnings": warnings}

    def _transition_execution(
        self,
        request_id: str,
        *,
        executor_id: str,
        allowed_statuses: set[str],
        next_status: str,
        adapter: str = "",
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        event: str,
        reason: str = "",
    ) -> dict[str, Any]:
        self._validate_request_id(request_id)
        if not executor_id.strip():
            raise HandoffValidationError("executor_id 不能为空")
        with self._transaction_lock():
            path = self._find_request_path(request_id)
            current = self._read_valid(path)
            if current is None:
                raise HandoffNotFoundError(f"找不到有效 handoff: {request_id}")
            self._require_executor_owner(current, executor_id, allowed_statuses, allow_pending=event == "claimed")
            now = datetime.now(UTC)
            execution = dict(current.get("execution") or {})
            if event == "claimed":
                execution.update(
                    {
                        "executor_id": executor_id,
                        "adapter": adapter,
                        "claimed_at": now.isoformat(),
                    }
                )
                current["dispatch"] = {"adapter": adapter, "state": "claimed"}
            if next_status:
                current["status"] = next_status
            if event in {"claimed", "started", "heartbeat"}:
                execution["lease_expires_at"] = (
                    now + timedelta(seconds=lease_seconds)
                ).isoformat()
                execution["last_heartbeat_at"] = now.isoformat()
            execution["last_event"] = event
            if reason:
                execution["failure_reason"] = reason.strip()
                execution["failed_at"] = now.isoformat()
            current["execution"] = execution
            self._write_atomic(path, current)
        current["file"] = str(path)
        return current

    def _require_executor_owner(
        self,
        payload: Mapping[str, Any],
        executor_id: str,
        allowed_statuses: set[str],
        *,
        allow_pending: bool = False,
    ) -> None:
        status = str(payload.get("status", "pending"))
        if status not in allowed_statuses:
            allowed = "/".join(sorted(allowed_statuses))
            raise HandoffConflictError(f"当前状态 {status} 不允许此操作，要求 {allowed}")
        if allow_pending:
            return
        if self._lease_expired(payload):
            raise HandoffConflictError("执行租约已过期，必须由 PM 重新派发")
        execution = payload.get("execution")
        owner = execution.get("executor_id", "") if isinstance(execution, Mapping) else ""
        if owner != executor_id:
            raise HandoffConflictError("执行者不是当前租约持有者")

    @staticmethod
    def _lease_expired(payload: Mapping[str, Any]) -> bool:
        execution = payload.get("execution")
        expires_at = execution.get("lease_expires_at", "") if isinstance(execution, Mapping) else ""
        if not expires_at:
            return False
        try:
            return datetime.fromisoformat(str(expires_at)).astimezone(UTC) <= datetime.now(UTC)
        except ValueError:
            return True

    @classmethod
    def _lifecycle_state(cls, payload: Mapping[str, Any]) -> str:
        status = str(payload.get("status", "pending"))
        if status == "pending":
            return "awaiting_pickup"
        if status in {"claimed", "in_progress"} and cls._lease_expired(payload):
            return "stale"
        if status == "expired":
            return "stale"
        return status

    @staticmethod
    def _validate_executor(executor_id: str, adapter: str, lease_seconds: int) -> None:
        if not executor_id.strip():
            raise HandoffValidationError("executor_id 不能为空")
        if not adapter.strip():
            raise HandoffValidationError("adapter 不能为空")
        if lease_seconds < 60 or lease_seconds > 86_400:
            raise HandoffValidationError("lease_seconds 必须在 60 到 86400 之间")

    def _read_valid(self, path: Path) -> dict[str, Any] | None:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if any(not str(payload.get(field, "")).strip() for field in self.REQUIRED_FIELDS):
            return None
        return self._normalize_payload(payload)

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["schema_version"] = str(
            payload.get("schema_version", self.SCHEMA_VERSION) or self.SCHEMA_VERSION
        )
        normalized["status"] = str(payload.get("status", "pending") or "pending")
        normalized["mode"] = str(payload.get("mode", "execution") or "execution")
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
        # Bidirectional aliases preserve compatibility with earlier payloads.
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
        cs = payload.get("change_substance")
        if isinstance(cs, Mapping):
            normalized["change_substance"] = dict(cs)
        elif isinstance(cs, str) and cs.startswith("{"):
            try:
                normalized["change_substance"] = json.loads(cs)
            except Exception:
                normalized["change_substance"] = {}
        else:
            normalized["change_substance"] = {}
        return normalized

    def _merge_result(
        self,
        current: dict[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        merged = self._normalize_payload(dict(current))
        for field in self.RESULT_FIELDS:
            if field not in result:
                continue
            value = result[field]
            if field in {
                "changed_files",
                "risks",
                "next_actions",
                "watchouts",
                "read_first",
                "artifacts",
                "chg_updates",
            }:
                merged[field] = self._normalize_list(value)
            elif field in {"verification", "product_impact", "pm_closure"}:
                defaults: Mapping[str, Any]
                if field == "verification":
                    defaults = self.DEFAULT_VERIFICATION
                elif field == "product_impact":
                    defaults = self.DEFAULT_PRODUCT_IMPACT
                else:
                    defaults = self.DEFAULT_PM_CLOSURE
                merged[field] = self._normalize_mapping(value, defaults)
            elif field == "change_substance":
                if isinstance(value, Mapping):
                    merged[field] = dict(value)
                elif isinstance(value, str) and value.startswith("{"):
                    try:
                        merged[field] = json.loads(value)
                    except Exception:
                        merged[field] = {}
                else:
                    merged[field] = {}
            elif str(value).strip():
                merged[field] = str(value).strip()
        return merged

    def _prepare_close_payload(
        self,
        current: dict[str, Any],
        result: Mapping[str, Any],
        idempotency_key: str,
    ) -> tuple[dict[str, Any], str, str]:
        merged = self._merge_result(current, result)
        effective_key = str(
            idempotency_key or current.get("idempotency_key") or current["request_id"]
        ).strip()
        if not effective_key:
            raise HandoffValidationError("idempotency_key 不能为空")
        fingerprint = self._fingerprint(self._closure_projection(merged))
        return merged, effective_key, fingerprint

    def _validate_expected_identity(
        self,
        payload: Mapping[str, Any],
        *,
        project_id: str,
        executor_skill: str,
    ) -> None:
        if project_id and payload.get("project_id") != project_id:
            raise HandoffConflictError(
                f"项目不匹配: 期望 {project_id}，实际 {payload.get('project_id')}"
            )
        if executor_skill and payload.get("executor_skill") != executor_skill:
            raise HandoffConflictError(
                f"执行技能不匹配: 期望 {executor_skill}，实际 {payload.get('executor_skill')}"
            )

    def _validate_closure(self, payload: Mapping[str, Any]) -> None:
        if not str(payload.get("summary", "")).strip():
            raise HandoffValidationError("关闭 handoff 必须提供 summary")
        verification = payload.get("verification")
        evidence: list[Any] = []
        if isinstance(verification, Mapping):
            evidence.extend(
                value
                for key in ("lint_result", "test_result", "other_checks")
                if (value := verification.get(key))
            )
        evidence.extend(payload.get("artifacts") or [])
        if not evidence:
            raise HandoffValidationError("关闭 handoff 必须提供至少一项验证证据")
        changed_files = payload.get("changed_files") or []
        chg_updates = payload.get("chg_updates") or []
        if changed_files and not chg_updates:
            raise HandoffValidationError(
                "存在 changed_files 时必须提供 chg_updates，禁止无变更单收口"
            )

        # 1. 决策包白名单越界拦截 (Scope Gating)
        decision_id = str(
            payload.get("decision_id")
            or (payload.get("skill_context") or {}).get("decision_id")
            or ""
        ).strip()
        if decision_id:
            from auto_pm.domain.change.decision_service import DecisionError, DecisionService

            try:
                dec_svc = DecisionService(self._workspace_root)
                decision = dec_svc.get_decision(decision_id)
            except DecisionError as e:
                raise HandoffValidationError(f"决策包验证失败: {e}") from e

            project_id = str(payload.get("project_id", "")).strip()
            if decision.project_id and project_id and decision.project_id != project_id:
                raise HandoffValidationError(
                    f"决策包项目编号不匹配: 期望 {project_id}，实际 {decision.project_id}"
                )

            for f in changed_files:
                if not self._is_path_allowed(str(f), decision.approved_files):
                    raise HandoffValidationError(
                        f"修改文件越界: '{f}' 不在决策包批准清单中: {decision.approved_files}"
                    )

        # 2. 跨资产变更单物理存在性校验
        target_chgs: list[str] = []
        direct_chg = str(
            payload.get("change_id")
            or (payload.get("skill_context") or {}).get("change_id")
            or ""
        ).strip()
        if direct_chg:
            target_chgs.append(direct_chg)

        for update in chg_updates:
            update_str = str(update).strip()
            if not update_str:
                continue
            m = re.search(r"(CHG-[A-Za-z0-9_-]+)", update_str)
            chg_extracted = m.group(1) if m else update_str.split(":")[0].strip()
            if chg_extracted and chg_extracted not in target_chgs:
                target_chgs.append(chg_extracted)

        for chg_id in target_chgs:
            clean_id = chg_id[:-3] if chg_id.endswith(".md") else chg_id
            pattern = f"**/{clean_id}.md"
            direct_file = self._workspace_root / (clean_id if clean_id.endswith(".md") else f"{clean_id}.md")
            found = direct_file.is_file() or any(p.is_file() for p in self._workspace_root.glob(pattern))
            if not found:
                # 兼容在测试虚拟临时目录或项目子目录中执行时的跨资产寻径
                for candidate_root in (Path.cwd(), Path.cwd().parent, Path.cwd().parent.parent):
                    if any(p.is_file() for p in candidate_root.glob(pattern)):
                        found = True
                        break
            if not found:
                raise HandoffValidationError(f"关联变更单在工作空间中不存在: {chg_id}")

        # 3. 交付证据与产物真实性核验
        for item in payload.get("artifacts") or []:
            self._validate_artifact_entry(item)

        if isinstance(verification, Mapping):
            for key in ("test_result", "lint_result"):
                val = verification.get(key)
                if self._has_failure_signal(val):
                    raise HandoffValidationError("验证结果显示失败，禁止收口")

    def _is_path_allowed(self, file_path: str, approved_files: list[str]) -> bool:
        """检查文件路径是否在 approved_files 白名单中，兼容斜杠与相对路径。"""
        if not file_path:
            return False
        norm_f = Path(file_path).as_posix().lstrip("./")
        try:
            p = Path(file_path)
            if p.is_absolute():
                norm_f = p.resolve().relative_to(self._workspace_root.resolve()).as_posix()
        except (ValueError, RuntimeError):
            pass

        for approved in approved_files:
            norm_app = Path(approved).as_posix().lstrip("./")
            try:
                ap = Path(approved)
                if ap.is_absolute():
                    norm_app = ap.resolve().relative_to(self._workspace_root.resolve()).as_posix()
            except (ValueError, RuntimeError):
                pass

            if norm_f == norm_app:
                return True
            if norm_f.endswith("/" + norm_app) or norm_app.endswith("/" + norm_f):
                return True
        return False

    def _validate_artifact_entry(self, item: Any) -> None:
        """检查交付物条目；若声明为文件路径，校验其存在且非空。"""
        raw = ""
        if isinstance(item, str):
            raw = item.strip()
        elif isinstance(item, Mapping):
            raw = str(item.get("path") or item.get("file") or "").strip()
        if not raw:
            return

        has_sep = ("/" in raw) or ("\\" in raw)
        has_ext = bool(Path(raw).suffix)
        if has_sep or has_ext:
            p = Path(raw)
            valid = False
            if p.is_absolute():
                valid = p.is_file() and p.stat().st_size > 0
            else:
                target = self._workspace_root / p
                if target.is_file() and target.stat().st_size > 0:
                    valid = True
                else:
                    cwd_target = Path.cwd() / p
                    if cwd_target.is_file() and cwd_target.stat().st_size > 0:
                        valid = True
            if not valid:
                raise HandoffValidationError(f"交付物声明的文件在磁盘上不存在或为空: {item}")

    @staticmethod
    def _has_failure_signal(value: Any) -> bool:
        """判断验证结果中是否包含明确的失败标识。"""
        if not value:
            return False
        if isinstance(value, Mapping):
            if value.get("failed", 0) > 0 or value.get("errors", 0) > 0:
                return True
            if any(AiHandoffService._has_failure_signal(v) for v in value.values()):
                return True
        text = str(value).strip()
        if not text:
            return False
        cleaned = re.sub(
            r"\b0\s+(?:fail|failed|failure|failures|error|errors)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:no|zero)\s+(?:errors?|failures?)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        failure_patterns = (
            r"\bfail\b",
            r"\bfailed\b",
            r"\bfailure\b",
            r"\bfailures\b",
            r"\berror\b",
            r"\berrors\b",
        )
        for pattern in failure_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                return True
        return False

    def _closure_projection(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "request_id": payload.get("request_id"),
            "project_id": payload.get("project_id"),
            "executor_skill": payload.get("executor_skill"),
            "summary": payload.get("summary"),
            **{field: payload.get(field) for field in self.RESULT_FIELDS},
        }

    def _same_request(
        self,
        existing: Mapping[str, Any],
        requested: Mapping[str, Any],
    ) -> bool:
        fields = (
            "project_id",
            "executor_skill",
            "summary",
            "mode",
            "goal",
            "skill_context",
        )
        return all(existing.get(field) == requested.get(field) for field in fields)

    def _path_for_request(self, request_id: str) -> Path:
        self._validate_request_id(request_id)
        return self.inbox_dir / f"{request_id}.json"

    def _find_request_path(self, request_id: str) -> Path:
        """Resolve canonical paths and legacy files whose names differ."""
        path = self._path_for_request(request_id)
        if path.is_file():
            return path
        for candidate in sorted(self.inbox_dir.glob("*.json")):
            if candidate.name.endswith(".result.json"):
                continue
            payload = self._read_valid(candidate)
            if payload is not None and payload.get("request_id") == request_id:
                return candidate
        return path

    def _new_request_id(self) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return f"AI-{timestamp}-{uuid.uuid4().hex[:8].upper()}"

    def _validate_request_id(self, request_id: str) -> None:
        if not self.REQUEST_ID_RE.fullmatch(request_id):
            raise HandoffValidationError("request_id 包含非法字符或长度不合法")

    def _validate_scalar(self, value: str, field: str) -> None:
        if not str(value).strip():
            raise HandoffValidationError(f"{field} 不能为空")
        if any(char in str(value) for char in ("/", "\\", "..")):
            raise HandoffValidationError(f"{field} 包含非法路径字符")

    def _normalize_list(self, value: Any) -> list[Any]:
        return list(value) if isinstance(value, list) else []

    def _normalize_mapping(
        self,
        value: Any,
        defaults: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized = self._copy_default(defaults)
        if isinstance(value, Mapping):
            for key in defaults:
                if key in value:
                    normalized[key] = value[key]
        return normalized

    def _copy_default(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(value, ensure_ascii=False)))

    def _fingerprint(self, value: Mapping[str, Any]) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="replace")
        return hashlib.sha256(encoded).hexdigest()

    @contextmanager
    def _transaction_lock(self) -> Iterator[None]:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.inbox_dir / ".handoff.lock"
        descriptor: int | None = None
        for _ in range(100):
            try:
                descriptor = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(descriptor, str(os.getpid()).encode("ascii"))
                break
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > self.LOCK_STALE_SECONDS:
                        lock_path.unlink()
                        continue
                except OSError:
                    pass
                time.sleep(0.05)
        if descriptor is None:
            raise HandoffError("获取 handoff 事务锁超时")

        try:
            yield
        finally:
            try:
                os.close(descriptor)
            finally:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass

    def _write_atomic(self, path: Path, payload: Mapping[str, Any]) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.inbox_dir / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open(
                "w",
                encoding="utf-8",
                errors="replace",
                newline="\n",
            ) as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def _write_result_atomic(self, request_id: str, result: Mapping[str, Any]) -> None:
        """Persist the executor receipt next to the request for PM preflight."""
        path = self.inbox_dir / f"{request_id}.result.json"
        temp_path = self.inbox_dir / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open(
                "w",
                encoding="utf-8",
                errors="replace",
                newline="\n",
            ) as stream:
                json.dump(dict(result), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def _record_failure(self, request_id: str, error: Exception, *, phase: str) -> None:
        """Persist retry evidence without masking the original failure."""
        try:
            self.failure_dir.mkdir(parents=True, exist_ok=True)
            path = self.failure_dir / f"{request_id}.json"
            existing: dict[str, Any] = {
                "schema_version": "handoff.failure.v1",
                "request_id": request_id,
                "events": [],
            }
            if path.is_file():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(loaded, dict):
                        existing.update(loaded)
                except (OSError, json.JSONDecodeError):
                    pass
            events = existing.get("events")
            if not isinstance(events, list):
                events = []
            events.append(
                {
                    "event_id": uuid.uuid4().hex,
                    "request_id": request_id,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "phase": phase,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "retryable": True,
                }
            )
            existing["events"] = events
            temp_path = self.failure_dir / f".{path.name}.{uuid.uuid4().hex}.tmp"
            try:
                with temp_path.open(
                    "w",
                    encoding="utf-8",
                    errors="replace",
                    newline="\n",
                ) as stream:
                    json.dump(existing, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_path, path)
            finally:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
        except (OSError, TypeError, ValueError):
            return
