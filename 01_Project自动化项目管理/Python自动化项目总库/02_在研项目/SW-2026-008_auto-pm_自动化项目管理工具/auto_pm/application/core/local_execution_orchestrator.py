"""Run one blocking local execution Saga from durable claim through projection."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from auto_pm.core.execution_adapter_service import ExecutionDispatchResult
from auto_pm.core.execution_supervisor_service import (
    ExecutionCollectionPendingError,
    ExecutionSupervisorError,
    ExecutionSupervisorService,
    LeaseCapability,
)
from auto_pm.core.microtask_projection_service import (
    MicrotaskProjectionError,
    MicrotaskProjectionIndeterminateError,
    MicrotaskProjectionService,
)

from auto_pm.contracts.continuity import LeaseItem, RunState
from auto_pm.contracts.execution_adapter import (
    ExecutionMicrotaskMaterialization,
    ExecutionMicrotaskPlan,
    ExecutionStartEvidence,
    ForegroundExecutionReceipt,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    clean_git_environment,
    is_link_like,
)
from auto_pm.infrastructure.local_executor import (
    LocalCodexExecutor,
    LocalExecutionRequest,
    LocalExecutionResult,
    LocalExecutionStatus,
    LocalHandshakeStatus,
)


class LocalExecutionOrchestratorError(RuntimeError):
    """Raised when the foreground Saga cannot preserve exactly-once boundaries."""


class LocalExecutionOrchestrator:
    """Retain the sole process handle until collection and governed finalization."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        store: ContinuityStore | None = None,
        executor: LocalCodexExecutor | None = None,
        supervisor: ExecutionSupervisorService | None = None,
        projection: MicrotaskProjectionService | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._store = store or ContinuityStore(self._root)
        self._executor = executor or LocalCodexExecutor()
        self._supervisor = supervisor or ExecutionSupervisorService(self._root)
        self._projection = projection or MicrotaskProjectionService(
            self._root, store=self._store
        )

    def execute(
        self,
        *,
        dispatch: ExecutionDispatchResult,
        microtask: ExecutionMicrotaskMaterialization,
        lease_token_environment: str,
        lease_seconds: int = 86_400,
        renew_before_seconds: int = 3_600,
        renewal_interval_seconds: float = 30.0,
        handshake_timeout_seconds: float = 60.0,
    ) -> ForegroundExecutionReceipt:
        """Block until projection-gated VERIFYING or truthful FAILED/PENDING."""

        plan = microtask.plan
        intent = dispatch.intent
        if (
            plan.operation_id != intent.operation_id
            or plan.run_id != intent.receipt.run_id
            or plan.approved_model != intent.receipt.executor_id
            or plan.repository_path != str(Path(plan.repository_path).resolve())
        ):
            raise LocalExecutionOrchestratorError("dispatch 与 MicrotaskPlan 身份不一致")
        try:
            existing_claim = self._store.get_execution_start_claim(plan.operation_id)
        except ContinuityStoreError as error:
            raise LocalExecutionOrchestratorError(str(error)) from error
        if existing_claim is not None:
            if (
                existing_claim.run_id != plan.run_id
                or existing_claim.plan_request_sha256 != plan.request_sha256
                or existing_claim.marker_sha256 != plan.marker_sha256
                or existing_claim.microtask_commit != microtask.commit
            ):
                raise LocalExecutionOrchestratorError("existing start claim 与请求不一致")
            return self._replay_receipt(
                plan.operation_id, existing_claim.claim_sha256
            )
        self._assert_materialization(microtask)
        request = LocalExecutionRequest(
            repository=plan.repository_path,
            allowed_paths=plan.declared_dirty_paths,
            model=plan.approved_model,
            prompt=plan.objective,
            sensitive_values=(dispatch.lease.token,),
            excluded_environment_keys=(lease_token_environment,),
        )
        try:
            self._executor.validate(request)
            run = self._store.get_run(plan.run_id)
            lease = self._store.get_lease(plan.run_id)
            claim, created = self._store.claim_execution_start(
                operation_id=plan.operation_id,
                run_id=plan.run_id,
                expected_run_version=run.version,
                owner_id=dispatch.receipt.owner_id,
                lease_token=dispatch.lease.token,
                plan_request_sha256=plan.request_sha256,
                marker_sha256=plan.marker_sha256,
                repository_path=plan.repository_path,
                microtask_commit=microtask.commit,
            )
        except (ContinuityStoreError, ValueError) as error:
            raise LocalExecutionOrchestratorError(str(error)) from error
        if not created:
            return self._replay_receipt(plan.operation_id, claim.claim_sha256)
        capability = self._capability(lease, dispatch.lease.token)
        started = self._executor.start(request)
        if isinstance(started, LocalExecutionResult):
            self._supervisor.fail_claimed_ready(
                capability, idempotency_key=f"{plan.operation_id}:local-start"
            )
            return self._receipt(
                plan.operation_id,
                plan.run_id,
                "FAILED",
                claim.claim_sha256,
                started,
                None,
            )
        handle = started
        handshake = self._executor.handshake(
            handle, timeout_seconds=handshake_timeout_seconds
        )
        if handshake.status is not LocalHandshakeStatus.STARTED or handshake.evidence is None:
            result = self._executor.wait(
                handle,
                force_status=(
                    LocalExecutionStatus.TIMED_OUT
                    if handshake.status is LocalHandshakeStatus.TIMED_OUT
                    else LocalExecutionStatus.FAILED
                ),
                error=handshake.error,
            )
            self._supervisor.fail_claimed_ready(
                capability, idempotency_key=f"{plan.operation_id}:handshake"
            )
            return self._receipt(
                plan.operation_id,
                plan.run_id,
                "FAILED",
                claim.claim_sha256,
                result,
                None,
            )
        evidence = handshake.evidence
        try:
            self._supervisor.record_started(
                run_id=plan.run_id,
                owner_id=dispatch.receipt.owner_id,
                lease_token=dispatch.lease.token,
                evidence=evidence,
                idempotency_key=f"{plan.operation_id}:run-started",
                reap_current=lambda: self._executor.reap(handle),
            )
            collected = self._supervisor.collect_completion(
                capability,
                wait_and_collect=lambda: self._executor.wait(
                    handle, evidence=evidence
                ),
                reap_current=lambda: self._executor.reap(handle),
                lease_seconds=lease_seconds,
                renew_before_seconds=renew_before_seconds,
                renewal_interval_seconds=renewal_interval_seconds,
                idempotency_key=f"{plan.operation_id}:collect",
            )
        except ExecutionCollectionPendingError:
            return ForegroundExecutionReceipt(
                operation_id=plan.operation_id,
                run_id=plan.run_id,
                status="PENDING",
                claim_sha256=claim.claim_sha256,
            )
        except ExecutionSupervisorError as error:
            raise LocalExecutionOrchestratorError(str(error)) from error
        projection_receipt = None
        if collected.disposition == "ZERO_EXIT":
            try:
                projection_receipt = self._projection.project(
                    plan.operation_id,
                    expected_source_commit=microtask.commit,
                )
            except MicrotaskProjectionIndeterminateError:
                return ForegroundExecutionReceipt(
                    operation_id=plan.operation_id,
                    run_id=plan.run_id,
                    status="PENDING",
                    claim_sha256=claim.claim_sha256,
                )
            except MicrotaskProjectionError:
                projection_receipt = None
        try:
            completed = self._supervisor.finalize_collected(
                collected,
                projection_receipt=projection_receipt,
                idempotency_key=f"{plan.operation_id}:finalize",
            )
        except ExecutionSupervisorError as error:
            raise LocalExecutionOrchestratorError(str(error)) from error
        return self._receipt(
            plan.operation_id,
            plan.run_id,
            completed.run_state.value,
            claim.claim_sha256,
            completed.result,
            (
                projection_receipt.projection_sha256
                if projection_receipt is not None
                else None
            ),
        )

    def _replay_receipt(
        self, operation_id: str, claim_sha256: str
    ) -> ForegroundExecutionReceipt:
        try:
            plan = self._store.get_execution_microtask_plan(operation_id)
            projection = self._store.get_execution_projection(operation_id)
            if plan is None:
                raise LocalExecutionOrchestratorError("start claim replay 缺少 Plan")
            run = self._store.get_run(plan.run_id)
            if run.state is RunState.VERIFYING and projection is not None:
                _owner, evidence = self._store.get_run_started_evidence(plan.run_id)
                return ForegroundExecutionReceipt(
                    operation_id=operation_id,
                    run_id=plan.run_id,
                    status="VERIFYING",
                    claim_sha256=claim_sha256,
                    process_id=evidence.process_id,
                    session_id=evidence.session_id,
                    exit_code=0,
                    projection_sha256=projection.projection_sha256,
                )
            if run.state is RunState.FAILED:
                failed_evidence: ExecutionStartEvidence | None
                try:
                    _owner, failed_evidence = self._store.get_run_started_evidence(
                        plan.run_id
                    )
                except ContinuityStoreError:
                    failed_evidence = None
                return ForegroundExecutionReceipt(
                    operation_id=operation_id,
                    run_id=plan.run_id,
                    status="FAILED",
                    claim_sha256=claim_sha256,
                    process_id=failed_evidence.process_id if failed_evidence else None,
                    session_id=failed_evidence.session_id if failed_evidence else None,
                )
        except ContinuityStoreError as error:
            raise LocalExecutionOrchestratorError(str(error)) from error
        return ForegroundExecutionReceipt(
            operation_id=operation_id,
            run_id=plan.run_id,
            status="PENDING",
            claim_sha256=claim_sha256,
        )

    @staticmethod
    def _capability(lease: LeaseItem, token: str) -> LeaseCapability:
        try:
            run_id = lease.run_id
            owner_id = lease.owner_id
            version = lease.version
            expires_at = datetime.fromisoformat(lease.expires_at)
        except (AttributeError, ValueError) as error:
            raise LocalExecutionOrchestratorError("lease capability 无法恢复") from error
        if expires_at.tzinfo is None:
            raise LocalExecutionOrchestratorError("lease capability 时间无时区")
        return LeaseCapability(
            run_id=run_id,
            owner_id=owner_id,
            version=version,
            expires_at=expires_at,
            token=token,
        )

    def _assert_materialization(self, materialization: ExecutionMicrotaskMaterialization) -> None:
        plan = materialization.plan
        repository = Path(plan.repository_path)
        marker = repository / ".codex-microtask.json"
        try:
            linked = is_link_like(repository) or is_link_like(marker)
        except ControlRootGuardError as error:
            raise LocalExecutionOrchestratorError(
                "microtask repository/marker link fact 无法读取"
            ) from error
        if linked or not marker.is_file():
            raise LocalExecutionOrchestratorError("microtask repository/marker 无法证明")
        expected_marker = self._canonical(self._marker(plan))
        if (
            marker.read_bytes() != expected_marker + b"\n"
            or hashlib.sha256(expected_marker).hexdigest() != plan.marker_sha256
        ):
            raise LocalExecutionOrchestratorError("microtask marker hash/载荷漂移")
        if self._git(repository, "rev-parse", "HEAD") != materialization.commit:
            raise LocalExecutionOrchestratorError("microtask materialization commit 漂移")
        if self._git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
            raise LocalExecutionOrchestratorError("microtask repository start 前必须 clean")

    @staticmethod
    def _receipt(
        operation_id: str,
        run_id: str,
        status: str,
        claim_sha256: str,
        result: LocalExecutionResult,
        projection_sha256: str | None,
    ) -> ForegroundExecutionReceipt:
        return ForegroundExecutionReceipt(
            operation_id=operation_id,
            run_id=run_id,
            status=status,
            claim_sha256=claim_sha256,
            process_id=result.process_id,
            session_id=result.session_id,
            exit_code=result.exit_code,
            projection_sha256=projection_sha256,
        )

    @staticmethod
    def _marker(plan: ExecutionMicrotaskPlan) -> dict[str, object]:
        return {
            "schema_version": "codex-microtask.v1",
            "operation_id": plan.operation_id,
            "mission_id": plan.mission_id,
            "run_id": plan.run_id,
            "approved_model": plan.approved_model,
            "objective": plan.objective,
            "owned_paths": list(plan.owned_paths),
            "declared_dirty_paths": list(plan.declared_dirty_paths),
            "source_worktree_path": plan.source_worktree_path,
            "baseline_git_head": plan.baseline_git_head,
            "repository_path": plan.repository_path,
            "manifest": [item.model_dump(mode="json") for item in plan.manifest],
            "manifest_sha256": plan.manifest_sha256,
            "request_sha256": plan.request_sha256,
        }

    @staticmethod
    def _canonical(payload: object) -> bytes:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
            env=clean_git_environment(),
        )
        if result.returncode != 0:
            raise LocalExecutionOrchestratorError("Git 无法证明 microtask start 边界")
        return result.stdout.strip()


__all__ = ["LocalExecutionOrchestrator", "LocalExecutionOrchestratorError"]
