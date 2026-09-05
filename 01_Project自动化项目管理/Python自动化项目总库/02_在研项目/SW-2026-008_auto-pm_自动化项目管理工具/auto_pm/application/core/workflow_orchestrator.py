"""auto_pm.application.core.workflow_orchestrator - Cockpit OS 工作流核心编排引擎

遵循 Clean Architecture 架构与 DEV-300 / DEV-210 / PM-042 规范，
整合变更服务 (ChangeService)、决策服务 (DecisionService)、项目服务 (ProjectService)、
规范注册表 (SpecRegistry) 以及事务管理器 (ChangeTransactionManager)，
统一提供工作流方案规划流水线 (plan)、执行流水线 (execute) 与上下文恢复 (resume)。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final

from auto_pm.application.core.change_transaction import ChangeTransactionManager
from auto_pm.application.core.project_service import ProjectService
from auto_pm.contracts.workflow_dtos import (
    TransactionStatus,
    WorkflowExecuteRequestDTO,
    WorkflowExecuteResultDTO,
    WorkflowPlanRequestDTO,
    WorkflowPlanResultDTO,
    WorkflowResumeDTO,
)
from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.decision_service import DecisionService
from auto_pm.domain.spec.core.registry import SpecRegistry
from auto_pm.infrastructure.logging.audit import audit_log

logger = logging.getLogger(__name__)

__all__ = [
    "TransactionStatus",
    "WorkflowOrchestrator",
]

#: 领域到规范集的默认映射规则
DOMAIN_SPECS_MAP: Final[dict[str, list[str]]] = {
    "SCPT": ["PM-042", "DEV-210", "DEV-300"],
    "PLC": ["PM-042", "LSP-905", "STD-830"],
    "HMI": ["PM-042", "DEV-216", "DEV-218"],
}
DEFAULT_SPECS: Final[list[str]] = ["PM-042", "DEV-300"]


class WorkflowOrchestrator:
    """Cockpit OS 工作流核心编排引擎

    负责协调变更管理、决策锁死、项目状态与事务沙箱，提供自动化规划与门禁流转。
    """

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        *,
        change_service: ChangeService | None = None,
        decision_service: DecisionService | None = None,
        project_service: ProjectService | None = None,
        spec_registry: SpecRegistry | None = None,
        transaction_manager: ChangeTransactionManager | None = None,
    ) -> None:
        if workspace_root is not None:
            self.workspace_root: Path = Path(workspace_root).resolve()
        else:
            env_ws = os.environ.get("AUTO_PM_WORKSPACE", "").strip()
            self.workspace_root = Path(env_ws or ".").resolve()

        self.change_service: ChangeService = change_service or ChangeService(
            str(self.workspace_root)
        )
        self.decision_service: DecisionService = decision_service or DecisionService(
            self.workspace_root
        )
        self.project_service: ProjectService = project_service or ProjectService(
            str(self.workspace_root)
        )
        self.spec_registry: SpecRegistry = spec_registry or SpecRegistry(self.workspace_root)
        self.transaction_manager: ChangeTransactionManager = (
            transaction_manager or ChangeTransactionManager(self.workspace_root)
        )

    def _resolve_project_path(self, project_id: str) -> str | None:
        """解析并校验项目物理根路径"""
        project_path = self.change_service._locator.get_project_path(project_id)
        if project_path and os.path.isdir(project_path):
            return str(project_path)

        for p in self.project_service.list_projects():
            if p.project_id == project_id and os.path.isdir(p.path):
                return str(p.path)

        return None

    def _bind_specs(self, domain: str) -> list[str]:
        """动态关联并过滤 Obsidian 规范"""
        candidates = DOMAIN_SPECS_MAP.get(domain.upper(), DEFAULT_SPECS)
        try:
            self.spec_registry.load()
        except Exception as exc:
            logger.warning("加载 SpecRegistry 异常: %s", exc)

        if self.spec_registry and self.spec_registry.raw.get("specs"):
            filtered = [s for s in candidates if self.spec_registry.get_spec(s) is not None]
            return filtered if filtered else list(candidates)

        return list(candidates)

    def _register_intent(
        self,
        project_path: str,
        project_id: str,
        change_id: str,
        title: str,
        target_files: list[str],
        specs_bound: list[str],
    ) -> None:
        """在目标项目 PM_SESSION_<PID>.md 登记规划意图"""
        pm_path = Path(project_path) / f"PM_SESSION_{project_id}.md"
        if not pm_path.exists():
            matches = list(Path(project_path).glob(f"PM_SESSION_{project_id}*.md"))
            if matches:
                pm_path = matches[0]

        today = datetime.now().strftime("%Y-%m-%d")
        files_str = ", ".join(target_files) if target_files else "无"
        specs_str = ", ".join(specs_bound) if specs_bound else "无"
        log_entry = f"  - {today} [规划中] {change_id} {title}：目标文件 [{files_str}]，绑定规范 [{specs_str}]"

        try:
            if pm_path.exists():
                content = pm_path.read_text(encoding="utf-8")
                if "- change_log:" in content:
                    content = content.replace("- change_log:\n", f"- change_log:\n{log_entry}\n", 1)
                elif "## 5. Logs" in content:
                    content = content.replace(
                        "## 5. Logs", f"## 5. Logs\n\n- change_log:\n{log_entry}\n", 1
                    )
                else:
                    content = content.rstrip() + f"\n\n## 5. Logs\n- change_log:\n{log_entry}\n"
                pm_path.write_text(content, encoding="utf-8")
            else:
                initial_content = (
                    f"# PM_SESSION_{project_id}\n\n"
                    f"## 0. Meta\n- project_id: {project_id}\n\n"
                    f"## 5. Logs\n- change_log:\n{log_entry}\n"
                )
                pm_path.write_text(initial_content, encoding="utf-8")
        except OSError as exc:
            logger.warning("登记 PM_SESSION 意图失败 %s: %s", pm_path, exc)

    def plan(self, req: WorkflowPlanRequestDTO) -> WorkflowPlanResultDTO:
        """工作流方案规划流水线 (WBS 2.1)

        1. 校验目标项目物理存在性，不存在立即拦截返回 success=False；
        2. 扫描匹配已有草稿状态变更单，若无则自动调用 ChangeService.create_change_request 创建；
        3. 根据领域动态关联 Obsidian 规范集合，结合 SpecRegistry 过滤确认；
        4. 若提供 approver，按 PM-042 状态机合规推进至 approved，并调用 DecisionService 锁死白名单；
        5. 在目标项目 PM_SESSION_<PID>.md 中记录规划意图；
        6. 返回强类型 WorkflowPlanResultDTO 规划成果。
        """
        project_path = self._resolve_project_path(req.project_id)
        if not project_path:
            logger.warning("工作流规划被拦截: 项目不存在 %s", req.project_id)
            return WorkflowPlanResultDTO(
                success=False,
                project_id=req.project_id,
                change_id="",
                decision_id="",
                specs_bound=[],
                message=f"项目不存在: {req.project_id}",
            )

        change_id = ""
        decision_id = ""

        try:
            # 1. 匹配已有草稿单，无则新建
            drafts = self.change_service.list_change_requests(req.project_id, status="draft")
            domain_matched = [d for d in drafts if getattr(d, "domain", "") == req.domain]
            chosen_drafts = domain_matched if domain_matched else drafts

            if chosen_drafts:
                change_id = chosen_drafts[0].change_number
                logger.info("复用已有草稿变更单: %s (项目 %s)", change_id, req.project_id)
            else:
                cr = self.change_service.create_change_request(
                    project_id=req.project_id,
                    domain=req.domain,
                    business_nature=req.change_type or "OPT",
                    impact_scope=["MODULE"],
                    applicant=req.approver or "pm-workflow",
                    background=req.title,
                    necessity=f"工作流自动化规划: {req.title}",
                )
                change_id = cr.change_number
                logger.info("自动创建新变更单: %s (项目 %s)", change_id, req.project_id)

            # 2. 动态关联并过滤规范
            specs_bound = self._bind_specs(req.domain)

            # 3. 审批与决策包固化
            if req.approver:
                cr_curr = self.change_service.get_change_request(
                    change_id, project_id=req.project_id
                )
                curr_status = cr_curr.status if cr_curr else "draft"

                if curr_status == "draft":
                    self.change_service.transition_status(
                        change_id, "submitted", approver=req.approver, project_id=req.project_id
                    )
                    self.change_service.transition_status(
                        change_id, "under_review", approver=req.approver, project_id=req.project_id
                    )
                    self.change_service.transition_status(
                        change_id,
                        "approved",
                        approver=req.approver,
                        comment="工作流规划自动批准",
                        project_id=req.project_id,
                    )
                elif curr_status == "submitted":
                    self.change_service.transition_status(
                        change_id, "under_review", approver=req.approver, project_id=req.project_id
                    )
                    self.change_service.transition_status(
                        change_id,
                        "approved",
                        approver=req.approver,
                        comment="工作流规划自动批准",
                        project_id=req.project_id,
                    )
                elif curr_status == "under_review":
                    self.change_service.transition_status(
                        change_id,
                        "approved",
                        approver=req.approver,
                        comment="工作流规划自动批准",
                        project_id=req.project_id,
                    )

                # 调用 DecisionService 锁死白名单
                decision_pkg = self.decision_service.create_decision(
                    change_id=change_id,
                    approver=req.approver,
                    project_id=req.project_id,
                    approved_files=req.target_files,
                )
                decision_id = decision_pkg.decision_id
                logger.info(
                    "成功生成结构化决策包: %s, 白名单文件数=%d",
                    decision_id,
                    len(req.target_files),
                )

            # 4. 在 PM_SESSION 登记意图
            self._register_intent(
                project_path=project_path,
                project_id=req.project_id,
                change_id=change_id,
                title=req.title,
                target_files=req.target_files,
                specs_bound=specs_bound,
            )

            return WorkflowPlanResultDTO(
                success=True,
                project_id=req.project_id,
                change_id=change_id,
                decision_id=decision_id,
                specs_bound=specs_bound,
                message=f"工作流规划成功: {change_id}",
                metadata={
                    "title": req.title,
                    "domain": req.domain,
                    "target_files": list(req.target_files),
                    "approver": req.approver,
                },
            )

        except Exception as exc:
            logger.error("工作流方案规划执行异常: %s", exc, exc_info=True)
            return WorkflowPlanResultDTO(
                success=False,
                project_id=req.project_id,
                change_id=change_id,
                decision_id=decision_id,
                specs_bound=[],
                message=f"工作流方案规划异常: {exc}",
            )

    def _get_decision_for_change(self, change_id: str, decision_id: str = "") -> Any | None:
        """获取变更单关联的决策包，优先按 change_id 查询并支持精确回退。"""
        try:
            decisions = self.decision_service.list_decisions(change_id=change_id)
            if decisions:
                return decisions[-1]
        except Exception as exc:
            logger.debug("按变更单查询决策包失败: %s", exc)

        if decision_id:
            try:
                return self.decision_service.get_decision(decision_id)
            except Exception as exc:
                logger.debug("按决策标识查询决策包失败: %s", exc)

        return None

    @staticmethod
    def _canonical_relative_path(path: object) -> str | None:
        """Return a strict, portable project-relative POSIX path.

        The decision package is the authority for a write scope.  Treating a
        path as a plain string is not sufficient: ``..``, absolute paths,
        platform separators, wildcards and empty components can all widen the
        scope after a later filesystem operation.  This method deliberately
        accepts the same narrow form as the decision package contract.
        """
        if not isinstance(path, str) or not path or "\\" in path:
            return None
        candidate = PurePosixPath(path)
        if (
            candidate.is_absolute()
            or candidate.anchor
            or any(part in ("", ".", "..") for part in candidate.parts)
        ):
            return None
        if any(char in path for char in "*?[]"):
            return None
        normalized = candidate.as_posix()
        return normalized if normalized == path else None

    @classmethod
    def _canonical_path_set(cls, paths: object) -> set[str] | None:
        """Canonicalise a path list and reject malformed or duplicate values."""
        if not isinstance(paths, list):
            return None
        canonical: set[str] = set()
        for path in paths:
            normalized = cls._canonical_relative_path(path)
            if normalized is None or normalized in canonical:
                return None
            canonical.add(normalized)
        return canonical

    def _failure(
        self, req: WorkflowExecuteRequestDTO, message: str, status: str = "failed"
    ) -> WorkflowExecuteResultDTO:
        """Create a fail-closed result without performing an audit write."""
        logger.warning("工作流执行被拦截: %s", message)
        return WorkflowExecuteResultDTO(
            success=False,
            project_id=req.project_id,
            change_id=req.change_id,
            status=status,
            error=message,
            message=message,
        )

    def _approved_file_set(self, decision: Any) -> set[str] | None:
        """Read the immutable decision whitelist in its canonical form."""
        raw_files: object
        if isinstance(decision, Mapping):
            raw_files = decision.get("approved_files", [])
        else:
            raw_files = getattr(decision, "approved_files", [])
        return self._canonical_path_set(raw_files)

    def _resolve_contained_path(self, relative_path: str) -> Path:
        """Resolve a canonical path and prove it remains under workspace_root."""
        workspace = self.workspace_root.resolve()
        target = (workspace / relative_path).resolve()
        try:
            target.relative_to(workspace)
        except ValueError as exc:
            raise ValueError(f"目标路径越出工作区: {relative_path}") from exc
        return target

    def execute(self, req: WorkflowExecuteRequestDTO) -> WorkflowExecuteResultDTO:
        """Execute an approved file change, or validate it without writing.

        ``verify_only`` is strictly zero-write: it does not create a
        transaction directory, touch a decision/change record, write an audit
        record, or invoke a callback.  Normal execution accepts only explicit
        UTF-8 text mappings under the immutable decision whitelist.  Git
        staging and commits are deliberately outside this application service.
        """
        if req.auto_commit:
            return self._failure(req, "禁止编排器执行隐式 Git 提交")
        if req.metadata.get("action") is not None:
            return self._failure(req, "禁止通过 metadata.action 注入任意回调")
        if req.metadata.get("simulate_error") is not None:
            return self._failure(req, "禁止通过 metadata 注入执行测试钩子")

        # 1. Read-only identity and state validation.
        project = self.project_service.get_project(req.project_id)
        if not project:
            return self._failure(req, f"项目不存在: {req.project_id}")

        cr = self.change_service.get_change_request(req.change_id, project_id=req.project_id)
        if not cr:
            return self._failure(req, f"变更单不存在: {req.change_id}")

        if cr.status not in ("approved", "implementing"):
            return self._failure(
                req,
                f"变更单状态非法: {cr.status}，仅允许 approved 或 implementing 状态执行",
                cr.status,
            )

        decision = self._get_decision_for_change(req.change_id, req.metadata.get("decision_id", ""))
        if decision is None:
            return self._failure(req, f"未找到变更单对应的审批决策包: {req.change_id}")
        approved_files = self._approved_file_set(decision)
        if approved_files is None:
            return self._failure(req, "审批决策白名单格式非法，拒绝执行")

        requested_files = self._canonical_path_set(req.metadata.get("target_files", []))
        if requested_files is None:
            return self._failure(req, "请求目标文件必须为无重复的 canonical POSIX 相对路径列表")
        files_raw = req.metadata.get("files", {})
        if not isinstance(files_raw, Mapping) or not all(
            isinstance(path, str) and isinstance(content, str)
            for path, content in files_raw.items()
        ):
            return self._failure(req, "文件变更必须是 canonical 路径到文本内容的映射")
        file_paths = self._canonical_path_set(list(files_raw.keys()))
        if file_paths is None:
            return self._failure(req, "文件变更路径必须为无重复的 canonical POSIX 相对路径")
        effective_files = requested_files | file_paths
        if not effective_files.issubset(approved_files):
            return self._failure(req, "目标文件超出审批决策白名单范围")
        try:
            resolved_files = {
                relative: self._resolve_contained_path(relative) for relative in effective_files
            }
        except ValueError as exc:
            return self._failure(req, str(exc))

        # A verify request has no write, including no audit record or state update.
        if req.verify_only:
            return WorkflowExecuteResultDTO(
                success=True,
                project_id=req.project_id,
                change_id=req.change_id,
                status="verified",
                files_changed=[],
                ledger_clean=True,
                git_committed=False,
                commit_hash="",
                message=f"预检验证通过: {req.change_id}",
            )

        target_status = req.metadata.get("target_status", "pending_acceptance")
        if target_status not in ("pending_acceptance", "completed"):
            return self._failure(req, "目标状态仅允许 pending_acceptance 或 completed")

        # Normal execution only writes the explicitly approved, contained files.
        try:
            with self.transaction_manager.transaction(req.project_id, req.change_id) as tx:
                cr_file_path = self.change_service._locator.find_change_file(
                    req.change_id, project_id=req.project_id
                )
                if cr_file_path and os.path.isfile(cr_file_path):
                    tx.backup_file(cr_file_path)

                project_path = getattr(project, "path", None) or self._resolve_project_path(
                    req.project_id
                )
                ledger_path: str | None = None
                if project_path:
                    from auto_pm.domain.change.path_resolver import find_ledger_file

                    ledger_path = find_ledger_file(project_path)
                    if ledger_path and os.path.isfile(ledger_path):
                        tx.backup_file(ledger_path)

                if cr.status == "approved":
                    self.change_service.transition_status(
                        req.change_id, "implementing", approver=req.actor, project_id=req.project_id
                    )

                for fpath, content in files_raw.items():
                    canonical = self._canonical_relative_path(fpath)
                    if canonical is None:  # Defensive: validated before transaction.
                        raise ValueError(f"非法文件路径: {fpath}")
                    abs_path = resolved_files[canonical]
                    if abs_path.exists():
                        tx.backup_file(abs_path)
                    else:
                        tx.track_created_file(abs_path)
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(content, encoding="utf-8")

                current_cr = self.change_service.get_change_request(
                    req.change_id, project_id=req.project_id
                )
                curr_st = current_cr.status if current_cr else "implementing"

                if target_status == "completed":
                    if curr_st == "implementing":
                        self.change_service.transition_status(
                            req.change_id,
                            "pending_acceptance",
                            approver=req.actor,
                            project_id=req.project_id,
                        )
                        curr_st = "pending_acceptance"
                    if curr_st == "pending_acceptance":
                        self.change_service.transition_status(
                            req.change_id,
                            "accepting",
                            approver=req.actor,
                            project_id=req.project_id,
                        )
                        curr_st = "accepting"
                    if curr_st == "accepting":
                        self.change_service.transition_status(
                            req.change_id,
                            "completed",
                            approver=req.actor,
                            comment=req.metadata.get("comment", "实施完成验收通过"),
                            verification_conclusion=req.metadata.get(
                                "verification_conclusion", "全部通过"
                            ),
                            allow_partial_verification=False,
                            project_id=req.project_id,
                        )
                        final_status = "completed"
                    else:
                        final_status = curr_st
                elif target_status == "pending_acceptance":
                    if curr_st == "implementing":
                        self.change_service.transition_status(
                            req.change_id,
                            "pending_acceptance",
                            approver=req.actor,
                            project_id=req.project_id,
                        )
                        final_status = "pending_acceptance"
                    else:
                        final_status = curr_st
                else:
                    final_status = curr_st

                files_changed = sorted(file_paths)

            audit_log(
                "workflow_execute",
                project_id=req.project_id,
                change_id=req.change_id,
                status=final_status,
                success=True,
                files_changed=files_changed,
                git_committed=False,
                commit_hash="",
                actor=req.actor,
            )
            return WorkflowExecuteResultDTO(
                success=True,
                project_id=req.project_id,
                change_id=req.change_id,
                status=final_status,
                files_changed=files_changed,
                ledger_clean=True,
                git_committed=False,
                commit_hash="",
                message=f"工作流执行成功: {req.change_id} -> {final_status}",
                metadata={
                    "files_changed_count": len(files_changed),
                    "target_status": final_status,
                },
            )

        except Exception as exc:
            logger.error("工作流执行异常回滚: %s", exc, exc_info=True)
            return self._failure(req, f"工作流执行异常: {exc}")

    def resume(self, project_id: str) -> WorkflowResumeDTO:
        """Return an explicit non-resumable snapshot without touching the workspace.

        There is no durable, authenticated resume checkpoint in this module.
        Returning an apparently clean or actionable resume token would invite a
        caller to continue from unverified state, so the method deliberately
        fails closed and requires a fresh external fact package.
        """
        return WorkflowResumeDTO(
            project_id=project_id,
            fact_fingerprint="",
            git_head="",
            git_clean=False,
            active_changes=[],
            next_legal_action="manual_fact_package_required",
            read_set=[],
            metadata={
                "resumable": False,
                "reason": "no_authenticated_resume_checkpoint",
            },
        )
