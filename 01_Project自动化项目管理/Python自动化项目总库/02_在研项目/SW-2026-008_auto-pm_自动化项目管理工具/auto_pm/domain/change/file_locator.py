"""PLC-HMI 概念映射：SFB 库函数（文件定位器（查找项目中的变更单文件））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变更单文件路径定位器（M3-Iter2 从 ChangeService 拆分）

负责：
- 项目路径解析（_get_project_path）
- 变更编号生成（_generate_change_number）
- 变更单文件路径计算（_get_change_file_path）
- 跨项目变更单文件查找（_find_change_file）
- 全工作空间变更单扫描（_scan_all_change_files）

ChangeService 通过组合方式使用本模块，保持向后兼容。

M3-Iter6：路径常量统一到 auto_pm.core.paths，消除硬编码。
V0.2.1-P1-6：find_change_file/scan_all_change_files 改为递归识别项目目录，
              避免找到非项目目录（如 0100_PLC自动化/00_项目管理/）下的残留文件。
"""

from __future__ import annotations

import datetime
import logging
import os
import re

from auto_pm.change.parser import ChgParser
from auto_pm.change.path_resolver import (
    extract_domain_from_change_number,
    find_ledger_file,
    scan_change_files,
)
from auto_pm.core.paths import CHANGE_REQUESTS_PATH
from auto_pm.models import ChangeSummary
from auto_pm.utils.file_utils import read_file

log = logging.getLogger(__name__)


