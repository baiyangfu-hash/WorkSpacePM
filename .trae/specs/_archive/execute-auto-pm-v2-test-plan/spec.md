# 执行 auto-pm V2.0 全功能自动化测试计划 Spec

## Why

auto-pm V2.0 已制定全功能自动化测试计划（`09_整改项/V2.0-全功能自动化测试计划.md`），覆盖 CLI + GUI 全功能模块约 380 个测试用例，分 L1 单元/L2 集成/L3 端到端/L4 侧自动四层。测试套件（pytest-qt、pytest-benchmark 等）已安装到虚拟环境。需要按计划逐层执行测试，发现功能缺陷与回归问题，并在测试结束后生成检查清单供用户核对需求完成情况。

## What Changes

- **执行现有测试基线**：运行 `tests/` 下所有现有测试，建立通过/失败基线
- **执行 L1 单元测试**：CLI（project/plc/python/change/template/gui/全局选项）、Core Service（ProjectService/TemplateService/ChangeService）、DB 层（DatabaseManager/Repository/SyncService）、Models、Config/Logging/Utils
- **执行 L2 GUI 测试**：MainWindow、ProjectListView、ProjectWorkspaceView、GlobalView、OverviewTab、4 个 Dialog、3 个 Widget、角色适配
- **执行 L3 端到端测试**：PLC/Python 项目完整生命周期、导入工作流、变更管理流程、DB 同步工作流、GUI 完整工作流、三源数据一致性、多角色工作流
- **执行 L4 侧自动测试**：CLI 真实命令侧自动测试（PowerShell 脚本驱动）、GUI 启动+导航+工具栏+列表+工作区+对话框+角色切换+状态栏侧自动验证
- **执行 Bug 回归测试**：Bug-1（路径前缀匹配）、Bug-2（变更单同步路径）、Bug-4（retrofit _src_path 推断）、Bug-5（扫描深度统一为 4）、UI-001/002/003/004 整改项回归
- **执行性能测试（可选）**：list_projects/list_projects_cached/sync_to_cache/GUI 启动加载/搜索响应基准测试
- **生成最终检查清单**：测试结束后在 `09_整改项/` 目录生成检查清单，覆盖所有功能模块的完成情况，供用户核对

## Impact

- **Affected specs**：
  - `09_整改项/V2.0-全功能自动化测试计划.md`（执行依据）
  - `09_整改项/V2.0-GUI-验证整改清单.md`（UI 整改项回归依据）
- **Affected code**：
  - `auto_pm/cli/`（所有 CLI 命令组：project/plc/python/change/template/gui/__main__）
  - `auto_pm/core/`（ProjectService、TemplateService）
  - `auto_pm/change/`（ChangeService、Parser、Generator、LedgerUpdater、PathResolver）
  - `auto_pm/plc/`（PlcChecker、PlcRepairer）
  - `auto_pm/db/`（DatabaseManager、ProjectRepository、ChangeRequestRepository、ScanLogRepository、SyncService）
  - `auto_pm/models/`（Project、ChangeRequest、ChangeSummary、business_line）
  - `auto_pm/ui/`（MainWindow、ProjectListView、ProjectWorkspaceView、GlobalView、OverviewTab、4 Dialog、3 Widget、roles）
  - `auto_pm/config/`、`auto_pm/logging/`、`auto_pm/utils/`
  - `tests/`（所有现有测试 + 可能新增的测试用例）
- **Affected deliverables**：
  - `09_整改项/V2.0-测试执行检查清单.md`（最终交付物，供用户核对需求完成情况）

## ADDED Requirements

### Requirement: 测试执行环境准备

系统 SHALL 在执行测试前完成环境准备，包括激活工作空间虚拟环境、验证测试套件已安装、确认 auto-pm 可调用。

#### Scenario: 虚拟环境激活成功
- **WHEN** 执行 `& "<工作空间根>\.venv\Scripts\Activate.ps1"`
- **THEN** `python --version` 指向 `.venv` 内的 Python
- **AND** `pip list` 含 pytest、pytest-qt、pytest-cov、pytest-benchmark、PySide6

#### Scenario: 测试套件缺失
- **WHEN** 检测到 pytest-qt 或 PySide6 未安装
- **THEN** 报告用户并停止测试执行

### Requirement: L1 单元测试执行

系统 SHALL 按测试计划第 3 章执行 L1 单元测试，覆盖 CLI 6 个子命令组、Core Service 3 个、DB 层 4 个、Models、Config/Logging/Utils。

#### Scenario: CLI project 子命令组测试
- **WHEN** 执行 `tests/cli/test_project.py` 及扩展用例
- **THEN** 覆盖 CLI-PROJ-001 至 CLI-PROJ-039 共 39 个用例
- **AND** 记录每个用例的通过/失败状态

#### Scenario: Core Service 测试
- **WHEN** 执行 `tests/core/` 下所有测试
- **THEN** 覆盖 SVC-PROJ-001 至 SVC-PROJ-042、SVC-TPL-001 至 SVC-TPL-008、SVC-CHG-001 至 SVC-CHG-023、SVC-PLC-001 至 SVC-PLC-016
- **AND** 记录测试结果

