# ruff: noqa: E402
"""auto-pm 自动化项目管理工具 - 工业级 Clean Architecture 顶层导出

5 大标准分层：
1. contracts: 强类型 DTO 与接口协议
2. domain: 核心业务领域 (plc, change, spec, vartable, modbus, models, constraint)
3. infrastructure: 基础设施组件 (db, logging, utils, config)
4. application: 门禁引擎、应用编排与外观门面 (workbench_facade, core services, delivery)
5. ui: 表现层 (qml, bridges, cli)
"""

from __future__ import annotations

import os

__app_name__ = "auto-pm"
__version__ = "1.2.3"
__author__ = "auto-pm team"

# ── PEP 420 标准包路径扩展：将 Clean Architecture 分层子目录加入 auto_pm 包查找链 ──
_pkg_dir = os.path.dirname(__file__)
for _sub in ("domain", "infrastructure", "application", "ui"):
    _sub_path = os.path.join(_pkg_dir, _sub)
    if os.path.isdir(_sub_path) and _sub_path not in __path__:
        __path__.append(_sub_path)

# 导入 5 大标准分层
import auto_pm.application as application
import auto_pm.contracts as contracts
import auto_pm.domain as domain
import auto_pm.infrastructure as infrastructure
import auto_pm.ui as ui

__all__ = [
    "__app_name__",
    "__version__",
    "__author__",
    "contracts",
    "domain",
    "infrastructure",
    "application",
    "ui",
]
