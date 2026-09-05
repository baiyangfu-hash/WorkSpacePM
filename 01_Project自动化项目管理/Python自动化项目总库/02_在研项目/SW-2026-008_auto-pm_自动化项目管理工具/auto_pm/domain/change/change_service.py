"""PLC-HMI 概念映射：SFB 库函数（变更单服务（CRUD 操作））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变更管理 Service - 变更单 CRUD + 状态流转

M3-Iter2 重构：从 870 行上帝类拆分为 4 个职责单一的类：
- ChangeService（本类）：CRUD + 状态流转编排
- ChangeFileLocator：文件路径定位
- ChangeMarkdownEditor：Markdown 内容编辑
- TransitionGuardChecker：状态流转门禁检查

本类通过组合方式使用上述模块，保留旧方法签名以向后兼容。
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from typing import TYPE_CHECKING, Any, cast

from auto_pm.change.constants import (
    LEDGER_STATUS_MAP,
    ChangeRequest,
    ChangeSummary,
    SpecViolationError,
    TransitionGuardError,
    validate_business_nature,
    validate_domain,
    validate_impact_scope,
    validate_status_transition,
    validate_urgency,
)
from auto_pm.change.file_locator import ChangeFileLocator
from auto_pm.change.guard_checker import TransitionGuardChecker
from auto_pm.change.markdown_editor import ChangeMarkdownEditor
from auto_pm.change.parser import ChgParser
from auto_pm.change.path_resolver import find_ledger_file, get_or_create_ledger_file
from auto_pm.core.paths import PG_MONITORING_DIR
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository, ProjectRepository
from auto_pm.models import ApprovalRecord
from auto_pm.models.change import ImpactAnalysis
from auto_pm.models.project import ProjectRecord
from auto_pm.utils.file_utils import (
    StaleFileError,
    get_mtime,
    read_file_snapshot,
    write_file,
)

if TYPE_CHECKING:
    from auto_pm.change.generator import ChgGenerator
    from auto_pm.change.ledger_updater import LedgerUpdater

log = logging.getLogger(__name__)


def _is_verification_passed(conclusion: str) -> bool:
    """检查验证结论是否表示通过（V0.3.0-M0.5-Phase1 BUG-001 修复）

    规则：
    - 必须包含"通过"关键词
    - 不能包含"不通过"/"部分通过"/"未通过"等否定关键词（强约束：未通过不得完成验收）

    允许的表达：
    - "全部通过"
    - "全部通过（附说明）"
    - "通过，存在观察项"
    - "通过"

    拒绝的表达：
    - "不通过"
    - "部分通过"（部分通过不是全部通过，视为未通过）
    - "未通过"
    - ""（空）
    """
    if not conclusion:
        return False
    # 否定关键词清单：包含任一即视为未通过
    fail_keywords = ["不通过", "部分通过", "未通过"]
    for kw in fail_keywords:
        if kw in conclusion:
            return False
    return "通过" in conclusion


# 台帐状态文案映射（TD-T10 修复：transition 流转后自动更新台帐状态行）
_LEDGER_STATUS_MAP = LEDGER_STATUS_MAP  # 向后兼容别名（CHG-108 缺陷 1：常量已提取到 constants.py）


class ChangeService:
    """变更管理 Service - 变更单 CRUD + 状态流转

    通过组合 ChangeFileLocator / ChangeMarkdownEditor / TransitionGuardChecker
    实现职责分离。本类保留对外的旧方法签名（如 _find_change_file 等）以避免
    破坏调用方，内部全部委托给组合对象。
    """

    # update_change_request 允许修改的字段
    _UPDATABLE_FIELDS: set[str] = {
        # §4/§3.4 基本字段
        "background",
        "necessity",
        "references",
        "planned_date",
        "urgency",
        # §6 影响分析字段（M3-1 新增）
        "risk_level",
        "mitigation",
        "propagation_chain",
        "constraint_impacts",
        "domain_impacts",
    }

    # update_change_request 禁止修改的字段（受保护）
    _PROTECTED_FIELDS: set[str] = {"change_number", "project_id", "status"}

    def __init__(self, workspace_root: str, db: DatabaseManager | None = None) -> None:
        self.workspace_root = workspace_root
        self._parser = ChgParser()
        # 延迟导入，避免循环依赖
        self._generator: ChgGenerator | None = None
        self._ledger_updater: LedgerUpdater | None = None
        # DB 缓存（可选，传入后 list_all_changes/update/delete 会同步缓存）
        self.db = db
        self._repo: ChangeRequestRepository | None = ChangeRequestRepository(db) if db else None
        # M2-3 T55: 项目表 Repository（用于满足 change_requests 外键约束）
        self._project_repo: ProjectRepository | None = ProjectRepository(db) if db else None
        # M3-Iter2: 组合职责单一的辅助类
        self._locator = ChangeFileLocator(workspace_root, self._parser)
        self._editor = ChangeMarkdownEditor()
        self._guard = TransitionGuardChecker()

    def _get_generator(self) -> ChgGenerator:
        if self._generator is None:
            from auto_pm.change.generator import ChgGenerator

            self._generator = ChgGenerator()
        return self._generator

    def _get_ledger_updater(self) -> LedgerUpdater:
        if self._ledger_updater is None:
            from auto_pm.change.ledger_updater import LedgerUpdater

            self._ledger_updater = LedgerUpdater()
        return self._ledger_updater

    @staticmethod
    def _find_project_root_from_path(file_path: str) -> str | None:
        """从文件路径向上查找项目根目录（TD-T10 修复）

        判据：包含 `00_项目管理` 或 `01_项目文档` 目录的路径视为项目根目录。

        Args:
            file_path: CHG 文件路径

        Returns:
            项目根目录路径，未找到返回 None
        """
        current = os.path.dirname(os.path.abspath(file_path))
        while current and current != os.path.dirname(current):
            # CHG-SCPT-2026-146: 5大过程组统一路径，通过监控过程组目录识别项目根
            if os.path.isdir(os.path.join(current, PG_MONITORING_DIR)):
                return current
            current = os.path.dirname(current)
        return None

    def create_change_request(
        self,
        project_id: str,
        domain: str,
        business_nature: str,
        impact_scope: list[str],
        applicant: str,
        background: str,
        necessity: str,
        references: str = "",
        planned_date: str | None = None,
        urgency: str = "normal",
        retrofit: bool = False,
    ) -> ChangeRequest:
        """创建变更单

        1. 生成变更编号 CHG-{DOMAIN}-{YYYY}-{XXX}
        2. 渲染 CHG-040 模板
        3. 保存 Markdown 文件
        4. 更新版本变更台帐

        Args:
            retrofit: CHG-108 缺陷 3 修复——"先实施后补"工作流。
                True 时直接创建 closed 状态变更单（跳过状态流转），
                §3.4 写入 closed，台账写入 ✅已关闭 + 完成日期。
                适用于已实施的变更事后补单场景。
        """
        project_path = self._locator.get_project_path(project_id)
        if not project_path:
            log.error("创建变更单失败: 项目不存在 %s", project_id)
            raise ValueError(f"项目不存在: {project_id}")

        # 规范校验：创建前必须通过
        validate_domain(domain)
        validate_business_nature(business_nature)
        validate_impact_scope(impact_scope)
        validate_urgency(urgency)

        # 生成变更编号
        change_number = self._locator.generate_change_number(project_path, domain)
        log.info(
            "创建变更单: %s, 项目=%s, 领域=%s, 性质=%s, 范围=%s, retrofit=%s",
            change_number,
            project_id,
            domain,
            business_nature,
            impact_scope,
            retrofit,
        )

        # 构造 ChangeRequest（CHG-108 缺陷 3：retrofit 模式直接 closed）
        today = datetime.date.today().isoformat()
        initial_status = "closed" if retrofit else "draft"
        cr = ChangeRequest(
            change_number=change_number,
            project_id=project_id,
            project_name=project_id,
            domain=domain,
            business_nature=business_nature,
            impact_scope=impact_scope,
            applicant=applicant,
            apply_date=today,
            planned_date=planned_date or today,
            urgency=urgency,
            background=background,
            necessity=necessity,
            references=references,
            status=initial_status,
        )

        # 生成文件路径
        file_path = self._locator.get_change_file_path(project_path, change_number)

        # 防护：禁止覆盖已存在且状态为终态的变更单
        if os.path.isfile(file_path):
            try:
                existing_cr = self._parser.parse(file_path)
                if existing_cr.status in ("closed", "archived"):
                    raise ValueError(
                        f"变更单文件已存在且状态为 {existing_cr.status}（终态），禁止覆盖: {file_path}"
                    )
                log.warning(
                    "变更单文件已存在，将覆盖: %s (当前状态=%s)",
                    file_path,
                    existing_cr.status,
                )
            except ValueError:
                raise
            except (OSError, UnicodeDecodeError) as exc:
                # P1-③ 修复：原缺陷仅 log.warning 后跳过，异常信息不足且行为静默。
                # 现改为 log.error + exc_info=True 完整记录 traceback，便于试用期间追溯。
                # 保留覆盖行为：文件解析失败可能为损坏，用户显式创建新变更单时应允许覆盖。
                log.error(
                    "变更单文件已存在但解析失败，将覆盖: %s: %s",
                    file_path,
                    exc,
                    exc_info=True,
                )

        # 渲染并保存
        content = self._get_generator().render(cr)
        write_file(file_path, content)
        cr.file_path = file_path
        log.info("变更单文件已保存: %s", file_path)

        # 更新台帐
        # V0.2.1-P2-8: 台帐文件不存在时自动创建（含变更单索引表格骨架）
        # CHG-085：调用 update() 时传入 applicant/apply_date，避免台账字段空缺
        # CHG-108 缺陷 3：retrofit 模式下追加记录后立即更新状态为 ✅已关闭 + 完成日期
        ledger_path = get_or_create_ledger_file(project_path)
        if ledger_path:
            apply_date = planned_date or datetime.date.today().isoformat()
            self._get_ledger_updater().update(
                ledger_path,
                change_number,
                background[:50],
                applicant=applicant,
                apply_date=apply_date,
            )
            if retrofit:
                # retrofit 模式：台账状态直接写 ✅已关闭 + 完成日期
                self._get_ledger_updater().update_status(
                    ledger_path,
                    change_number,
                    "✅已关闭",
                    complete_date=today,
                    applicant=applicant,
                    apply_date=apply_date,
                )
                log.info("retrofit 模式: 台账状态直接置为 ✅已关闭: %s", change_number)
            log.info("台帐已更新: %s", ledger_path)
        else:
            log.warning("台帐文件创建失败，跳过更新: %s", project_path)

        # M2-3 T53: 同步写入 DB 缓存和影响分析
        if self._repo is not None:
            # T55: 先确保 projects 表有记录（change_requests.project_id 外键约束）
            if self._project_repo and self._project_repo.get_by_id(project_id) is None:
                self._project_repo.upsert(
                    ProjectRecord(
                        project_id=project_id,
                        name=project_id,
                        path=project_path,
                        stack="unknown",
                    )
                )
            # 然后写 change_requests + impact_analysis
            summary = self._parser.to_summary(cr)
            self._repo.upsert(summary, file_path, get_mtime(file_path))
            analysis = self._parser.to_impact_analysis(cr)
            self._repo.save_impact_analysis(analysis)
            log.debug("DB 缓存和影响分析已写入: %s", change_number)

        return cr

    def list_change_requests(
        self,
        project_id: str,
        status: str | None = None,
        domain: str | None = None,
    ) -> list[ChangeSummary]:
        """列出变更单，支持筛选"""
        project_path = self._locator.get_project_path(project_id)
        if not project_path:
            log.warning("列出变更单: 项目不存在 %s", project_id)
            return []

        from auto_pm.change.path_resolver import scan_change_files

        change_files = scan_change_files(project_path)
        log.info(
            "列出变更单: %s, 共%d个文件, 筛选status=%s domain=%s",
            project_id,
            len(change_files),
            status,
            domain,
        )
        summaries: list[ChangeSummary] = []
        for cf in change_files:
            cr = self._parser.parse(cf)
            summary = self._parser.to_summary(cr)
            # 筛选
            if status and summary.status != status:
                continue
            if domain and summary.domain != domain:
                continue
            summaries.append(summary)

        log.info("筛选结果: %d 条变更单", len(summaries))

        # V9: 按照时间倒序显示（若时间相同或无效，按变更编号倒序），确保最近的变更单在最上面
        def sort_key(s: ChangeSummary) -> tuple[str, str]:
            d = s.apply_date or ""
            if d == "待补充":
                d = ""
            return (d, s.change_number or "")

        summaries.sort(key=sort_key, reverse=True)
        return summaries

    def get_change_request(
        self, change_number: str, project_id: str | None = None
    ) -> ChangeRequest | None:
        """获取变更单完整内容

        Args:
            change_number: 变更单编号
            project_id: 项目编号（可选，跨项目单号冲突时指定，TD-A04 修复）
        """
        file_path = self._locator.find_change_file(change_number, project_id=project_id)
        if not file_path:
            log.warning("获取变更单: 文件未找到 %s", change_number)
            return None
        log.debug("获取变更单: %s, 文件=%s", change_number, file_path)
        return self._parser.parse(file_path)

    def _check_all_verification_items_passed(self, content: str) -> list[int]:
        """检查 §10.1 验证项清单是否全部通过（CHG-085 门禁强化）

        解析 §10.1 表格所有数据行，返回未通过项的序号列表。
        空行（序号为空或非数字）跳过，不视为未通过。

        列结构（generator.py §10.1 模板）:
            | # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
        状态列位于 parts[6]，移除 ☑/☐ 标记后判定：
            - 空 → 未填写，视为未通过
            - 含"不通过"/"未通过" → 未通过
            - 不含"通过" → 未通过
            - 含"通过"且不含否定关键词 → 通过

        Args:
            content: CHG 文件完整内容

        Returns:
            未通过项的序号列表（空列表表示全部通过或无 §10.1 章节）
        """
        # 定位 §10.1 起始位置（兼容 ### 10.1 / ### §10.1）
        sec_match = re.search(r"^###\s*§?\s*10\.1\b", content, re.MULTILINE)
        if not sec_match:
            return []  # 无 §10.1 章节，不强制校验（向后兼容旧变更单）

        # §10.1 区域：从章节头结束到下一个 ## 标题
        start = sec_match.end()
        next_sec = re.search(r"^##\s", content[start:], re.MULTILINE)
        end = start + next_sec.start() if next_sec else len(content)
        section = content[start:end]

        pending: list[int] = []
        for line in section.split("\n"):
            line = line.rstrip()
            if not line.startswith("|"):
                continue
            # 跳过分隔行
            if "---" in line:
                continue
            parts = line.split("|")
            if len(parts) < 7:
                continue
            seq_str = parts[1].strip()
            # 跳过表头行
            if seq_str in ("#", "序号", "No", "no"):
                continue
            # 跳过空序号行（模板占位符）
            if not seq_str:
                continue
            # 跳过非数字序号
            try:
                seq = int(seq_str)
            except ValueError:
                continue
            # 检查状态列（parts[6]）
            status = parts[6].strip() if len(parts) > 6 else ""
            # 移除 ☑/☐ 等标记后判断
            status_clean = status.replace("☑", "").replace("☐", "").strip()
            # 空状态视为未填写（未通过）
            if not status_clean:
                pending.append(seq)
                continue
            # 包含"不通过"/"未通过"视为未通过
            if "不通过" in status_clean or "未通过" in status_clean:
                pending.append(seq)
                continue
            # 必须包含"通过"才视为通过
            if "通过" not in status_clean:
                pending.append(seq)

        return pending

    # CHG 章节完整性要求（12 章节需非空才能流转到 closed）
    # 格式: (章节号, 章节名称, 检测正则)
    _REQUIRED_CHAPTERS: list[tuple[str, str, str]] = [
        ("5", "§5 变更前后", r"^###\s*§?\s*5\b"),
        ("6.1", "§6.1 五大约束影响", r"^###\s*§?\s*6\.1\b"),
        ("6.2", "§6.2 跨领域影响", r"^###\s*§?\s*6\.2\b"),
        ("6.3", "§6.3 变更传播链", r"^###\s*§?\s*6\.3\b"),
        ("7", "§7 实施计划", r"^###\s*§?\s*7\b"),
        ("8.1", "§8.1 审批流程", r"^###\s*§?\s*8\.1\b"),
        ("8.2", "§8.2 审批结论", r"^###\s*§?\s*8\.2\b"),
        ("9", "§9 变更实施记录", r"^###\s*§?\s*9\b"),
        ("10.1", "§10.1 验证项清单", r"^###\s*§?\s*10\.1\b"),
        ("10.2", "§10.2 跨领域联动验证", r"^###\s*§?\s*10\.2\b"),
        ("10.3", "§10.3 验证结论", r"^###\s*§?\s*10\.3\b"),
        ("11", "§11 版本详细变更说明", r"^###\s*§?\s*11\b"),
        ("12", "§12 附录", r"^###\s*§?\s*12\b"),
    ]

    def _check_chapter_completeness(self, content: str) -> list[str]:
        """检查 CHG 变更单 12 章节完整性（P2-5）

        在流转到 closed 前校验所有必需章节是否非空。
        返回缺失的章节名称列表（空列表表示全部完整）。

        Args:
            content: CHG 文件完整内容

        Returns:
            缺失的章节名称列表
        """
        missing: list[str] = []
        for _num, name, pattern in self._REQUIRED_CHAPTERS:
            match = re.search(pattern, content, re.MULTILINE)
            if not match:
                missing.append(name)
                continue
            # 检查章节是否有实质内容（不只是标题行）
            # match.end() 位于章节编号之后（如 "11" 之后），需跳过当前标题行剩余部分
            # 否则标题文字（如 "版本详细变更说明"）会被误判为正文，导致空正文章节漏检
            start = match.end()
            line_end = content.find("\n", start)
            if line_end != -1:
                start = line_end + 1
            # 找到下一个 ## 或 ### 标题
            next_sec = re.search(r"^#{2,3}\s", content[start:], re.MULTILINE)
            end = start + next_sec.start() if next_sec else len(content)
            section_content = content[start:end].strip()
            # 如果章节内容为空（只有标题），视为缺失
            if not section_content or section_content in ("", "-", "无", "N/A"):
                missing.append(name)
        return missing

    def _check_doc_sync(self, project_id: str | None) -> list[str]:
        """运行文档同步检查（SHC-011, SHC-014）（CHG-SCPT-2026-145）

        在 CHG 流转到 completed 前调用，检查版本号一致性和文档索引有效性。
        返回 ERROR 级别的检查结果描述列表（空列表表示通过）。

        Args:
            project_id: 项目编号（如 SW-2026-008）

        Returns:
            ERROR 级别检查结果描述列表
        """
        if not project_id:
            return []

        try:
            from pathlib import Path

            from auto_pm.spec.core.checker_base import HealthChecker, Severity
            from auto_pm.spec.core.config import WorkspaceConfig
            from auto_pm.spec.core.registry import SpecRegistry
            from auto_pm.spec.core.scanner import SpecScanner
        except ImportError:
            log.warning("文档同步检查依赖不可用，跳过")
            return []

        workspace = Path(self.workspace_root)
        workspace = Path(self.workspace_root)
        # 查找项目根目录（优先使用包含标志文件的根目录，避免命中子目录测试/历史 PM_SESSION）
        pm_files = list(workspace.rglob(f"PM_SESSION_{project_id}*.md"))
        if not pm_files:
            return []  # 找不到 PM_SESSION 文件时跳过

        target_pm = pm_files[0]
        for f in pm_files:
            p = f.parent
            if (
                (p / ".copier-answers.yml").exists()
                or (p / ".plc.json").exists()
                or (p / "pyproject.toml").exists()
            ):
                target_pm = f
                break

        project_root = target_pm.parent
        config = WorkspaceConfig(workspace=workspace)
        scanner = SpecScanner(workspace=workspace, config=config, project_root=project_root)
        registry = SpecRegistry(workspace)
        registry.load()  # 显式加载，确保依赖 registry 数据的检查器可正常工作

        hc = HealthChecker()
        errors: list[str] = []
        for check_id in ("SHC-011", "SHC-014"):
            results = hc.run_by_id(check_id, registry, scanner)
            for r in results:
                if r.severity == Severity.ERROR:
                    errors.append(f"[{check_id}] {r.message}: {r.details}")
        return errors

    def transition_status(
        self,
        change_number: str,
        new_status: str,
        approver: str = "",
        comment: str = "",
        verification_conclusion: str = "全部通过",
        allow_partial_verification: bool = False,
        project_id: str | None = None,
    ) -> ChangeRequest | None:
        """状态流转（PM-042 V2.2.0 §5.2 状态机）

        更新变更单文件中的审批/实施/验证章节。
        状态机定义见 spec_constants.STATUS_FLOW，门禁规则见 _check_transition_guards。

        验收流程（V2.2.0 新增）:
            implementing → pending_acceptance → accepting → completed
                                                         ↘ implementing（返工）
        """
        file_path = self._locator.find_change_file(change_number, project_id=project_id)
        if not file_path:
            log.warning("状态流转: 变更单文件未找到 %s", change_number)
            return None

        log.info(
            "状态流转: %s → %s, 审批人=%s, 验证结论=%s",
            change_number,
            new_status,
            approver,
            verification_conclusion,
        )

        # 读取当前内容，获取当前状态
        content, original_mtime = read_file_snapshot(file_path)
        if not content:
            log.error("状态流转: 读取变更单内容失败 %s", file_path)
            return None

        # 规范校验：状态流转必须合法
        current_cr = self._parser.parse(file_path)
        try:
            validate_status_transition(current_cr.status, new_status)
        except SpecViolationError as e:
            log.error("状态流转校验失败: %s", e)
            raise

        today = datetime.date.today().isoformat()

        # ---- 分状态处理写入逻辑和门禁校验 ----
        # 门禁规则完整清单: PM-042 V2.2.0 第四章

        if new_status == "completed":
            # [PM-042 §5.2] accepting → completed: 验证通过路径
            # 门禁1: verification_conclusion 必须包含"通过"且不包含"不通过"（V0.3.0-M0.5-Phase1 BUG-001 修复）
            # 允许自然表达：全部通过 / 全部通过（附说明）/ 通过，存在观察项 等
            # 拒绝：不通过 / 部分不通过 / 未通过 等
            if not _is_verification_passed(verification_conclusion):
                raise TransitionGuardError(
                    f"变更单 {change_number} 验证结论为'{verification_conclusion}'，"
                    "需包含'通过'且不包含'不通过'才能完成验收；"
                    "如验证不通过请使用「退回返工」(accepting → implementing)"
                )

            # [CHG-085 门禁2] §10.1 验证项清单必须全部通过，禁止只填 §10.3 验证结论就流转到 completed
            pending_items = self._check_all_verification_items_passed(content)
            if pending_items and not allow_partial_verification:
                raise TransitionGuardError(
                    f"变更单 {change_number} §10.1 验证项清单存在未通过项（编号：{pending_items}），"
                    "禁止仅凭 §10.3 验证结论流转到 completed；"
                    "请补全 §10.1 验证项或使用 --allow-partial-verification 显式标注部分验证闭环"
                )
            final_conclusion = verification_conclusion
            if pending_items and allow_partial_verification:
                # 部分验证闭环：在验证结论中标注待验证项
                pending_str = ",".join(str(i) for i in pending_items)
                final_conclusion = (
                    f"{verification_conclusion} [部分验证闭环] "
                    f"待验证项：{pending_str}；其余项已验证通过"
                )

            # [CHG-SCPT-2026-145 门禁3] 文档同步检查：SHC-011 版本号一致性 + SHC-014 文档索引有效性
            # 确保变更闭环前 PRD/INT/DSN/TEC 索引有效、版本号四件套一致
            doc_errors = self._check_doc_sync(project_id)
            if doc_errors:
                raise TransitionGuardError(
                    f"变更单 {change_number} 文档同步检查失败（SHC-011/SHC-014）：\n"
                    + "\n".join(f"  - {e}" for e in doc_errors)
                )

            # 门禁通过：写入验证行和验证结论到§10
            verify_row = (
                f"| 1 | 实施完成验证 | 所有变更项已实施 | 通过 | 通过 "
                f"| ☑{final_conclusion} | {approver} | {today} |\n"
            )
            content = self._editor.append_to_verification_table(content, verify_row)
            content = self._editor.update_verification_conclusion(content, final_conclusion)
            # 注意：§3.4 状态字段更新统一在下方第 299 行执行，避免时序 bug（KNOWN-1 修复）

        elif new_status == "closed":
            # [P2-5] completed → closed: 关闭变更单
            # 门禁: 12 章节完整性检查（CHG-SCPT-2026-153: P2-5）
            missing_chapters = self._check_chapter_completeness(content)
            if missing_chapters:
                raise TransitionGuardError(
                    f"变更单 {change_number} 章节不完整，"
                    f"缺失 {len(missing_chapters)} 个必需章节: "
                    + ", ".join(missing_chapters)
                    + "；请补全所有章节后再流转到 closed"
                )
            self._guard.check(current_cr, new_status, approver, comment)

        elif new_status == "archived":
            # [PM-042 V2.3.0 §5.2] completed → archived: 归档
            # 门禁: 仅 completed 状态可归档（在 _check_transition_guards 中校验）
            self._guard.check(current_cr, new_status, approver, comment)

        elif new_status == "pending_acceptance":
            # [PM-042 §5.2] implementing → pending_acceptance: 提交验收
            # 门禁: §9 实施记录至少一条（第四章）
            self._guard.check(current_cr, new_status, approver, comment)

        elif new_status == "accepting":
            # [PM-042 §5.2] pending_acceptance → accepting: 开始验收
            # 门禁: 无额外门禁（第四章）
            self._guard.check(current_cr, new_status, approver, comment)

        elif new_status == "implementing" and current_cr.status == "accepting":
            # [PM-042 §5.2] accepting → implementing: 验证不通过，返工重做
            # 门禁: 无额外门禁 — 允许立即返回重做（第四章 路径B）
            self._guard.check(current_cr, new_status, approver, comment)

        else:
            # 其他流转：门禁检查已有内容
            self._guard.check(current_cr, new_status, approver, comment)

        # 1. 更新 §3.4 变更状态字段（状态持久化的主路径）
        content = self._editor.update_status_field(content, new_status)

        # 2. 更新相关章节记录
        if new_status in ("approved", "conditionally_approved", "rejected"):
            # 审批环节名称使用中文语义化标签（对齐 STATUS_LABELS）
            from auto_pm.change.constants import STATUS_LABELS

            status_label = STATUS_LABELS.get(new_status, new_status)
            approval_row = f"| **{status_label}** | {approver} | {comment or '同意'} | {today} | {approver} |\n"
            content = self._editor.append_to_approval_table(content, approval_row)
        elif new_status == "implementing":
            # 区分首次实施 vs 返工重做
            if current_cr.status in ("approved", "conditionally_approved"):
                impl_row = f"| {today} | {approver} | 实施中 | 开始实施 | 进行中 | |\n"
            else:
                # accepting → implementing（返工）：记录返工原因
                impl_row = f"| {today} | {approver} | 返工重做 | 验证不通过: {(comment or '需重新实施')[:30]} | 返工中 | |\n"
            content = self._editor.append_to_implementation_table(content, impl_row)
        # completed: §10 已在门禁前写入
        # pending_acceptance / accepting: 无额外章节需要写入

        try:
            write_file(file_path, content, expected_mtime=original_mtime)
        except StaleFileError as exc:
            log.error("状态流转: 文件已被外部修改，取消写入 %s: %s", file_path, exc)
            return None

        # M2-3 T52: 同步写入审批历史到 DB（每次流转追加一条记录）
        if self._repo is not None:
            self._repo.save_approval_record(
                change_number=change_number,
                to_status=new_status,
                approver=approver,
                comment=comment,
                from_status=current_cr.status,
                project_id=current_cr.project_id,
            )
            log.debug("审批历史已写入 DB: %s %s → %s", change_number, current_cr.status, new_status)

        # TD-T10 修复：同步更新台帐状态行（transition 流转后自动回写台帐）
        project_path = self._find_project_root_from_path(file_path)
        if project_path:
            ledger_path = find_ledger_file(project_path)
            if ledger_path:
                status_label = _LEDGER_STATUS_MAP.get(new_status, "🔄进行中")
                # CHG-085：流转到 completed/closed/archived 时回写完成日期
                complete_date = ""
                if new_status in ("completed", "closed", "archived"):
                    complete_date = datetime.date.today().isoformat()
                self._get_ledger_updater().update_status(
                    ledger_path,
                    change_number,
                    status_label,
                    complete_date=complete_date,
                    applicant=current_cr.applicant,
                    apply_date=current_cr.apply_date,
                )
                log.debug("台帐状态已同步: %s → %s", change_number, status_label)

        # 重新解析返回
        result = self._parser.parse(file_path)
        log.info("状态流转完成: %s, 新状态=%s", change_number, result.status)
        return result

    def list_approval_history(
        self, change_number: str, project_id: str | None = None
    ) -> list[ApprovalRecord]:
        """查询变更单审批流转历史（供 GUI 审批时间线使用，M3-3 T73）

        Args:
            change_number: 变更单编号
            project_id: 项目编号（B4 新增）

        Returns:
            审批记录列表（按时间顺序，即 id 升序）；无 DB 或无记录时返回空列表
        """
        if self._repo is None:
            return []
        return cast(
            list[ApprovalRecord],
            self._repo.list_approval_history(change_number, project_id=project_id),
        )

    def get_impact_analysis(
        self, change_number: str, project_id: str | None = None
    ) -> ImpactAnalysis | None:
        """查询变更单的影响分析记录（供 GUI 验证摘要使用，M3）

        Args:
            change_number: 变更单编号
            project_id: 项目编号（B4 新增）

        Returns:
            ImpactAnalysis 或 None（无 DB 或无记录时返回 None）
        """
        if self._repo is None:
            return None
        return self._repo.get_impact_analysis(change_number, project_id=project_id)

    # ---- 跨项目查询 / 修改 / 删除 ----

    def list_all_changes(
        self,
        status: str | None = None,
        domain: str | None = None,
        urgency: str | None = None,
        project_id: str | None = None,
    ) -> list[ChangeSummary]:
        """跨项目查询所有变更单（用于变更中心全局列表）

        Args:
            status: 按状态筛选（draft/submitted/approved/implementing/completed/archived 等）
            domain: 按领域筛选（ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE）
            urgency: 按紧急程度筛选（normal/urgent/critical）。注意：DB 缓存模式未持久化
                urgency 字段，DB 路径返回的 summary.urgency 均为默认值 "normal"，因此
                urgency 筛选仅在文件扫描模式（_repo=None）下完整可用。
            project_id: 按项目编号筛选

        Returns:
            变更单摘要列表，按 change_number 排序
        """
        # 优先从 DB 缓存查询；未注入 DB 时回退到文件系统扫描
        if self._repo is not None:
            changes = self._repo.list_all()
        else:
            changes = self._locator.scan_all_change_files()

        if status:
            changes = [c for c in changes if c.status == status]
        if domain:
            changes = [c for c in changes if c.domain == domain]
        if urgency:
            changes = [c for c in changes if c.urgency == urgency]
        if project_id:
            changes = [c for c in changes if c.project_id == project_id]

        log.info(
            "跨项目查询变更单: status=%s domain=%s urgency=%s project_id=%s → %d 条",
            status,
            domain,
            urgency,
            project_id,
            len(changes),
        )
        return sorted(changes, key=lambda c: c.change_number)

    def update_change_request(
        self,
        change_number: str,
        lookup_project_id: str | None = None,
        **kwargs: Any,
    ) -> ChangeRequest | None:
        """修改变更单字段

        支持修改的字段：
        - §4/§3.4 基本字段: background, necessity, references, planned_date, urgency
        - §6 影响分析字段: risk_level, mitigation, propagation_chain,
          constraint_impacts(dict), domain_impacts(dict)
        不允许修改：change_number, project_id, status（用 transition_status）

        Args:
            change_number: 变更单编号
            **kwargs: 要修改的字段（str 或 dict）

        Returns:
            更新后的 ChangeRequest，失败返回 None

        Raises:
            ValueError: 尝试修改受保护字段
            SpecViolationError: urgency 值不合法
        """
        # 1. 校验字段合法性
        for key in kwargs:
            if key in self._PROTECTED_FIELDS:
                log.error("修改变更单: 字段 %s 不允许修改", key)
                raise ValueError(
                    f"字段 '{key}' 不允许修改"
                    + ("（使用 transition_status 修改状态）" if key == "status" else "")
                )

        # 2. 获取变更单文件
        file_path = self._locator.find_change_file(change_number, project_id=lookup_project_id)
        if not file_path:
            log.warning("修改变更单: 文件未找到 %s", change_number)
            return None

        # 3. 校验 urgency 合法性
        if "urgency" in kwargs and kwargs["urgency"] is not None:
            validate_urgency(kwargs["urgency"])

        # 4. 读取文件内容
        content, original_mtime = read_file_snapshot(file_path)
        if not content:
            log.error("修改变更单: 读取文件失败 %s", file_path)
            return None

        # 5. 逐字段修改 .md 章节
        updated_fields: list[str] = []
        for field, value in kwargs.items():
            if field not in self._UPDATABLE_FIELDS or value is None:
                log.debug("修改变更单: 跳过字段 %s（不可修改或为 None）", field)
                continue
            new_content = self._editor.update_field(content, field, value)
            if new_content != content:
                content = new_content
                updated_fields.append(field)

        if not updated_fields:
            log.warning("修改变更单: 无有效字段被更新 %s", change_number)
            return self._parser.parse(file_path)

        # 6. 写回文件
        try:
            write_file(file_path, content, expected_mtime=original_mtime)
        except StaleFileError as exc:
            log.error("修改变更单: 文件已被外部修改，取消写入 %s: %s", file_path, exc)
            return None
        log.info("变更单已修改: %s, 字段=%s", change_number, updated_fields)

        # 7. 重新解析
        updated = self._parser.parse(file_path)

        # 8. 更新 DB 缓存
        if self._repo is not None:
            summary = self._parser.to_summary(updated)
            self._repo.upsert(summary, file_path, get_mtime(file_path))
            # M2-3 T54: 同步更新影响分析
            analysis = self._parser.to_impact_analysis(updated)
            self._repo.save_impact_analysis(analysis)
            log.debug("DB 缓存和影响分析已更新: %s", change_number)

        return updated

    def delete_change_request(self, change_number: str, project_id: str | None = None) -> bool:
        """删除变更单（文件 + DB 缓存）

        Args:
            change_number: 变更单编号
            project_id: 项目编号（可选，跨项目单号冲突时指定，TD-A04 修复）

        Returns:
            True 删除成功，False 不存在
        """
        file_path = self._locator.find_change_file(change_number, project_id=project_id)
        file_deleted = False

        # 1. 删除 .md 文件
        if file_path:
            try:
                os.remove(file_path)
                file_deleted = True
                log.info("变更单文件已删除: %s", file_path)
            except OSError as e:
                log.error("删除变更单文件失败: %s: %s", file_path, e)
        else:
            log.warning("删除变更单: 文件未找到 %s", change_number)

        # 2. 从 DB 缓存删除
        db_deleted = False
        if self._repo is not None:
            db_deleted = self._repo.delete(change_number, project_id=project_id)
            if db_deleted:
                log.info("DB 缓存记录已删除: %s", change_number)

        # 文件或 DB 任一删除成功即视为成功
        return file_deleted or db_deleted

    # ── 向后兼容的委托方法（M3-Iter2 保留签名，内部委托给组合对象） ──

    def _get_project_path(self, project_id: str) -> str | None:
        """[已委托] 根据项目编号获取项目路径（向后兼容包装）"""
        return cast(str | None, self._locator.get_project_path(project_id))

    def _generate_change_number(self, project_path: str, domain: str) -> str:
        """[已委托] 生成变更编号（向后兼容包装）"""
        return cast(str, self._locator.generate_change_number(project_path, domain))

    def _get_change_file_path(self, project_path: str, change_number: str) -> str:
        """[已委托] 根据变更编号获取文件路径（向后兼容包装）"""
        return cast(str, self._locator.get_change_file_path(project_path, change_number))

    def _find_change_file(self, change_number: str, project_id: str | None = None) -> str | None:
        """[已委托] 根据变更编号查找文件（向后兼容包装）"""
        return cast(
            str | None, self._locator.find_change_file(change_number, project_id=project_id)
        )

    def _scan_all_change_files(self) -> list[ChangeSummary]:
        """[已委托] 扫描工作空间所有项目的变更单文件（向后兼容包装）"""
        return cast(list[ChangeSummary], self._locator.scan_all_change_files())

    def _append_to_approval_table(self, content: str, row: str) -> str:
        """[已委托] 在审批流程表格末尾追加一行（向后兼容包装）"""
        return cast(str, self._editor.append_to_approval_table(content, row))

    def _append_to_implementation_table(self, content: str, row: str) -> str:
        """[已委托] 在实施记录表格末尾追加一行（向后兼容包装）"""
        return cast(str, self._editor.append_to_implementation_table(content, row))

    def _append_to_verification_table(self, content: str, row: str) -> str:
        """[已委托] 在验证表格末尾追加一行（向后兼容包装）"""
        return cast(str, self._editor.append_to_verification_table(content, row))

    def _update_status_field(self, content: str, new_status: str) -> str:
        """[已委托] 更新 §3.4 变更状态字段（向后兼容包装）"""
        return cast(str, self._editor.update_status_field(content, new_status))

    def _update_verification_conclusion(self, content: str, conclusion: str) -> str:
        """[已委托] 更新 §10.2 验证结论（向后兼容包装）"""
        return cast(str, self._editor.update_verification_conclusion(content, conclusion))

    def _update_field(self, content: str, field: str, value: str) -> str:
        """[已委托] 根据字段名分发到对应的章节更新逻辑（向后兼容包装）"""
        return cast(str, self._editor.update_field(content, field, value))

    def _update_text_block(self, content: str, label: str, value: str) -> str:
        """[已委托] 更新 §4 中的文本块（向后兼容包装）"""
        return cast(str, self._editor._update_text_block(content, label, value))

    def _update_table_field(self, content: str, field_name: str, value: str) -> str:
        """[已委托] 更新 §3.4 表格中的字段值（向后兼容包装）"""
        return cast(str, self._editor._update_table_field(content, field_name, value))

    def _check_transition_guards(
        self,
        cr: ChangeRequest,
        target_status: str,
        approver: str,
        comment: str,
    ) -> None:
        """[已委托] 检查流转门禁条件（向后兼容包装）"""
        self._guard.check(cr, target_status, approver, comment)

    @staticmethod
    def _render_urgency_value(urgency: str) -> str:
        """[已委托] 渲染紧急程度为 ☑/□ 格式（向后兼容包装）"""
        return cast(str, ChangeMarkdownEditor.render_urgency_value(urgency))

    # 保留旧类属性以兼容外部引用
    _CHANGE_FILE_SEARCH_PATHS = ChangeFileLocator.CHANGE_FILE_SEARCH_PATHS
