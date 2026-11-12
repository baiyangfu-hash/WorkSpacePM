"""PLC-HMI 概念映射：UDT 自定义数据类型（PLC 项目信息（PLC 项目元数据数据结构））

像 PLC 的 UDT（User Defined Type），定义数据结构。

--- 原始注释 ---

PLC 检查与修复模型（迁移自 plc/models.py:dataclass）

常量（STD_DIRS/STD_PRDS/NAMING_RULES 等）仍保留在 plc/models.py。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

from auto_pm.domain.models.enums import CheckStatus, DocType, ProjectType, RepairStatus

# 检查器写 Siemens 语言服务两项用的名字（检查器、基线逐条比、证据摘要都引用这里）。
# 找不到插件时 check 这一项是 warn（“未验证”），不会是 pass（D-295）
LANGUAGE_SERVICE_CHECK = "Siemens 语言服务 check"
LANGUAGE_SERVICE_TEST = "Siemens 语言服务 test"


class CheckItem(BaseModel):
    """单条检查项"""

    item: str = Field(..., description="检查项名称")
    status: CheckStatus = Field(..., description="状态: pass/warn/fail")
    message: str = Field("", description="详细说明")
    # 逐条明细（“文件:行 说明”），汇总只给个数时由这里逐条列出（TD-SW008-573）；没有明细的检查项为空
    details: list[str] = Field(default_factory=list, description="逐条明细")

    model_config = ConfigDict()


class CheckResult(BaseModel):
    """结构检查结果"""

    project_path: str = Field(..., description="项目路径")
    project_type: ProjectType = Field("standard", description="项目类型: standard/syslib_fb")
    items: list[CheckItem] = Field(default_factory=list, description="检查项列表")
    pass_count: int = Field(0, description="通过数")
    warn_count: int = Field(0, description="警告数")
    fail_count: int = Field(0, description="失败数")
    # V0.4.1 Step 3: PLC 检查不适用口径
    # 对 Python 项目（无 .plc.json + 有 pyproject.toml）直接返回 not_applicable=True，
    # 不跑 5 项检查、不累加 fail_count；驾驶舱据此跳过该项目避免误报
    not_applicable: bool = Field(False, description="是否不适用 PLC 检查（Python 项目）")
    not_applicable_reason: str = Field("", description="不适用原因")

    model_config = ConfigDict()

    def add(self, item: str, status: str, message: str, details: list[str] | None = None) -> None:
        """添加一条检查项并更新计数；details 是逐条明细（文件:行 说明），可省"""
        self.items.append(CheckItem(item=item, status=status, message=message, details=list(details or [])))
        if status == "pass":
            self.pass_count += 1
        elif status == "warn":
            self.warn_count += 1
        else:
            self.fail_count += 1

    @property
    def all_pass(self) -> bool:
        """是否全部通过（无 fail）"""
        return self.fail_count == 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def language_service_verified(self) -> bool | None:
        """Siemens 语言服务（插件命令行）这一层有没有真跑过，``--json`` 里同名字段。

        True＝跑了（过没过看 fail_count）；False＝本机没找到插件，语法和类型没人查过，不能当通过；
        None＝这次没有这一层（没要求跑、不是带 .plc.json 的 PLC 项目）。
        """
        statuses = [item.status for item in self.items if item.item == LANGUAGE_SERVICE_CHECK]
        if not statuses:
            return None
        return "warn" not in statuses


class RepairAction(BaseModel):
    """单条修复动作"""

    item: str = Field(..., description="修复项名称")
    action: str = Field("", description="修复动作描述")
    destructive: bool = Field(False, description="是否破坏性操作")
    status: RepairStatus = Field(..., description="状态: fixed/skipped/failed")
    detail: str = Field("", description="详细说明")

    model_config = ConfigDict()


class RepairResult(BaseModel):
    """自动修复结果"""

    project_path: str = Field(..., description="项目路径")
    actions: list[RepairAction] = Field(default_factory=list, description="修复动作列表")
    fixed_count: int = Field(0, description="已修复数")
    skipped_count: int = Field(0, description="已跳过数")
    failed_count: int = Field(0, description="失败数")
    before_check: CheckResult | None = Field(None, description="修复前检查结果")
    after_check: CheckResult | None = Field(None, description="修复后检查结果")

    model_config = ConfigDict()

    def add(
        self, item: str, action: str, destructive: bool, status: str, detail: str
    ) -> None:
        """添加一条修复动作并更新计数"""
        self.actions.append(
            RepairAction(
                item=item, action=action, destructive=destructive, status=status, detail=detail
            )
        )
        if status == "fixed":
            self.fixed_count += 1
        elif status == "skipped":
            self.skipped_count += 1
        else:
            self.failed_count += 1


class RenamePlan(BaseModel):
    """文档重命名计划"""

    old_path: str = Field(..., description="原文件路径")
    new_path: str = Field(..., description="新文件路径")
    doc_type: DocType = Field(..., description="文档类型: REQ/INT/DSN/TEC")
    applied: bool = Field(False, description="是否已执行")
    backup_path: str = Field("", description="备份路径（.bak）")

    model_config = ConfigDict()


class StandardizeResult(BaseModel):
    """文档标准化结果"""

    project_path: str = Field(..., description="项目路径")
    plans: list[RenamePlan] = Field(default_factory=list, description="重命名计划列表")
    applied_count: int = Field(0, description="已应用数")
    skipped_count: int = Field(0, description="已跳过数")
    reference_updates: list[str] = Field(default_factory=list, description="引用更新列表")

    model_config = ConfigDict()
