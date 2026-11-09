# auto-pm PLC 落地就绪度深度审查与改进 Spec

## Why

用户诉求：**通过 auto-pm 能正常管理 PLC 项目（Python 暂时搁置）**，要求评估完成度与落地时间。

经对 `SW-2026-008_auto-pm_自动化项目管理工具` 的代码 + 文档 + 三个参考项目（SysLib / DJ-2026-000 / DJ-2026-005）+ 全局规范/PLC 规范的深度交叉审查，识别出**核心代码完成度 91%、GUI 88%、但 PLC 项目实际管理能力仅约 30%** 的严重落差。

工具基于"标准应用项目位于根目录"的假设设计，与三个参考项目的实际结构存在系统性偏差，**直接运行 `auto-pm plc check` 会产生误报、`plc repair` 会破坏项目结构**。本 spec 旨在记录阻断性问题、给出修复路线，让工具真正能管理 PLC 项目。

## What Changes

### 阻断性问题修复（P0，必须先做）

- **修复 P0-1**：DJ-2026-005 双 `.plc.json` 冲突——支持 LSP-907§3.1 嵌套布局，优先读 `02_PLC程序/通用ST程序及变量表/.plc.json`
- **修复 P0-2**：SysLib 被误判为 `standard`——新增 `library` 项目类型，跳过 STD_DIRS 检查
- **修复 P0-3**：SysLib FB 子目录完全漏扫——对库项目递归扫描 FB_* 子目录
- **修复 P0-4**：`db/sync.py` Bug-2 修复不完整——统一路径常量到 `path_resolver._CHANGE_SEARCH_PATHS`，覆盖 PLC + Python 双路径
- **修复 P0-5**：`ChangeService._get_project_path` 与 `ProjectService._scan` 工作空间根处理不一致——统一为递归扫描，复用 `ProjectService.find_project_path`

### 重要问题修复（P1）

- **修复 P1-1**：DJ-2026-005 变更管理目录布局不被识别——`STD_DIRS` 支持 `00_项目管理/04_变更管理` 布局
- **修复 P1-2**：DJ-2026-000 扁平结构被误判——新增 `minimal`（小型/验证）项目类型，跳过 STD_DIRS 检查
- **修复 P1-3**：`parser._all_verification_passed` 逻辑缺陷——修正 `total_count` 计数规则
- **修复 P1-4**：`change_service` 临时文件泄漏——改用 `try/finally`
- **修复 P1-5**：`checker.py:93` SysLib 路径子串误判——改为 `os.path.basename` 精确匹配
- **修复 P1-6**：`workspace_view.change_updated` 信号未连接——主窗口补充连接以刷新状态栏
- **修复 P1-7**：`_status_change` 硬编码为 0——调用 `ChangeService.list_all_changes()` 获取实际计数

### 文档与测试同步（P2）

- 同步 PM_SESSION 测试数（778→688）和状态字段矛盾
- 重新生成完整的覆盖率报告（修复截断问题）
- 文档四件套版本对齐（PRD V2.0.2 → INT/DSN/TEC 同步）
- 更新测试检查清单（413/71% → 688/81%）

### 暂时搁置项（用户明确要求）

- Python 项目管理（`python init/check` 空壳）——保持现状
- 多角色适配（角色-Tab 映射 0%）——保持现状
- V2.1~V2.5 路线图中的 Python 相关条目——保持现状

## Impact

- **Affected specs**：
  - `rebuild-auto-pm-v2-unified/spec.md` — V2.0.1 路线图需插入"PLC 落地就绪"前置任务
  - `PRD V2.0.2` — §1.4 Bug 清单需补充 P0-1~P0-5、P1-1~P1-2
  - `LSP-907 项目配置规范` — 需明确"嵌套 .plc.json 布局"和"库项目类型"的规范地位
- **Affected code**：
  - `auto_pm/plc/checker.py` — `_detect_project_type` 新增 library/minimal 类型、SysLib 路径精确匹配
  - `auto_pm/plc/models.py` — `STD_DIRS` 支持 `00_项目管理/04_变更管理` 布局、新增 `LIBRARY_SKIP_DIRS`/`MINIMAL_SKIP_DIRS`
  - `auto_pm/plc/repairer.py` — `_minimal_plc_json` 移除硬编码 libraries 路径、库项目跳过修复
  - `auto_pm/core/project_service.py` — `_read_plc_json` 支持嵌套布局、`_scan` 对库项目递归 FB 子目录
  - `auto_pm/change/change_service.py` — `_get_project_path` 改为递归扫描、临时文件 try/finally、路径常量统一
  - `auto_pm/change/path_resolver.py` — 定义单一真源 `_CHANGE_SEARCH_PATHS`
  - `auto_pm/db/sync.py` — `_sync_changes` 复用 `path_resolver._CHANGE_SEARCH_PATHS`
  - `auto_pm/change/parser.py` — `_all_verification_passed` 逻辑修正
  - `auto_pm/ui/main_window.py` — 连接 `change_updated` 信号、`_status_change` 实际计数
- **Affected docs**：
  - `PM_SESSION_SW-2026-008.md` — 修正测试数和状态字段
  - `09_整改项/覆盖率报告.txt` — 重新生成完整报告
  - `00_项目基础信息/002_接口文档_INT.md` ~ `004_技术方案文档_TEC.md` — 同步至 V2.0.2

## ADDED Requirements

### Requirement: PLC 项目识别准确性

The system SHALL correctly identify all three reference PLC project types: library projects (SysLib), minimal/verification projects (DJ-2026-000), and full application projects (DJ-2026-005) with nested `.plc.json` layout.

