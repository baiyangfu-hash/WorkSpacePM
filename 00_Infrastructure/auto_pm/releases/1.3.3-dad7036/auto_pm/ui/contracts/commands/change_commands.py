"""PLC-HMI 概念映射：HMI 画面数据结构（变更命令定义（创建/编辑/审批变更单的参数））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

Change 相关 Command 定义"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateChangeCommand:
    """创建变更单命令

    impact_scope 默认空列表，由 GUI 创建表单填写（如 ["约束1", "约束2"]）。
    M3 之前硬编码为 []，M3 起改为 command 字段透传。
    """

    project_id: str
    title: str
    domain: str
    nature: str
    background: str
    necessity: str
    applicant: str
    impact_scope: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TransitionChangeCommand:
    change_id: str
    target_status: str
    operator: str
    note: str | None
    allow_partial_verification: bool
    project_id: str | None = None
