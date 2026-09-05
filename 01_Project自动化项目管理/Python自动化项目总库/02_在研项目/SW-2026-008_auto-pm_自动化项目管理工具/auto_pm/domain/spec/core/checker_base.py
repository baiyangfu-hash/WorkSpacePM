"""PLC-HMI 概念映射：SFB 库函数（检查器基类（所有规范检查器的父类））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

import importlib
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from .registry import SpecRegistry
from .scanner import SpecScanner


class Severity(IntEnum):
    INFO = 1
    WARNING = 2
    ERROR = 3


@dataclass
class CheckResult:
    check_id: str
    severity: Severity
    message: str
    details: str = ""
    fix_suggestion: str = ""


class BaseChecker(ABC):
    @abstractmethod
    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]: ...


class DuplicateChecker(BaseChecker):
    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        duplicates = scanner.find_duplicates()
        for spec_num, paths in duplicates.items():
            path_list = ", ".join(str(p) for p in paths)
            results.append(
                CheckResult(
                    check_id="SHC-001",
                    severity=Severity.ERROR,
                    message=f"规范 {spec_num} 存在重复文件",
                    details=f"文件列表: {path_list}",
                    fix_suggestion="保留一个主文件，将其余文件移至归档目录并更新注册表",
                )
            )
        return results


class VersionMismatchChecker(BaseChecker):
    @staticmethod
    def _normalize_version(v: str) -> str:
        return v.lstrip("Vv")

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        all_specs = scanner.scan_all()
        for spec_num, paths in all_specs.items():
            spec_info = registry.get_spec(spec_num)
            if not spec_info:
                continue
            for path in paths:
                fm = scanner.extract_frontmatter(path)
                if fm and isinstance(fm, dict):
                    file_version = fm.get("version")
                else:
                    file_version = scanner.extract_version(path)
                if file_version and spec_info.version:
                    norm_file = self._normalize_version(file_version)
                    norm_reg = self._normalize_version(spec_info.version)
                    if norm_file != norm_reg:
                        results.append(
                            CheckResult(
                                check_id="SHC-002",
                                severity=Severity.WARNING,
                                message=f"规范 {spec_num} 版本不一致",
                                details=f"注册表版本: {spec_info.version}, 文件版本: {file_version}, 文件: {path}",
                                fix_suggestion="更新注册表中的版本号或更新文件frontmatter中的version字段使其一致",
                            )
                        )
        return results


class DeprecatedRefChecker(BaseChecker):
    _ACTIVE_REF_PATTERNS = re.compile(r"(遵循|参照|引用|参考|依据|按照|遵守)\s*[:：]?\s*.*?")
    _DEPRECATED_CONTEXT_PATTERNS = re.compile(r"(已废弃|替代|deprecated|取代|替换为|替代为)")
    _SPEC_ID_RE = re.compile(r"(?:SW|PM|PLC|PY|CODE|LSP|INT)-\d{3,4}(?:-\d{3})?")

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        deprecated_ids = {s.spec_id for s in registry.get_deprecated()}
        if not deprecated_ids:
            return results

        all_specs = scanner.scan_all()
        for spec_num, paths in all_specs.items():
            for path in paths:
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError):
                    continue

                for line_no, line in enumerate(content.splitlines(), 1):
                    refs = self._SPEC_ID_RE.findall(line)
                    if not refs:
                        continue
                    if not self._ACTIVE_REF_PATTERNS.search(line):
                        continue
                    if self._DEPRECATED_CONTEXT_PATTERNS.search(line):
                        continue
                    for ref_id in refs:
                        if ref_id in deprecated_ids:
                            results.append(
                                CheckResult(
                                    check_id="SHC-003",
                                    severity=Severity.WARNING,
                                    message=f"规范 {spec_num} 主动引用了已废弃规范 {ref_id}",
                                    details=f"文件: {path}, 第{line_no}行: {line.strip()}",
                                    fix_suggestion=f"将引用更新为 {ref_id} 的替代规范",
                                )
                            )
        return results


class IndexLinkChecker(BaseChecker):
    _MDLINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    _SPEC_ID_RE = re.compile(r"(?:SW|PM|PLC|PY|CODE|LSP|INT)-\d{3,4}(?:-\d{3})?")

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        for output_path in scanner.config.full_output_paths.values():
            if not output_path.exists():
                continue
            try:
                with open(output_path, encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            for line_no, line in enumerate(content.splitlines(), 1):
                for match in self._MDLINK_RE.finditer(line):
                    link_text = match.group(1)
                    link_target = match.group(2)
                    spec_match = self._SPEC_ID_RE.search(link_text)
                    if not spec_match:
                        continue
                    spec_id = spec_match.group(0)
                    target_path = output_path.parent / link_target
                    if not target_path.exists():
                        results.append(
                            CheckResult(
                                check_id="SHC-004",
                                severity=Severity.ERROR,
                                message=f"索引文件中列出的规范文件不存在: {spec_id}",
                                details=f"索引文件: {output_path}, 第{line_no}行, 链接目标: {link_target}",
                                fix_suggestion=f"检查文件 {link_target} 是否存在，或更新索引中的链接",
                            )
                        )
        return results


class UnlistedSpecChecker(BaseChecker):
    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        all_specs = scanner.scan_all()
        for spec_num, paths in all_specs.items():
            spec_info = registry.get_spec(spec_num)
            if not spec_info:
                results.append(
                    CheckResult(
                        check_id="SHC-005",
                        severity=Severity.WARNING,
                        message=f"规范 {spec_num} 未在注册表中登记",
                        details=f"文件: {paths[0]}",
                        fix_suggestion=f"将规范 {spec_num} 添加到注册表",
                    )
                )
        return results


class ObsidianLinkChecker(BaseChecker):
    _WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
    _MDLINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    _SPEC_ID_RE = re.compile(r"(?:SW|PM|PLC|PY|CODE|LSP|INT)-\d{3,4}(?:-\d{3})?")

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        all_specs = scanner.scan_all()
        for spec_num, paths in all_specs.items():
            for path in paths:
                try:
                    with open(path, encoding="utf-8") as f:
                        lines = f.readlines()
                except (OSError, UnicodeDecodeError):
                    continue

                in_code_block = False
                in_frontmatter = False
                fm_line_count = 0

                for line_no, line in enumerate(lines, 1):
                    stripped = line.strip()

                    if line_no == 1 and stripped == "---":
                        in_frontmatter = True
                        fm_line_count = 1
                        continue
                    if in_frontmatter:
                        if stripped == "---" and fm_line_count > 0:
                            in_frontmatter = False
                        fm_line_count += 1
                        continue

                    if stripped.startswith("```"):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block:
                        continue

                    for match in self._WIKILINK_RE.finditer(line):
                        target = match.group(1)
                        spec_match = self._SPEC_ID_RE.search(target)
                        if spec_match:
                            ref_id = spec_match.group(0)
                            target_path = self._resolve_wikilink(path, target, scanner)
                            if target_path and not target_path.exists():
                                results.append(
                                    CheckResult(
                                        check_id="SHC-006",
                                        severity=Severity.WARNING,
                                        message=f"规范 {spec_num} 的Obsidian链接指向不存在的文件: {ref_id}",
                                        details=f"文件: {path}, 第{line_no}行, 链接: [[{target}]]",
                                        fix_suggestion="检查链接目标文件是否存在，或更新链接",
                                    )
                                )
                            else:
                                spec_info = registry.get_spec(ref_id)
                                if spec_info and spec_info.lifecycle == "deprecated":
                                    results.append(
                                        CheckResult(
                                            check_id="SHC-006",
                                            severity=Severity.WARNING,
                                            message=f"规范 {spec_num} 链接了已废弃规范 {ref_id}",
                                            details=f"文件: {path}, 第{line_no}行, 链接: [[{target}]]",
                                            fix_suggestion=f"更新链接指向 {ref_id} 的替代规范",
                                        )
                                    )

                    for match in self._MDLINK_RE.finditer(line):
                        link_text = match.group(1)
                        link_target = match.group(2)
                        spec_match = self._SPEC_ID_RE.search(link_text) or self._SPEC_ID_RE.search(
                            link_target
                        )
                        if spec_match:
                            ref_id = spec_match.group(0)
                            target_path = path.parent / link_target
                            if not target_path.exists():
                                results.append(
                                    CheckResult(
                                        check_id="SHC-006",
                                        severity=Severity.WARNING,
                                        message=f"规范 {spec_num} 的Markdown链接指向不存在的文件: {ref_id}",
                                        details=f"文件: {path}, 第{line_no}行, 链接: [{link_text}]({link_target})",
                                        fix_suggestion="检查链接目标文件是否存在，或更新链接",
                                    )
                                )
                            else:
                                spec_info = registry.get_spec(ref_id)
                                if spec_info and spec_info.lifecycle == "deprecated":
                                    results.append(
                                        CheckResult(
                                            check_id="SHC-006",
                                            severity=Severity.WARNING,
                                            message=f"规范 {spec_num} 链接了已废弃规范 {ref_id}",
                                            details=f"文件: {path}, 第{line_no}行, 链接: [{link_text}]({link_target})",
                                            fix_suggestion=f"更新链接指向 {ref_id} 的替代规范",
                                        )
                                    )
        return results

    def _resolve_wikilink(
        self,
        source_file: Path,
        target: str,
        scanner: SpecScanner,
    ) -> Path | None:
        for spec_dir in scanner.config.full_spec_dirs:
            candidate = spec_dir / f"{target}.md"
            if candidate.exists():
                return candidate
        candidate = source_file.parent / f"{target}.md"
        return candidate


class FrontmatterChecker(BaseChecker):
    _REQUIRED_FIELDS = ["spec_id", "title", "version", "lifecycle"]

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        all_specs = scanner.scan_all()
        for spec_num, paths in all_specs.items():
            for path in paths:
                fm = scanner.extract_frontmatter(path)
                if fm is None:
                    results.append(
                        CheckResult(
                            check_id="SHC-007",
                            severity=Severity.INFO,
                            message=f"规范 {spec_num} 缺少frontmatter",
                            details=f"文件: {path}",
                            fix_suggestion="添加包含spec_id、title、version、lifecycle的YAML frontmatter",
                        )
                    )
                    continue
                missing = [f for f in self._REQUIRED_FIELDS if f not in fm or not fm[f]]
                if missing:
                    results.append(
                        CheckResult(
                            check_id="SHC-007",
                            severity=Severity.INFO,
                            message=f"规范 {spec_num} frontmatter缺少必填字段",
                            details=f"文件: {path}, 缺少字段: {', '.join(missing)}",
                            fix_suggestion=f"补充缺失字段: {', '.join(missing)}",
                        )
                    )
        return results


class RulesPathChecker(BaseChecker):
    _RULES_DIR = ".trae/rules"

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        workspace = scanner.workspace
        rules_dir = workspace / self._RULES_DIR
        if not rules_dir.exists():
            return results

        rule_files: list[Path] = []
        for ext in ("*.md", "*.yaml", "*.yml"):
            rule_files.extend(rules_dir.glob(ext))

        for rule_file in rule_files:
            try:
                with open(rule_file, encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            spec_refs = re.findall(r"(?:SW|PM|PLC|PY|CODE|LSP|INT)-\d{3,4}(?:-\d{3})?", content)
            for ref_id in set(spec_refs):
                spec_info = registry.get_spec(ref_id)
                if not spec_info:
                    ref_path = self._find_ref_path(workspace, ref_id, content)
                    if ref_path and not ref_path.exists():
                        results.append(
                            CheckResult(
                                check_id="SHC-008",
                                severity=Severity.ERROR,
                                message=f"规则文件引用的规范路径无效: {ref_id}",
                                details=f"文件: {rule_file}, 引用路径: {ref_path}",
                                fix_suggestion=f"更新规则文件中 {ref_id} 的引用路径",
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                check_id="SHC-008",
                                severity=Severity.INFO,
                                message=f"规则文件引用了未注册规范 {ref_id}",
                                details=f"文件: {rule_file}",
                                fix_suggestion=f"注册规范 {ref_id} 或更新规则文件中的引用",
                            )
                        )
                elif spec_info.lifecycle == "deprecated":
                    results.append(
                        CheckResult(
                            check_id="SHC-008",
                            severity=Severity.WARNING,
                            message=f"规则文件引用了已废弃规范 {ref_id}",
                            details=f"文件: {rule_file}",
                            fix_suggestion=f"更新引用为 {ref_id} 的替代规范",
                        )
                    )
        return results

    def _find_ref_path(self, workspace: Path, ref_id: str, content: str) -> Path | None:
        path_pattern = re.compile(rf"{re.escape(ref_id)}[^\s]*?[:\s]+([^\s]+\.(?:md|yaml|yml))")
        match = path_pattern.search(content)
        if match:
            return workspace / match.group(1)
        if spec_info := getattr(self, "_last_spec_info", None):
            if spec_info.canonical_path:
                return workspace / Path(spec_info.canonical_path)
        return None


class PMSessionRefChecker(BaseChecker):
    _PATH_REF_RE = re.compile(r"(?:^|\s)(\S+/\S+\.\w{2,6})(?:\s|$)")
    _MDLINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    _ARTIFACTS_SECTION_RE = re.compile(
        r"^##\s*4\.?\s*Artifacts?\s*Index",
        re.MULTILINE,
    )
    _NEXT_SECTION_RE = re.compile(r"^##\s*\d", re.MULTILINE)

    def _extract_artifacts_section(self, content: str) -> str:
        m = self._ARTIFACTS_SECTION_RE.search(content)
        if not m:
            return content
        start = m.start()
        rest = content[start + len(m.group(0)) :]
        nm = self._NEXT_SECTION_RE.search(rest)
        if nm:
            return content[start : start + len(m.group(0)) + nm.start()]
        return content[start:]

    def _clean_path_ref(self, ref_path_str: str) -> str:
        cleaned = ref_path_str.rstrip(".,;:)]}>")
        paren_idx = cleaned.find("(")
        if paren_idx > 0:
            cleaned = cleaned[:paren_idx].rstrip()
        return cleaned

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        workspace = scanner.workspace

        pm_files = scanner.iter_pm_session_files()
        if not pm_files:
            return results

        for pm_file in pm_files:
            try:
                content = pm_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            base_dir = pm_file.parent

            artifacts_content = self._extract_artifacts_section(content)

            refs_seen: set[str] = set()
            for match in self._PATH_REF_RE.finditer(artifacts_content):
                ref_path_str = self._clean_path_ref(match.group(1))
                if not ref_path_str or ref_path_str.startswith(("http:", "https:")):
                    continue
                if ref_path_str in refs_seen:
                    continue
                refs_seen.add(ref_path_str)

                target = base_dir / ref_path_str
                if not target.exists():
                    results.append(
                        CheckResult(
                            check_id="SHC-009",
                            severity=Severity.WARNING,
                            message=f"PM_SESSION 引用的路径不存在: {ref_path_str}",
                            details=f"PM文件: {pm_file.relative_to(workspace)}",
                            fix_suggestion=f"确认 {ref_path_str} 文件是否存在，或更新 PM_SESSION 中的引用",
                        )
                    )

            for line_no, line in enumerate(artifacts_content.splitlines(), 1):
                for match in self._MDLINK_RE.finditer(line):
                    link_target = match.group(2)
                    if link_target.startswith(("http:", "https:", "#")):
                        continue
                    target = base_dir / link_target
                    if not target.exists() and link_target.endswith(".md"):
                        results.append(
                            CheckResult(
                                check_id="SHC-009",
                                severity=Severity.WARNING,
                                message=f"PM_SESSION markdown链接目标不存在: {link_target}",
                                details=f"PM文件: {pm_file.relative_to(workspace)}, 第{line_no}行",
                                fix_suggestion=f"确认 {link_target} 文件是否存在，或更新链接",
                            )
                        )

        return results


class SpecCrossRefChecker(BaseChecker):
    _MDLINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    _SPEC_ID_RE = re.compile(r"(?:SW|PM|PLC|PY|CODE|LSP|INT)-\d{3,4}(?:-\d{3})?")

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        all_specs = scanner.scan_all()

        for spec_num, paths in all_specs.items():
            for path in paths:
                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                base_dir = path.parent

                for line_no, line in enumerate(content.splitlines(), 1):
                    for match in self._MDLINK_RE.finditer(line):
                        link_text = match.group(1)
                        link_target = match.group(2)
                        if link_target.startswith(("http:", "https:", "#", "./")):
                            continue

                        if not self._SPEC_ID_RE.search(link_text) and not self._SPEC_ID_RE.search(
                            link_target
                        ):
                            continue

                        target_path = base_dir / link_target
                        if not target_path.exists():
                            results.append(
                                CheckResult(
                                    check_id="SHC-010",
                                    severity=Severity.WARNING,
                                    message=f"规范 {spec_num} 交叉引用目标不存在: {link_target}",
                                    details=f"文件: {path.relative_to(scanner.workspace)}, 第{line_no}行",
                                    fix_suggestion=f"确认 {link_target} 文件是否存在，或更新引用为正确的文件名",
                                )
                            )

        return results


class VersionConsistencyChecker(BaseChecker):
    """SHC-011: 版本号四件套一致性检查（CHG-SCPT-2026-145）

    检查 pyproject.toml version ↔ CHANGELOG.md 最新版本 ↔ PM_SESSION §2 ↔ PM_SESSION §8
    四处版本号是否一致。基于 project-rule.md "迭代文档同步规则（强制）"。
    """

    _PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
    _CHANGELOG_VERSION_RE = re.compile(r"^##\s*\[(?!Unreleased)([^\]]+)\]", re.MULTILINE)
    _PM_VERSION_RE = re.compile(r"(?:代码基线|版本基线|基线)\s*\*{0,2}V?(\d+(?:\.\d+)+)\*{0,2}")
    _NEXT_SECTION_RE = re.compile(r"^##\s*\d", re.MULTILINE)

    @staticmethod
    def _normalize_version(v: str) -> str:
        return v.lstrip("Vv")

    def _extract_section(self, content: str, section_num: int) -> str:
        pattern = re.compile(rf"^##\s*{section_num}\.?\s", re.MULTILINE)
        m = pattern.search(content)
        if not m:
            return ""
        start = m.start()
        rest = content[start + len(m.group(0)) :]
        nm = self._NEXT_SECTION_RE.search(rest)
        if nm:
            return content[start : start + len(m.group(0)) + nm.start()]
        return content[start:]

    def _read_pyproject_version(self, path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        m = self._PYPROJECT_VERSION_RE.search(content)
        return m.group(1) if m else None

    def _read_changelog_version(self, path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        m = self._CHANGELOG_VERSION_RE.search(content)
        return m.group(1) if m else None

    def _extract_pm_version(self, section_content: str) -> str | None:
        if not section_content:
            return None
        m = self._PM_VERSION_RE.search(section_content)
        return m.group(1) if m else None

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        pm_files = scanner.iter_pm_session_files()
        if not pm_files:
            return results

        for pm_file in pm_files:
            project_root = pm_file.parent
            try:
                pm_content = pm_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            pyproject_ver = self._read_pyproject_version(project_root / "pyproject.toml")
            changelog_ver = self._read_changelog_version(project_root / "CHANGELOG.md")
            pm_s2_ver = self._extract_pm_version(self._extract_section(pm_content, 2))
            pm_s8_ver = self._extract_pm_version(self._extract_section(pm_content, 8))

            versions: dict[str, str | None] = {
                "pyproject.toml": pyproject_ver,
                "CHANGELOG.md": changelog_ver,
                "PM_SESSION §2": pm_s2_ver,
                "PM_SESSION §8": pm_s8_ver,
            }

            # 基准版本优先级：pyproject.toml > CHANGELOG.md > §2
            canonical = pyproject_ver or changelog_ver or pm_s2_ver
            if not canonical:
                continue

            canonical_norm = self._normalize_version(canonical)
            for source, ver in versions.items():
                if ver is None:
                    # pyproject.toml/CHANGELOG.md 可能不存在（非Python项目），跳过
                    if source in ("pyproject.toml", "CHANGELOG.md"):
                        continue
                    results.append(
                        CheckResult(
                            check_id="SHC-011",
                            severity=Severity.ERROR,
                            message=f"{source} 未找到版本号",
                            details=f"PM文件: {pm_file.name}, 期望版本: {canonical}",
                            fix_suggestion=f"在 {source} 中补充版本号 {canonical}",
                        )
                    )
                elif self._normalize_version(ver) != canonical_norm:
                    results.append(
                        CheckResult(
                            check_id="SHC-011",
                            severity=Severity.ERROR,
                            message=f"{source} 版本号不一致",
                            details=f"{source}: {ver}, 期望: {canonical}, PM文件: {pm_file.name}",
                            fix_suggestion=f"将 {source} 的版本号统一为 {canonical}",
                        )
                    )
        return results


class TestCountConsistencyChecker(BaseChecker):
    """SHC-012: 测试数一致性检查（CHG-SCPT-2026-145）

    检查 PM_SESSION §3 中声明的 pytest 通过数 ↔ 实际 junit xml 结果一致性。
    依赖 pytest 配置 --junitxml=coverage/junit/test-results.xml。
    """

    _PASSED_RE = re.compile(r"pytest\s+(\d+)\s+passed")
    _SECTION_3_RE = re.compile(r"^##\s*3\.?\s", re.MULTILINE)
    _NEXT_SECTION_RE = re.compile(r"^##\s*\d", re.MULTILINE)
    _JUNIT_CANDIDATES = [
        "coverage/junit/test-results.xml",
        "test_reports/junit.xml",
        "test-results/junit.xml",
    ]

    def _extract_section_3(self, content: str) -> str:
        m = self._SECTION_3_RE.search(content)
        if not m:
            return ""
        start = m.start()
        rest = content[start + len(m.group(0)) :]
        nm = self._NEXT_SECTION_RE.search(rest)
        if nm:
            return content[start : start + len(m.group(0)) + nm.start()]
        return content[start:]

    def _read_junit_test_count(self, project_root: Path) -> int | None:
        for rel_path in self._JUNIT_CANDIDATES:
            junit_path = project_root / rel_path
            if not junit_path.exists():
                continue
            try:
                tree = ET.parse(str(junit_path))
                root = tree.getroot()
                # junit xml: <testsuites tests="N"> 或 <testsuite tests="N">
                tests_attr = root.get("tests")
                if tests_attr is None:
                    suite = root.find(".//testsuite")
                    if suite is not None:
                        tests_attr = suite.get("tests")
                if tests_attr:
                    return int(tests_attr)
            except (ET.ParseError, ValueError, OSError):
                continue
        return None

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        pm_files = scanner.iter_pm_session_files()
        if not pm_files:
            return results

        for pm_file in pm_files:
            project_root = pm_file.parent
            try:
                pm_content = pm_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            section3 = self._extract_section_3(pm_content)
            # 取最后一个 "pytest N passed" 作为最新声明
            matches = self._PASSED_RE.findall(section3)
            if not matches:
                continue  # §3 中没有测试数声明，跳过

            declared_count = int(matches[-1])
            actual_count = self._read_junit_test_count(project_root)

            if actual_count is None:
                results.append(
                    CheckResult(
                        check_id="SHC-012",
                        severity=Severity.WARNING,
                        message="未找到 junit xml 测试结果文件",
                        details=(
                            f"PM文件: {pm_file.name}, §3声明: {declared_count} passed, "
                            f"查找路径: {', '.join(self._JUNIT_CANDIDATES)}"
                        ),
                        fix_suggestion="运行 pytest 生成 junit xml，或配置 --junitxml 参数",
                    )
                )
            elif actual_count != declared_count:
                results.append(
                    CheckResult(
                        check_id="SHC-012",
                        severity=Severity.WARNING,
                        message=f"测试通过数不一致: §3声明 {declared_count} vs junit xml {actual_count}",
                        details=f"PM文件: {pm_file.name}",
                        fix_suggestion="重新运行 pytest 并更新 PM_SESSION §3 中的测试数声明",
                    )
                )
        return results


class VerificationStatusChecker(BaseChecker):
    """SHC-013: 验证状态标注检查（CHG-SCPT-2026-145）

    检查 PM_SESSION §8 Handoff Notes 中是否标注 [已验证]/[待验证]。
    基于 project_memory "未验证禁止回写" 约束。
    """

    _SECTION_8_RE = re.compile(r"^##\s*8\.?\s", re.MULTILINE)
    _NEXT_SECTION_RE = re.compile(r"^##\s*\d", re.MULTILINE)
    _VERIFIED_RE = re.compile(r"\[已验证\]|\[待验证\]")

    def _extract_section_8(self, content: str) -> str:
        m = self._SECTION_8_RE.search(content)
        if not m:
            return ""
        start = m.start()
        rest = content[start + len(m.group(0)) :]
        nm = self._NEXT_SECTION_RE.search(rest)
        if nm:
            return content[start : start + len(m.group(0)) + nm.start()]
        return content[start:]

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        pm_files = scanner.iter_pm_session_files()
        if not pm_files:
            return results

        for pm_file in pm_files:
            try:
                pm_content = pm_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            section8 = self._extract_section_8(pm_content)
            if not section8:
                continue

            if not self._VERIFIED_RE.search(section8):
                results.append(
                    CheckResult(
                        check_id="SHC-013",
                        severity=Severity.WARNING,
                        message="PM_SESSION §8 缺少验证状态标注",
                        details=(f"PM文件: {pm_file.name}, §8 中未发现 [已验证] 或 [待验证] 标注"),
                        fix_suggestion=(
                            "在 §8 的结论性条目后标注 [已验证] 或 [待验证]，"
                            "确保未验证结论不作为决策依据"
                        ),
                    )
                )
        return results


class DocIndexValidityChecker(BaseChecker):
    """SHC-014: 文档索引有效性检查（CHG-SCPT-2026-145）

    检查 PM_SESSION §4 Artifacts Index 中 PRD/INT/DSN/TEC：
    1. 四类核心文档是否齐全
    2. 路径是否有效（相对于 PM_SESSION 所在目录）
    与 SHC-009 的差异：SHC-009 检查所有路径引用，SHC-014 聚焦 req/int/dsn/tec 齐全性。

    CHG-SCPT-2026-153: P1-2 修复 — 排除模板文件、占位符路径和忽略清单。
    """

    _SECTION_4_RE = re.compile(r"^##\s*4\.?\s*(?:(?:Artifacts?|File)\s+)?(?:Index)?", re.MULTILINE)
    _NEXT_SECTION_RE = re.compile(r"^##\s*\d", re.MULTILINE)
    _DOC_ENTRY_RE = re.compile(
        r"^-\s*(prd|req|int|dsn|tec)\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE
    )
    _COMPONENT_PM_SESSION_RE = re.compile(
        r"^PM_SESSION_(?:FB|FC|DB|OB|UDT)[A-Za-z0-9_-]*\.md$",
        re.IGNORECASE,
    )
    _REQUIRED_DOCS = {"req", "int", "dsn", "tec"}
    _DOC_TYPE_ALIASES = {"prd": "req"}
    _LEGACY_DOC_CANDIDATES: dict[str, tuple[str, ...]] = {
        "req": ("PRD/需求分析文档_REQ.md",),
        "int": ("PRD/接口文档_INT.md",),
        "dsn": ("PRD/详细设计说明书_DSN.md",),
        "tec": ("PRD/技术方案文档_TEC.md",),
    }
    _TEMPLATE_DIR_MARKERS = (
        ".trae/project-bootstrap",
        "templates",
    )
    _PLACEHOLDER_PATH_MARKERS = {
        "",
        "-",
        "无",
        "none",
        "null",
        "n/a",
        "na",
        "待补充",
        "待填写",
        "待完善",
        "待更新",
        "待创建",
        "todo",
        "tbd",
        "placeholder",
    }

    def _is_template_file(self, pm_file: Path) -> bool:
        path_str = str(pm_file).replace("\\", "/")
        for marker in self._TEMPLATE_DIR_MARKERS:
            if f"/{marker}/" in path_str:
                return True
        return "PM_SESSION_TEMPLATE" in pm_file.name

    def _is_placeholder_path(self, doc_path_str: str) -> bool:
        normalized = doc_path_str.strip()
        if not normalized:
            return True

        lowered = normalized.lower()
        if lowered in self._PLACEHOLDER_PATH_MARKERS:
            return True

        wrapped = lowered.strip("()[]{}<> \t")
        if wrapped in self._PLACEHOLDER_PATH_MARKERS:
            return True

        # 模板变量或占位表达式不应被当成真实路径校验。
        if "{{" in normalized or "}}" in normalized:
            return True
        if re.search(r"\{[A-Za-z0-9_]+\}", normalized):
            return True

        return False

    def _should_skip_pm_file(self, pm_file: Path) -> bool:
        return bool(self._COMPONENT_PM_SESSION_RE.match(pm_file.name))

    def _extract_section_4(self, content: str) -> str:
        m = self._SECTION_4_RE.search(content)
        if not m:
            return ""
        start = m.start()
        rest = content[start + len(m.group(0)) :]
        nm = self._NEXT_SECTION_RE.search(rest)
        if nm:
            return content[start : start + len(m.group(0)) + nm.start()]
        return content[start:]

    def _discover_legacy_docs(self, project_root: Path) -> dict[str, str]:
        inferred: dict[str, str] = {}
        for doc_type, candidates in self._LEGACY_DOC_CANDIDATES.items():
            for candidate in candidates:
                if (project_root / candidate).exists():
                    inferred[doc_type] = candidate
                    break
        return inferred

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        pm_files = scanner.iter_pm_session_files()
        if not pm_files:
            return results

        for pm_file in pm_files:
            # 跳过模板文件（CHG-SCPT-2026-153: P1-2）
            if self._is_template_file(pm_file):
                continue
            if self._should_skip_pm_file(pm_file):
                continue

            project_root = pm_file.parent
            try:
                pm_content = pm_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            section4 = self._extract_section_4(pm_content)
            if not section4:
                continue  # 没有 §4 章节则跳过

            # 解析文档条目（跳过占位符路径）
            found_docs: dict[str, str] = {}
            for match in self._DOC_ENTRY_RE.finditer(section4):
                doc_type = match.group(1).lower()
                doc_type = self._DOC_TYPE_ALIASES.get(doc_type, doc_type)
                doc_path_str = match.group(2).strip().split()[0]  # 取路径部分（去掉注释）
                # 跳过占位符（CHG-SCPT-2026-153: P1-2）
                if self._is_placeholder_path(doc_path_str):
                    continue
                found_docs[doc_type] = doc_path_str

            if found_docs.keys() != self._REQUIRED_DOCS:
                for doc_type, legacy_path in self._discover_legacy_docs(project_root).items():
                    found_docs.setdefault(doc_type, legacy_path)

            # 检查必需文档是否齐全
            missing = self._REQUIRED_DOCS - set(found_docs.keys())
            if missing:
                results.append(
                    CheckResult(
                        check_id="SHC-014",
                        severity=Severity.ERROR,
                        message=f"PM_SESSION §4 缺少必需文档索引: {', '.join(sorted(missing))}",
                        details=f"PM文件: {pm_file.name}",
                        fix_suggestion=(
                            f"在 §4 Artifacts Index 中补充 {', '.join(sorted(missing))} 文档路径"
                        ),
                    )
                )

            # 检查路径有效性
            for doc_type, doc_path_str in found_docs.items():
                if doc_path_str.startswith(("http:", "https:")):
                    continue
                doc_path = project_root / doc_path_str
                if not doc_path.exists():
                    results.append(
                        CheckResult(
                            check_id="SHC-014",
                            severity=Severity.ERROR,
                            message=f"§4 文档索引路径无效: {doc_type} → {doc_path_str}",
                            details=f"PM文件: {pm_file.name}, 完整路径: {doc_path}",
                            fix_suggestion=(
                                f"确认 {doc_path_str} 文件是否存在，或更新 §4 中的路径"
                            ),
                        )
                    )
        return results


class NumberConflictChecker(BaseChecker):
    """SHC-015: 检测跨前缀编号冲突（如 TOOL-906 与 LSP-906 编号相同）

    规范编号（number 字段）在全局注册表中必须唯一，不区分 type_prefix。
    编号冲突会导致 AI 在引用"906 规范"时产生歧义。
    """

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        # 构建 number → [spec_id, ...] 的映射
        number_map: dict[str, list[str]] = {}
        for spec_id, spec_info in registry._specs.items():
            num = spec_info.number
            if num:
                number_map.setdefault(num, []).append(spec_id)

        for num, spec_ids in number_map.items():
            if len(spec_ids) > 1:
                results.append(
                    CheckResult(
                        check_id="SHC-015",
                        severity=Severity.WARNING,
                        message=f"编号 {num} 存在跨前缀冲突",
                        details=f"冲突条目: {', '.join(spec_ids)}",
                        fix_suggestion=(
                            "为其中一个条目分配唯一编号，或在规范 ID 中"
                            "明确区分（如 TOOL-9060 vs LSP-906）"
                        ),
                    )
                )
        return results


class DriftWarningChecker(BaseChecker):
    """SHC-016: 将所有含 drift_warning 字段的规范条目作为强制告警输出

    drift_warning 字段存在于 spec_registry.json 原始数据中，
    但在 SpecRegistry.load() 中被 clean.pop() 剥离，导致告警被静默忽略。
    此 Checker 从 registry._raw 直接读取原始数据，确保漂移警告可见。
    """

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        raw_specs: dict[str, object] = registry.raw.get("specs", {})
        for spec_id, raw_info in raw_specs.items():
            if not isinstance(raw_info, dict):
                continue
            drift = raw_info.get("drift_warning")
            if drift:
                results.append(
                    CheckResult(
                        check_id="SHC-016",
                        severity=Severity.WARNING,
                        message=f"{spec_id} 存在规范漂移警告",
                        details=str(drift),
                        fix_suggestion=(
                            "同步项目副本版本至真源版本，或移除已解决的 drift_warning 字段"
                        ),
                    )
                )
        return results


class SkillContractDriftChecker(BaseChecker):
    """SHC-017: 技能文档↔代码契约漂移对账器（CHG-SCPT-2026-167）

    以「代码为唯一真源」动态提取关键常量，校验技能文档
    （<workspace>/.trae/skills/**）是否仍包含这些值；漂移即报 SHC-017。
    """

    def check(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        from .skill_contracts import SKILL_CONTRACTS

        results: list[CheckResult] = []
        for contract in SKILL_CONTRACTS:
            truth_values: list[str] = []
            for ct in contract.code_truths:
                try:
                    module = importlib.import_module(ct.module)
                    attr = getattr(module, ct.attribute)
                except (ImportError, AttributeError):
                    continue
                if ct.kind == "value":
                    truth_values.append(str(attr))
                elif ct.kind == "keys":
                    try:
                        truth_values.extend(str(k) for k in attr.keys())
                    except AttributeError:
                        continue
            truth_values.extend(contract.literals)
            if not truth_values:
                continue

            for relpath in contract.doc_relpaths:
                doc_path = scanner.workspace / relpath
                if not doc_path.exists():
                    continue
                try:
                    content = doc_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for value in truth_values:
                    if value not in content:
                        results.append(
                            CheckResult(
                                check_id="SHC-017",
                                severity=contract.severity,
                                message=(
                                    f"{contract.contract_id} {contract.title} 漂移："
                                    f"文档缺失真源值 {value}"
                                ),
                                details=f"文档: {relpath}",
                                fix_suggestion=(f"同步 {relpath}，使其包含代码真源值 {value}"),
                            )
                        )
        return results


_CHECKER_MAP: dict[str, type[BaseChecker]] = {
    "SHC-001": DuplicateChecker,
    "SHC-002": VersionMismatchChecker,
    "SHC-003": DeprecatedRefChecker,
    "SHC-004": IndexLinkChecker,
    "SHC-005": UnlistedSpecChecker,
    "SHC-006": ObsidianLinkChecker,
    "SHC-007": FrontmatterChecker,
    "SHC-008": RulesPathChecker,
    "SHC-009": PMSessionRefChecker,
    "SHC-010": SpecCrossRefChecker,
    "SHC-011": VersionConsistencyChecker,
    "SHC-012": TestCountConsistencyChecker,
    "SHC-013": VerificationStatusChecker,
    "SHC-014": DocIndexValidityChecker,
    "SHC-015": NumberConflictChecker,
    "SHC-016": DriftWarningChecker,
    "SHC-017": SkillContractDriftChecker,
}


class HealthChecker:
    def __init__(self) -> None:
        self._checkers: list[BaseChecker] = [cls() for cls in _CHECKER_MAP.values()]

    def run_all(
        self,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        for checker in self._checkers:
            results.extend(checker.check(registry, scanner))
        return results

    def run_by_id(
        self,
        check_id: str,
        registry: SpecRegistry,
        scanner: SpecScanner,
    ) -> list[CheckResult]:
        checker_cls = _CHECKER_MAP.get(check_id)
        if checker_cls is None:
            return []
        checker = checker_cls()
        return checker.check(registry, scanner)
