"""SQLite 索引缓存层

文件系统为单一真源，DB 仅作缓存提升 GUI 列表/搜索性能。
- schema.py: 表结构 DDL
- connection.py: 连接管理
- repository.py: 数据访问层（CRUD）
- sync.py: 增量扫描同步（延迟导入避免循环依赖）
"""

from typing import Any

from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository, ProjectRepository, ScanLogRepository

__all__ = [
    "DatabaseManager",
    "ProjectRepository",
    "ChangeRequestRepository",
    "ScanLogRepository",
    "SyncService",
]


def __getattr__(name: str) -> Any:
    """延迟导入 SyncService 避免循环依赖

    sync.py 依赖 core.project_service，而 project_service 依赖 db.connection，
    通过 __init__.py 的立即导入会形成循环。使用 PEP 562 延迟导入。
    """
    if name == "SyncService":
        from auto_pm.db.sync import SyncService

        return SyncService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
