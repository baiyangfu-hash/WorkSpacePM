"""LedgerUpdater 单元测试"""

from __future__ import annotations

from pathlib import Path

from auto_pm.change.ledger_updater import LedgerUpdater


class TestLedgerUpdaterUpdate:
    """LedgerUpdater.update 测试"""

    def test_update_appends_row(self, tmp_path: Path) -> None:
        """update 在台帐变更单索引中追加一行"""
        ledger = tmp_path / "01_版本变更台帐.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 描述 |\n"
            "|------|----------|------|\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.update(str(ledger), "CHG-PLC-2026-001", "修复阀门时序")

        content = ledger.read_text(encoding="utf-8")
        assert "CHG-PLC-2026-001" in content
        assert "修复阀门时序" in content

    def test_update_empty_file(self, tmp_path: Path) -> None:
        """update 对空文件不写入"""
        ledger = tmp_path / "empty.md"
        ledger.write_text("", encoding="utf-8")

        updater = LedgerUpdater()
        updater.update(str(ledger), "CHG-PLC-2026-001", "测试")

        content = ledger.read_text(encoding="utf-8")
        assert content == ""

    def test_update_nonexistent_file(self, tmp_path: Path) -> None:
        """update 对不存在的文件不抛异常"""
        updater = LedgerUpdater()
        # read_file 对不存在的文件返回空字符串，update 应安全退出
        updater.update(str(tmp_path / "nonexistent.md"), "CHG-PLC-2026-001", "测试")

    def test_update_no_index_table(self, tmp_path: Path) -> None:
        """update 对无变更单索引表格的台帐不写入"""
        ledger = tmp_path / "no_index.md"
        ledger.write_text("# 版本变更台帐\n\n无索引表格\n", encoding="utf-8")

        updater = LedgerUpdater()
        updater.update(str(ledger), "CHG-PLC-2026-001", "测试")

        content = ledger.read_text(encoding="utf-8")
        assert "CHG-PLC-2026-001" not in content

    def test_update_sequential_numbering(self, tmp_path: Path) -> None:
        """update 连续追加时序号递增"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 描述 |\n"
            "|------|----------|------|\n"
            "| 001 | CHG-PLC-2026-001 | 修复1 |\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.update(str(ledger), "CHG-DOCU-2026-002", "文档更新")

        content = ledger.read_text(encoding="utf-8")
        assert "002" in content
        assert "CHG-DOCU-2026-002" in content

    def test_update_description_reference_is_not_duplicate(self, tmp_path: Path) -> None:
        """描述列引用目标编号时，update 仍应新增目标行。"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
            "| 008 | [→ CHG-SAFE-2026-008](./01_变更单/CHG-SAFE/CHG-SAFE-2026-008.md) | SAFE | fubai | 2026-09-12 | 依赖 CHG-SAFE-2026-007 收尾 | | 🔄待验收 |\n",
            encoding="utf-8",
        )

        LedgerUpdater().update(str(ledger), "CHG-SAFE-2026-007", "active release 修复")

        content = ledger.read_text(encoding="utf-8")
        assert "[→ CHG-SAFE-2026-008]" in content
        assert "[→ CHG-SAFE-2026-007]" in content


class TestGetNextSequence:
    """LedgerUpdater._get_next_sequence 测试"""

    def test_empty_content(self) -> None:
        """空内容返回 1"""
        updater = LedgerUpdater()
        assert updater._get_next_sequence("") == 1

    def test_no_index(self) -> None:
        """无变更单索引返回 1"""
        updater = LedgerUpdater()
        content = "# 标题\n\n无索引\n"
        assert updater._get_next_sequence(content) == 1

    def test_with_existing_entries(self) -> None:
        """有已有条目时返回 max+1"""
        updater = LedgerUpdater()
        content = (
            "# 台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 |\n"
            "|------|----------|\n"
            "| 001 | CHG-001 |\n"
            "| 003 | CHG-003 |\n"
        )
        assert updater._get_next_sequence(content) == 4

    def test_non_digit_sequence_ignored(self) -> None:
        """非数字序号被忽略"""
        updater = LedgerUpdater()
        content = (
            "# 台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 |\n"
            "|------|----------|\n"
            "| abc | CHG-001 |\n"
        )
        assert updater._get_next_sequence(content) == 1


