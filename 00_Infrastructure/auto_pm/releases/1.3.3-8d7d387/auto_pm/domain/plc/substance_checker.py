"""PLC-HMI 概念映射：SFB 库函数（实质检查器（检查 PLC 代码实质内容））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

文档实质化检查器

检查 PRD/DSN/INT/TEC 文档是否为空壳（字数 < 阈值）、章节是否完整、关键内容是否填充。
用于 V2.0.1-B 实质化检查能力。
"""

from __future__ import annotations

import logging
import os
import re

from auto_pm.core.paths import find_prd_dir
from auto_pm.models.plc import CheckResult

log = logging.getLogger(__name__)

# 文档字数阈值（中文按字符数，英文按词数，任一达标即视为 PASS）
_MIN_CHINESE_CHARS = 800
_MIN_ENGLISH_WORDS = 1000

# 最少章节数（## 标题数量）
_MIN_SECTION_COUNT = 3

# 占位符关键词（出现这些词视为未填充）
_PLACEHOLDER_KEYWORDS = [
    "待补充",
    "待填写",
    "TODO",
    "TBD",
    "待完善",
    "待更新",
    "占位",
    "placeholder",
]


class SubstanceChecker:
    """文档实质化检查器

    检查 PRD/DSN/INT/TEC 文档的实质化程度：
    - 文档是否存在
    - 字数是否达到阈值
    - 章节是否完整
    - 关键内容是否填充（非占位符）
    """

    # PRD 文档类型与文件名映射
    PRD_DOCS = [
        ("REQ", "需求分析文档_REQ.md"),
        ("INT", "接口文档_INT.md"),
        ("DSN", "详细设计说明书_DSN.md"),
        ("TEC", "技术方案文档_TEC.md"),
    ]

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)

    def check_project(self, project_path: str) -> CheckResult:
        """检查项目文档实质化程度

        Args:
            project_path: 项目根目录绝对路径

        Returns:
            CheckResult: 检查结果
        """
        result = CheckResult(project_path=project_path)
        result.project_type = "substance_check"

        found = find_prd_dir(project_path)
        if found is None:
            result.add(
                item="PRD 目录",
                status="fail",
                message=f"PRD 目录不存在: {project_path}",
            )
            return result
        prd_dir, _prd_name = found

        # 2. 逐个检查 PRD 文档
        for doc_type, filename in self.PRD_DOCS:
            self._check_doc(prd_dir, filename, doc_type, result)

        log.info(
            "文档实质化检查完成: %s - pass=%d warn=%d fail=%d",
            os.path.basename(project_path),
            result.pass_count,
            result.warn_count,
            result.fail_count,
        )
        return result

    def check_workspace(self, scan_depth: int = 4) -> list[CheckResult]:
        """扫描工作空间下所有项目并逐一检查文档实质化

        Args:
            scan_depth: 扫描深度

        Returns:
            所有项目的检查结果列表
        """
        results: list[CheckResult] = []
        self._scan(self.workspace_root, results, depth=0, max_depth=scan_depth)
        return results

    def _check_doc(
        self,
        prd_dir: str,
        filename: str,
        doc_type: str,
        result: CheckResult,
    ) -> None:
        """检查单个文档的实质化程度"""
        doc_path = os.path.join(prd_dir, filename)

        # 1. 文档是否存在
        if not os.path.isfile(doc_path):
            result.add(
                item=f"{doc_type} 文档存在性",
                status="fail",
                message=f"文件不存在: {filename}",
            )
            return

        result.add(item=f"{doc_type} 文档存在性", status="pass", message="")

        # 读取文档内容
        try:
            with open(doc_path, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            result.add(
                item=f"{doc_type} 文档读取",
                status="fail",
                message=f"读取失败: {e}",
            )
            return

        # 2. 字数检查（中文按字符数，英文按词数，任一达标即 PASS）
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", content))
        english_words = len(re.findall(r"[a-zA-Z]+", content))
        if chinese_chars >= _MIN_CHINESE_CHARS or english_words >= _MIN_ENGLISH_WORDS:
            result.add(
                item=f"{doc_type} 字数",
                status="pass",
                message=(
                    f"中文字符 {chinese_chars}（阈值 {_MIN_CHINESE_CHARS}），"
                    f"英文单词 {english_words}（阈值 {_MIN_ENGLISH_WORDS}）"
                ),
            )
        else:
            result.add(
                item=f"{doc_type} 字数",
                status="warn",
                message=(
                    f"中文字符 {chinese_chars} < 阈值 {_MIN_CHINESE_CHARS}，"
                    f"英文单词 {english_words} < 阈值 {_MIN_ENGLISH_WORDS}（疑似空壳）"
                ),
            )

        # 3. 章节数检查（## 标题，排除 ### 及以上，允许 ## 后无空格）
        section_count = len(re.findall(r"^##(?!\s*#)\s*", content, re.MULTILINE))
        if section_count < _MIN_SECTION_COUNT:
            result.add(
                item=f"{doc_type} 章节数",
                status="warn",
                message=f"章节数 {section_count} < 阈值 {_MIN_SECTION_COUNT}",
            )
        else:
            result.add(
                item=f"{doc_type} 章节数",
                status="pass",
                message=f"章节数 {section_count}",
            )

        # 4. 占位符检查（按密度判定严重程度）
        placeholder_count = 0
        placeholder_hits: list[str] = []
        content_lower = content.lower()
        for keyword in _PLACEHOLDER_KEYWORDS:
            count = content_lower.count(keyword.lower())
            if count > 0:
                placeholder_count += count
                placeholder_hits.append(keyword)

        if placeholder_count == 0:
            result.add(item=f"{doc_type} 占位符", status="pass", message="")
        else:
            # 占位符密度 = 占位符出现次数 / 非空行数
            non_empty_lines = [line for line in content.split("\n") if line.strip()]
            line_count = max(len(non_empty_lines), 1)
            density = placeholder_count / line_count
            density_pct = round(density * 100, 1)

            if density > 0.7:
                status = "fail"
            elif density > 0.3:
                status = "warn"
            else:
                status = "pass"

            result.add(
                item=f"{doc_type} 占位符",
                status=status,
                message=(
                    f"发现占位符 {placeholder_count} 次，密度 {density_pct}%"
                    f"（{', '.join(placeholder_hits)}）"
                ),
            )

    def _scan(
        self,
        path: str,
        results: list[CheckResult],
        depth: int,
        max_depth: int,
    ) -> None:
        """递归扫描目录，识别项目"""
        if depth > max_depth:
            return

        try:
            entries = os.listdir(path)
        except OSError:
            return

        for entry in entries:
            entry_path = os.path.join(path, entry)
            if not os.path.isdir(entry_path):
                continue
            if entry.startswith(".") or entry.startswith("__"):
                continue

            # 判断是否是项目目录（有 PRD 目录或 .plc.json 或 .copier-answers.yml）
            if (
                find_prd_dir(entry_path) is not None
                or os.path.isfile(os.path.join(entry_path, ".plc.json"))
                or os.path.isfile(os.path.join(entry_path, ".copier-answers.yml"))
            ):
                result = self.check_project(entry_path)
                results.append(result)
            else:
                self._scan(entry_path, results, depth + 1, max_depth)
