"""ChangeService 单元测试"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import (
    SpecViolationError,
    validate_business_nature,
    validate_domain,
    validate_impact_scope,
    validate_status_transition,
    validate_urgency,
)


class TestChangeService:
    """变更管理 Service 测试"""

    def test_create_change_request(self, workspace_root: str, project_id: str) -> None:
        """测试创建变更单"""
        if not os.path.isdir(workspace_root):
            pytest.skip("工作空间目录不存在")

        svc = ChangeService(workspace_root)
        cr = svc.create_change_request(
            project_id=project_id,
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试人员",
            background="测试变更背景",
            necessity="测试变更必要性",
        )

        assert cr.change_number.startswith("CHG-PLC-")
        assert cr.status == "draft"
        assert cr.project_id == project_id
        assert os.path.isfile(cr.file_path)

        # 清理：删除测试创建的文件
        if os.path.isfile(cr.file_path):
            os.remove(cr.file_path)

    def test_list_change_requests(self, workspace_root: str, project_id: str) -> None:
        """测试列出变更单"""
        if not os.path.isdir(workspace_root):
            pytest.skip("工作空间目录不存在")

        svc = ChangeService(workspace_root)
        changes = svc.list_change_requests(project_id)

        assert isinstance(changes, list)
        # TEST-2026-001 应该有变更单（conftest 创建了 CHG-DOCU-2026-001）
        if changes:
            assert changes[0].change_number.startswith("CHG-")

    def test_list_change_requests_with_filter(self, workspace_root: str, project_id: str) -> None:
        """测试筛选变更单"""
        if not os.path.isdir(workspace_root):
            pytest.skip("工作空间目录不存在")

        svc = ChangeService(workspace_root)
        changes = svc.list_change_requests(project_id, domain="DOCU")

        assert isinstance(changes, list)
        for c in changes:
            assert c.domain == "DOCU"

    def test_get_change_request(self, workspace_root: str) -> None:
        """测试获取变更单详情"""
        if not os.path.isdir(workspace_root):
            pytest.skip("工作空间目录不存在")

        svc = ChangeService(workspace_root)
        cr = svc.get_change_request("CHG-DOCU-2026-001")

        assert cr is not None, "变更单 CHG-DOCU-2026-001 未找到，fixture 可能缺项目标志文件"
        assert cr.change_number == "CHG-DOCU-2026-001"
        assert cr.domain == "DOCU"

    def test_get_change_request_not_found(self, workspace_root: str) -> None:
        """测试查询不存在的变更单"""
        svc = ChangeService(workspace_root)
        cr = svc.get_change_request("CHG-NONEXISTENT-9999-999")

        assert cr is None

    def test_generate_change_number(self, workspace_root: str, project_id: str) -> None:
        """测试变更编号生成"""
        if not os.path.isdir(workspace_root):
            pytest.skip("工作空间目录不存在")

        svc = ChangeService(workspace_root)
        project_path = os.path.join(workspace_root, project_id)

        num1 = svc._generate_change_number(project_path, "PLC")
        assert num1.startswith("CHG-PLC-")

        # 连续生成应递增
        num2 = svc._generate_change_number(project_path, "PLC")
        assert num2.startswith("CHG-PLC-")

    def test_create_change_request_project_not_found(self, workspace_root: str) -> None:
        """创建变更单时项目不存在抛 ValueError"""
        svc = ChangeService(workspace_root)
        with pytest.raises(ValueError, match="项目不存在"):
            svc.create_change_request(
                project_id="NONEXISTENT-9999",
                domain="PLC",
                business_nature="DEF",
                impact_scope=["LOCAL"],
                applicant="测试",
                background="背景",
                necessity="必要性",
            )

    def test_create_change_request_invalid_domain(self, workspace_root: str, project_id: str) -> None:
        """创建变更单时非法领域抛 SpecViolationError"""
        svc = ChangeService(workspace_root)
        with pytest.raises(SpecViolationError, match="技术领域"):
            svc.create_change_request(
                project_id=project_id,
                domain="INVALID",
                business_nature="DEF",
                impact_scope=["LOCAL"],
                applicant="测试",
                background="背景",
                necessity="必要性",
            )

    def test_list_change_requests_project_not_found(self, workspace_root: str) -> None:
        """列出变更单时项目不存在返回空列表"""
        svc = ChangeService(workspace_root)
        result = svc.list_change_requests("NONEXISTENT-9999")
        assert result == []

    def test_get_project_path_not_found(self, workspace_root: str) -> None:
        """_get_project_path 对不存在的项目返回 None"""
        svc = ChangeService(workspace_root)
        assert svc._get_project_path("NONEXISTENT-9999") is None

    def test_get_project_path_exists(self, workspace_root: str, project_id: str) -> None:
        """_get_project_path 对存在的项目返回路径"""
        svc = ChangeService(workspace_root)
        result = svc._get_project_path(project_id)
        assert result is not None
        assert project_id in result

    def test_find_change_file_no_domain(self, workspace_root: str) -> None:
        """_find_change_file 对无领域编号返回 None"""
        svc = ChangeService(workspace_root)
        assert svc._find_change_file("X") is None

    def test_find_change_file_nonexistent_workspace(self, tmp_path: Path) -> None:
        """_find_change_file 对不存在的工作空间目录返回 None"""
        svc = ChangeService(str(tmp_path / "nonexistent"))
        assert svc._find_change_file("CHG-PLC-2026-001") is None

    def test_create_refuses_overwrite_closed_change(
        self, workspace_root: str, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P2 根源修复：禁止覆盖已存在且状态为 closed 的变更单

        场景：编号生成器回退到已用编号（如台帐被清理后），目标文件已存在且状态为 closed。
        应抛出 ValueError，防止终态变更单被覆盖。
        """
        svc = ChangeService(workspace_root)

        # 把已有的 CHG-DOCU-2026-001.md 状态改为 closed
        chg_path = os.path.join(
            workspace_root, project_id,
            "04_监控", "01_变更管理", "01_变更单",
            "CHG-DOCU", "CHG-DOCU-2026-001.md",
        )
        with open(chg_path, encoding="utf-8") as f:
            content = f.read()
        # 在 §3.4 部分插入"变更状态 | closed"行
        content = content.replace(
            "| 紧急程度 |",
            "| 变更状态 | closed |\n| 紧急程度 |",
        )
        with open(chg_path, "w", encoding="utf-8") as f:
            f.write(content)

        # mock 编号生成器返回已存在的编号
        monkeypatch.setattr(
            svc._locator, "generate_change_number",
            lambda *args: "CHG-DOCU-2026-001",
        )

        with pytest.raises(ValueError, match="终态"):
            svc.create_change_request(
                project_id=project_id,
                domain="DOCU",
                business_nature="DEF",
                impact_scope=["LOCAL"],
                applicant="测试",
                background="背景",
                necessity="必要性",
            )

    def test_create_change_request_retrofit(self, tmp_path: Path) -> None:
        """CHG-108 缺陷3: retrofit 模式直接创建 closed 状态变更单

        验证：
          1. 返回的 cr.status == "closed"（而非 draft）
          2. 生成的 CHG 文件 §3.4 状态字段 == "closed"
          3. 台账记录状态 == "✅已关闭" + 完成日期

        使用独立的 tmp_path 构造完整项目结构（含完整台账骨架），
        避免依赖 workspace_root fixture 的简化台账。
        """
        workspace_root = str(tmp_path)
        project_id = "TEST-2026-001"
        project_path = os.path.join(workspace_root, project_id)
        # 项目标志文件
        os.makedirs(project_path, exist_ok=True)
        with open(os.path.join(project_path, f"PM_SESSION_{project_id}.md"), "w", encoding="utf-8") as f:
            f.write("# PM_SESSION\n")
        # 完整台账骨架（含 ## 变更单索引 标题 + 8列结构）
        ledger_dir = os.path.join(project_path, "04_监控", "01_变更管理", "02_变更记录")
        os.makedirs(ledger_dir, exist_ok=True)
        ledger_path = os.path.join(ledger_dir, "01_版本变更台帐.md")
        with open(ledger_path, "w", encoding="utf-8") as f:
            f.write(
                "# 版本变更台帐\n\n"
                "## 变更单索引\n\n"
                "| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |\n"
                "|------|----------|------|--------|----------|----------|----------|------|\n"
            )

        svc = ChangeService(workspace_root)
        cr = svc.create_change_request(
            project_id=project_id,
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="retrofit测试人员",
            background="retrofit模式测试背景",
            necessity="retrofit模式测试必要性",
            retrofit=True,
        )

        # 1. 返回状态为 closed
        assert cr.change_number.startswith("CHG-PLC-")
        assert cr.status == "closed", f"retrofit 模式应返回 closed，实际: {cr.status}"
        assert os.path.isfile(cr.file_path)

        # 2. CHG 文件 §3.4 状态字段为 closed
        with open(cr.file_path, encoding="utf-8") as f:
            chg_content = f.read()
        assert "| 变更状态 | closed |" in chg_content, "CHG 文件 §3.4 状态字段应为 closed"

        # 3. 台账记录状态为 ✅已关闭 + 完成日期
        with open(ledger_path, encoding="utf-8") as f:
            ledger_content = f.read()
        assert cr.change_number in ledger_content, "台账应包含 retrofit 创建的变更编号"
        assert "✅已关闭" in ledger_content, "台账状态应为 ✅已关闭"


