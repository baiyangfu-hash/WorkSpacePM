"""Stable-side isolation and external review for cockpit dogfooding."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class DogfoodIsolationError(RuntimeError):
    """Raised when a candidate is outside the allowed dogfood boundary."""


class DogfoodRunner:
    """Inspect a candidate from the stable control plane without executing it."""

    DEFAULT_SCOPE = (
        Path("00_Infrastructure") / "auto_pm",
        Path("main.py"),
        Path("setup_env.bat"),
    )
    DEFAULT_ALLOWED_PREFIXES = (
        "00_infrastructure/auto_pm/",
        "main.py",
        "setup_env.bat",
    )
    EXCLUDED_DIRS = frozenset(
        {
            ".auto-pm",
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            "build",
            "coverage",
            "dist",
            "htmlcov",
            "node_modules",
            ".venv",
        }
    )

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def inspect(
        self,
        candidate_path: str | Path,
        *,
        stable_path: str | Path | None = None,
        allowed_prefixes: tuple[str, ...] = DEFAULT_ALLOWED_PREFIXES,
    ) -> dict[str, Any]:
        """Collect comparable stable/candidate facts without changing either tree."""
        stable = self._resolve_existing(stable_path or self.workspace_root, "stable_path")
        candidate = self._resolve_existing(candidate_path, "candidate_path")
        self._validate_candidate_location(candidate)
        if stable == candidate:
            raise DogfoodIsolationError("stable_path 与 candidate_path 不能相同")

        stable_snapshot = self._snapshot(stable)
        candidate_snapshot = self._snapshot(candidate)
        changed_files = candidate_snapshot["changed_files"]
        violations = [
            path
            for path in changed_files
            if not self._is_allowed(path, allowed_prefixes)
        ]
        return {
            "schema_version": "dogfood.isolation.v1",
            "reviewer": "stable-control-plane",
            "stable": stable_snapshot,
            "candidate": candidate_snapshot,
            "candidate_changed_files": changed_files,
            "allowlist": list(allowed_prefixes),
            "allowlist_violations": violations,
            "isolated_paths": stable != candidate,
            "stable_clean": stable_snapshot["working_tree_clean"],
            "candidate_scope_safe": not violations,
        }

    def prepare_candidate(
        self,
        candidate_path: str | Path,
        *,
        stable_path: str | Path | None = None,
        base_ref: str = "HEAD",
        create_environment: bool = False,
    ) -> dict[str, Any]:
        """Create a detached candidate worktree only from a clean stable tree."""
        stable = self._resolve_existing(stable_path or self.workspace_root, "stable_path")
        candidate = Path(candidate_path).resolve()
        self._validate_candidate_location(candidate)
        if candidate.exists():
            if not candidate.is_dir():
                raise DogfoodIsolationError(f"候选路径不是目录: {candidate}")
            if any(candidate.iterdir()):
                raise DogfoodIsolationError(f"候选目录非空，拒绝覆盖: {candidate}")
        else:
            candidate.parent.mkdir(parents=True, exist_ok=True)

        _, _, changed_files = self._git_state(stable)
        if changed_files:
            raise DogfoodIsolationError(
                f"稳定控制面不是干净树，拒绝创建候选: {len(changed_files)} 个变更"
            )
        result = self._run_git(stable, "worktree", "add", "--detach", str(candidate), base_ref)
        if result.returncode != 0:
            raise DogfoodIsolationError(
                f"创建候选 worktree 失败: {result.stderr.strip() or result.stdout.strip()}"
            )

        environment = ""
        if create_environment:
            environment = self._create_environment(candidate)
        candidate_snapshot = self._snapshot(candidate)
        return {
            "schema_version": "dogfood.isolation.v1",
            "reviewer": "stable-control-plane",
            "stable_path": str(stable),
            "candidate_path": str(candidate),
            "base_ref": base_ref,
            "base_sha": candidate_snapshot["git_sha"],
            "candidate": candidate_snapshot,
            "environment": environment,
            "environment_ready": bool(environment),
        }

    def review(
        self,
        candidate_path: str | Path,
        *,
        stable_path: str | Path | None = None,
        baseline_stable_fingerprint: str = "",
        allowed_prefixes: tuple[str, ...] = DEFAULT_ALLOWED_PREFIXES,
        write_report: bool = True,
    ) -> dict[str, Any]:
        """Perform the stable-side review and optionally persist its evidence."""
        report = self.inspect(
            candidate_path,
            stable_path=stable_path,
            allowed_prefixes=allowed_prefixes,
        )
        stable = report["stable"]
        baseline_match = (
            not baseline_stable_fingerprint
            or stable["scope_fingerprint"] == baseline_stable_fingerprint
        )
        candidate_runtime_changes = [
            path
            for path in report["candidate_changed_files"]
            if self._is_runtime_path(path)
        ]
        checks = {
            "stable_clean": report["stable_clean"],
            "candidate_scope_safe": report["candidate_scope_safe"],
            "candidate_isolated": report["isolated_paths"],
            "stable_baseline_match": baseline_match,
            "no_runtime_changes": not candidate_runtime_changes,
        }
        report.update(
            {
                "checks": checks,
                "candidate_runtime_changes": candidate_runtime_changes,
                "passed": all(checks.values()),
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        if write_report:
            report["evidence_file"] = str(self.write_report(report))
        return report

    def write_report(self, report: dict[str, Any]) -> Path:
        """Write evidence to ignored runtime storage, never into a project ledger."""
        run_id = f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        report_dir = self.workspace_root / ".auto-pm" / "reports" / "dogfood" / run_id
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "isolation-review.json"
        temp_path = report_dir / f".{report_path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open(
                "w",
                encoding="utf-8",
                errors="replace",
                newline="\n",
            ) as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
            temp_path.replace(report_path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
        return report_path

    def _snapshot(self, root: Path) -> dict[str, Any]:
        git_root, git_sha, changed_files = self._git_state(root)
        return {
            "path": str(root),
            "git_root": str(git_root) if git_root else "",
            "git_sha": git_sha,
            "working_tree_clean": not changed_files,
            "changed_files": changed_files,
            "scope_fingerprint": self._scope_fingerprint(root),
        }

    def _git_state(self, path: Path) -> tuple[Path | None, str, list[str]]:
        git_root_result = self._run_git(path, "rev-parse", "--show-toplevel")
        if git_root_result.returncode != 0:
            return None, "", []
        git_root = Path(git_root_result.stdout.strip()).resolve()
        sha_result = self._run_git(path, "rev-parse", "HEAD")
        status_result = self._run_git(path, "status", "--porcelain", "--untracked-files=all")
        changed_files = []
        if status_result.returncode == 0:
            changed_files = [self._status_path(line) for line in status_result.stdout.splitlines() if line]
        return git_root, sha_result.stdout.strip() if sha_result.returncode == 0 else "", changed_files

    def _scope_fingerprint(self, root: Path) -> str:
        digest = hashlib.sha256()
        files: list[Path] = []
        for relative in self.DEFAULT_SCOPE:
            target = root / relative
            if target.is_file():
                files.append(target)
            elif target.is_dir():
                files.extend(path for path in target.rglob("*") if path.is_file())
        for path in sorted(files):
            if any(part in self.EXCLUDED_DIRS for part in path.relative_to(root).parts):
                continue
            relative_path = path.relative_to(root).as_posix()
            digest.update(relative_path.encode("utf-8", errors="replace"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def _resolve_existing(self, path: str | Path, field: str) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_dir():
            raise DogfoodIsolationError(f"{field} 不存在或不是目录: {resolved}")
        return resolved

    def _create_environment(self, candidate: Path) -> str:
        environment = candidate / ".venv"
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(environment)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise DogfoodIsolationError(
                f"创建候选独立环境失败: {result.stderr.strip() or result.stdout.strip()}"
            )
        return str(environment)

    def _validate_candidate_location(self, candidate: Path) -> None:
        worktree_root = (self.workspace_root / ".auto-pm" / "worktrees").resolve()
        try:
            candidate.relative_to(worktree_root)
        except ValueError as exc:
            raise DogfoodIsolationError(
                f"候选路径必须位于隔离目录 {worktree_root}: {candidate}"
            ) from exc

    def _is_allowed(self, path: str, prefixes: tuple[str, ...]) -> bool:
        normalized = path.replace("\\", "/").lower()
        return any(
            normalized == prefix.lower().rstrip("/")
            or normalized.startswith(prefix.lower())
            for prefix in prefixes
        )

    def _is_runtime_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/").lower()
        return (
            normalized.startswith(".auto-pm/")
            or normalized.endswith((".db", ".sqlite", ".sqlite3"))
            or "/__pycache__/" in normalized
            or normalized.endswith((".pyc", ".pyo"))
        )

    def _status_path(self, line: str) -> str:
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        return path.replace("\\", "/")

    def _run_git(self, path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
