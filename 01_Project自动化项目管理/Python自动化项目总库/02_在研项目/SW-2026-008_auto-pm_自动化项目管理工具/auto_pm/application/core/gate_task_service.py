"""Identity and lifecycle for the shared full regression gate."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from auto_pm.application.core.gate_run_service import GateRunError, manifest_sha256, project_dir_in
from auto_pm.infrastructure.gate_task_store import GateAttempt, GateTaskStore

SHA = re.compile(r"[0-9a-f]{40}")
# Increment when execution or receipt semantics change independently of the group manifest.
POLICY = "gate-full-v1"
TERMINAL = {"failed", "stopped", "unavailable", "passed"}


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(path), *args],
        capture_output=True, encoding="utf-8", errors="replace",  # lenient-decode: Git diagnostics may use the host code page
        timeout=30, check=False,
    )
    if result.returncode:
        raise GateRunError(f"Git 无法核对候选：{result.stderr.strip()}")
    return result.stdout.strip()


@dataclass(frozen=True)
class GateCandidate:
    commit: str
    tree: str
    base: str
    manifest: str
    policy: str

    @classmethod
    def from_worktree(cls, root: Path, worktree: Path) -> GateCandidate:
        if Path(git(worktree, "rev-parse", "--show-toplevel")).resolve() != worktree:
            raise GateRunError("请指定工位的 Git 根目录")
        if Path(git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve() != (
            Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        ):
            raise GateRunError("工位与控制根不属于同一本 Git 仓库")
        if git(worktree, "status", "--porcelain", "--untracked-files=all"):
            raise GateRunError("候选工位有未提交内容")
        project_dir_in(worktree)
        commit = git(worktree, "rev-parse", "HEAD")
        base = git(root, "rev-parse", "refs/heads/main")
        if commit == base or git(root, "merge-base", base, commit) != base:
            raise GateRunError("候选必须基于当前 main，且包含待合并提交")
        tree = git(worktree, "rev-parse", f"{commit}^{{tree}}")
        return cls(commit, tree, base, manifest_sha256(), POLICY)

    @property
    def key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Observation:
    state: str
    handle: str = ""
    detail: str = ""


class Executor(Protocol):
    def launch(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation: ...
    def inspect(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation: ...
    def stop(self, attempt: GateAttempt) -> None: ...


class GateTaskService:
    def __init__(self, store: GateTaskStore, cloud: Executor, local: Executor) -> None:
        self.store = store
        self.executors = {"github": cloud, "local": local}

    def start(self, candidate: GateCandidate) -> GateAttempt:
        attempt, new = self.store.reserve(candidate.key, "github")
        return self._launch(attempt, candidate) if new else self.status(attempt.id)

    def status(self, attempt_id: str) -> GateAttempt:
        attempt = self._get(attempt_id)
        if attempt.state in TERMINAL:
            return attempt
        candidate = GateCandidate(**json.loads(attempt.key))
        result = self.executors[attempt.backend].inspect(attempt, candidate)
        return self.store.observe(attempt, result.state, result.handle, result.detail)

    def current(self, candidate: GateCandidate) -> GateAttempt | None:
        attempt = self.store.latest(candidate.key)
        if attempt is None:
            return None
        attempt = self.status(attempt.id)
        if attempt.backend == "local" and attempt.state == "passed":
            result = self.executors["local"].inspect(attempt, candidate)
            if result.state != "passed" or result.detail != attempt.detail:
                raise GateRunError("本机门禁的原始日志或摘要无法按原凭证复核")
        return attempt

    def stop(self, attempt_id: str) -> GateAttempt:
        attempt = self.status(attempt_id)
        if attempt.state in TERMINAL:
            return attempt
        if not attempt.handle:
            raise GateRunError("尚无法确认执行端已接单，不能请求停止。请先查状态")
        self.executors[attempt.backend].stop(attempt)
        return self.status(attempt.id)

    def retry(
        self, attempt_id: str, candidate: GateCandidate, *, local: bool = False, approval: str = ""
    ) -> GateAttempt:
        previous = self.status(attempt_id)
        if candidate.key != previous.key:
            raise GateRunError("候选、main 或门禁规则已变更。请用 gate start 登记新任务")
        if previous.state not in {"failed", "stopped", "unavailable"}:
            raise GateRunError(f"当前状态 {previous.state} 无法重试")
        if local and (
            (previous.state not in {"stopped", "unavailable"}
             and not (previous.backend == "local" and previous.state == "failed"))
            or not re.fullmatch(r"user-confirmation:[^\s]+", approval)
        ):
            raise GateRunError("本机切换需要已确认停止或不可用的执行端，以及用户确认引用")
        attempt, new = self.store.reserve(
            candidate.key, "local" if local else "github", previous_id=previous.id, approval=approval
        )
        return self._launch(attempt, candidate) if new else self.status(attempt.id)

    def _get(self, attempt_id: str) -> GateAttempt:
        attempt = self.store.get(attempt_id)
        if attempt is None:
            raise GateRunError(f"找不到门禁任务 {attempt_id}")
        return attempt

    def _launch(self, attempt: GateAttempt, candidate: GateCandidate) -> GateAttempt:
        result = self.executors[attempt.backend].launch(attempt, candidate)
        # Concurrent status checks may already have learned the execution handle.
        current = self._get(attempt.id)
        if current.state != "unknown" or current.handle:
            return current
        return self.store.observe(current, result.state, result.handle, result.detail)
