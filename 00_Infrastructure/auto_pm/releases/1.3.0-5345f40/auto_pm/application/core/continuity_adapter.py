"""Stateless adapter boundary for independent AI providers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from auto_pm.core.continuity_resume_service import ContinuityResumeService


class ContinuityAdapter:
    """Expose the same continuity facts to any named provider without owning state."""

    def __init__(self, workspace_root: str | Path, provider: str) -> None:
        if not provider.strip():
            raise ValueError("provider 不能为空")
        self.provider = provider
        self._resume = ContinuityResumeService(workspace_root)

    def resume(
        self,
        *,
        project_id: str = "",
        invocation_path: str | Path | None = None,
        work_id: str = "",
        run_id: str = "",
    ) -> dict[str, Any]:
        """Return canonical data; provider identity deliberately does not alter payload."""
        payload = self._resume.collect(
            project_id=project_id,
            invocation_path=invocation_path,
            work_id=work_id,
            run_id=run_id,
        )
        return cast(dict[str, Any], payload.model_dump(mode="json"))
