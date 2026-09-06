"""PLC-HMI 概念映射：SFB 库函数（规范扫描器（文件系统扫描/发现规范文件））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .config import WorkspaceConfig

_KNOWN_PREFIXES = (
    "SW", "PM", "PLC", "PY", "CODE", "LSP", "INT", "DEV",
    "TOOL", "CHK", "OPS", "CHG", "BUG", "TEST", "REQ",
    "DES", "SUM", "PROJ", "TECH", "TASK", "PRD",
)

_PREFIXES_PATTERN = "|".join(_KNOWN_PREFIXES)

_SPEC_ID_HEAD_RE = re.compile(
    rf"^(?:{_PREFIXES_PATTERN})-\d{{3,4}}(?:-\d{{3}})?"
)

_NUM_HEAD_RE = re.compile(r"^(\d{3,4})_")

_PREFIX_SUFFIX_RE = re.compile(
    rf"_({_PREFIXES_PATTERN})$"
)


class SpecScanner:
    def __init__(
        self,
        workspace: Path,
        config: WorkspaceConfig | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.workspace = workspace
        self.config = config or WorkspaceConfig(workspace=workspace)
        self.project_root = project_root.resolve() if project_root else None

    def _spec_dirs(self) -> list[Path]:
        return self.config.full_spec_dirs

    def _collect_md_files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        files = sorted(directory.rglob("*.md"))
        # 排除归档文件（PM_SESSION_*archive* 等），避免过时路径引用产生噪音 WARN
        files = [f for f in files if "archive" not in f.name.lower()]
        return files

    def iter_pm_session_files(self) -> list[Path]:
        base_dir = self.project_root or self.workspace
        if not base_dir.exists():
            return []
        if self.project_root:
            candidates = sorted(base_dir.glob("PM_SESSION_*.md"))
        else:
            candidates = sorted(base_dir.rglob("PM_SESSION_*.md"))
        # Windows 文件系统大小写不敏感，glob/rglob 会把 pm_session_guide.md
        # 之类的说明文档也卷进来；这里再做一次严格文件名过滤。
        return [
            path for path in candidates
            if (
                path.name.startswith("PM_SESSION_")
                and path.suffix == ".md"
                and not self._is_archived_pm_session(path)
            )
        ]

    def _is_archived_pm_session(self, file_path: Path) -> bool:
        lower_name = file_path.name.lower()
        if "pm_session_template" in lower_name:
            return True
        if "_archive_" in lower_name or lower_name.endswith("_archive.md"):
            return True

        for part in file_path.parts:
            lower_part = part.lower()
            if lower_part in {"_archive", "archive", "templates"}:
                return True
            if lower_part == ".trae":
                continue
            if lower_part == "project-bootstrap":
                return True

        return False

    def _extract_spec_number(self, file_path: Path) -> str | None:
        name = file_path.stem

        head_match = _SPEC_ID_HEAD_RE.match(name)
        if head_match:
            return head_match.group(0)

        num_match = _NUM_HEAD_RE.match(name)
        prefix_match = _PREFIX_SUFFIX_RE.search(name)

        if num_match and prefix_match:
            number = num_match.group(1)
            prefix = prefix_match.group(1)
            return f"{prefix}-{number}"

        if prefix_match and not num_match:
            return None

        if num_match and not prefix_match:
            return None

        return None

    def scan_all(self) -> dict[str, list[Path]]:
        result: dict[str, list[Path]] = {}
        for spec_dir in self._spec_dirs():
            for md_file in self._collect_md_files(spec_dir):
                spec_num = self._extract_spec_number(md_file)
                if spec_num:
                    result.setdefault(spec_num, []).append(md_file)
        return result

    def scan_by_domain(self, domain: str) -> list[Path]:
        domain_dir = self.workspace / domain
        return self._collect_md_files(domain_dir)

    def extract_version(self, file_path: Path) -> str | None:
        try:
            with open(file_path, encoding="utf-8") as f:
                head = f.read(500)
        except (OSError, UnicodeDecodeError):
            return None
        ver_match = re.search(
            r"(?:版本|version|v)\s*[:：]?\s*(\d+(?:\.\d+)+)",
            head,
            re.IGNORECASE,
        )
        if ver_match:
            return ver_match.group(1)
        return None

    def extract_frontmatter(self, file_path: Path) -> dict[str, Any] | None:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return None
        if not content.startswith("---"):
            return None
        end = content.find("---", 3)
        if end == -1:
            return None
        fm_text = content[3:end].strip()
        try:
            data = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            return None
        if isinstance(data, dict):
            return data
        return None

    def find_duplicates(self) -> dict[str, list[Path]]:
        all_specs = self.scan_all()
        duplicates: dict[str, list[Path]] = {}
        for spec_num, paths in all_specs.items():
            if len(paths) > 1:
                duplicates[spec_num] = paths
        return duplicates
