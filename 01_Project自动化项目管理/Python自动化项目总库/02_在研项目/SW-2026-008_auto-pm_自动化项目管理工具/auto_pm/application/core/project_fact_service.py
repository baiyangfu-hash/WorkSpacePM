"""Read-only collection and validation of PM project fact packages."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from auto_pm.core.project_service import ProjectService
from pydantic import ValidationError

from auto_pm.contracts.project_fact_snapshot import (
    AvailableCheckFact,
    CodeStructureFact,
    FactValidationResult,
    FileFingerprint,
    GitFact,
    OpenChangeFact,
    ProjectFactSnapshot,
    SpecSnapshotFact,
    SpecVersionDrift,
)

log = logging.getLogger(__name__)

_RUNTIME_ROOT_RE: Final[re.Pattern[str]] = re.compile(
    r"^-\s*runtime_root:\s*`?([^`\r\n]+)`?\s*$", re.MULTILINE
)
_CHANGE_STATUS_RE: Final[re.Pattern[str]] = re.compile(
    r"\|\s*变更状态\s*\|\s*([^|]+)\|", re.IGNORECASE
)
_SPEC_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^##\s+Spec\s+Snapshot", re.IGNORECASE)
_TERMINAL_CHANGE_STATUSES: Final[frozenset[str]] = frozenset(
    {"completed", "closed", "archived"}
)
_EXCLUDED_STRUCTURE_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "build", "coverage", "dist", "venv"}
)
_CLEAN_ARCHITECTURE_LAYERS: Final[tuple[str, ...]] = (
    "contracts",
    "domain",
    "infrastructure",
    "application",
    "ui",
)


class ProjectFactError(RuntimeError):
    """Raised when a fact package cannot be collected or decoded safely."""


class ProjectFactService:
    """Collect and verify decision evidence without mutating workspace assets."""

    DEFAULT_TTL_SECONDS: Final[int] = 900

    def __init__(self, workspace_root: str, project_service: ProjectService | None = None) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._project_service = project_service or ProjectService(str(self._workspace_root))

    def collect(
        self,
        project_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> ProjectFactSnapshot:
        """Build a fact package from current workspace evidence without writing files."""
        if ttl_seconds <= 0:
            raise ProjectFactError("事实包有效期必须大于 0 秒")

        project = self._project_service.get_project(project_id)
        if project is None:
            raise ProjectFactError(f"项目不存在: {project_id}")

        project_path = Path(project.path).resolve()
        self._require_workspace_path(project_path, "项目路径")
        pm_session_path = self._find_pm_session(project_path, project_id)
        pm_session_content = self._read_text(pm_session_path)
        runtime_root = self._resolve_runtime_root(pm_session_content, project_path)
        collected_at = datetime.now(UTC)

        draft = ProjectFactSnapshot(
            evidence_id="",
            fingerprint="",
            project_id=project_id,
            workspace_root=str(self._workspace_root),
            project_path=str(project_path),
            collected_at=collected_at,
            expires_at=collected_at + timedelta(seconds=ttl_seconds),
            git=self._collect_git_fact(),
            pm_session=self._fingerprint_file(pm_session_path),
            open_changes=self._collect_open_changes(project_path),
            spec_snapshot=self._collect_spec_snapshot(pm_session_content),
            code_structure=self._collect_code_structure(runtime_root),
            available_checks=self._collect_available_checks(runtime_root, project.stack),
        )
        fingerprint = draft.integrity_fingerprint()
        return draft.model_copy(
            update={
                "fingerprint": fingerprint,
                "evidence_id": f"FACT-{fingerprint[:16].upper()}",
            }
        )

    def load_snapshot(self, fact_file: str | Path) -> ProjectFactSnapshot:
        """Load an externally persisted fact package without changing it."""
        path = Path(fact_file)
        try:
            payload = json.loads(self._read_text(path))
            return ProjectFactSnapshot.model_validate(payload)
        except (json.JSONDecodeError, OSError, ValidationError) as error:
            raise ProjectFactError(f"事实包无法读取或不符合 Schema: {path}") from error

    def validate(
        self,
        snapshot: ProjectFactSnapshot,
        expected_project_id: str,
    ) -> FactValidationResult:
        """Reject missing, stale, tampered, mismatched, or drifted evidence."""
        failures: list[str] = []
        required_values: tuple[tuple[str, str], ...] = (
            ("事实包项目编号", snapshot.project_id),
            ("事实包工作空间", snapshot.workspace_root),
            ("事实包项目路径", snapshot.project_path),
            ("事实包完整性指纹", snapshot.fingerprint),
            ("事实包 evidence_id", snapshot.evidence_id),
            ("Git 仓库根", snapshot.git.repository_root),
            ("Git SHA", snapshot.git.head),
            ("PM_SESSION 路径", snapshot.pm_session.path),
            ("PM_SESSION 指纹", snapshot.pm_session.sha256),
            ("规范注册表路径", snapshot.spec_snapshot.registry.path),
            ("规范注册表指纹", snapshot.spec_snapshot.registry.sha256),
            ("代码运行根", snapshot.code_structure.runtime_root),
        )
        for label, value in required_values:
            if not value.strip():
                failures.append(f"事实包缺少{label}，拒绝消费")
        if not expected_project_id:
            failures.append("缺少预期项目编号，拒绝消费事实包")
        elif snapshot.project_id != expected_project_id:
            failures.append(
                f"项目身份不一致: 事实包={snapshot.project_id}, 预期={expected_project_id}"
            )

        now = datetime.now(UTC)
        if snapshot.expires_at <= now:
            failures.append("事实包已过期，必须重新执行 project preflight")
        if snapshot.expires_at <= snapshot.collected_at:
            failures.append("事实包有效期无效，拒绝消费")
        if snapshot.collected_at > now + timedelta(minutes=1):
            failures.append("事实包采集时间晚于当前时间，拒绝消费")
        if snapshot.workspace_root != str(self._workspace_root):
            failures.append("事实包所属工作空间不一致")
        if snapshot.fingerprint != snapshot.integrity_fingerprint():
            failures.append("事实包完整性指纹不匹配，可能已被篡改")
        if snapshot.evidence_id != f"FACT-{snapshot.fingerprint[:16].upper()}":
            failures.append("事实包 evidence_id 与完整性指纹不一致")

        if failures:
            return FactValidationResult(
                valid=False,
                evidence_id=snapshot.evidence_id,
                failures=failures,
            )

        try:
            current = self.collect(snapshot.project_id)
        except ProjectFactError as error:
            return FactValidationResult(
                valid=False,
                evidence_id=snapshot.evidence_id,
                failures=[f"当前工作空间无法复核事实包: {error}"],
            )

        comparisons: tuple[tuple[str, object, object], ...] = (
            ("项目路径", snapshot.project_path, current.project_path),
            ("Git SHA", snapshot.git.head, current.git.head),
            ("Git 工作树状态", snapshot.git.status, current.git.status),
            ("PM_SESSION 指纹", snapshot.pm_session.sha256, current.pm_session.sha256),
            (
                "规范注册表指纹",
                snapshot.spec_snapshot.registry.sha256,
                current.spec_snapshot.registry.sha256,
            ),
            ("开放变更单", snapshot.open_changes, current.open_changes),
            ("代码运行根", snapshot.code_structure.runtime_root, current.code_structure.runtime_root),
        )
        for label, expected, actual in comparisons:
            if expected != actual:
                failures.append(f"{label} 已变化，必须重新执行 project preflight")

        return FactValidationResult(
            valid=not failures,
            evidence_id=snapshot.evidence_id,
            failures=failures,
        )

    def _collect_git_fact(self) -> GitFact:
        repository_root = self._run_git("rev-parse", "--show-toplevel")
        if repository_root.returncode != 0:
            raise ProjectFactError("工作空间不是可验证的 Git 仓库")

        head = self._run_git("rev-parse", "HEAD")
        if head.returncode != 0 or not head.stdout.strip():
            raise ProjectFactError("Git HEAD 不可用，无法建立可信事实包")

        status = self._run_git("status", "--porcelain=v1", "--untracked-files=normal")
        if status.returncode != 0:
            raise ProjectFactError(f"无法读取 Git 工作树状态: {status.stderr.strip()}")

        return GitFact(
            repository_root=repository_root.stdout.strip(),
            head=head.stdout.strip(),
            status=[line for line in status.stdout.splitlines() if line],
        )

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self._workspace_root,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                text=True,
                timeout=5,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProjectFactError(f"Git 只读查询失败: {error}") from error

    def _find_pm_session(self, project_path: Path, project_id: str) -> Path:
        expected = project_path / f"PM_SESSION_{project_id}.md"
        if expected.is_file():
            return expected
        candidates = sorted(project_path.glob("PM_SESSION_*.md"))
        if candidates:
            return candidates[0]
        raise ProjectFactError(f"缺少 PM_SESSION: {expected}")

    def _resolve_runtime_root(self, pm_session_content: str, project_path: Path) -> Path:
        match = _RUNTIME_ROOT_RE.search(pm_session_content)
        if match:
            candidate = Path(match.group(1).strip())
            runtime_root = candidate if candidate.is_absolute() else self._workspace_root / candidate
            if runtime_root.is_dir():
                resolved = runtime_root.resolve()
                self._require_workspace_path(resolved, "runtime_root")
                return resolved

        default_runtime = self._workspace_root / "00_Infrastructure" / "auto_pm"
        if default_runtime.is_dir():
            return default_runtime.resolve()
        return project_path

    def _require_workspace_path(self, path: Path, label: str) -> None:
        try:
            path.relative_to(self._workspace_root)
        except ValueError as error:
            raise ProjectFactError(f"{label} 位于工作空间外，拒绝采集: {path}") from error

    def _collect_open_changes(self, project_path: Path) -> list[OpenChangeFact]:
        changes: list[OpenChangeFact] = []
        for change_file in sorted(project_path.rglob("CHG-*.md")):
            relative_parts = {part.lower() for part in change_file.relative_to(project_path).parts}
            if "archive" in relative_parts or "archive_cold" in relative_parts:
                continue
            content = self._read_text(change_file)
            status_match = _CHANGE_STATUS_RE.search(content)
            status = status_match.group(1).strip().lower() if status_match else "unknown"
            if status in _TERMINAL_CHANGE_STATUSES:
                continue
            changes.append(
                OpenChangeFact(
                    change_number=change_file.stem,
                    status=status,
                    domain=change_file.parent.name.removeprefix("CHG-"),
                    file_path=str(change_file.resolve()),
                )
            )
        return changes

    def _collect_spec_snapshot(self, pm_session_content: str) -> SpecSnapshotFact:
        registry_path = self._workspace_root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
        if not registry_path.is_file():
            raise ProjectFactError(f"缺少规范注册表: {registry_path}")
        try:
            registry_payload = json.loads(self._read_text(registry_path))
        except json.JSONDecodeError as error:
            raise ProjectFactError(f"规范注册表格式无效: {registry_path}") from error

        versions = self._extract_registry_versions(registry_payload)
        if not versions:
            raise ProjectFactError("规范注册表不包含可用的版本信息")

        project_versions = self._extract_project_spec_versions(pm_session_content)
        drifts = [
            SpecVersionDrift(
                spec_id=spec_id,
                project_version=project_version,
                registry_version=versions[spec_id],
            )
            for spec_id, project_version in sorted(project_versions.items())
            if spec_id in versions and project_version != versions[spec_id]
        ]
        return SpecSnapshotFact(
            registry=self._fingerprint_file(registry_path),
            registry_versions=dict(sorted(versions.items())),
            project_versions=dict(sorted(project_versions.items())),
            drifts=drifts,
        )

    @staticmethod
    def _extract_registry_versions(payload: object) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        specs = payload.get("specs")
        if isinstance(specs, dict):
            return {
                str(spec_id): str(info["version"])
                for spec_id, info in specs.items()
                if isinstance(info, dict) and "version" in info
            }
        if isinstance(specs, list):
            return {
                str(item["spec_id"]): str(item["version"])
                for item in specs
                if isinstance(item, dict) and "spec_id" in item and "version" in item
            }
        return {}

    @staticmethod
    def _extract_project_spec_versions(pm_session_content: str) -> dict[str, str]:
        lines = pm_session_content.splitlines()
        heading_index = next(
            (index for index, line in enumerate(lines) if _SPEC_HEADING_RE.match(line.strip())),
            None,
        )
        if heading_index is None:
            return {}

        table_lines: list[str] = []
        for line in lines[heading_index + 1 :]:
            stripped = line.strip()
            if stripped.startswith("|"):
                table_lines.append(stripped)
            elif table_lines:
                break
        if len(table_lines) < 3:
            return {}

        header = ProjectFactService._split_table_row(table_lines[0])
        spec_column = next(
            (
                index
                for index, value in enumerate(header)
                if value.lower().replace(" ", "") in {"规范编号", "规范id", "spec_id"}
            ),
            None,
        )
        version_column = next(
            (
                index
                for index, value in enumerate(header)
                if value.lower().replace(" ", "") in {"版本号", "版本", "version"}
            ),
            None,
        )
        if spec_column is None or version_column is None:
            return {}

        versions: dict[str, str] = {}
        for line in table_lines[2:]:
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            cells = ProjectFactService._split_table_row(line)
            if len(cells) <= max(spec_column, version_column):
                continue
            spec_id = cells[spec_column].strip()
            version = cells[version_column].strip()
            if spec_id and version:
                versions[spec_id] = version
        return versions

    @staticmethod
    def _split_table_row(line: str) -> list[str]:
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        return [cell.strip() for cell in stripped.split("|")]

    def _collect_code_structure(self, runtime_root: Path) -> CodeStructureFact:
        source_root = runtime_root / "auto_pm" if (runtime_root / "auto_pm").is_dir() else runtime_root
        if not source_root.is_dir():
            raise ProjectFactError(f"代码运行根不存在: {source_root}")

        top_level = sorted(
            entry.name
            for entry in runtime_root.iterdir()
            if entry.is_dir() and entry.name not in _EXCLUDED_STRUCTURE_DIRECTORIES
        )
        layers = [layer for layer in _CLEAN_ARCHITECTURE_LAYERS if (source_root / layer).is_dir()]
        python_file_count = 0
        for _current_root, directory_names, file_names in os.walk(source_root, followlinks=False):
            directory_names[:] = [
                name for name in directory_names if name not in _EXCLUDED_STRUCTURE_DIRECTORIES
            ]
            python_file_count += sum(1 for name in file_names if name.endswith(".py"))

        return CodeStructureFact(
            runtime_root=str(runtime_root),
            source_root=str(source_root),
            top_level_directories=top_level,
            clean_architecture_layers=layers,
            python_file_count=python_file_count,
        )

    def _collect_available_checks(self, runtime_root: Path, stack: str) -> list[AvailableCheckFact]:
        has_python_project = stack.lower() == "python"
        has_pyproject = (runtime_root / "pyproject.toml").is_file()
        registry_exists = (
            self._workspace_root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
        ).is_file()
        return [
            AvailableCheckFact(
                check_id="python-check",
                command="python -m auto_pm -w <workspace> python check <project_id>",
                available=has_python_project,
                reason="项目技术栈不是 python" if not has_python_project else "",
            ),
            AvailableCheckFact(
                check_id="pytest",
                command="python -m pytest --no-cov -q",
                available=has_pyproject,
                reason="运行根缺少 pyproject.toml" if not has_pyproject else "",
            ),
            AvailableCheckFact(
                check_id="ruff",
                command="ruff check auto_pm",
                available=has_pyproject,
                reason="运行根缺少 pyproject.toml" if not has_pyproject else "",
            ),
            AvailableCheckFact(
                check_id="mypy",
                command="mypy auto_pm",
                available=has_pyproject,
                reason="运行根缺少 pyproject.toml" if not has_pyproject else "",
            ),
            AvailableCheckFact(
                check_id="doctor",
                command="python -m auto_pm -w <workspace> doctor",
                available=True,
            ),
            AvailableCheckFact(
                check_id="spec-check",
                command="python -m auto_pm -w <workspace> spec check",
                available=registry_exists,
                reason="缺少 spec_registry.json" if not registry_exists else "",
            ),
        ]

    @staticmethod
    def _fingerprint_file(path: Path) -> FileFingerprint:
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ProjectFactError(f"无法读取事实源文件: {path}") from error
        return FileFingerprint(
            path=str(path.resolve()),
            sha256=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise ProjectFactError(f"无法读取文本事实源: {path}") from error