class TestValidationFunctions:
    """变更管理规范校验函数测试"""

    def test_validate_domain_valid(self) -> None:
        """合法领域通过"""
        validate_domain("PLC")
        validate_domain("DOCU")

    def test_validate_domain_invalid(self) -> None:
        """非法领域抛异常"""
        with pytest.raises(SpecViolationError, match="技术领域"):
            validate_domain("INVALID")

    def test_validate_business_nature_valid(self) -> None:
        """合法业务性质通过"""
        validate_business_nature("DEF")
        validate_business_nature("REQ")

    def test_validate_business_nature_invalid(self) -> None:
        """非法业务性质抛异常"""
        with pytest.raises(SpecViolationError, match="业务性质"):
            validate_business_nature("INVALID")

    def test_validate_impact_scope_valid(self) -> None:
        """合法影响范围通过"""
        validate_impact_scope(["LOCAL", "MODULE"])

    def test_validate_impact_scope_invalid(self) -> None:
        """非法影响范围抛异常"""
        with pytest.raises(SpecViolationError, match="影响范围"):
            validate_impact_scope(["INVALID"])

    def test_validate_urgency_valid(self) -> None:
        """合法紧急程度通过"""
        validate_urgency("normal")
        validate_urgency("urgent")
        validate_urgency("critical")

    def test_validate_urgency_invalid(self) -> None:
        """非法紧急程度抛异常"""
        with pytest.raises(SpecViolationError, match="紧急程度"):
            validate_urgency("INVALID")

    def test_validate_status_transition_valid(self) -> None:
        """合法状态流转通过"""
        validate_status_transition("draft", "submitted")

    def test_validate_status_transition_invalid_current(self) -> None:
        """非法当前状态抛异常"""
        with pytest.raises(SpecViolationError, match="当前状态"):
            validate_status_transition("invalid_status", "submitted")

    def test_validate_status_transition_invalid_target(self) -> None:
        """非法目标状态抛异常"""
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("draft", "completed")


