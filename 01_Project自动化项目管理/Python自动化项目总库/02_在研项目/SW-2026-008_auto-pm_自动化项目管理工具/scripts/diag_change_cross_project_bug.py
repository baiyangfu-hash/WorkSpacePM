"""诊断脚本：验证 ChangeFileLocator.find_change_file 跨项目单号冲突 bug

构造场景：
- 工作空间下两个项目：DJ-2026-005 / SW-2026-008
- 两个项目都有一个 CHG-DOCU-2026-001.md（不同内容，不同状态）
- 调用 find_change_file("CHG-DOCU-2026-001")，观察返回哪个项目的文件

预期（bug 存在）：返回 os.listdir 顺序的第一个匹配，不按 project_id 过滤
预期（修复后）：find_change_file(change_number, project_id="SW-2026-008") 返回 SW 项目的文件
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# 把项目根加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from auto_pm.domain.change.file_locator import ChangeFileLocator  # noqa: E402
from auto_pm.domain.change.parser import ChgParser  # noqa: E402


def _make_project(workspace: Path, project_id: str, chg_number: str, status: str) -> Path:
    """创建一个项目目录，内含一个指定状态的变更单"""
    project_dir = workspace / f"{project_id}_TestProject"
    project_dir.mkdir(parents=True, exist_ok=True)
    # 项目标志文件
    (project_dir / f"PM_SESSION_{project_id}.md").write_text(f"# PM_SESSION {project_id}\n", encoding="utf-8")

    # 变更单文件路径：00_项目管理/04_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-001.md
    chg_dir = project_dir / "00_项目管理" / "04_变更管理" / "01_变更单" / "CHG-DOCU"
    chg_dir.mkdir(parents=True, exist_ok=True)
    chg_file = chg_dir / f"{chg_number}.md"

    # 写一个最小可解析的变更单（不同项目用不同 background 以区分）
    bg = f"这是 {project_id} 项目的 {chg_number} 变更单（状态: {status}）"
    chg_file.write_text(
        f"""# 变更单

## 1. 文档基础信息

**文档标题**：变更单
**文档版本**：V2.1.0
**编制日期**：2026-07-09
**编制人**：fubai
**审核人**：

## 2. 版本变更记录

| 版本号 | 变更内容 | 变更人 | 变更日期 | 详细说明 |
|--------|----------|--------|----------|----------|
| V1.0.0 | 初始版本 | fubai | 2026-07-09 | 变更单创建 |

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | {chg_number} |
| 项目名称 | {project_id} |
| 项目编号 | {project_id} |

### 3.1 技术领域（必选）
| 领域 | 选择 | 说明 |
|------|------|------|
| □ **ELEC** 电气设计 | - | - |
| □ **MECH** 机械结构 | - | - |
| □ **PLC** PLC程序 | - | - |
| □ **HMI** HMI程序 | - | - |
| □ **SCPT** Python脚本 | - | - |
| ☑ **DOCU** 工程文档 | **选中** | - |
| □ **SAFE** 安全功能 | - | - |

### 3.2 业务性质（必选）
| 性质 | 选择 | 典型场景 |
|------|------|----------|
| □ **REQ** 需求变更 | - | - |
| □ **DEF** 缺陷修复 | - | - |
| ☑ **OPT** 优化改进 | **选中** | - |
| □ **CFG** 配置调整 | - | - |
| □ **EMRG** 紧急变更 | - | - |

### 3.3 影响范围（可多选）
| 范围 | 选择 | 审批要求 |
|------|------|----------|
| ☑ **LOCAL** 局部变更 | **选中** | - |
| □ **MODULE** 模块级变更 | - | - |
| □ **SYSTEM** 系统级变更 | - | - |
| □ **CROSS** 跨系统变更 | - | - |
| □ **SAFE** 安全相关变更 | - | - |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | fubai |
| 申请日期 | 2026-07-09 |
| 预计实施日期 | 2026-07-09 |
| 紧急程度 | ☑一般 □紧急 □非常紧急 |
| 变更状态 | {status} |

## 4. 变更原因

**变更背景**：
{bg}

**变更必要性**：
测试用

**参考依据**：
无

## 5. 变更内容

### 5.1 变更前（当前状态）
| 项目 | 当前值/描述 |
|------|-----------|
| 测试 | 测试 |

### 5.2 变更后（目标状态）
| 项目 | 目标值/描述 |
|------|-----------|
| 测试 | 测试 |

## 6. 变更影响分析

### 6.1 项目约束影响（PMBOK五大约束）

| 约束维度 | 影响程度 | 影响描述 | 应对措施 |
|---------|:--------:|----------|----------|
| **范围(Scope)** | ☑无 | - | - |
| **进度(Schedule)** | ☑无 | - | - |
| **成本(Cost)** | ☑无 | - | - |
| **质量(Quality)** | ☑低 | - | - |
| **风险(Risk)** | ☑低 | - | - |

**风险等级**（PMBOK风险评估）：☑低

**缓解措施**（风险应对策略）：
无

### 6.2 技术领域影响（跨领域变更必填！）

> **无跨领域影响，跳过。**

### 6.3 变更传播链（跨领域变更必填！）

> **无跨领域影响，跳过。**

**关联变更单清单:**
| 关联单号 | 关联领域 | 关联原因 | 状态 |
|----------|----------|----------|:----:|
| 无 | - | - | - |

## 7. 变更实施计划

| 序号 | 任务描述 | 负责人(角色) | 开始日期 | 完成日期 | 前置依赖 | 备注 |
|------|----------|-------------|----------|----------|----------|------|
| T1 | 测试 | fubai | 2026-07-09 | 2026-07-09 | 无 | - |