#### Scenario: SysLib 库项目识别
- **WHEN** auto-pm 扫描 `0100_PLC自动化/01_SharedLibraries/SysLib/`
- **THEN** 识别为 `library` 项目类型，跳过 STD_DIRS 检查，递归扫描 FB_* 子目录

#### Scenario: DJ-2026-000 小型项目识别
- **WHEN** auto-pm 扫描 `0100_PLC自动化/DJ-2026-000/`
- **THEN** 识别为 `minimal` 项目类型（扁平结构），跳过 STD_DIRS 检查

#### Scenario: DJ-2026-005 嵌套 .plc.json 识别
- **WHEN** auto-pm 扫描 `0100_PLC自动化/DJ-2026-005/`
- **THEN** 优先读取 `02_PLC程序/通用ST程序及变量表/.plc.json`（V6.0.0 真实数据），而非根目录 `.plc.json`（V1.0.0 占位数据）

#### Scenario: 库项目 FB 子目录递归扫描
- **WHEN** auto-pm 扫描 SysLib 库项目
- **THEN** 递归检查 `actuator/FB_1011_CylinderControl/` 等 12 个 FB 子目录，每个 FB 子目录按 `syslib_fb` 类型检查

### Requirement: PLC 检查不破坏项目结构

The system SHALL NOT create directories or files that pollute the existing project structure during `plc check` and `plc repair` operations.

#### Scenario: 库项目跳过 STD_DIRS 修复
- **WHEN** 用户对 SysLib 执行 `auto-pm plc repair SysLib`
- **THEN** 跳过 02_PLC程序/通用ST程序及变量表、03_HMI设计、04_现场调试、04_变更管理 等应用项目目录的创建

#### Scenario: DJ-2026-005 不创建重复变更管理目录
- **WHEN** 用户对 DJ-2026-005 执行 `auto-pm plc repair DJ-2026-005`
- **THEN** 不创建根级 `04_变更管理` 目录（因 `00_项目管理/04_变更管理` 已存在）

### Requirement: 变更管理跨层级一致性

The system SHALL provide consistent project path resolution between `ProjectService` and `ChangeService`, supporting recursive workspace scanning.

#### Scenario: 跨层级变更单管理
- **WHEN** workspace_root=`c:\Users\fubai\Desktop\My_Workspace`，用户执行 `auto-pm change list DJ-2026-005`
- **THEN** ChangeService 递归查找项目路径，正确找到 `0100_PLC自动化/DJ-2026-005/`，列出 CHG-PLC-2026-001~005

#### Scenario: DB 同步覆盖 PLC + Python 路径
- **WHEN** SyncService 同步变更单到 DB
- **THEN** 同时扫描 PLC 路径 `00_项目管理/04_变更管理/01_变更单/CHG-*/` 和 Python 路径 `01_项目文档/03_执行过程/02_变更管理/`

### Requirement: GUI 状态栏准确性

The system SHALL display accurate change counts in the main window status bar.

#### Scenario: 变更数实时刷新
- **WHEN** 用户在工作区 ChangeTab 创建/流转变更单
- **THEN** `change_updated` 信号触发主窗口状态栏 `_status_change` 重新查询 `ChangeService.list_all_changes()` 并更新计数

## MODIFIED Requirements

### Requirement: PLC 项目检查（LSP-907）

原 V2.0 仅检查根目录结构，套用 `standard` 类型。修改为：支持 `standard`/`library`/`minimal`/`syslib_fb` 四种项目类型，按类型差异化检查；支持 LSP-907§3.1 嵌套 `.plc.json` 布局；支持 `00_项目管理/04_变更管理` 布局。

### Requirement: 变更管理路径常量

原 V2.0 路径常量在 `change_service.py`、`path_resolver.py`、`db/sync.py` 三处定义不一致。修改为：以 `path_resolver._CHANGE_SEARCH_PATHS` 为单一真源，其他模块统一 import 引用。

### Requirement: GUI 主窗口状态栏

原 V2.0 `_status_change` 硬编码为 0。修改为：调用 `ChangeService.list_all_changes()` 获取实际计数，并通过 `workspace_view.change_updated` 信号实时刷新。

## REMOVED Requirements

### Requirement: 多角色适配（角色-Tab 映射）
**Reason**: 用户明确要求"Python 暂时搁置"，多角色适配主要服务于 Python 工程师/规范编辑角色，且当前完成度 0%，非 PLC 落地阻断项
**Migration**: 推迟到 V2.5 或后续版本，V2.0.1 不纳入范围

### Requirement: Python 项目管理（python init/check）
**Reason**: 用户明确要求"Python 暂时搁置"，`cli/python/__init__.py` 当前为空壳占位
**Migration**: 保持现状，推迟到 V2.5 实现

## 审查数据基线（2026-06-22）

| 维度 | 完成度 | 阻断性问题数 |
|------|--------|------------|
| 核心代码 | 91% | 2（Bug-2 不完整 + 路径常量不一致） |
| GUI | 88% | 1（多角色适配缺失，已移出范围） |
| PLC 项目管理 | 30% | 5（P0-1~P0-5） |
| 测试 | 8.5/10 | 0（688 用例 81% 覆盖） |
| 文档 | 8.0/10 | 3（PM_SESSION/覆盖率报告/版本不对齐） |

## 落地就绪度评估

**当前状态**：不可落地。`auto-pm plc check/repair` 对三个参考项目均会产生误报或破坏结构。

**修复 P0 后状态**：可对 DJ-2026-005（实际落地项目）正确执行 check/repair/standardize/change 命令。

**修复 P0+P1 后状态**：可对三个参考项目全部正确执行，达到"能正常管理 PLC 项目"的落地目标。

**预计修复工作量**：P0 五项 + P1 七项，涉及 9 个代码文件 + 3 个文档文件，按现有代码质量推测可在 V2.0.1 迭代内完成。