class TestChg085VerificationGate:
    """CHG-085 §10.1 验证项清单门禁测试"""

    def _make_service(self, tmp_path: Path) -> ChangeService:
        """构造 ChangeService（_check_all_verification_items_passed 不依赖 workspace）"""
        return ChangeService(str(tmp_path))

    def _make_content(self, items: list[tuple[int, str]]) -> str:
        """构造含 §10.1 验证项清单的 CHG 内容

        Args:
            items: [(序号, 状态), ...]，状态如 "☑通过"/"□待验证"/"不通过"/""
        """
        rows = "\n".join(
            f"| {seq} | 验证项{seq} | 标准 | 预期 | 实际 | {status} | 验证人 | 日期 |"
            for seq, status in items
        )
        return (
            "# CHG-SCPT-2026-085\n\n"
            "## §3 变更基本信息\n\n"
            "状态: accepting\n\n"
            "### 10.1 验证项清单\n\n"
            "| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |\n"
            "|---|--------|----------|----------|----------|------|--------|----------|\n"
            f"{rows}\n\n"
            "### 10.2 跨领域联动验证\n\n"
            "### 10.3 验证结论\n"
        )

    def test_no_section_returns_empty(self, tmp_path: Path) -> None:
        """无 §10.1 章节时返回空列表（向后兼容旧变更单）"""
        svc = self._make_service(tmp_path)
        content = "# CHG\n\n## §3 基本信息\n\n状态: accepting\n"
        assert svc._check_all_verification_items_passed(content) == []

    def test_all_passed_returns_empty(self, tmp_path: Path) -> None:
        """§10.1 全部通过时返回空列表"""
        svc = self._make_service(tmp_path)
        content = self._make_content([
            (1, "☑通过"),
            (2, "☑通过"),
            (3, "☑全部通过"),
        ])
        assert svc._check_all_verification_items_passed(content) == []

    def test_has_pending_returns_pending_items(self, tmp_path: Path) -> None:
        """§10.1 存在未通过项时返回未通过项序号列表"""
        svc = self._make_service(tmp_path)
        content = self._make_content([
            (1, "☑通过"),
            (2, "□待验证"),   # 状态为"待验证"→ 未通过
            (3, "不通过"),     # 明确不通过
            (4, ""),           # 空状态 → 未通过
        ])
        pending = svc._check_all_verification_items_passed(content)
        assert pending == [2, 3, 4]