class ChangeFileLocator:
    """变更单文件路径定位器

    CHG-SCPT-2026-146: 5大过程组统一路径，破坏性切换后不再区分 PLC / Python。
    封装变更单文件的路径约定（04_监控/01_变更管理/）和查找逻辑。
    """

    # 变更单搜索路径（直接拼接 CHG-{domain}/{change_number}.md 的基础路径，含 01_变更单）
    # CHG-SCPT-2026-146: 5大过程组统一路径，破坏性切换后单路径
    # 注：path_resolver._CHANGE_SEARCH_PATHS 用 CHANGE_SCAN_PATH（不含 01_变更单）做递归扫描；
    #     此处需要含 01_变更单 的完整路径以直接定位文件
    CHANGE_FILE_SEARCH_PATHS = [
        os.path.join(*CHANGE_REQUESTS_PATH),
        os.path.join("11_监控", "01_变更管理", "01_变更单"),
        os.path.join("00_项目管理", "01_变更管理", "01_变更单"),
    ]

    def __init__(self, workspace_root: str, parser: ChgParser) -> None:
        self.workspace_root = workspace_root
        self._parser = parser

    def get_project_path(self, project_id: str) -> str | None:
        """根据项目编号获取项目路径

        项目目录命名约定为 ``{project_id}_{project_name}``（见 cmd_create），
        因此优先按 ``{project_id}_`` 前缀匹配；同时保留精确匹配以向后兼容。

        V0.2.1-P2-3: 递归搜索工作空间子目录。项目可能创建在技术栈子目录下
        （如 0100_PLC自动化/ 或 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/），
        仅搜索 workspace_root 一层会找不到这些项目。
        """
        # 0. Check if workspace root itself matches the project_id (e.g. running in auto-pm own workspace root)
        try:
            # Check if PM_SESSION_*.md exists in workspace_root and matches project_id
            for entry in os.listdir(self.workspace_root):
                if entry.startswith("PM_SESSION_") and entry.endswith(".md"):
                    pid = entry[len("PM_SESSION_") : -len(".md")]
                    if pid == project_id:
                        return self.workspace_root
            # Or if .copier-answers.yml in workspace_root has project_id
            answers_path = os.path.join(self.workspace_root, ".copier-answers.yml")
            if os.path.isfile(answers_path):
                import yaml

                with open(answers_path, encoding="utf-8") as f:
                    answers = yaml.safe_load(f) or {}
                if answers.get("project_id") == project_id:
                    return self.workspace_root
        except Exception:
            pass

        # 1. 精确匹配（向后兼容：目录名 == project_id）
        candidate = os.path.join(self.workspace_root, project_id)
        if os.path.isdir(candidate):
            return candidate

        if not os.path.isdir(self.workspace_root):
            return None

        prefix = project_id + "_"

        # 2. 工作空间根目录直接匹配
        try:
            for name in os.listdir(self.workspace_root):
                full_path = os.path.join(self.workspace_root, name)
                if (name == project_id or name.startswith(prefix)) and os.path.isdir(full_path):
                    return full_path
        except OSError:
            pass

        # V0.2.1-P2-3: 3. 递归搜索子目录（项目可能在技术栈子目录下）
        return self._recursive_find_project_dir(
            self.workspace_root, project_id, prefix, depth=0, max_depth=4
        )

    def _recursive_find_project_dir(
        self,
        current_dir: str,
        project_id: str,
        prefix: str,
        depth: int,
        max_depth: int,
    ) -> str | None:
        """递归搜索项目目录

        策略：
        1. 遍历当前目录的子目录
        2. 若子目录名匹配 project_id 或前缀，返回该目录
        3. 若子目录不是项目目录，递归搜索
        4. 若子目录是项目目录（但不匹配），跳过（不递归进入其他项目）
        """
        if depth > max_depth:
            return None

        try:
            entries = os.listdir(current_dir)
        except OSError:
            return None

        # 跳过隐藏目录和 Python 缓存目录
        filtered = [e for e in entries if not e.startswith(".") and not e.startswith("__")]

        for entry in filtered:
            entry_path = os.path.join(current_dir, entry)
            if not os.path.isdir(entry_path):
                continue

            # 检查是否是目标项目目录
            if entry == project_id or entry.startswith(prefix):
                return entry_path

            # 若不是项目目录，递归搜索
            # 使用与 ProjectScanner 相同的标志判断是否为项目目录
            if not self._is_project_dir(entry_path):
                result = self._recursive_find_project_dir(
                    entry_path, project_id, prefix, depth + 1, max_depth
                )
                if result:
                    return result

        return None

    def generate_change_number(self, project_path: str, domain: str) -> str:
        """生成变更编号 CHG-{DOMAIN}-{YYYY}-{XXX}

        扫描已有变更单，确定下一个序号
        """
        year = str(datetime.date.today().year)
        change_files = scan_change_files(project_path)

        # 找出同领域同年的最大序号
        max_seq = 0
        prefix = f"CHG-{domain}-{year}-"
        for cf in change_files:
            basename = os.path.splitext(os.path.basename(cf))[0]
            if basename.startswith(prefix):
                seq_str = basename[len(prefix) :]
                try:
                    seq = int(seq_str)
                    max_seq = max(max_seq, seq)
                except ValueError:
                    pass

        # 同步检查台帐中已记录的最大序号（防止文件删除后编号回退）
        # 注意：必须解析台帐表格的"变更编号"列，而非全文正则匹配，
        # 否则描述列中的 CHG 编号引用（如"原 CHG-PLC-2026-006"）会被误判为有效条目
        ledger_path = find_ledger_file(project_path)
        if ledger_path:
            ledger_content = read_file(ledger_path)
            if ledger_content:
                for line in ledger_content.splitlines():
                    line = line.strip()
                    if not line.startswith("|"):
                        continue
                    cells = [c.strip() for c in line.split("|")]
                    if len(cells) < 3:
                        continue
                    # 第2列是"变更编号"列（首列 | 后是空字符串，所以 cells[2] 是序号后的变更编号）
                    # 跳过表头和分隔行
                    cn_cell = cells[2]
                    if "变更编号" in cn_cell or cn_cell.startswith("---"):
                        continue
                    # 跳过标记为缺失的条目
                    if "缺失" in cn_cell:
                        continue
                    for match in re.finditer(rf"{re.escape(prefix)}(\d+)", cn_cell):
                        seq = int(match.group(1))
                        max_seq = max(max_seq, seq)

        next_seq = max_seq + 1
        result = f"CHG-{domain}-{year}-{next_seq:03d}"
        log.debug("生成变更编号: %s (已有同领域最大序号=%d)", result, max_seq)
        return result

    def get_change_file_path(self, project_path: str, change_number: str) -> str:
        """根据变更编号获取文件路径

        按优先级搜索多套目录约定（PLC / Python），命中已有目录返回，
        未命中时使用 PLC 约定路径（默认创建路径）。

        格式: {搜索路径}/CHG-{DOMAIN}/CHG-{DOMAIN}-{YYYY}-{XXX}.md
        """
        domain = extract_domain_from_change_number(change_number)
        # 优先匹配已有目录
        for rel_path in self.CHANGE_FILE_SEARCH_PATHS:
            base_dir = os.path.join(project_path, rel_path, f"CHG-{domain}")
            if os.path.isdir(base_dir):
                return os.path.join(base_dir, f"{change_number}.md")
        # 未匹配已有目录 → 使用5大过程组统一路径（默认创建路径）
        # CHG-SCPT-2026-146: 统一路径 04_监控/01_变更管理/01_变更单/
        return os.path.join(
            project_path,
            *CHANGE_REQUESTS_PATH,
            f"CHG-{domain}",
            f"{change_number}.md",
        )

    def find_change_file(self, change_number: str, project_id: str | None = None) -> str | None:
        """根据变更编号查找文件

        递归遍历工作空间下的项目目录，按 PLC / Python 两套路径约定搜索。

        识别项目目录的标志（与 ProjectScanner 对齐）：
        - .copier-answers.yml
        - .plc.json
        - PM_SESSION_*.md

        非项目目录（如 0100_PLC自动化/00_项目管理/）会被跳过，
        避免找到残留的空变更单文件。

        Args:
            change_number: 变更单编号
            project_id: 项目编号（可选）。提供时优先在该项目目录内搜索，
                       避免跨项目单号冲突时返回错误项目的文件（TD-A04 修复）。
                       未提供或项目定位失败时回退到递归全工作空间搜索（向后兼容）。
        """
        domain = extract_domain_from_change_number(change_number)
        if not domain:
            log.warning("查找变更单: 无法从编号提取领域 %s", change_number)
            return None

        if not os.path.isdir(self.workspace_root):
            log.warning("查找变更单: 工作空间目录不存在 %s", self.workspace_root)
            return None

        # TD-A04 修复：提供 project_id 时优先在该项目目录内搜索
        if project_id:
            project_path = self.get_project_path(project_id)
            if project_path:
                result = self._find_change_in_project(project_path, change_number, domain)
                if result:
                    return result
                log.debug(
                    "查找变更单: project_id=%s 定位到项目目录但未找到变更单 %s，回退递归搜索",
                    project_id,
                    change_number,
                )
            else:
                log.warning(
                    "查找变更单: project_id=%s 未定位到项目目录，回退递归搜索",
                    project_id,
                )

        # 递归遍历工作空间，只在项目目录内搜索变更单文件（向后兼容）
        return self._recursive_find_change_file(
            self.workspace_root, change_number, domain, depth=0, max_depth=5
        )

    def _find_change_in_project(
        self, project_path: str, change_number: str, domain: str
    ) -> str | None:
        """在指定项目目录内按 PLC/Python 两套路径约定搜索变更单文件

        TD-A04 修复新增：提供 project_id 时走此方法，避免递归全工作空间。
        """
        for rel_path in self.CHANGE_FILE_SEARCH_PATHS:
            candidate = os.path.join(project_path, rel_path, f"CHG-{domain}", f"{change_number}.md")
            if os.path.isfile(candidate):
                return candidate
        return None

    def _is_project_dir(self, dir_path: str) -> bool:
        """判断目录是否为项目目录（与 ProjectScanner 标志对齐）

        项目目录标志：
        - .copier-answers.yml（Copier 模板生成的项目）
        - .plc.json（PLC 项目）
        - PM_SESSION_*.md（PM 会话记录）
        """
        if os.path.isfile(os.path.join(dir_path, ".copier-answers.yml")):
            return True
        if os.path.isfile(os.path.join(dir_path, ".plc.json")):
            return True
        try:
            for entry in os.listdir(dir_path):
                if entry.startswith("PM_SESSION_") and entry.endswith(".md"):
                    return True
        except OSError:
            pass
        return False

    def _recursive_find_change_file(
        self,
        current_dir: str,
        change_number: str,
        domain: str,
        depth: int,
        max_depth: int,
    ) -> str | None:
        """递归查找变更单文件

        策略：
        1. 进入目录后先判断是否为项目目录
        2. 若是项目目录，按 PLC/Python 两套路径约定搜索变更单文件
        3. 若不是项目目录，继续递归子目录
        """
        if depth > max_depth:
            return None

        try:
            entries = os.listdir(current_dir)
        except OSError:
            return None

        # 跳过隐藏目录和 Python 缓存目录
        filtered_entries = [e for e in entries if not e.startswith(".") and not e.startswith("__")]

        # 若是项目目录，按路径约定搜索变更单文件
        if self._is_project_dir(current_dir):
            for rel_path in self.CHANGE_FILE_SEARCH_PATHS:
                candidate = os.path.join(
                    current_dir,
                    rel_path,
                    f"CHG-{domain}",
                    f"{change_number}.md",
                )
                if os.path.isfile(candidate):
                    return candidate
            # 项目目录内不再递归（变更单应放在项目根的标准路径下）
            return None

        # 非项目目录：递归子目录
        for entry in filtered_entries:
            entry_path = os.path.join(current_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            result = self._recursive_find_change_file(
                entry_path, change_number, domain, depth + 1, max_depth
            )
            if result:
                return result

        return None

    def scan_all_change_files(self) -> list[ChangeSummary]:
        """扫描工作空间所有项目的变更单文件（无 DB 时的回退路径）

        递归遍历 workspace_root，只在项目目录内调用 scan_change_files
        解析所有 CHG-*.md 文件并转换为 ChangeSummary。

        V0.2.1-P1-6：改为递归识别项目目录，避免扫描非项目目录
        （如 0100_PLC自动化/00_项目管理/）下的残留文件。
        """
        summaries: list[ChangeSummary] = []
        if not os.path.isdir(self.workspace_root):
            return summaries

        self._recursive_scan_projects(self.workspace_root, summaries, depth=0, max_depth=5)
        return summaries

    def _recursive_scan_projects(
        self,
        current_dir: str,
        summaries: list[ChangeSummary],
        depth: int,
        max_depth: int,
    ) -> None:
        """递归扫描项目目录，收集变更单摘要"""
        if depth > max_depth:
            return

        try:
            entries = os.listdir(current_dir)
        except OSError:
            return

        filtered_entries = [e for e in entries if not e.startswith(".") and not e.startswith("__")]

        # 若是项目目录，扫描其变更单文件
        if self._is_project_dir(current_dir):
            for cf in scan_change_files(current_dir):
                try:
                    cr = self._parser.parse(cf)
                    summaries.append(self._parser.to_summary(cr))
                except Exception as e:
                    log.warning("解析变更单文件失败，跳过: %s: %s", cf, e)
            # 项目目录内不再递归
            return

        # 非项目目录：递归子目录
        for entry in filtered_entries:
            entry_path = os.path.join(current_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            self._recursive_scan_projects(entry_path, summaries, depth + 1, max_depth)
