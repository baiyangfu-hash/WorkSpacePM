"""auto_pm.domain.change.decision_service - 决策包管理服务

负责阶段 1 审批后决策包（Decision Package）的生成、检索与校验。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.change.parser import ChgParser
from auto_pm.contracts.decision_package import SCHEMA_VERSION, DecisionPackageDTO
from auto_pm.models import ChangeRequest

log = logging.getLogger(__name__)


class DecisionError(Exception):
    """决策包通用异常基类"""


class DecisionValidationError(DecisionError):
    """决策包校验失败"""


class DecisionNotFoundError(DecisionError):
    """决策包未找到"""


class DecisionService:
    """决策包领域服务"""

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.decisions_dir = self.workspace_root / ".auto-pm" / "decisions"
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def _generate_decision_id(self) -> str:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        token = uuid.uuid4().hex[:8].upper()
        return f"DEC-{date_str}-{token}"

    def create_decision(
        self,
        change_id: str,
        approver: str,
        *,
        project_id: str = "",
        approved_files: list[str] | None = None,
        conditions: list[str] | None = None,
        decision_id: str = "",
    ) -> DecisionPackageDTO:
        """从已审批的变更单生成固化的结构化决策包"""
        if not change_id.strip():
            raise DecisionValidationError("必须指定 change_id")
        if not approver.strip():
            raise DecisionValidationError("必须指定 approver (审批人)")

        # 变更编号只在项目账内唯一。跨项目可能存在同号单据，因此决策包必须
        # 使用 project_id 消歧；未限定项目且命中多个单据时必须 fail-closed。
        parser = ChgParser()
        candidates: list[tuple[Path, ChangeRequest]] = []
        for path in sorted(self.workspace_root.glob(f"**/{change_id}.md")):
            if not path.is_file():
                continue
            try:
                parsed = parser.parse(str(path))
            except Exception as e:
                log.warning("变更单候选解析失败 %s: %s", path, e)
                continue
            if project_id and parsed.project_id != project_id:
                continue
            candidates.append((path, parsed))

        if not candidates:
            suffix = f"（项目 {project_id}）" if project_id else ""
            raise DecisionNotFoundError(f"未找到变更单文件: {change_id}.md{suffix}")
        if len(candidates) > 1:
            projects = sorted({str(item.project_id) for _, item in candidates})
            raise DecisionValidationError(
                f"变更单编号跨项目重号: {change_id}，请通过 --pid 指定项目；"
                f"候选项目: {', '.join(projects)}"
            )
        _, cr = candidates[0]

        valid_statuses = (
            "approved",
            "conditionally_approved",
            "implementing",
            "pending_acceptance",
            "accepting",
            "completed",
            "closed",
        )
        if cr.status not in valid_statuses:
            raise DecisionValidationError(
                f"变更单当前状态为 '{cr.status}'，尚未获得批准，无法生成决策包"
            )

        resolved_pid = project_id or cr.project_id
        scope_raw = cr.impact_scope
        if isinstance(scope_raw, list):
            resolved_scope = "/".join(str(s) for s in scope_raw)
        else:
            resolved_scope = str(scope_raw or "MODULE")
        conclusion = "conditionally_approved" if cr.status == "conditionally_approved" else "approved"

        # 提取或使用传入的批准文件清单
        effective_files: list[str] = []
        if approved_files:
            effective_files = [str(f).strip() for f in approved_files if str(f).strip()]
        else:
            # 从 §5 提取文件
            s5_text = (getattr(cr, "sections", {}) or {}).get("5", "")
            for line in s5_text.splitlines():
                if "涉及文件/交付物" in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2:
                        raw_files = parts[1].replace("<br>", "\n").splitlines()
                        for rf in raw_files:
                            rf_clean = rf.strip().strip("-").strip("*").strip()
                            if rf_clean and rf_clean not in ("（待填写）", "(待填写)", "无涉及文件记录"):
                                effective_files.append(rf_clean)
        # 去重并保持顺序
        effective_files = list(dict.fromkeys(effective_files))

        resolved_dec_id = decision_id or self._generate_decision_id()
        now_iso = datetime.now(UTC).isoformat()

        dto = DecisionPackageDTO(
            decision_id=resolved_dec_id,
            project_id=resolved_pid,
            change_id=change_id,
            approved_scope=resolved_scope,
            approved_files=effective_files,
            approver=approver,
            approved_at=now_iso,
            decision_conclusion=conclusion,
            conditions=list(conditions or []),
            schema_version=SCHEMA_VERSION,
        )

        target_file = self.decisions_dir / f"{resolved_dec_id}.json"
        target_file.write_text(
            json.dumps(dto.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("决策包已成功固化: %s", target_file)
        return dto

    def get_decision(self, decision_id: str) -> DecisionPackageDTO:
        """获取指定决策包"""
        target_file = self.decisions_dir / f"{decision_id}.json"
        if not target_file.is_file():
            raise DecisionNotFoundError(f"未找到决策包: {decision_id}")
        data = json.loads(target_file.read_text(encoding="utf-8"))
        return DecisionPackageDTO.from_dict(data)

    def list_decisions(
        self,
        project_id: str = "",
        change_id: str = "",
    ) -> list[DecisionPackageDTO]:
        """列出决策包列表，支持按项目与变更单过滤"""
        results: list[DecisionPackageDTO] = []
        for file in sorted(self.decisions_dir.glob("DEC-*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                dto = DecisionPackageDTO.from_dict(data)
                if project_id and dto.project_id != project_id:
                    continue
                if change_id and dto.change_id != change_id:
                    continue
                results.append(dto)
            except Exception as e:
                log.warning("解析决策包文件失败 %s: %e", file, e)
        return results
