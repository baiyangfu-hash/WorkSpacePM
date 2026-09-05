"""PLC-HMI 概念映射：SFB 库函数（PM_SESSION 管理（读取/写入/归档项目管理会话））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

PM_SESSION 解析/归档/检查服务

提供 PM_SESSION_SW-2026-008.md 文件的章节级解析、归档和健康检查能力。

三层真源架构（CHG-087 Stage 1 建立，CHG-088 Stage 2 自动化）：
1. Active 主文件：保留最新迭代状态
2. Historical 归档：archive_V*.md 完整保留历史
3. Event 实体：CHG-*.md 变更单
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from auto_pm.core.paths import PG_CLOSING_DIR

# 章节标题正则：## N. Title（N 为数字）
SECTION_HEADER_PATTERN = re.compile(r"^##\s+(\d+)\.\s+(.+)$")

# 健康检查阈值（CHG-087 Stage 1 基线：170 行 / 62KB）
MAX_FILE_SIZE_KB = 150  # 主文件最大 150KB
MAX_FILE_LINES = 200  # 主文件最大 200 行

# 必须存在的章节（Stage 1 后基线，§7 已归档删除）
REQUIRED_SECTIONS = {"0", "1", "2", "3", "4", "5", "6", "8", "9"}
# §7 应该不存在（已归档）
DEPRECATED_SECTIONS = {"7"}

# 归档目录约定（CHG-SCPT-2026-146: 5大过程组，归档归入 05_收尾）
ARCHIVE_DIR_NAME = "PM_SESSION归档"
ARCHIVE_DIR_PARENT = PG_CLOSING_DIR
# 旧归档路径（向后兼容，阶段3.5物理迁移后移除）
LEGACY_ARCHIVE_DIR_PARENT = "00_项目管理"
ARCHIVE_FILE_PATTERN = "PM_SESSION_{project_id}_archive_{version}.md"

# §8 Handoff Notes 条目识别前缀（CHG-109 条目级归档）
SECTION8_CURRENT_STATE_PREFIX = "- current_state"
SECTION8_SKILL_HANDOFF_PREFIX = "- skill_handoff"
SECTION8_ARCHIVE_NOTE_PREFIX = ">"

# 归档文件大小阈值（超过则切分到新文件，防止单文件过大无法 Read）
ARCHIVE_FILE_MAX_SIZE_KB = 200

# 变更信号文件扫描（CHG-SCPT-2026-166: 落账新鲜度 WARN 检查）
CHANGE_SIGNAL_PATTERNS: tuple[str, ...] = ("CHG-*.md", "*.scl", "*.py")
SCAN_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "htmlcov",
        "coverage",
        "dist",
        "build",
        "site-packages",
    }
)


@dataclass
class PmSessionSection:
    """PM_SESSION 章节"""

    number: str  # "0", "1", ..., "9"
    title: str  # "Meta", "Positioning（项目定位）", ...
    start_line: int  # 0-based 行号（header 行）
    end_line: int  # 0-based 行号（exclusive）
    header_line: str  # "## 0. Meta"
    content: str  # 章节内容（不含 header 行）

    @property
    def line_count(self) -> int:
        """章节总行数（含 header）"""
        return self.end_line - self.start_line


@dataclass
class PmSessionParseResult:
    """PM_SESSION 解析结果"""

    file_path: Path
    total_lines: int
    sections: list[PmSessionSection]
    pre_header_lines: list[str] = field(default_factory=list)  # 章节标题之前的行

    def get_section(self, number: str) -> PmSessionSection | None:
        """按章节号获取章节"""
        for s in self.sections:
            if s.number == number:
                return s
        return None

    def find_missing_required(self) -> set[str]:
        """查找缺失的必须章节"""
        existing = {s.number for s in self.sections}
        return REQUIRED_SECTIONS - existing

    def find_deprecated_present(self) -> set[str]:
        """查找不应存在的已归档章节"""
        existing = {s.number for s in self.sections}
        return existing & DEPRECATED_SECTIONS


@dataclass
class CheckResult:
    """健康检查结果"""

    file_path: Path
    file_size_kb: float
    total_lines: int
    missing_required: set[str]
    deprecated_present: set[str]
    is_oversized: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """是否健康（无缺失章节 + 无已归档章节回归 + 未超规模）"""
        return not self.missing_required and not self.deprecated_present and not self.is_oversized


@dataclass
class ArchiveResult:
    """归档结果"""

    archive_file: Path
    archived_sections: list[str]  # 归档的章节号
    archived_line_count: int
    main_file_lines_before: int
    main_file_lines_after: int
    backup_file: Path | None = None


class PmSessionParser:
    """PM_SESSION 章节级解析器"""

    def parse_file(self, file_path: Path) -> PmSessionParseResult:
        """解析 PM_SESSION 文件

        Args:
            file_path: PM_SESSION 文件路径

        Returns:
            PmSessionParseResult
        """
        content = file_path.read_text(encoding="utf-8")
        return self.parse_content(content, file_path)

    def parse_content(self, content: str, file_path: Path | None = None) -> PmSessionParseResult:
        """解析 PM_SESSION 内容字符串

        Args:
            content: PM_SESSION markdown 内容
            file_path: 文件路径（仅用于结果标记）

        Returns:
            PmSessionParseResult
        """
        lines = content.splitlines(keepends=False)
        sections: list[PmSessionSection] = []
        pre_header_lines: list[str] = []

        current_section: PmSessionSection | None = None

        for i, line in enumerate(lines):
            match = SECTION_HEADER_PATTERN.match(line)
            if match:
                # 保存前一个章节
                if current_section is not None:
                    current_section.end_line = i
                    current_section.content = "\n".join(lines[current_section.start_line + 1 : i])
                    sections.append(current_section)

                # 开始新章节
                section_number = match.group(1)
                section_title = match.group(2).strip()
                current_section = PmSessionSection(
                    number=section_number,
                    title=section_title,
                    start_line=i,
                    end_line=-1,
                    header_line=line,
                    content="",
                )
            elif current_section is None:
                pre_header_lines.append(line)

        # 保存最后一个章节
        if current_section is not None:
            current_section.end_line = len(lines)
            current_section.content = "\n".join(lines[current_section.start_line + 1 : len(lines)])
            sections.append(current_section)

        return PmSessionParseResult(
            file_path=file_path or Path(),
            total_lines=len(lines),
            sections=sections,
            pre_header_lines=pre_header_lines,
        )


class PmSessionCheckService:
    """PM_SESSION 健康检查服务"""

    def __init__(self, parser: PmSessionParser | None = None) -> None:
        self.parser = parser or PmSessionParser()

    def _check_ledger_freshness(self, file_path: Path) -> str | None:
        """落账新鲜度检查（CHG-SCPT-2026-166）

        若 PM_SESSION 之后仍有变更信号文件更新，返回告警文案（WARN 级软提示，
        不影响 is_healthy 判定）；无锚点文件或未滞后时返回 None。

        Args:
            file_path: PM_SESSION 文件路径（约定位于项目根目录）

        Returns:
            告警文案或 None
        """
        project_dir = file_path.parent
        anchor_files: list[Path] = []
        for pattern in CHANGE_SIGNAL_PATTERNS:
            for path in project_dir.rglob(pattern):
                if not path.is_file():
                    continue
                if any(part in SCAN_SKIP_DIRS for part in path.parts):
                    continue
                anchor_files.append(path)
        if not anchor_files:
            return None
        session_mtime = file_path.stat().st_mtime
        latest = max(f.stat().st_mtime for f in anchor_files)
        if latest > session_mtime:
            return "落账可能滞后：检测到 PM_SESSION 之后仍有变更文件更新"
        return None

    def check(self, file_path: Path) -> CheckResult:
        """检查 PM_SESSION 文件健康状态

        Args:
            file_path: PM_SESSION 文件路径

        Returns:
            CheckResult
        """
        if not file_path.exists():
            raise FileNotFoundError(f"PM_SESSION 文件不存在: {file_path}")

        result = self.parser.parse_file(file_path)
        file_size = file_path.stat().st_size
        file_size_kb = file_size / 1024.0

        missing_required = result.find_missing_required()
        deprecated_present = result.find_deprecated_present()
        is_oversized = file_size_kb > MAX_FILE_SIZE_KB or result.total_lines > MAX_FILE_LINES

        warnings: list[str] = []
        if missing_required:
            warnings.append(f"缺失必须章节: {sorted(missing_required)}")
        if deprecated_present:
            warnings.append(f"已归档章节回归: {sorted(deprecated_present)}")
        if file_size_kb > MAX_FILE_SIZE_KB:
            warnings.append(f"文件大小 {file_size_kb:.1f}KB 超过阈值 {MAX_FILE_SIZE_KB}KB")
        if result.total_lines > MAX_FILE_LINES:
            warnings.append(f"文件行数 {result.total_lines} 超过阈值 {MAX_FILE_LINES}")

        # CHG-SCPT-2026-166: 落账新鲜度 WARN（不影响 is_healthy）
        freshness_warning = self._check_ledger_freshness(file_path)
        if freshness_warning is not None:
            warnings.append(freshness_warning)

        return CheckResult(
            file_path=file_path,
            file_size_kb=round(file_size_kb, 1),
            total_lines=result.total_lines,
            missing_required=missing_required,
            deprecated_present=deprecated_present,
            is_oversized=is_oversized,
            warnings=warnings,
        )


class PmSessionArchiveService:
    """PM_SESSION 归档服务

    将指定章节的早期内容移动到归档文件，主文件保留最新内容 + 归档索引。
    """

    def __init__(self, parser: PmSessionParser | None = None) -> None:
        self.parser = parser or PmSessionParser()

    def archive_section(
        self,
        main_file: Path,
        archive_file: Path,
        section_number: str,
        keep_recent: int = 0,
        create_backup: bool = True,
    ) -> ArchiveResult:
        """归档指定章节

        Args:
            main_file: PM_SESSION 主文件路径
            archive_file: 归档文件路径
            section_number: 要归档的章节号（如 "6"）
            keep_recent: 主文件保留该章节最近 N 行内容（0=整章归档）
            create_backup: 是否创建主文件备份

        Returns:
            ArchiveResult
        """
        if not main_file.exists():
            raise FileNotFoundError(f"PM_SESSION 主文件不存在: {main_file}")

        parse_result = self.parser.parse_file(main_file)
        section = parse_result.get_section(section_number)
        if section is None:
            raise ValueError(f"章节 §{section_number} 不存在于 {main_file}")

        main_lines_before = parse_result.total_lines
        backup_file: Path | None = None

        if create_backup:
            backup_file = main_file.with_suffix(main_file.suffix + ".bak_archive")
            shutil.copy2(main_file, backup_file)

        # 计算要归档的行范围
        # 章节结构：[start_line]=header, [start_line+1, end_line)=content
        section_total_lines = section.end_line - section.start_line
        content_lines = section_total_lines - 1  # 不含 header
        if keep_recent >= content_lines:
            # 保留行数 >= 内容行数，无需归档
            return ArchiveResult(
                archive_file=archive_file,
                archived_sections=[section_number],
                archived_line_count=0,
                main_file_lines_before=main_lines_before,
                main_file_lines_after=main_lines_before,
                backup_file=backup_file,
            )

        lines_to_archive = main_file.read_text(encoding="utf-8").splitlines(keepends=False)

        if keep_recent == 0:
            # 整章归档（包括 header）：主文件删除整个章节
            archived_content_lines = lines_to_archive[section.start_line : section.end_line]
            archived_content = "\n".join(archived_content_lines)
            # 主文件：删除整个章节
            new_main_lines = (
                lines_to_archive[: section.start_line] + lines_to_archive[section.end_line :]
            )
        else:
            # 保留 header + 最后 keep_recent 行内容
            archive_end = section.end_line - keep_recent
            archived_content_lines = lines_to_archive[section.start_line + 1 : archive_end]
            # 归档内容：header 副本（方便归档文件识别章节）+ 归档的内容行
            archived_content = section.header_line + "\n" + "\n".join(archived_content_lines)
            # 主文件：保留 header 行 + 最后 keep_recent 行内容
            new_main_lines = (
                lines_to_archive[: section.start_line + 1]  # 保留到 header 行（含）
                + lines_to_archive[archive_end:]  # 保留最后 keep_recent 行
            )

        # 追加到归档文件
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        if archive_file.exists():
            existing = archive_file.read_text(encoding="utf-8")
            archive_file.write_text(
                existing.rstrip("\n") + "\n\n" + archived_content + "\n",
                encoding="utf-8",
            )
        else:
            # 新建归档文件，添加标题
            header = "# PM_SESSION 归档\n\n> 由 auto-pm pm-session archive 自动生成\n\n"
            archive_file.write_text(header + archived_content + "\n", encoding="utf-8")

        # 重写主文件
        main_file.write_text("\n".join(new_main_lines) + "\n", encoding="utf-8")

        # 验证重写后的行数
        new_parse = self.parser.parse_file(main_file)

        return ArchiveResult(
            archive_file=archive_file,
            archived_sections=[section_number],
            archived_line_count=len(archived_content_lines),
            main_file_lines_before=main_lines_before,
            main_file_lines_after=new_parse.total_lines,
            backup_file=backup_file,
        )

    def archive_section_8(
        self,
        main_file: Path,
        archive_file: Path,
        keep_entries: int = 8,
        create_backup: bool = True,
    ) -> ArchiveResult:
        """§8 专用归档：条目级归档（CHG-109）

        §8 Handoff Notes 结构（最新在上，旧在下）：
            ## 8. Handoff Notes          ← 保留（header）
            - current_state: ...          ← 保留（最新状态）
            - skill_handoff_xxx (最新)    ← 保留（最新 N 条）
            ...                           ← 归档（旧条目）
            - skill_handoff_zzz (最旧)    ← 归档
            > 归档说明                     ← 保留（归档指针）

        与 archive_section() 的区别：
            - archive_section 按"行"归档（适用于 §6 最新在下的结构）
            - archive_section_8 按"条目"归档（适用于 §8 最新在上的倒序结构）

        Args:
            main_file: PM_SESSION 主文件路径
            archive_file: 归档文件路径
            keep_entries: 保留最新 N 条 skill_handoff 条目（current_state* 始终保留）
            create_backup: 是否创建主文件备份

        Returns:
            ArchiveResult
        """
        if not main_file.exists():
            raise FileNotFoundError(f"PM_SESSION 主文件不存在: {main_file}")

        parse_result = self.parser.parse_file(main_file)
        section = parse_result.get_section("8")
        if section is None:
            raise ValueError(f"章节 §8 不存在于 {main_file}")

        main_lines_before = parse_result.total_lines
        all_lines = main_file.read_text(encoding="utf-8").splitlines(keepends=False)

        # §8 行范围 [section.start_line, section.end_line)
        section_lines = all_lines[section.start_line : section.end_line]

        # 识别条目：header + 后续空行 → 保留；然后逐条识别
        # header 行（index 0）+ 后续空行
        header_end = 1
        while header_end < len(section_lines) and not section_lines[header_end].strip():
            header_end += 1

        # 从 header_end 开始识别条目（每个条目 = 起始行 + 后续空行）
        entries: list[tuple[int, int, str]] = []  # (start_idx, end_idx, entry_type)
        i = header_end
        while i < len(section_lines):
            stripped = section_lines[i].strip()
            if not stripped:
                i += 1
                continue

            if stripped.startswith(SECTION8_CURRENT_STATE_PREFIX):
                etype = "current_state"
            elif stripped.startswith(SECTION8_SKILL_HANDOFF_PREFIX):
                etype = "skill_handoff"
            elif stripped.startswith(SECTION8_ARCHIVE_NOTE_PREFIX):
                etype = "archive_note"
            else:
                etype = "other"

            # 条目范围 [start, end) 包含起始行 + 后续空行
            start = i
            j = i + 1
            while j < len(section_lines) and not section_lines[j].strip():
                j += 1
            entries.append((start, j, etype))
            i = j

        # 分离 skill_handoff 条目
        skill_handoff_entries = [(s, e, t) for s, e, t in entries if t == "skill_handoff"]

        # 备份
        backup_file: Path | None = None
        if create_backup:
            backup_file = main_file.with_suffix(main_file.suffix + ".bak_archive")
            shutil.copy2(main_file, backup_file)

        if len(skill_handoff_entries) <= keep_entries:
            # 无需归档
            return ArchiveResult(
                archive_file=archive_file,
                archived_sections=["8"],
                archived_line_count=0,
                main_file_lines_before=main_lines_before,
                main_file_lines_after=main_lines_before,
                backup_file=backup_file,
            )

        # 确定要归档的 skill_handoff 条目（超出 keep_entries 的旧条目）
        entries_to_archive = skill_handoff_entries[keep_entries:]
        archive_line_indices: set[int] = set()
        for start, end, _ in entries_to_archive:
            for idx in range(start, end):
                archive_line_indices.add(idx)

        # 构造归档内容和新 §8 内容
        archived_lines: list[str] = []
        new_section_lines: list[str] = []
        for idx, line in enumerate(section_lines):
            if idx in archive_line_indices:
                archived_lines.append(line)
            else:
                new_section_lines.append(line)

        # 归档内容：添加分隔标记
        archived_content = (
            f"--- §8 归档补充（{date.today().isoformat()}）："
            f"以下 {len(entries_to_archive)} 条 skill_handoff 从 Active PM_SESSION §8 迁移 ---\n\n"
            + "\n".join(archived_lines)
        )

        # 新主文件：替换 §8 范围
        new_main_lines = (
            all_lines[: section.start_line] + new_section_lines + all_lines[section.end_line :]
        )

        # 归档文件大小检查（超 200KB 切分到新文件）
        target_archive = self._resolve_archive_file(archive_file)

        # 追加到归档文件
        target_archive.parent.mkdir(parents=True, exist_ok=True)
        if target_archive.exists():
            existing = target_archive.read_text(encoding="utf-8")
            target_archive.write_text(
                existing.rstrip("\n") + "\n\n" + archived_content + "\n",
                encoding="utf-8",
            )
        else:
            header = "# PM_SESSION 归档\n\n> 由 auto-pm pm-session archive 自动生成\n\n"
            target_archive.write_text(header + archived_content + "\n", encoding="utf-8")

        # 重写主文件
        main_file.write_text("\n".join(new_main_lines) + "\n", encoding="utf-8")

        new_parse = self.parser.parse_file(main_file)

        return ArchiveResult(
            archive_file=target_archive,
            archived_sections=["8"],
            archived_line_count=len(archived_lines),
            main_file_lines_before=main_lines_before,
            main_file_lines_after=new_parse.total_lines,
            backup_file=backup_file,
        )

    def _resolve_archive_file(self, archive_file: Path) -> Path:
        """归档文件大小检查：超 ARCHIVE_FILE_MAX_SIZE_KB 切分到新文件

        防止单个归档文件过大（超过 Read 128KB 限制），当文件超过 200KB 时
        自动创建带日期的新归档文件。

        Args:
            archive_file: 原始归档文件路径

        Returns:
            实际使用的归档文件路径（可能是新切分的文件）
        """
        if not archive_file.exists():
            return archive_file

        size_kb = archive_file.stat().st_size / 1024.0
        if size_kb <= ARCHIVE_FILE_MAX_SIZE_KB:
            return archive_file

        # 超过阈值，创建新归档文件：archive_auto_<YYYYMMDD>.md
        date_str = date.today().strftime("%Y%m%d")
        stem = archive_file.stem  # 如 PM_SESSION_SW-2026-008_archive_V0.6.0
        new_name = f"{stem}_auto_{date_str}.md"
        new_file = archive_file.parent / new_name

        # 同日文件已存在则加序号
        seq = 1
        while new_file.exists():
            new_file = archive_file.parent / f"{stem}_auto_{date_str}_{seq}.md"
            seq += 1

        return new_file


def generate_view(parse_result: PmSessionParseResult) -> str:
    """从 PM_SESSION 解析结果生成只读视图

    提取 §2 Current Focus + §3 Status Summary，生成简洁的只读 markdown 视图。

    Args:
        parse_result: PM_SESSION 解析结果

    Returns:
        只读视图 markdown 字符串
    """
    lines: list[str] = [
        "# PM_SESSION 只读视图",
        "",
        f"> 源文件: {parse_result.file_path}",
        f"> 总行数: {parse_result.total_lines}",
        f"> 章节数: {len(parse_result.sections)}",
        "",
    ]

    # §2 Current Focus
    section_2 = parse_result.get_section("2")
    if section_2:
        lines.append(f"## §2 {section_2.title}")
        lines.append("")
        lines.append(section_2.content.rstrip())
        lines.append("")

    # §3 Status Summary
    section_3 = parse_result.get_section("3")
    if section_3:
        lines.append(f"## §3 {section_3.title}")
        lines.append("")
        lines.append(section_3.content.rstrip())
        lines.append("")

    # §9 Next Actions
    section_9 = parse_result.get_section("9")
    if section_9:
        lines.append(f"## §9 {section_9.title}")
        lines.append("")
        lines.append(section_9.content.rstrip())
        lines.append("")

    return "\n".join(lines)