#### Scenario: DB 层测试
- **WHEN** 执行 `tests/db/` 下所有测试
- **THEN** 覆盖 DB-CONN/DB-REPO/DB-CHG/DB-SCAN/DB-SYNC 全部用例
- **AND** 记录测试结果

### Requirement: L2 GUI 测试执行

系统 SHALL 按测试计划第 4 章执行 L2 GUI 测试，使用 `QT_QPA_PLATFORM=offscreen` 离屏模式，覆盖 MainWindow、ProjectListView、ProjectWorkspaceView、GlobalView、OverviewTab、4 个 Dialog、3 个 Widget、角色适配。

#### Scenario: GUI 测试离屏模式
- **WHEN** 设置 `QT_QPA_PLATFORM=offscreen` 并执行 `tests/ui/` 下所有测试
- **THEN** 覆盖 GUI-MW-001 至 GUI-MW-035、GUI-PLV-001 至 GUI-PLV-027、GUI-WS-001 至 GUI-WS-015、GUI-GV-001 至 GUI-GV-010、GUI-OV-001 至 GUI-OV-004、GUI-PC/SB/FB、GUI-DLG-NEW/EDIT/DEL/IMP、GUI-ROLE-001 至 GUI-ROLE-009
- **AND** 记录测试结果

### Requirement: L3 端到端测试执行

系统 SHALL 按测试计划第 5 章执行 L3 端到端测试，覆盖 6 个完整工作流、三源数据一致性、多角色工作流。

#### Scenario: PLC 项目完整生命周期
- **WHEN** 执行 E2E-001 测试用例
- **THEN** 验证 create→list→show→edit→plc check→plc repair→plc standardize→change create→change list→change transition→project delete 全流程
- **AND** 每步成功，最终项目被删除

#### Scenario: 三源数据一致性
- **WHEN** 执行 E2E-SRC-001 至 E2E-SRC-005
- **THEN** 验证 .copier-answers.yml（真源）、PM_SESSION、DB 缓存三源数据一致

### Requirement: L4 侧自动测试执行

系统 SHALL 按测试计划第 6 章执行 L4 侧自动测试，包括 CLI 真实命令侧自动测试（PowerShell 脚本驱动）和 GUI 启动+交互侧自动验证。

#### Scenario: CLI 侧自动测试
- **WHEN** 在隔离测试工作空间中执行 SIDE-CLI-001 至 SIDE-CLI-023 及异常场景 SIDE-CLI-ERR-001 至 SIDE-CLI-ERR-007
- **THEN** 验证每个 CLI 命令在真实环境中的端到端可用性
- **AND** 记录每个命令的 exit_code 和输出

#### Scenario: GUI 侧自动测试
- **WHEN** 启动 GUI 并按 SIDE-GUI-001 至 SIDE-GUI-064 清单验证
- **THEN** 验证启动、导航、工具栏、列表、工作区、对话框、角色切换、状态栏、UI 整改项回归
- **AND** 记录验证结果（截图存档可选）

### Requirement: Bug 回归测试执行

系统 SHALL 按测试计划第 8 章执行 Bug 回归测试，覆盖 Bug-1/2/4/5 和 UI-001/002/003/004 整改项。

#### Scenario: Bug 回归
- **WHEN** 执行 `tests/test_bug1_get_project_path.py`、`tests/test_bug2_sync_changes.py`、`tests/test_bug4_retrofit_src_path.py`、`tests/test_bug5_scan_depth.py`
- **THEN** 所有 Bug 回归测试通过
- **AND** 记录测试结果

### Requirement: 性能测试执行（可选）

系统 SHOULD 按测试计划第 7 章执行性能测试，覆盖 list_projects、list_projects_cached、sync_to_cache、GUI 启动加载、GUI 搜索响应。

#### Scenario: 性能基准
- **WHEN** 执行 PERF-001 至 PERF-007
- **THEN** 记录响应时间，验证是否满足预期阈值

### Requirement: 生成最终检查清单

系统 SHALL 在测试结束后，在 `09_整改项/` 目录生成 `V2.0-测试执行检查清单.md`，覆盖所有功能模块的测试执行情况、通过/失败统计、缺陷清单、需求完成度，供用户核对。

#### Scenario: 检查清单生成
- **WHEN** 所有测试执行完成
- **THEN** 在 `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\09_整改项\V2.0-测试执行检查清单.md` 生成检查清单
- **AND** 检查清单含：测试概览、分层测试结果、Bug 回归结果、UI 整改项回归结果、缺陷清单、需求完成度核对表
- **AND** 每个检查项含状态（✅通过/❌失败/⚠️部分/⏭️跳过）和说明

## MODIFIED Requirements

### Requirement: 测试结果记录

测试执行过程中 SHALL 实时记录每个测试用例的执行结果，包括用例 ID、状态、失败原因、耗时。记录格式支持后续生成检查清单。

## REMOVED Requirements

无移除项。