class TestInsertRowToIndexTable:
    """LedgerUpdater._insert_row_to_index_table 测试"""

    def test_insert_after_separator(self) -> None:
        """在分隔行后插入新行"""
        updater = LedgerUpdater()
        content = (
            "# 台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 |\n"
            "|------|----------|\n"
        )
        new_row = "| 001 | CHG-001 | 测试 |\n"
        result = updater._insert_row_to_index_table(content, new_row)
        assert "CHG-001" in result
        # 新行应在分隔行之后
        lines = result.split("\n")
        found_sep = False
        for line in lines:
            if "---" in line:
                found_sep = True
            elif found_sep and "CHG-001" in line:
                break

    def test_no_index_section(self) -> None:
        """无变更单索引时不插入"""
        updater = LedgerUpdater()
        content = "# 台帐\n\n无索引\n"
        new_row = "| 001 | CHG-001 | 测试 |\n"
        result = updater._insert_row_to_index_table(content, new_row)
        assert "CHG-001" not in result


class TestLedgerUpdaterUpdateStatus:
    """LedgerUpdater.update_status 测试（TD-T10 修复）"""

    def test_update_status_updates_last_column(self, tmp_path: Path) -> None:
        """update_status 更新指定变更单的状态列（最后一列）"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-001 | SCPT | fubai | 2026-06-25 | 测试 | | 🔄待处理 |\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.update_status(str(ledger), "CHG-SCPT-2026-001", "✅已关闭")

        content = ledger.read_text(encoding="utf-8")
        assert "✅已关闭" in content
        assert "🔄待处理" not in content
        # 其他列保持不变
        assert "CHG-SCPT-2026-001" in content
        assert "fubai" in content

    def test_update_status_not_found_triggers_self_heal(self, tmp_path: Path) -> None:
        """CHG-108 缺陷2: update_status 未找到 change_number 时自愈补建新行"""
        ledger = tmp_path / "ledger.md"
        original = (
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 状态 |\n"
            "|------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-001 | 🔄待处理 |\n"
        )
        ledger.write_text(original, encoding="utf-8")

        updater = LedgerUpdater()
        # 传入 applicant/apply_date 供自愈补建使用
        updater.update_status(
            str(ledger),
            "CHG-SCPT-2026-999",
            "✅已关闭",
            applicant="fubai",
            apply_date="2026-07-09",
        )

        content = ledger.read_text(encoding="utf-8")
        # CHG-108 缺陷2: 自愈补建后应包含目标变更编号
        assert "CHG-SCPT-2026-999" in content
        assert "✅已关闭" in content
        # 原有记录保持不变
        assert "CHG-SCPT-2026-001" in content
        # 自愈补建的序号应为 002（原 max=001）
        assert "002" in content

    def test_update_status_empty_file(self, tmp_path: Path) -> None:
        """update_status 对空文件不抛异常"""
        ledger = tmp_path / "empty.md"
        ledger.write_text("", encoding="utf-8")

        updater = LedgerUpdater()
        updater.update_status(str(ledger), "CHG-SCPT-2026-001", "✅已关闭")

        content = ledger.read_text(encoding="utf-8")
        assert content == ""

    def test_update_status_multiple_rows_only_updates_target(self, tmp_path: Path) -> None:
        """update_status 多行时只更新目标行"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 状态 |\n"
            "|------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-001 | 🔄待处理 |\n"
            "| 002 | CHG-SCPT-2026-002 | 🔄待处理 |\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.update_status(str(ledger), "CHG-SCPT-2026-002", "✅已关闭")

        content = ledger.read_text(encoding="utf-8")
        # 目标行已更新
        assert "CHG-SCPT-2026-002 | ✅已关闭" in content
        # 非目标行保持不变
        assert "CHG-SCPT-2026-001 | 🔄待处理" in content

    def test_update_status_ignores_change_number_in_other_row_description(
        self, tmp_path: Path
    ) -> None:
        """描述列引用目标编号时，不能抢先命中并更新非目标行。"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
            "| 008 | [→ CHG-SAFE-2026-008](./01_变更单/CHG-SAFE/CHG-SAFE-2026-008.md) | SAFE | fubai | 2026-09-12 | 依赖 CHG-SAFE-2026-007 收尾 | | 🔄待验收 |\n"
            "| 007 | [→ CHG-SAFE-2026-007](./01_变更单/CHG-SAFE/CHG-SAFE-2026-007.md) | SAFE | fubai | 2026-09-12 | active release 修复 | | 🔄实施中 |\n",
            encoding="utf-8",
        )

        LedgerUpdater().update_status(str(ledger), "CHG-SAFE-2026-007", "🔄待验收")

        rows = [line.strip() for line in ledger.read_text(encoding="utf-8").splitlines()]
        row_008 = next(row for row in rows if "[→ CHG-SAFE-2026-008]" in row)
        row_007 = next(row for row in rows if "[→ CHG-SAFE-2026-007]" in row)
        assert row_008.endswith("| 🔄待验收 |")
        assert row_007.endswith("| 🔄待验收 |")

    def test_update_status_requires_exact_change_number_cell(self, tmp_path: Path) -> None:
        """编号列的相邻编号或前后缀不能替代目标编号。"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
            "| 001 | [→ CHG-SAFE-2026-0070](./01_变更单/CHG-SAFE/CHG-SAFE-2026-0070.md) | SAFE | fubai | 2026-09-12 | 相邻编号 | | 🔄实施中 |\n"
            "| 002 | legacy-CHG-SAFE-2026-007 | SAFE | fubai | 2026-09-12 | 前缀编号 | | 🔄实施中 |\n"
            "| 003 | CHG-SAFE-2026-007-legacy | SAFE | fubai | 2026-09-12 | 后缀编号 | | 🔄实施中 |\n"
            "| 004 | [→ CHG-SAFE-2026-007](./01_变更单/CHG-SAFE/CHG-SAFE-2026-007.md) | SAFE | fubai | 2026-09-12 | 目标编号 | | 🔄实施中 |\n",
            encoding="utf-8",
        )

        LedgerUpdater().update_status(str(ledger), "CHG-SAFE-2026-007", "✅已关闭")

        rows = [line.strip() for line in ledger.read_text(encoding="utf-8").splitlines()]
        target_row = next(row for row in rows if "[→ CHG-SAFE-2026-007]" in row)
        assert target_row.endswith("| ✅已关闭 |")
        for non_target in rows:
            if "[→ CHG-SAFE-2026-007]" not in non_target and "CHG-SAFE-2026-007" in non_target:
                assert non_target.endswith("| 🔄实施中 |")


