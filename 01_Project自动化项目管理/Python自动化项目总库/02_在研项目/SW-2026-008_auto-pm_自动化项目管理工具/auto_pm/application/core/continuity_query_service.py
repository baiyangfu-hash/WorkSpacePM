"""Compile the versioned, capability-flagged query on top of Resume v2 (V05-A).

Read-only: resume, orient and the SDK all go through this producer, so the capability flags, the runtime identity and the refusal of unsupported actions
are produced in exactly one place. It never initialises a store, writes a file or starts a process.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from auto_pm.contracts import continuity_query as query_contract
from auto_pm.contracts.continuity_query import (
    CAPABILITY_CONTRACT_VERSION,
    QUERY_SCHEMA_VERSION,
    ActionCapability,
    ContinuityQuery,
    QueriedAction,
    RuntimeCapabilities,
)
from auto_pm.contracts.continuity_resume import ContinuityResume

from .continuity_resume_service import ContinuityResumeError, ContinuityResumeService


class ContinuityQueryError(RuntimeError):
    """Raised when the query cannot be compiled or asks for an unknown action."""


def _producer_sha256() -> str:
    """Hash the loaded producer bytes: this module and the contract it speaks."""

    digest = hashlib.sha256()
    for path in (Path(__file__).resolve(), Path(query_contract.__file__).resolve()):
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class ContinuityQueryService:
    """One producer of the shared query for every entry point."""

    def __init__(
        self,
        workspace_root: str | Path,
        now: Callable[[], datetime] | None = None,
        *,
        execution_root: str | Path | None = None,
    ) -> None:
        self._resume = ContinuityResumeService(workspace_root, now, execution_root=execution_root)

    def query(
        self,
        *,
        project_id: str = "",
        invocation_path: str | Path | None = None,
        work_id: str = "",
        run_id: str = "",
        requested_action: str = "",
    ) -> ContinuityResume:
        """Return Resume v2 with the query block attached; an asked action is answered UNSUPPORTED."""

        asked: ActionCapability | None = None
        if requested_action:
            try:
                asked = ActionCapability(action=QueriedAction(requested_action))
            except ValueError as error:
                known = ", ".join(action.value for action in QueriedAction)
                raise ContinuityQueryError(f"未知的查询动作 {requested_action!r}；已知动作: {known}") from error
        try:
            resume = self._resume.collect(
                project_id=project_id,
                invocation_path=invocation_path,
                work_id=work_id,
                run_id=run_id,
            )
        except ContinuityResumeError as error:
            raise ContinuityQueryError(str(error)) from error
        capabilities = RuntimeCapabilities(
            actions=tuple(ActionCapability(action=action) for action in QueriedAction)
        )
        context = resume.context
        producer_path = str(Path(__file__).resolve())
        producer_sha = _producer_sha256()
        seed = {
            "resume": resume.evidence_id,
            "schema": QUERY_SCHEMA_VERSION,
            "capability_contract": CAPABILITY_CONTRACT_VERSION,
            "capabilities": capabilities.model_dump(mode="json"),
            "requested_action": asked.model_dump(mode="json") if asked else None,
            "producer_sha256": producer_sha,
        }
        digest = hashlib.sha256(
            json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        block = ContinuityQuery(
            control_root=context.control_root,
            execution_root=context.execution_root,
            candidate_commit=context.candidate_commit,
            configured_release_id=context.configured_release_id,
            effective_release_id=context.effective_release_id,
            runtime_load_path=context.runtime_load_path,
            runtime_fallback_reason=context.runtime_fallback_reason,
            producer_load_path=producer_path,
            producer_sha256=producer_sha,
            capabilities=capabilities,
            requested_action=asked,
            evidence_id=f"QUERY-{digest[:16].upper()}",
        )
        return resume.model_copy(update={"query": block})
