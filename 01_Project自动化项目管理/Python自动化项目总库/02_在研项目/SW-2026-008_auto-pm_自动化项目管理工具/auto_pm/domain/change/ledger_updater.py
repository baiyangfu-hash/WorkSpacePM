"""PLC-HMI 概念映射：SFB 库函数（台账更新器（同步变更单到台账数据库））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

版本变更台帐更新器"""

from __future__ import annotations

import logging
import re

from auto_pm.utils.file_utils import read_file, write_file

log = logging.getLogger(__name__)

# 驾驶舱维护的「变更单索引」表骨架（与 path_resolver.get_or_create_ledger_file 新建台账时写入的一致）
INDEX_TABLE_SECTION = (
    "## 变更单索引\n\n"
    "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
    "|------|----------|------|--------|----------|----------|----------|------|\n"
)


class LedgerUpdater:
    """版本变更台帐更新器"""

    def ensure_index_table(self, ledger_path: str) -> bool:
        """台账没有「变更单索引」表时在文末补上空表骨架（D09 迁入硬挡 N3）

        模板生成的台账和 DJ-2026-009 的现有台账都没有这张表，建单写不进、
        ``ledger reconcile --fix`` 也补不了行。只由对账自愈调用；已有表格时不改动文件。

        Returns:
            是否补建了表格
        """
        content = read_file(ledger_path)
        if not content or self._has_index_table(content) or self._legacy_table_at(content):
            # 已有能认出的旧格式明细表（DJ-2026-009）时行就写在那张表里，不再另补一张
            return False
        separator = "" if content.endswith("\n\n") else ("\n" if content.endswith("\n") else "\n\n")
        write_file(ledger_path, content + separator + INDEX_TABLE_SECTION)
        log.info("台帐已补建变更单索引表: %s", ledger_path)
        return True

    @staticmethod
    def _has_index_table(content: str) -> bool:
        """与 _insert_row_to_index_table 同一判定：标题行之后、遇到正文之前出现表格分隔行"""
        in_index = False
        for line in content.split("\n"):
            stripped = line.strip()
            if "变更单索引" in stripped:
                in_index = True
                continue
            if not in_index:
                continue
            if stripped.startswith("|"):
                if re.match(r"^\|[\s\-:|]+\|$", stripped):
                    return True
            elif stripped:
                in_index = False
        return False

    def update(
        self,
        ledger_path: str,
        change_number: str,
        desc: str,
        applicant: str = "",
        apply_date: str = "",
    ) -> None:
        """在台帐的变更单索引部分追加一条记录

        Args:
            ledger_path: 台帐文件路径
            change_number: 变更编号 (如 CHG-DOCU-2026-001)
            desc: 变更描述
            applicant: 变更申请人（CHG-085 新增，写入"申请人"列）
            apply_date: 申请日期（CHG-085 新增，写入"申请日期"列，格式 YYYY-MM-DD）
        """
        content = read_file(ledger_path)
        if not content:
            log.warning("台帐文件为空或读取失败: %s", ledger_path)
            return

        # 去重检查：仅变更编号列中的精确编号可阻止追加。
        if any(
            self._matches_change_number_row(line, change_number)
            for line in content.split("\n")
        ):
            log.info("台帐中已存在 %s，跳过追加", change_number)
            return

        # 提取领域
        domain = ""
        parts = change_number.split("-")
        if len(parts) >= 2:
            domain = parts[1]

        # 生成新的序号
        seq = self._get_next_sequence(content)

        # 生成变更单链接
        link = f"[→ {change_number}](./01_变更单/CHG-{domain}/{change_number}.md)"

        legacy = self._legacy_table_header(content)
        if legacy is not None:
            # 旧格式台帐（如 DJ-2026-009“变更明细台账”）：按它自己的表头列顺序填
            updated = self._insert_row_to_legacy_table(
                content,
                self._legacy_row(
                    legacy,
                    {"number": change_number, "domain": domain, "applicant": applicant,
                     "apply_date": apply_date, "desc": desc, "status": "🔄待处理"},
                ),
            )
            if updated != content:
                write_file(ledger_path, updated)
                log.info("台帐已更新（旧格式表）: 追加 %s", change_number)
            else:
                log.warning("台帐更新失败: 未找到变更单索引表格 %s", ledger_path)
            return

        # 构造新行（CHG-085：填入申请人/申请日期列，原 L47 留空导致台账字段缺失）
        # 列结构：| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |
        new_row = (
            f"| {seq:03d} | {link} | {domain} | {applicant} | {apply_date} "
            f"| {desc} | | 🔄待处理 |\n"
        )

        # 在变更单索引表格中插入
        updated = self._insert_row_to_index_table(content, new_row)
        if updated != content:
            write_file(ledger_path, updated)
            log.info("台帐已更新: 追加 %s (序号%03d)", change_number, seq)
        else:
            log.warning("台帐更新失败: 未找到变更单索引表格 %s", ledger_path)

    def update_status(
        self,
        ledger_path: str,
        change_number: str,
        status: str,
        complete_date: str = "",
        applicant: str = "",
        apply_date: str = "",
    ) -> None:
        """更新台帐中指定变更单的状态行（TD-T10 修复 + CHG-085 完成日期回写 + CHG-108 缺陷 2 自愈）

        CHG-108 缺陷 2 修复：找不到行时自动补建（自愈），不再静默 warning。
        补建时使用 applicant/apply_date 参数（若提供），desc 用 change_number 占位。

        Args:
            ledger_path: 台帐文件路径
            change_number: 变更编号（如 CHG-SCPT-2026-064）
            status: 新状态文案（如"✅已关闭"、"✅已归档"、"🔄实施中"）
            complete_date: 完成日期（CHG-085 新增，status 为"✅已关闭"/"✅已归档"时
                写入"完成日期"列，格式 YYYY-MM-DD；其他状态忽略）
            applicant: 申请人（CHG-108 自愈补建时写入"申请人"列）
            apply_date: 申请日期（CHG-108 自愈补建时写入"申请日期"列）
        """
        content = read_file(ledger_path)
        if not content:
            log.warning("台帐文件为空或读取失败: %s", ledger_path)
            return

        lines = content.split("\n")
        updated = False
        status_part, date_part = self._status_parts(content)
        for i, line in enumerate(lines):
            if not self._matches_change_number_row(line, change_number):
                continue

            parts = line.split("|")
            # 列结构：| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |
            # split 后：['', ' 序号 ', ' 变更编号 ', ..., ' 状态 ', '']
            # 标准表：状态列 = parts[-2]，完成日期列 = parts[-3]；旧格式表按表头定位
            if len(parts) >= 4:  # 至少有内容列（首尾空字符串 + 至少 2 列）
                parts[status_part] = f" {status} "
                # CHG-085：closed/archived 时回写完成日期列
                if complete_date and status in ("✅已关闭", "✅已归档") and date_part is not None:
                    parts[date_part] = f" {complete_date} "
                    log.info("台帐完成日期已回写: %s → %s", change_number, complete_date)
                lines[i] = "|".join(parts)
                updated = True
                log.info("台帐状态已更新: %s → %s", change_number, status)
                break

        if updated:
            write_file(ledger_path, "\n".join(lines))
        else:
            # CHG-108 缺陷 2 修复：自愈补建（找不到行时自动补建，不再静默 warning）
            log.warning("台帐未找到 %s 的行，触发自愈补建", change_number)
            # 提取领域
            parts_cn = change_number.split("-")
            domain = parts_cn[1] if len(parts_cn) >= 2 else ""
            # 生成序号
            seq = self._get_next_sequence(content)
            # 生成变更单链接
            link = f"[→ {change_number}](./01_变更单/CHG-{domain}/{change_number}.md)"
            # 完成日期（仅 closed/archived 状态写入）
            complete_date_str = (
                complete_date if complete_date and status in ("✅已关闭", "✅已归档") else ""
            )
            # 构造新行（直接写入目标状态，desc 用 change_number 占位）
            new_row = (
                f"| {seq:03d} | {link} | {domain} | {applicant} | {apply_date} "
                f"| {change_number} | {complete_date_str} | {status} |\n"
            )
            legacy = self._legacy_table_header(content)
            if legacy is not None:
                updated_content = self._insert_row_to_legacy_table(
                    content,
                    self._legacy_row(
                        legacy,
                        {"number": change_number, "domain": domain, "applicant": applicant,
                         "apply_date": apply_date, "desc": change_number,
                         "complete_date": complete_date_str, "status": status},
                    ),
                )
            else:
                updated_content = self._insert_row_to_index_table(content, new_row)
            if updated_content != content:
                write_file(ledger_path, updated_content)
                log.info(
                    "台帐自愈补建: %s (序号%03d, 状态=%s)", change_number, seq, status
                )
            else:
                log.error(
                    "台帐自愈补建失败: 未找到变更单索引表格 %s", ledger_path
                )

    @classmethod
    def _matches_change_number_row(cls, line: str, change_number: str) -> bool:
        """仅当 Markdown 表格的变更编号列精确匹配时返回 True。"""
        stripped = line.strip()
        if not stripped.startswith("|"):
            return False

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            return False

        # 标准台账的变更编号在第 2 列；两列表格与旧格式表（DJ-2026-009“变更明细台账”）
        # 以第 1 列为编号。标准表第 1 列是数字序号，不会误中。
        change_cell_index = 1 if len(cells) > 2 else 0
        return cls._matches_change_number_cell(
            cells[change_cell_index], change_number
        ) or cls._matches_change_number_cell(cells[0], change_number)

    @staticmethod
    def _matches_change_number_cell(cell: str, change_number: str) -> bool:
        """仅接受变更编号单元格中的精确文本或精确 Markdown 链接。"""
        normalized = cell.strip()
        if normalized == change_number:
            return True

        link_match = re.fullmatch(r"\[(?P<label>[^\]]+)\]\((?P<target>[^)]+)\)", normalized)
        if link_match is None:
            return False

        label = link_match.group("label").strip().removeprefix("→").strip()
        target_name = link_match.group("target").rsplit("/", maxsplit=1)[-1]
        return label == change_number or target_name == f"{change_number}.md"

    def remove(self, ledger_path: str, change_number: str) -> None:
        """从台帐中删除指定变更单的行（TD-T10 修复，供测试 fixture 清理用）

        Args:
            ledger_path: 台帐文件路径
            change_number: 变更编号
        """
        content = read_file(ledger_path)
        if not content:
            return

        lines = content.split("\n")
        new_lines: list[str] = []
        removed = False
        for line in lines:
            if self._matches_change_number_row(line, change_number):
                removed = True
                log.info("台帐条目已删除: %s", change_number)
                continue  # 跳过该行（删除）
            new_lines.append(line)

        if removed:
            write_file(ledger_path, "\n".join(new_lines))

    # 旧格式表表头 → 字段；没列出的栏（影响模块、关联版本等）留空
    _LEGACY_COLUMNS: dict[str, str] = {
        "序号": "seq",
        "变更编号": "number",
        "变更单号": "number",
        "领域": "domain",
        "申请人": "applicant",
        "责任人": "applicant",
        "申请日期": "apply_date",
        "变更描述": "desc",
        "变更标题": "desc",
        "描述": "desc",
        "完成日期": "complete_date",
        "验证日期": "complete_date",
        "状态": "status",
    }

    @staticmethod
    def _table_cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    @classmethod
    def _legacy_table_at(cls, content: str) -> tuple[int, list[str]] | None:
        """没有“变更单索引”标题时，找第一张能认出的旧格式明细表：（表头行号, 表头）。

        表头要同时有编号栏（“变更编号”或“变更单号”）和“状态”栏，并且至少有一行编号栏里写着
        真的 CHG 编号。模板里只有“*暂无变更记录*”占位行的空明细表不认，交给
        ``ensure_index_table`` 补标准索引表（D09 迁入 N3：``update()`` 不往占位表里写）。
        """
        if "变更单索引" in content:
            return None
        lines = content.split("\n")
        for i, line in enumerate(lines[:-1]):
            stripped = line.strip()
            if not stripped.startswith("|") or not re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
                continue
            header = [cell.strip("* ") for cell in cls._table_cells(stripped)]
            number_cols = [n for n, name in enumerate(header) if cls._LEGACY_COLUMNS.get(name) == "number"]
            if not number_cols or "状态" not in header:
                continue
            for row in lines[i + 2 :]:
                if not row.strip().startswith("|"):
                    break
                cells = cls._table_cells(row)
                if len(cells) > number_cols[0] and re.search(r"CHG-[A-Z]+-\d{4}-\d+", cells[number_cols[0]]):
                    return i, header
        return None

    @classmethod
    def _legacy_table_header(cls, content: str) -> list[str] | None:
        found = cls._legacy_table_at(content)
        return None if found is None else found[1]

    @classmethod
    def _insert_row_to_legacy_table(cls, content: str, new_row: str) -> str:
        """旧格式表行间不空行：插在分隔行之后、紧贴已有行。"""
        found = cls._legacy_table_at(content)
        if found is None:
            return content
        lines = content.split("\n")
        at = found[0] + 2
        return "\n".join([*lines[:at], new_row, *lines[at:]])

    @classmethod
    def _legacy_row(cls, header: list[str], values: dict[str, str]) -> str:
        cells = [values.get(cls._LEGACY_COLUMNS.get(name, ""), "") for name in header]
        return "| " + " | ".join(cells) + " |"

    @classmethod
    def _status_parts(cls, content: str) -> tuple[int, int | None]:
        """``line.split("|")`` 下的（状态栏, 完成日期栏）下标；标准表是最后两栏。"""
        header = cls._legacy_table_header(content)
        if header is None:
            return -2, -3
        status = header.index("状态") + 1
        date_cols = [i for i, name in enumerate(header) if cls._LEGACY_COLUMNS.get(name) == "complete_date"]
        return status, (date_cols[0] + 1 if date_cols else None)

    def _get_next_sequence(self, content: str) -> int:
        """获取变更单索引中的下一个序号"""
        max_seq = 0
        # 查找变更单索引表格中的序号
        in_index = False
        for line in content.split("\n"):
            line = line.strip()
            if "变更单索引" in line:
                in_index = True
                continue
            if in_index and line.startswith("|"):
                if re.match(r"^\|[\s\-:|]+\|$", line):
                    continue
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if cells and cells[0].isdigit():
                    try:
                        seq = int(cells[0])
                        max_seq = max(max_seq, seq)
                    except ValueError:
                        pass
            elif in_index and not line.startswith("|") and line:
                in_index = False
        return max_seq + 1

    def _insert_row_to_index_table(self, content: str, new_row: str) -> str:
        """在变更单索引表格中插入新行（在表头和分隔行之后）

        新行始终插入到表格顶部（表头分隔行下方），形成倒序排列。
        变更单索引表格行间以空行分隔（new_row 末尾自带 \\n）。
        """
        lines = content.split("\n")
        result_lines: list[str] = []
        in_index = False
        header_found = False
        inserted = False

        for line in lines:
            result_lines.append(line)

            if "变更单索引" in line:
                in_index = True
                header_found = False
                continue

            if in_index and not inserted:
                stripped = line.strip()
                if stripped.startswith("|"):
                    if re.match(r"^\|[\s\-:|]+\|$", stripped):
                        # 分隔行，在之后插入
                        header_found = True
                        result_lines.append(new_row)
                        inserted = True
                    elif not header_found:
                        # 表头行，继续
                        pass
                elif stripped and not stripped.startswith("|"):
                    # 索引表格结束
                    in_index = False

        return "\n".join(result_lines)
