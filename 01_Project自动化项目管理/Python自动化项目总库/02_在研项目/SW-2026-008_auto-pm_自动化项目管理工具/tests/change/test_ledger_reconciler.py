"""LedgerReconciler 单元测试（CHG-108 缺陷 1 修复）

覆盖对账器三类差异检测 + 自动修复：
  - reconcile 只读扫描（缺失/孤儿/状态不一致）
  - auto_fix 补建缺失行
  - auto_fix 修复状态不一致
  - 孤儿记录不自动删除（保留人工审核）
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.change.ledger_reconciler import LedgerReconciler, ReconcileDiff

# 最小化有效 CHG-*.md 文件模板（含 §3/§4 章节，ChgParser 可解析）
_CHG_TEMPLATE = """# 变更单

## 1. 文档基础信息
**文档标题**：变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | {change_number} |
| 项目名称 | TEST |
| 项目编号 | TEST-2026-001 |

### 3.1 技术领域（必选）
| 领域 | 选择 |
|------|------|
| ☑ **SCPT** Python脚本 | **选中** |

### 3.2 业务性质（必选）
| 性质 | 选择 |
|------|------|
| ☑ **DEF** 缺陷修复 | **选中** |

### 3.3 影响范围（可多选）
| 范围 | 选择 |
|------|------|
| ☑ **LOCAL** 局部变更 | **选中** |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | {applicant} |
| 申请日期 | {apply_date} |
| 变更状态 | {status} |

## 4. 变更原因
**变更背景**：
{background}
"""

# 台账骨架（与 LedgerUpdater 期望的列结构对齐）
_LEDGER_FILENAME = "01_版本变更台账.md"
_LEGACY_LEDGER_FILENAME = "01_版本变更台帐.md"
_LEDGER_SKELETON = """# 版本变更台账

## 变更单索引

| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |
|------|----------|------|--------|----------|----------|----------|------|
"""


def _ledger_path(project: Path, *, legacy: bool = False) -> Path:
    """返回规范台账路径，或显式请求历史存量路径。"""
    filename = _LEGACY_LEDGER_FILENAME if legacy else _LEDGER_FILENAME
    return project / "04_监控" / "01_变更管理" / "02_变更记录" / filename


def _make_project(tmp_path: Path) -> Path:
    """构造最小化项目目录（PLC 约定路径）"""
    project = tmp_path / "TEST-2026-001"
    chg_dir = project / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True)
    ledger_dir = project / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True)
    # 新项目只创建规范字形台账；历史字形由兼容性测试单独覆盖。
    _ledger_path(project).write_text(_LEDGER_SKELETON, encoding="utf-8")
    return project


def _make_chg_file(
    project: Path,
    change_number: str,
    status: str = "draft",
    applicant: str = "fubai",
    apply_date: str = "2026-07-09",
    background: str = "测试变更背景",
) -> Path:
    """创建一个最小化有效 CHG 文件"""
    chg_dir = project / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    fname = f"{change_number}.md"
    content = _CHG_TEMPLATE.format(
        change_number=change_number,
        status=status,
        applicant=applicant,
        apply_date=apply_date,
        background=background,
    )
    fp = chg_dir / fname
    fp.write_text(content, encoding="utf-8")
    return fp


def _make_ledger_row(
    seq: int,
    change_number: str,
    status: str = "🔄待处理",
    applicant: str = "fubai",
    apply_date: str = "2026-07-09",
    complete_date: str = "",
) -> str:
    """构造台账数据行"""
    return (
        f"| {seq:03d} | [→ {change_number}](./01_变更单/CHG-SCPT/{change_number}.md) "
        f"| SCPT | {applicant} | {apply_date} | {change_number} | {complete_date} | {status} |\n"
    )


class TestReconcileDiff:
    """ReconcileDiff dataclass 测试"""

    def test_empty_diff_is_clean(self) -> None:
        """空差异 is_clean=True"""
        diff = ReconcileDiff()
        assert diff.is_clean is True

    def test_missing_makes_not_clean(self) -> None:
        diff = ReconcileDiff(missing_in_ledger=["CHG-SCPT-2026-001"])
        assert diff.is_clean is False

    def test_orphan_makes_not_clean(self) -> None:
        diff = ReconcileDiff(orphan_in_ledger=["CHG-SCPT-2026-999"])
        assert diff.is_clean is False

    def test_mismatch_makes_not_clean(self) -> None:
        diff = ReconcileDiff(status_mismatches=[("CHG-001", "✅已关闭", "🔄待处理")])
        assert diff.is_clean is False

    def test_summary_format(self) -> None:
        diff = ReconcileDiff(
            missing_in_ledger=["a"],
            orphan_in_ledger=["b"],
            status_mismatches=[("c", "x", "y")],
        )
        s = diff.summary()
        assert "缺失: 1" in s
        assert "孤儿): 1" in s
        assert "不一致: 1" in s


class TestLedgerReconcilerReconcile:
    """LedgerReconciler.reconcile 只读扫描测试"""

    def test_reconcile_clean(self, tmp_path: Path) -> None:
        """台账与 CHG 文件一致时 is_clean"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="draft")
        # 台账补一行
        ledger = _ledger_path(project)
        ledger.write_text(
            _LEDGER_SKELETON + _make_ledger_row(1, "CHG-SCPT-2026-001", "🔄待处理"),
            encoding="utf-8",
        )

        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert diff.is_clean is True
        assert diff.missing_in_ledger == []
        assert diff.orphan_in_ledger == []
        assert diff.status_mismatches == []

    def test_reconcile_detects_missing(self, tmp_path: Path) -> None:
        """CHG 文件存在但台账无记录 → missing_in_ledger"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="draft")
        _make_chg_file(project, "CHG-SCPT-2026-002", status="draft")
        # 台账只有 001
        ledger = _ledger_path(project)
        ledger.write_text(
            _LEDGER_SKELETON + _make_ledger_row(1, "CHG-SCPT-2026-001", "🔄待处理"),
            encoding="utf-8",
        )

        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert diff.missing_in_ledger == ["CHG-SCPT-2026-002"]
        assert diff.is_clean is False

    def test_reconcile_detects_orphan(self, tmp_path: Path) -> None:
        """台账有记录但 CHG 文件不存在 → orphan_in_ledger"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="draft")
        # 台账有 001 + 999（999 无文件）
        ledger = _ledger_path(project)
        ledger.write_text(
            _LEDGER_SKELETON
            + _make_ledger_row(1, "CHG-SCPT-2026-001", "🔄待处理")
            + _make_ledger_row(2, "CHG-SCPT-2026-999", "🔄待处理"),
            encoding="utf-8",
        )

        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert diff.orphan_in_ledger == ["CHG-SCPT-2026-999"]
        assert diff.is_clean is False

    def test_reconcile_detects_status_mismatch(self, tmp_path: Path) -> None:
        """CHG 状态(closed) vs 台账状态(待处理) 不一致"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="closed")
        ledger = _ledger_path(project)
        ledger.write_text(
            _LEDGER_SKELETON + _make_ledger_row(1, "CHG-SCPT-2026-001", "🔄待处理"),
            encoding="utf-8",
        )

        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert len(diff.status_mismatches) == 1
        cn, expected, actual = diff.status_mismatches[0]
        assert cn == "CHG-SCPT-2026-001"
        assert expected == "✅已关闭"  # LEDGER_STATUS_MAP["closed"]
        assert actual == "🔄待处理"
        assert diff.is_clean is False

    def test_reconcile_no_ledger_returns_empty(self, tmp_path: Path) -> None:
        """无台账文件时返回空 diff"""
        project = tmp_path / "TEST-2026-001"
        project.mkdir()
        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert diff.is_clean is True  # 空 diff 视为 clean


class TestLedgerReconcilerAutoFix:
    """LedgerReconciler.auto_fix 自动修复测试"""

    def test_auto_fix_missing_row(self, tmp_path: Path) -> None:
        """auto_fix 补建缺失行（draft 状态）"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="draft", applicant="alice")
        # 台账空（无 001 记录）
        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert diff.missing_in_ledger == ["CHG-SCPT-2026-001"]

        r.auto_fix(str(project), diff)

        # 修复后重新对账
        new_diff = r.reconcile(str(project))
        assert new_diff.is_clean is True
        # 台账应包含补建的记录
        ledger = _ledger_path(project)
        content = ledger.read_text(encoding="utf-8")
        assert "CHG-SCPT-2026-001" in content
        assert "alice" in content  # applicant 已回填

    def test_auto_fix_missing_row_with_closed_status(self, tmp_path: Path) -> None:
        """auto_fix 补建缺失行时按 CHG 实际状态修正（非默认待处理）"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="closed")
        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert diff.missing_in_ledger == ["CHG-SCPT-2026-001"]

        r.auto_fix(str(project), diff)

        new_diff = r.reconcile(str(project))
        assert new_diff.is_clean is True
        # 台账状态应为 ✅已关闭（非 🔄待处理）
        ledger = _ledger_path(project)
        content = ledger.read_text(encoding="utf-8")
        assert "✅已关闭" in content

    def test_auto_fix_status_mismatch(self, tmp_path: Path) -> None:
        """auto_fix 修复状态不一致"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="closed")
        ledger = _ledger_path(project)
        ledger.write_text(
            _LEDGER_SKELETON + _make_ledger_row(1, "CHG-SCPT-2026-001", "🔄待处理"),
            encoding="utf-8",
        )

        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert len(diff.status_mismatches) == 1

        r.auto_fix(str(project), diff)

        new_diff = r.reconcile(str(project))
        assert new_diff.is_clean is True
        # 台账状态已修正
        content = ledger.read_text(encoding="utf-8")
        assert "✅已关闭" in content
        assert "🔄待处理" not in content

    def test_auto_fix_orphan_not_deleted(self, tmp_path: Path) -> None:
        """auto_fix 不自动删除孤儿记录（保留人工审核）"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="draft")
        ledger = _ledger_path(project)
        ledger.write_text(
            _LEDGER_SKELETON
            + _make_ledger_row(1, "CHG-SCPT-2026-001", "🔄待处理")
            + _make_ledger_row(2, "CHG-SCPT-2026-999", "🔄待处理"),
            encoding="utf-8",
        )

        r = LedgerReconciler()
        diff = r.reconcile(str(project))
        assert diff.orphan_in_ledger == ["CHG-SCPT-2026-999"]

        r.auto_fix(str(project), diff)

        # 孤儿记录仍保留（未自动删除）
        content = ledger.read_text(encoding="utf-8")
        assert "CHG-SCPT-2026-999" in content

    def test_auto_fix_clean_no_op(self, tmp_path: Path) -> None:
        """auto_fix 对无差异时不修改"""
        project = _make_project(tmp_path)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="draft")
        ledger = _ledger_path(project)
        original = _LEDGER_SKELETON + _make_ledger_row(1, "CHG-SCPT-2026-001", "🔄待处理")
        ledger.write_text(original, encoding="utf-8")

        r = LedgerReconciler()
        r.auto_fix(str(project))  # 内部会 reconcile，无差异

        content = ledger.read_text(encoding="utf-8")
        assert content == original

    def test_auto_fix_missing_ledger_with_chg_files(self, tmp_path: Path) -> None:
        """台账文件不存在，但有变更单文件时，reconcile 返回缺失且 auto_fix 能自动创建台账并补全"""
        project = _make_project(tmp_path)
        # 删掉默认创建的台账文件
        ledger = _ledger_path(project)
        if ledger.exists():
            ledger.unlink()

        _make_chg_file(project, "CHG-SCPT-2026-001", status="closed", applicant="alice")

        r = LedgerReconciler()
        diff = r.reconcile(str(project))

        # 应该返回该变更单是 missing_in_ledger
        assert diff.missing_in_ledger == ["CHG-SCPT-2026-001"]
        assert diff.is_clean is False

        # 执行自愈自动修复
        r.auto_fix(str(project), diff)

        # 应该成功创建了台账并补齐了
        assert ledger.exists()
        new_diff = r.reconcile(str(project))
        assert new_diff.is_clean is True

        content = ledger.read_text(encoding="utf-8")
        assert "CHG-SCPT-2026-001" in content
        assert "alice" in content
        assert "✅已关闭" in content

    def test_reconcile_finds_legacy_ledger_filename(self, tmp_path: Path) -> None:
        """历史存量台帐仍可被发现，但新项目主路径使用台账。"""
        project = _make_project(tmp_path)
        canonical = _ledger_path(project)
        legacy = _ledger_path(project, legacy=True)
        canonical.replace(legacy)
        _make_chg_file(project, "CHG-SCPT-2026-001", status="draft")
        legacy.write_text(
            _LEDGER_SKELETON + _make_ledger_row(1, "CHG-SCPT-2026-001"),
            encoding="utf-8",
        )

        diff = LedgerReconciler().reconcile(str(project))

        assert diff.is_clean is True
        assert legacy.exists()
        assert not canonical.exists()