# ── P2-5: CHG 章节完整性校验测试 ──────────────────────────


class TestChapterCompleteness:
    """P2-5: CHG 章节完整性校验测试（_check_chapter_completeness + closed 门禁）"""

    def _make_service(self, tmp_path: Path) -> ChangeService:
        """构造 ChangeService（_check_chapter_completeness 不依赖 workspace）"""
        return ChangeService(str(tmp_path))

    def _build_full_chapters_content(self) -> str:
        """构建含全部 13 章节三级标题 + 实质内容 + completed 状态的 CHG markdown"""
        return """# 变更单

## 3. 变更基本信息

### 3.5 变更状态
| 字段 | 内容 |
|------|------|
| 变更状态 | completed |

### §5 变更前后
变更前内容描述
变更后内容描述

### §6.1 五大约束影响
约束影响分析内容

### §6.2 跨领域影响
跨领域影响分析

### §6.3 变更传播链
传播链分析内容

### §7 实施计划
实施计划内容

### §8.1 审批流程
审批流程内容

### §8.2 审批结论
审批结论内容

### §9 变更实施记录
实施记录内容

### §10.1 验证项清单
验证项内容

### §10.2 跨领域联动验证
联动验证内容

### §10.3 验证结论
验证结论内容

### §11 版本详细变更说明
版本变更说明内容

### §12 附录
附录内容
"""

    def test_required_chapters_count(self) -> None:
        """_REQUIRED_CHAPTERS 应包含 13 个章节"""
        assert len(ChangeService._REQUIRED_CHAPTERS) == 13

    def test_required_chapters_keys(self) -> None:
        """13 章节编号正确"""
        nums = [num for num, _name, _pattern in ChangeService._REQUIRED_CHAPTERS]
        assert nums == [
            "5", "6.1", "6.2", "6.3", "7",
            "8.1", "8.2", "9", "10.1", "10.2", "10.3", "11", "12",
        ]

    def test_check_chapter_completeness_all_present(self, tmp_path: Path) -> None:
        """13 章节齐全且非空时返回空列表"""
        svc = self._make_service(tmp_path)
        content = self._build_full_chapters_content()
        missing = svc._check_chapter_completeness(content)
        assert missing == [], f"应无缺失章节，实际缺失: {missing}"

    def test_check_chapter_completeness_generated_h2_format(
        self, tmp_path: Path
    ) -> None:
        """生成器使用的二级章节标题也应通过关闭前完整性检查"""
        svc = self._make_service(tmp_path)
        content = self._build_full_chapters_content().replace("### ", "## ")
        missing = svc._check_chapter_completeness(content)
        assert missing == [], f"二级标题格式不应被误判为缺失: {missing}"

    def test_check_chapter_completeness_nested_h2_sections(
        self, tmp_path: Path
    ) -> None:
        """带二级主标题和三级子标题的生成式章节应保留正文"""
        svc = self._make_service(tmp_path)
        content = self._build_full_chapters_content()
        content = content.replace(
            "### §5 变更前后\n变更前内容描述\n变更后内容描述",
            "## 5. 变更内容\n\n### 5.1 变更前\n变更前内容描述\n\n### 5.2 变更后\n变更后内容描述",
        )
        content = content.replace(
            "### §12 附录\n附录内容",
            "## 12. 附录\n\n### 12.1 填写指南\n附录内容",
        )
        missing = svc._check_chapter_completeness(content)
        assert missing == [], f"嵌套子标题不应导致章节被误判为空: {missing}"

    def test_check_chapter_completeness_missing(self, tmp_path: Path) -> None:
        """缺失 §11/§12 时返回对应章节名"""
        svc = self._make_service(tmp_path)
        content = self._build_full_chapters_content()
        content = content.replace(
            "### §11 版本详细变更说明\n版本变更说明内容\n\n", ""
        )
        content = content.replace("### §12 附录\n附录内容\n", "")
        missing = svc._check_chapter_completeness(content)
        assert "§11 版本详细变更说明" in missing
        assert "§12 附录" in missing

    def test_check_chapter_completeness_empty_section(self, tmp_path: Path) -> None:
        """章节标题存在但正文为空视为缺失"""
        svc = self._make_service(tmp_path)
        content = self._build_full_chapters_content()
        content = content.replace(
            "### §11 版本详细变更说明\n版本变更说明内容\n",
            "### §11 版本详细变更说明\n",
        )
        missing = svc._check_chapter_completeness(content)
        assert "§11 版本详细变更说明" in missing

    def test_check_chapter_completeness_legacy_format_no_section_sign(
        self, tmp_path: Path
    ) -> None:
        """旧格式 `### 10.1`（不带 §）能被匹配（§? 可选匹配兼容性）"""
        svc = self._make_service(tmp_path)
        content = """# 变更单

### 5 变更前后
内容

### 6.1 五大约束影响
内容

### 6.2 跨领域影响
内容

### 6.3 变更传播链
内容

### 7 实施计划
内容

### 8.1 审批流程
内容

### 8.2 审批结论
内容

### 9 变更实施记录
内容

### 10.1 验证项清单
内容

### 10.2 跨领域联动验证
内容

### 10.3 验证结论
内容

### 11 版本详细变更说明
内容

### 12 附录
内容
"""
        missing = svc._check_chapter_completeness(content)
        assert missing == [], f"旧格式（不带§）应兼容，实际缺失: {missing}"

    def test_transition_to_closed_blocked_when_incomplete(self, tmp_path: Path) -> None:
        """章节不完整时流转 closed 抛 TransitionGuardError"""
        from auto_pm.change.constants import TransitionGuardError

        project_id = "TEST-2026-001"
        project_path = tmp_path / project_id
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / f"PM_SESSION_{project_id}.md").write_text(
            "# PM_SESSION\n", encoding="utf-8"
        )
        chg_dir = (
            project_path / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-DOCU"
        )
        chg_dir.mkdir(parents=True, exist_ok=True)
        # completed 状态但无 §5-§12 三级标题章节
        (chg_dir / "CHG-DOCU-2026-001.md").write_text(
            "# 变更单\n\n## 3. 变更基本信息\n\n### 3.5 变更状态\n"
            "| 字段 | 内容 |\n|------|------|\n| 变更状态 | completed |\n",
            encoding="utf-8",
        )
        ledger_dir = (
            project_path / "04_监控" / "01_变更管理" / "02_变更记录"
        )
        ledger_dir.mkdir(parents=True, exist_ok=True)
        (ledger_dir / "01_版本变更台帐.md").write_text(
            "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n",
            encoding="utf-8",
        )

        svc = ChangeService(str(tmp_path))
        with pytest.raises(TransitionGuardError, match="章节不完整"):
            svc.transition_status(
                "CHG-DOCU-2026-001", "closed", approver="管理员"
            )

    def test_transition_to_closed_allowed_when_complete(self, tmp_path: Path) -> None:
        """13 章节齐全时流转 closed 成功"""
        project_id = "TEST-2026-001"
        project_path = tmp_path / project_id
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / f"PM_SESSION_{project_id}.md").write_text(
            "# PM_SESSION\n", encoding="utf-8"
        )
        chg_dir = (
            project_path / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-DOCU"
        )
        chg_dir.mkdir(parents=True, exist_ok=True)
        # completed 状态 + 全部 13 章节
        (chg_dir / "CHG-DOCU-2026-001.md").write_text(
            self._build_full_chapters_content(), encoding="utf-8"
        )
        ledger_dir = (
            project_path / "04_监控" / "01_变更管理" / "02_变更记录"
        )
        ledger_dir.mkdir(parents=True, exist_ok=True)
        (ledger_dir / "01_版本变更台帐.md").write_text(
            "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n",
            encoding="utf-8",
        )

        svc = ChangeService(str(tmp_path))
        cr = svc.transition_status(
            "CHG-DOCU-2026-001", "closed", approver="管理员"
        )
        assert cr is not None
        assert cr.status == "closed"
