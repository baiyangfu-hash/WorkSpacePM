"""变更管理测试共享 fixture"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest


@pytest.fixture
def tmp_dir() -> Generator[str, None, None]:
    """临时目录"""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_chg_content() -> str:
    """样例变更单内容"""
    return """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-001 |
| 项目名称 | TEST-2026-001 测试项目 |
| 项目编号 | TEST-2026-001 |

### 3.1 技术领域（必选）
| 领域 | 选择 | 说明 |
|------|------|------|
| □ **ELEC** 电气设计 | - | Eplan/接线图 |
| □ **PLC**   PLC程序 | **选中** | SCL/ST/LD |
| ☑ **DOCU** 工程文档 | **选中** | 设计说明书 |

### 3.2 业务性质（必选）
| 性质 | 选择 | 典型场景 |
|------|------|----------|
| ☑ **DEF** 缺陷修复 | **选中** | Bug修复 |

### 3.3 影响范围（可多选）
| 范围 | 选择 | 审批要求 |
|------|------|----------|
| ☑ **LOCAL**   局部变更 | **选中** | 项目经理审批 |
| ☑ **MODULE** 模块级变更 | **选中** | 项目负责人审批 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-01-15 |
| 预计实施日期 | 2026-01-20 |
| 紧急程度 | ☑一般 □紧急 □非常紧急 |

## 4. 变更原因

**变更背景**：
测试变更背景描述

**变更必要性**：
测试变更必要性描述

**参考依据**：
测试参考依据

## 8. 变更审批

### 8.1 审批流程（按影响范围分级）

| 审批环节 | 审批人 | 审批意见 | 审批日期 | 签字/电子签章 |
|----------|--------|----------|----------|---------------|
| **初审** | 李四 | 同意 | 2026-01-16 | 李四 |

### 8.2 审批结论
| 结论 | ☑ 通过 □ 有条件通过 □ 驳回 □ 拒绝 |
"""


@pytest.fixture
def workspace_root(tmp_dir: str) -> str:
    """临时工作空间根目录（含模拟项目结构）

    创建一个 TEST-2026-001 项目，包含变更单目录和台帐文件，
    供 ChangeService 集成测试使用。
    """
    project_id = "TEST-2026-001"
    project_path = os.path.join(tmp_dir, project_id)
    # 创建项目目录
    os.makedirs(project_path, exist_ok=True)
    # 创建项目标志文件，使 ChangeFileLocator._is_project_dir 识别为项目目录
    with open(
        os.path.join(project_path, f"PM_SESSION_{project_id}.md"), "w", encoding="utf-8"
    ) as f:
        f.write("# PM_SESSION\n")
    # 创建变更单目录
    chg_dir = os.path.join(project_path, "04_监控", "01_变更管理", "01_变更单", "CHG-DOCU")
    os.makedirs(chg_dir, exist_ok=True)
    # 写入一个样例变更单
    chg_file = os.path.join(chg_dir, "CHG-DOCU-2026-001.md")
    with open(chg_file, "w", encoding="utf-8") as f:
        f.write(_build_sample_chg_for_workspace())
    # 创建台帐目录和文件
    ledger_dir = os.path.join(project_path, "04_监控", "01_变更管理", "02_变更记录")
    os.makedirs(ledger_dir, exist_ok=True)
    ledger_file = os.path.join(ledger_dir, "01_版本变更台帐.md")
    with open(ledger_file, "w", encoding="utf-8") as f:
        f.write("# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|------|----------|------|\n")
    return tmp_dir


@pytest.fixture
def project_id() -> str:
    """项目编号"""
    return "TEST-2026-001"


@pytest.fixture
def chg_file(workspace_root: str) -> str:
    """变更单文件路径"""
    return os.path.join(
        workspace_root,
        "TEST-2026-001",
        "04_监控",
        "01_变更管理",
        "01_变更单",
        "CHG-DOCU",
        "CHG-DOCU-2026-001.md",
    )


def _build_sample_chg_for_workspace() -> str:
    """构建用于 workspace_root fixture 的样例变更单内容"""
    return """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-DOCU-2026-001 |
| 项目名称 | TEST-2026-001 测试项目 |
| 项目编号 | TEST-2026-001 |

### 3.1 技术领域（必选）
| 领域 | 选择 | 说明 |
|------|------|------|
| ☑ **DOCU** 工程文档 | **选中** | 设计说明书 |

### 3.2 业务性质（必选）
| 性质 | 选择 | 典型场景 |
|------|------|----------|
| ☑ **DEF** 缺陷修复 | **选中** | Bug修复 |

### 3.3 影响范围（可多选）
| 范围 | 选择 | 审批要求 |
|------|------|----------|
| ☑ **MODULE** 模块级变更 | **选中** | 项目负责人审批 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-01-15 |
| 预计实施日期 | 2026-01-20 |
| 紧急程度 | ☑一般 □紧急 □非常紧急 |

## 4. 变更原因

**变更背景**：
测试变更背景描述

**变更必要性**：
测试变更必要性描述

## 8. 变更审批

### 8.1 审批流程（按影响范围分级）

| 审批环节 | 审批人 | 审批意见 | 审批日期 | 签字/电子签章 |
|----------|--------|----------|----------|---------------|
| **初审** | 李四 | 同意 | 2026-01-16 | 李四 |

### 8.2 审批结论
| 结论 | ☑ 通过 □ 有条件通过 □ 驳回 □ 拒绝 |
"""
