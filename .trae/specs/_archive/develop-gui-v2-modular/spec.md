# auto-pm GUI V2.0 模块化重构开发 Spec

## Why

当前 GUI 功能过于简陋：项目平铺无分类、变更管理完全缺失、PLC 检查/修复无入口、全局功能页全部占位。原型设计已完成（`02_设计/GUI原型-V2.0.md` + `02_设计/GUI原型-V2.0.html`），后端服务层匹配度分析显示约 60% 功能已有后端支撑。需要按模块化方式重构 GUI，按后端支撑度排优先级迭代开发，并在每个迭代结束时进行 GUI 交互测试。

## What Changes

### 架构变更
- **BREAKING**：删除角色系统（`roles.py`、`MainWindow._role_menu`、`apply_role()`），所有功能对单一用户全开放
- **BREAKING**：重构 UI 目录结构为 8 个功能模块包（navigation/project_list/workspace/change_center/dialogs/global_pages/widgets/models）
- 替换 `MainWindow.navList` (QListWidget) 为 `NavigationTree` (QTreeWidget)，含总库分组+阶段子节点+计数徽标

### 功能新增（按后端支撑度排序）
- **后端已就绪**：变更Tab、检查Tab、文档Tab-模板更新、模板管理页
- **后端需补桥接**：项目分组视图、变更数统计、变更中心全局列表、按阶段筛选
- **后端需新建**：报告中心统计服务、变更单 update/delete、项目文档扫描服务

### 后端补充
- `ProjectRepository.list_by_phase(phase)` 新增
- `ProjectService.list_projects_filtered(stack, phase, business_line)` 新增
- `ProjectService.list_projects_with_change_count()` 新增
- `ChangeService.list_all_changes(status, domain)` 新增（跨项目查询）
- `ChangeService.update_change_request(...)` 新增
- `ChangeService.delete_change_request(change_number)` 新增
- `ReportService` 新增（统计聚合）

## Impact

- Affected specs: `execute-auto-pm-v2-test-plan`（测试基线需扩展 GUI 交互测试）
- Affected code:
  - `auto_pm/ui/` 全目录重构
  - `auto_pm/core/project_service.py` 新增筛选/统计方法
  - `auto_pm/change/change_service.py` 新增 list_all/update/delete
  - `auto_pm/db/repository.py` 新增 list_by_phase
  - `auto_pm/models/project.py` ProjectInfo 增加 file_mtime 字段
  - 新增 `auto_pm/core/report_service.py`

## ADDED Requirements

### Requirement: 模块化 UI 架构
The system SHALL organize GUI code into 8 independent modules (navigation, project_list, workspace, change_center, dialogs, global_pages, widgets, models), each module independently testable.

#### Scenario: 模块独立测试
- **WHEN** 开发者运行单个模块的测试
- **THEN** 该模块测试可独立通过，不依赖其他模块的 GUI 组件

### Requirement: 总库分类导航
The system SHALL display a tree navigation with PLC总库/Python总库 as top-level nodes, each expandable to show phase sub-nodes (在研/调试中/生产中/已归档) with project count badges.

#### Scenario: 点击阶段子节点筛选
- **WHEN** 用户点击"PLC总库 > 调试中"
- **THEN** 项目列表页显示 PLC 总库下所有 phase=commissioning 的项目

### Requirement: 项目分组视图
The system SHALL support 4 grouping modes (总库+业务线/总库+阶段/业务线/阶段) and 2 view modes (卡片/列表).

#### Scenario: 切换分组维度
- **WHEN** 用户在分组下拉中选择"总库+阶段"
- **THEN** 项目按 (stack, phase) 二维分组展示

### Requirement: 变更管理 GUI
The system SHALL expose ChangeService CRUD + 状态流转 to GUI via 变更Tab (项目工作区) and 变更中心 (全局页).

#### Scenario: 创建变更单
- **WHEN** 用户在变更Tab点击"创建变更单"并填写表单
- **THEN** 调用 ChangeService.create_change_request() 生成变更单文件，列表刷新

#### Scenario: 状态流转
- **WHEN** 用户在变更详情点击"提交审批"
- **THEN** 调用 ChangeService.transition_status()，状态更新为"待审批"

### Requirement: PLC 检查 GUI
The system SHALL expose PlcChecker/PlcRepairer to GUI via 检查Tab.

#### Scenario: 执行检查
- **WHEN** 用户点击"执行检查"
- **THEN** 调用 PlcChecker.check_project()，结果按 pass/warn/fail 分组展示

#### Scenario: 单项修复
- **WHEN** 用户点击某 warn/fail 项旁的"修复"按钮
- **THEN** 调用 PlcRepairer.repair_project(dry_run=False)，修复后该项变绿

### Requirement: GUI 交互测试
The system SHALL be tested via pytest-qt with real widget interaction (click/input/signal verification) for every GUI feature.

#### Scenario: 全功能交互测试
- **WHEN** 开发完成后运行 GUI 测试套件
- **THEN** 每个功能（导航/列表/工作区/变更/检查/文档/对话框）都有交互测试覆盖

### Requirement: 后端服务桥接
The system SHALL add Service-layer methods to bridge existing Repository capabilities to UI.

#### Scenario: 按阶段筛选项目
- **WHEN** UI 调用 ProjectService.list_projects_filtered(stack='plc', phase='commissioning')
- **THEN** 返回 PLC 总库下所有调试中项目

## MODIFIED Requirements

### Requirement: ProjectInfo 数据模型
ProjectInfo SHALL include `file_mtime: float` field for "最近修改时间" display in project cards.

### Requirement: MainWindow
MainWindow SHALL remove role menu and role-based tab visibility logic; all tabs visible to single user.

## REMOVED Requirements

### Requirement: 角色系统
**Reason**: 使用者一人兼顾所有角色，无需角色区分
**Migration**: 删除 `auto_pm/ui/roles.py`、`MainWindow._role_menu`、`MainWindow.apply_role()`、所有 Tab 的 `apply_role()` 方法