## 8. 变更审批

### 8.1 审批流程（按影响范围分级）

| 审批环节 | 审批人 | 审批意见 | 审批日期 | 签字/电子签章 |
|----------|--------|----------|----------|---------------|
| 已批准 | fubai | 通过 | 2026-07-09 | fubai |

### 8.2 审批结论
| 结论 | ☑ 通过 □ 有条件通过(附条件) □ 驳回(附原因) □ 拒绝(附原因) |
|------|----------------------------------------------------------|

## 9. 变更实施记录

| 实施日期 | 实施人 | 实施任务 | 实施内容摘要 | 实施结果 | 备注 |
|----------|--------|----------|-------------|----------|------|
| 2026-07-09 | fubai | T1 | 测试 | 完成 | - |

## 10. 变更验证

### 10.1 验证项清单

| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|------|--------|----------|
| 1 | 测试 | 测试 | 通过 | 通过 | ☑通过 | fubai | 2026-07-09 |

### 10.2 跨领域联动验证（如有传播链）

| 传播环节 | 关联变更单 | 该环节验证 | 验证人 | 验证日期 |
|----------|-----------|:---------:|--------|----------|
| 无 | - | ☑通过 | - | - |

### 10.3 验证结论
| 结论 | ☑ 全部通过,可关闭 □ 部分不通过,需返工 □ 需补充验证 |
|------|-------------------------------------------------------|

## 11. 版本详细变更说明

<a name="v100"></a>
### V1.0.0 版本详细变更
1. 变更单创建

[↑ 返回版本变更记录](#L13)

## 12. 附录

### 12.1 填写指南

无

### 12.2 参考资料
| 资料名称 | 版本 | 来源 |
|----------|------|------|
| 无 | - | - |

---

**文档版本**：V2.1.0
**编制日期**：2026-07-09
**编制人**：fubai
**审核人**：
""",
        encoding="utf-8",
    )
    return project_dir


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)

        # 构造两个项目，都有 CHG-DOCU-2026-001.md
        # DJ-2026-005 的变更单已 closed
        # SW-2026-008 的变更单是 draft（想流转的状态）
        _make_project(workspace, "DJ-2026-005", "CHG-DOCU-2026-001", "closed")
        _make_project(workspace, "SW-2026-008", "CHG-DOCU-2026-001", "draft")

        parser = ChgParser()
        locator = ChangeFileLocator(str(workspace), parser)

        # 1. 不带 project_id 调用 find_change_file（当前 CLI 行为）
        print("=" * 70)
        print("【测试1】find_change_file('CHG-DOCU-2026-001') 不带 project_id")
        print("=" * 70)
        found = locator.find_change_file("CHG-DOCU-2026-001")
        if found is None:
            print("  结果: 未找到")
        else:
            # 解析返回的文件，看是哪个项目的
            cr = parser.parse(found)
            print(f"  返回文件: {found}")
            print(f"  文件所属项目: {cr.project_id}")
            print(f"  文件状态: {cr.status}")
            print(f"  文件背景: {cr.background[:80]}...")

        # 2. 模拟用户想流转 SW-2026-008 的 CHG-DOCU-2026-001
        # 但 find_change_file 返回的可能是 DJ-2026-005 的（已 closed）
        # 状态流转 'closed' → 'submitted' 会失败
        print()
        print("=" * 70)
        print("【测试2】模拟用户场景：想流转 SW-2026-008 的 CHG-DOCU-2026-001 到 submitted")
        print("=" * 70)
        if found:
            cr = parser.parse(found)
            if cr.project_id != "SW-2026-008":
                print(f"  ❌ BUG 确认：find_change_file 返回的是 {cr.project_id} 的变更单（状态: {cr.status}）")
                print(f"  ❌ 用户想流转 SW-2026-008 的 draft 变更单，但实际拿到的是 {cr.project_id} 的 {cr.status} 变更单")
                print("  ❌ 若执行 transition_status('CHG-DOCU-2026-001', 'submitted') 会报 'closed → submitted 不合法'")
            else:
                print("  ✅ 返回的是 SW-2026-008 的变更单（这次没踩到 bug）")

        # 3. 测试 get_project_path 是否能正确定位项目
        print()
        print("=" * 70)
        print("【测试3】get_project_path 项目定位验证")
        print("=" * 70)
        for pid in ["DJ-2026-005", "SW-2026-008"]:
            p = locator.get_project_path(pid)
            print(f"  get_project_path('{pid}') = {p}")

        # 4. 验证：如果先用 project_id 定位项目，再在该项目内找变更单，能正确返回
        print()
        print("=" * 70)
        print("【测试4】修复方案验证：先定位项目，再在项目内找变更单")
        print("=" * 70)
        for pid in ["DJ-2026-005", "SW-2026-008"]:
            project_path = locator.get_project_path(pid)
            if project_path:
                # 在项目目录内手动构造变更单路径
                domain = "DOCU"
                chg_path = os.path.join(
                    project_path,
                    "00_项目管理", "04_变更管理", "01_变更单",
                    f"CHG-{domain}",
                    "CHG-DOCU-2026-001.md",
                )
                if os.path.isfile(chg_path):
                    cr = parser.parse(chg_path)
                    print(f"  ✅ 项目 {pid}: 找到变更单，状态={cr.status}, 背景={cr.background[:50]}...")
                else:
                    print(f"  ❌ 项目 {pid}: 变更单文件不存在 {chg_path}")


if __name__ == "__main__":
    main()