class TestLedgerUpdaterRemove:
    """LedgerUpdater.remove 测试（TD-T10 修复）"""

    def test_remove_deletes_row(self, tmp_path: Path) -> None:
        """remove 删除指定变更单的行"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 状态 |\n"
            "|------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-001 | 🔄待处理 |\n"
            "| 002 | CHG-SCPT-2026-002 | 🔄待处理 |\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.remove(str(ledger), "CHG-SCPT-2026-001")

        content = ledger.read_text(encoding="utf-8")
        assert "CHG-SCPT-2026-001" not in content
        assert "CHG-SCPT-2026-002" in content

    def test_remove_ignores_change_number_in_other_row_description(
        self, tmp_path: Path
    ) -> None:
        """remove 不得删除描述列仅引用目标编号的非目标行。"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
            "| 008 | [→ CHG-SAFE-2026-008](./01_变更单/CHG-SAFE/CHG-SAFE-2026-008.md) | SAFE | fubai | 2026-09-12 | 依赖 CHG-SAFE-2026-007 收尾 | | 🔄待验收 |\n"
            "| 007 | [→ CHG-SAFE-2026-007](./01_变更单/CHG-SAFE/CHG-SAFE-2026-007.md) | SAFE | fubai | 2026-09-12 | active release 修复 | | 🔄实施中 |\n",
            encoding="utf-8",
        )

        LedgerUpdater().remove(str(ledger), "CHG-SAFE-2026-007")

        content = ledger.read_text(encoding="utf-8")
        assert "[→ CHG-SAFE-2026-008]" in content
        assert "[→ CHG-SAFE-2026-007]" not in content

    def test_remove_not_found(self, tmp_path: Path) -> None:
        """remove 未找到 change_number 时不修改内容"""
        ledger = tmp_path / "ledger.md"
        original = (
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 状态 |\n"
            "|------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-001 | 🔄待处理 |\n"
        )
        ledger.write_text(original, encoding="utf-8")

        updater = LedgerUpdater()
        updater.remove(str(ledger), "CHG-SCPT-2026-999")

        content = ledger.read_text(encoding="utf-8")
        assert content == original

    def test_remove_empty_file(self, tmp_path: Path) -> None:
        """remove 对空文件不抛异常"""
        ledger = tmp_path / "empty.md"
        ledger.write_text("", encoding="utf-8")

        updater = LedgerUpdater()
        updater.remove(str(ledger), "CHG-SCPT-2026-001")

        content = ledger.read_text(encoding="utf-8")
        assert content == ""

    def test_remove_preserves_non_table_lines(self, tmp_path: Path) -> None:
        """remove 只删除表格行，保留非表格行（如标题、说明）"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "> 记录项目所有变更单的索引与状态\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 状态 |\n"
            "|------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-001 | 🔄待处理 |\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.remove(str(ledger), "CHG-SCPT-2026-001")

        content = ledger.read_text(encoding="utf-8")
        # 表格行已删除
        assert "CHG-SCPT-2026-001" not in content
        # 非表格行保留
        assert "# 版本变更台帐" in content
        assert "记录项目所有变更单的索引与状态" in content
        assert "## 变更单索引" in content


class TestLedgerUpdaterChg085:
    """CHG-085 新增：台账字段完整性（applicant/apply_date/complete_date）"""

    def test_update_with_applicant_and_date(self, tmp_path: Path) -> None:
        """update 调用时传入 applicant/apply_date，新行第 4/5 列非空"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.update(
            str(ledger),
            "CHG-SCPT-2026-085",
            "深度审查整改V0.5.4",
            applicant="fubai",
            apply_date="2026-07-03",
        )

        content = ledger.read_text(encoding="utf-8")
        assert "CHG-SCPT-2026-085" in content
        # 申请人列非空
        assert "fubai" in content
        # 申请日期列非空
        assert "2026-07-03" in content
        # 验证列顺序：解析新行，第 4 列=申请人，第 5 列=申请日期
        for line in content.split("\n"):
            if "CHG-SCPT-2026-085" in line and line.strip().startswith("|"):
                cells = [c.strip() for c in line.split("|")]
                # cells: ['', '001', 'CHG-...', 'SCPT', 'fubai', '2026-07-03', '深度...', '', '🔄待处理', '']
                assert cells[4] == "fubai", f"申请人列应为 fubai，实际: {cells[4]}"
                assert cells[5] == "2026-07-03", f"申请日期列应为 2026-07-03，实际: {cells[5]}"
                break

    def test_update_status_writes_complete_date(self, tmp_path: Path) -> None:
        """update_status 流转到 ✅已关闭 时回写完成日期列"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-085 | SCPT | fubai | 2026-07-03 | 测试 | | 🔄待处理 |\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        updater.update_status(
            str(ledger),
            "CHG-SCPT-2026-085",
            "✅已关闭",
            complete_date="2026-07-03",
        )

        content = ledger.read_text(encoding="utf-8")
        # 状态列已更新
        assert "✅已关闭" in content
        # 完成日期列已回写
        for line in content.split("\n"):
            if "CHG-SCPT-2026-085" in line and line.strip().startswith("|"):
                cells = [c.strip() for c in line.split("|")]
                # cells[7] = 完成日期列，cells[8] = 状态列
                assert cells[7] == "2026-07-03", f"完成日期列应为 2026-07-03，实际: {cells[7]}"
                assert cells[8] == "✅已关闭", f"状态列应为 ✅已关闭，实际: {cells[8]}"
                break

    def test_update_status_no_complete_date_for_non_closed(self, tmp_path: Path) -> None:
        """update_status 流转到非 closed/archived 状态时不写完成日期"""
        ledger = tmp_path / "ledger.md"
        ledger.write_text(
            "# 版本变更台帐\n\n"
            "## 变更单索引\n\n"
            "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
            "|------|----------|------|--------|----------|----------|----------|------|\n"
            "| 001 | CHG-SCPT-2026-085 | SCPT | fubai | 2026-07-03 | 测试 | | 🔄待处理 |\n",
            encoding="utf-8",
        )

        updater = LedgerUpdater()
        # 流转到 implementing（🔄实施中），传入 complete_date 应被忽略
        updater.update_status(
            str(ledger),
            "CHG-SCPT-2026-085",
            "🔄实施中",
            complete_date="2026-07-03",
        )

        content = ledger.read_text(encoding="utf-8")
        # 状态列已更新为实施中
        assert "🔄实施中" in content
        # 完成日期列应保持空（非 closed/archived 不写）
        for line in content.split("\n"):
            if "CHG-SCPT-2026-085" in line and line.strip().startswith("|"):
                cells = [c.strip() for c in line.split("|")]
                assert cells[7] == "", f"完成日期列应为空，实际: {cells[7]}"
                assert cells[8] == "🔄实施中", f"状态列应为 🔄实施中，实际: {cells[8]}"
                break
