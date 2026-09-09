"""PLC-HMI 概念映射：SFB 库函数（批量解析器（批量解析多个变量表文件））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

批量解析器

V2.3 Week3 T14：遍历目录多文件解析，聚合多个 ParseResult。

设计原则：
- 使用 format_detector 自动识别格式 + get_parser_for_format 工厂获取 Parser
- 不识别的格式跳过（记录到 skipped 列表，不抛异常）
- 单文件解析失败不中断整体批次（返回的 ParseResult 含 errors）
- 支持 recursive 递归扫描子目录

用法：
    batch_parser = BatchParser()
    results = batch_parser.parse_directory(Path("path/to/dir"), recursive=True)
    for result in results:
        if result.success:
            print(f"解析成功: {result.entry_count} 条")
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.vartable.models import FormatType, ParseResult
from auto_pm.vartable.parsers.format_detector import (
    detect_format,
    get_parser_for_format,
)

# 支持批量扫描的文件扩展名（用于 parse_directory 过滤候选文件）
# 不含 .csv/.txt/.md/.doc/.docx 等需内容特征识别的扩展名（避免误扫无关文件）
BATCH_SCAN_EXTENSIONS: tuple[str, ...] = (
    ".asc",
    ".asn",
    ".wr3",
    ".scl",
    ".awl",
    ".yml",
    ".yaml",
)

# 显式文件名（优先级最高，parse_directory 也会扫描）
BATCH_SCAN_FILENAMES: tuple[str, ...] = (
    "io_points.csv",
    "program_blocks.yml",
    "program_blocks.yaml",
    "communications.yml",
    "communications.yaml",
)


class BatchParser:
    """批量解析器

    遍历目录或文件列表，自动识别格式并解析，聚合多个 ParseResult。

    用法：
        batch_parser = BatchParser()
        results = batch_parser.parse_directory(Path("dir"), recursive=True)
        for result in results:
            if result.success:
                print(f"解析成功: {result.entry_count} 条")
    """

    def parse_directory(
        self,
        dir_path: str | Path,
        recursive: bool = False,
    ) -> list[ParseResult]:
        """批量解析目录下所有支持的格式

        Args:
            dir_path: 目录路径
            recursive: 是否递归扫描子目录（默认 False 只扫顶层）

        Returns:
            ParseResult 列表（每个文件一个 ParseResult，按文件名排序）
            不识别的格式跳过；解析失败的文件返回 success=False 的 ParseResult

        Raises:
            FileNotFoundError: 目录不存在
            NotADirectoryError: 路径不是目录
        """
        path = Path(dir_path)
        if not path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")
        if not path.is_dir():
            raise NotADirectoryError(f"路径不是目录: {dir_path}")

        # 收集候选文件
        if recursive:
            candidates = sorted(path.rglob("*"))
        else:
            candidates = sorted(path.iterdir())

        file_paths: list[Path] = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if self._is_supported(candidate):
                file_paths.append(candidate)

        return self.parse_files(file_paths)

    def parse_files(self, file_paths: list[Path]) -> list[ParseResult]:
        """批量解析指定文件列表

        Args:
            file_paths: 文件路径列表

        Returns:
            ParseResult 列表（每个文件一个 ParseResult，保持输入顺序）
            不识别的格式返回 success=False 的 ParseResult（含 warning）
        """
        results: list[ParseResult] = []
        for file_path in file_paths:
            result = self._parse_single(file_path)
            results.append(result)
        return results

    @staticmethod
    def _is_supported(file_path: Path) -> bool:
        """判断文件是否可能被支持（基于扩展名或文件名）

        用于 parse_directory 候选过滤，避免对每个文件都做内容检测。
        最终是否真正支持由 detect_format 决定。
        """
        ext = file_path.suffix.lower()
        if ext in BATCH_SCAN_EXTENSIONS:
            return True
        if file_path.name in BATCH_SCAN_FILENAMES:
            return True
        return False

    @staticmethod
    def _parse_single(file_path: Path) -> ParseResult:
        """解析单个文件（自动识别格式 + 工厂获取 Parser）

        Args:
            file_path: 文件路径

        Returns:
            ParseResult（成功/失败/不识别）
        """
        fmt = detect_format(file_path)
        if fmt == FormatType.UNKNOWN:
            return ParseResult(
                success=False,
                var_table=None,
                errors=(),
                warnings=(f"未识别的格式，跳过: {file_path}",),
            )

        parser_cls = get_parser_for_format(fmt)
        if parser_cls is None:
            return ParseResult(
                success=False,
                var_table=None,
                errors=(),
                warnings=(f"格式 {fmt.value} 无对应解析器: {file_path}",),
            )

        # 实例化并调用 parse()
        parser = parser_cls()
        result = parser.parse(file_path)
        if isinstance(result, ParseResult):
            return result
        return ParseResult(
            success=False,
            var_table=None,
            errors=(),
            warnings=(f"解析器返回类型异常: {file_path}",),
        )
