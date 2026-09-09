"""PLC-HMI 概念映射：SFB 库函数（数据库连接（SQLite 连接管理/WAL 模式））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

SQLite 连接管理

DB 路径: <workspace_root>/.auto-pm/index.db
使用 WAL 模式提升并发读性能。
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from auto_pm.db.schema import INDEX_DDL, TABLE_DDL, migrate_schema

log = logging.getLogger(__name__)


class DatabaseManager:
    """SQLite 连接管理器

    负责创建连接、初始化表结构、管理 DB 文件位置。
    连接复用：单例连接避免每次操作都创建新连接（CHG-SCPT-2026-100 T2）。
    """

    DB_DIR = ".auto-pm"
    DB_FILE = "index.db"

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.db_dir = os.path.join(self.workspace_root, self.DB_DIR)
        self.db_path = os.path.join(self.db_dir, self.DB_FILE)
        self._conn: sqlite3.Connection | None = None

    def _ensure_dir(self) -> None:
        """确保 DB 目录存在"""
        Path(self.db_dir).mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """获取 SQLite 连接（WAL 模式，外键开启，单例复用）

        Returns:
            sqlite3.Connection: 已配置的连接（同一实例多次调用返回同一对象）
        """
        if self._conn is None:
            self._ensure_dir()
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row  # 行以 dict-like 方式访问
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        """关闭连接（测试或显式释放时使用）"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:
        """初始化表结构（幂等，重复调用安全）

        执行顺序：表创建 → schema 迁移（ALTER TABLE ADD COLUMN）→ 索引创建。
        迁移在索引创建前执行，确保新增列存在后再创建依赖该列的索引。
        """
        with self.get_connection() as conn:
            for ddl in TABLE_DDL:
                conn.execute(ddl)
            migrate_schema(conn)
            for ddl in INDEX_DDL:
                conn.execute(ddl)
            conn.commit()
        log.info("DB schema 已初始化: %s", self.db_path)

    def drop_all(self) -> None:
        """删除所有表（仅用于测试/重置）"""
        with self.get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS scan_log")
            conn.execute("DROP TABLE IF EXISTS approval_history")
            conn.execute("DROP TABLE IF EXISTS impact_analysis")
            conn.execute("DROP TABLE IF EXISTS change_requests")
            conn.execute("DROP TABLE IF EXISTS projects")
            conn.commit()
        log.info("DB 所有表已删除: %s", self.db_path)

    def exists(self) -> bool:
        """DB 文件是否存在"""
        return os.path.isfile(self.db_path)
