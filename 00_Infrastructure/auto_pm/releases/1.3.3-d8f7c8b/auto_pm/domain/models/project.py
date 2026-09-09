"""PLC-HMI 概念映射：UDT 自定义数据类型（项目信息（Project/ProjectRecord 数据结构））

像 PLC 的 UDT（User Defined Type），定义数据结构。

--- 原始注释 ---

项目核心模型（迁移自 core/project_service.py:ProjectInfo）

文件系统为单一真源，本模型为内存表示 + DB 缓存载体。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from auto_pm.models.enums import ProjectPhase, ProjectSource, Stack

# 业务线类型（"" 表示未设置）
BusinessLine = Literal["SW", "DJ", "ZD", "XT", "WX", ""]

# 合法业务线前缀集合（与 BusinessLine 保持一致）
_VALID_BUSINESS_LINES = frozenset({"SW", "DJ", "ZD", "XT", "WX"})

# 项目编号正则：SW-2026-001, DJ-2026-010 等格式（前缀 2-4 位大写字母）
_PROJECT_ID_RE = re.compile(r"^([A-Z]{2,4})-\d{4}-\d{3}")


def extract_business_line(project_id: str) -> str:
    """从项目编号提取业务线前缀（如 SW-2026-008 → SW）

    业务线编码：SW=软件 / DJ=单机 / ZD=整线 / XT=升级 / WX=维保。
    无法识别或前缀非合法业务线时返回空字符串。

    注意：只返回 SW/DJ/ZD/XT/WX 五个合法业务线前缀，其他 2-4 位字母前缀
    （如 TEST/ABC/ABCD）一律返回空字符串，以保证与 BusinessLine 类型一致。
    """
    if not project_id:
        return ""
    m = _PROJECT_ID_RE.match(project_id)
    if m and m.group(1) in _VALID_BUSINESS_LINES:
        return m.group(1)
    return ""


class Project(BaseModel):
    """项目元数据

    迁移自 ProjectInfo dataclass。字段保持兼容，新增 phase/business_line 字段。
    """

    project_id: str = Field(..., description="项目编号，如 SW-2026-008")
    name: str = Field(..., description="项目名称")
    path: str = Field(..., description="项目绝对路径")
    stack: Stack = Field("unknown", description="技术栈: plc/python/unknown")
    version: str = Field("", description="版本号")
    description: str = Field("", description="描述")
    source: ProjectSource = Field("", description="元数据来源: copier/plc_json/pm_session/dirname")
    phase: ProjectPhase = Field(
        "", description="项目阶段: developing/commissioning/production/archived"
    )
    business_line: BusinessLine = Field("", description="业务线: SW/DJ/ZD/XT/WX")
    project_type: str = Field("", description="项目类型: single_machine/line_project 等")
    equipment_type: str = Field("", description="设备类型: conveyor/packaging 等")
    plc_vendor: str = Field("", description="PLC 品牌: Siemens/Mitsubishi 等")
    plc_model: str = Field("", description="PLC 型号: S7-1200 等")
    extra: dict[str, Any] = Field(default_factory=dict, description="额外字段")
    file_mtime: float = Field(0.0, description="项目文件最近修改时间")

    model_config = ConfigDict(from_attributes=True)


class ProjectRecord(Project):
    """DB 缓存记录（扩展扫描元数据）

    用于 SQLite 索引缓存表，记录扫描时间戳以支持增量同步。
    """

    last_scanned: str = Field("", description="最后扫描时间 ISO8601")
    scanner_version: str = Field("", description="扫描器版本（CHG-085：版本不匹配时强制重扫）")


# 兼容别名：现有代码中 ProjectInfo 仍可使用，指向 Project
ProjectInfo = Project
