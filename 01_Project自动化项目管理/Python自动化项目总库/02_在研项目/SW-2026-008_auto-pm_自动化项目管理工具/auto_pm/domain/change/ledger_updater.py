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


class LedgerUpdater:
    """版本变更台帐更新器"""

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

        # 去重检查：变更编号已存在于台帐中则跳过追加
        if change_number in content:
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
        for i, line in enumerate(lines):
            if change_number in line and line.strip().startswith("|"):
                parts = line.split("|")
                # 列结构：| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |
                # split 后：['', ' 序号 ', ' 变更编号 ', ..., ' 状态 ', '']
                # 状态列 = parts[-2]，完成日期列 = parts[-3]
                if len(parts) >= 4:  # 至少有内容列（首尾空字符串 + 至少 2 列）
                    # 状态列是最后一个内容列 = parts[-2]（parts[-1] 是行尾空字符串）
                    parts[-2] = f" {status} "
                    # CHG-085：closed/archived 时回写完成日期列（parts[-3]）
                    if complete_date and status in ("✅已关闭", "✅已归档"):
                        parts[-3] = f" {complete_date} "
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
            updated_content = self._insert_row_to_index_table(content, new_row)
            if updated_content != content:
                write_file(ledger_path, updated_content)
                log.info("台帐自愈补建: %s (序号%03d, 状态=%s)", change_number, seq, status)
            else:
                log.error("台帐自愈补建失败: 未找到变更单索引表格 %s", ledger_path)

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
            if change_number in line and line.strip().startswith("|"):
                removed = True
                log.info("台帐条目已删除: %s", change_number)
                continue  # 跳过该行（删除）
            new_lines.append(line)

        if removed:
            write_file(ledger_path, "\n".join(new_lines))

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
