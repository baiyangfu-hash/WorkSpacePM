"""PLC-HMI 概念映射：UDT 自定义数据类型

像 PLC 的 UDT（User Defined Type），定义项目中使用的数据结构。
- project.py: Project / ProjectRecord（像 PLC 的"项目信息"UDT）
- change.py: ChangeRequest / ChangeSummary（像 PLC 的"变更单"UDT）
- dto.py: 通用数据传输对象
- enums.py: 枚举类型（像 PLC 的常量定义）

--- 原始注释 ---
统一数据模型层（Pydantic v2）

迁移自分散的 dataclass 定义，统一到 Pydantic v2 BaseModel：
- project.py: Project / ProjectRecord（迁移自 core/project_service.py:ProjectInfo）
- change.py: ChangeRequest / ChangeSummary（迁移自 change/models.py）
- plc.py: CheckItem / CheckResult / RepairAction / RepairResult / RenamePlan / StandardizeResult
- dto.py: GUI / API 层 DTO
- enums.py: Literal 类型定义
"""

from auto_pm.models.change import (
    ApprovalRecord,
    ChangeRequest,
    ChangeSummary,
    ImpactAnalysis,
)
from auto_pm.models.dto import (
    ApiResponse,
    DashboardSummaryDTO,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectDetailDTO,
    ProjectListItem,
    ProjectUpdateRequest,
    ScanResult,
)
from auto_pm.models.plc import (
    CheckItem,
    CheckResult,
    RenamePlan,
    RepairAction,
    RepairResult,
    StandardizeResult,
)
from auto_pm.models.project import (
    BusinessLine,
    Project,
    ProjectInfo,
    ProjectRecord,
    extract_business_line,
)

__all__ = [
    # project
    "Project",
    "ProjectInfo",
    "ProjectRecord",
    "BusinessLine",
    "extract_business_line",
    # change
    "ChangeRequest",
    "ChangeSummary",
    "ImpactAnalysis",
    "ApprovalRecord",
    # plc
    "CheckItem",
    "CheckResult",
    "RepairAction",
    "RepairResult",
    "RenamePlan",
    "StandardizeResult",
    # dto
    "ProjectListItem",
    "ProjectDetail",
    "DashboardSummaryDTO",
    "ProjectDetailDTO",
    "ProjectCreateRequest",
    "ProjectUpdateRequest",
    "ScanResult",
    "ApiResponse",
]
