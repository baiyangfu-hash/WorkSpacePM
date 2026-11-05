# GUI 数据流修复 — 工作空间挂载后数据不显示

## Why
工作空间可以挂载打开，但 GUI 仅显示项目名称，所有详细数据（健康度、文档完成度、规范合规率、统计信息等）均不显示。根因是 store.js 的 getter 模式与所有 JS 文件中的直接赋值方式不兼容，导致状态变更静默丢失。

## What Changes
- **修复 store.js 与 ipc.js/navigation.js/dashboard.js 的状态管理不兼容** — 使 `state.xxx = value` 赋值能正确持久化到 Store
- **后端 `mount_workspace` 成功后发送 `workspace_opened` 事件** — 触发前端 UI 更新
- **修复 `get_dashboard_stats` 不传 workspace_path 的问题** — 前端调用时传入正确的路径
- **修复 `get_project_overview` 前后端数据格式不匹配** — 后端返回结构需与前端期望一致
- **修复 `list_directory_tree` 返回扁平列表而非树结构** — 前端期望嵌套树
- **补充前端集成测试** — 覆盖工作空间挂载→数据渲染的完整链路
- **补充 GUI 端到端测试** — 覆盖 IPC 通信的完整链路

## Impact
- Affected specs: 工作空间治理、Dashboard 数据聚合、项目详情
- Affected code: 
  - `ui_prototype/js/store.js` — 状态管理
  - `ui_prototype/js/ipc.js` — IPC 通信
  - `ui_prototype/js/navigation.js` — 导航与事件处理
  - `ui_prototype/js/views/dashboard.js` — Dashboard 视图
  - `ui_prototype/js/views/workspace.js` — 工作空间视图
  - `ui_prototype/js/views/project-detail.js` — 项目详情视图
  - `src/ui/webview_window.py` — IPC 桥接
  - `src/services/project_service.py` — 项目服务（数据格式调整）
  - `tests/` — 新增测试

## ADDED Requirements

### Requirement: 状态管理兼容性
系统 SHALL 保证 `window.state` 的属性赋值能正确持久化到 Store，使所有现有 JS 文件中的 `state.xxx = value` 语句正常工作。

#### Scenario: ipcMountWorkspace 设置 state 后视图可读取
- **WHEN** `ipcMountWorkspace` 执行 `state.workspaceProjects = [...]` 
- **THEN** `renderWorkspaceBrowse()` 中 `state.workspaceProjects` 返回正确的项目列表

#### Scenario: navigation.js 中 state 赋值后 statusBar 正确更新
- **WHEN** `onOpenWorkspace` 执行 `state.workspacePath = path`
- **THEN** `updateStatusBar()` 中 `state.workspacePath` 返回正确的路径

### Requirement: 后端事件推送
系统 SHALL 在 `mount_workspace` 成功后在 `_route` 方法中推送 `workspace_opened` 事件到前端。

#### Scenario: 挂载工作空间后 UI 自动刷新
- **WHEN** 用户通过 `ipcMountWorkspace` 挂载一个有效工作空间
- **THEN** 前端收到 `workspace_opened` 事件，自动更新侧边栏、状态栏并切换到 overview 视图

### Requirement: Dashboard 统计数据获取
`get_dashboard_stats` 前端调用 SHALL 传入当前工作空间路径，而非依赖后端默认值。

#### Scenario: 挂载工作空间后获取正确的 Dashboard 统计
- **WHEN** 用户挂载工作空间 `C:\Workspace`
- **THEN** `ipcGetDashboardStats()` 传入 `C:\Workspace` 并返回该工作空间的统计

### Requirement: 项目详情数据格式对齐
`get_project_overview` 后端返回 SHALL 包含 `business_identity`、`tech_environment`、`engineering_scale`、`project_status`、`change_ledger` 字段，与前端 `loadProjectOverview()` 期望一致。

#### Scenario: 点击项目卡片查看详情
- **WHEN** 用户点击项目卡片
- **THEN** 项目详情页显示：业务身份、技术环境、工程规模、工程状态、变更台账

### Requirement: 目录树返回嵌套结构
`list_directory_tree` SHALL 返回嵌套树结构（每个目录节点包含 `children` 数组），而非扁平列表。

#### Scenario: 项目详情页切换到"项目结构"Tab
- **WHEN** 用户点击"项目结构"Tab
- **THEN** 目录树正确渲染嵌套的文件夹和文件结构

### Requirement: 前端集成测试
系统 SHALL 提供前端集成测试，覆盖 Store 状态管理、IPC 调用、视图渲染的核心链路。

#### Scenario: Store 状态读写测试
- **WHEN** 运行 `Store.set('workspaceProjects', [{name: 'test'}])`
- **THEN** `Store.get('workspaceProjects')` 返回 `[{name: 'test'}]`

#### Scenario: 视图渲染读取 Store 状态
- **WHEN** Store 中有项目数据
- **THEN** `renderOverview()` 返回包含项目卡片的 HTML

### Requirement: GUI 端到端测试
系统 SHALL 提供 GUI 端到端测试，覆盖 `mount_workspace` → `get_dashboard_stats` → `get_project_overview` 的完整 IPC 链路。

#### Scenario: 完整工作空间挂载链路
- **WHEN** 调用 `mount_workspace` 传入有效路径
- **THEN** 返回 `{success: True, projects: [...], stats: {...}}`

#### Scenario: 完整项目详情链路
- **WHEN** 调用 `get_project_detail` 传入有效项目路径
- **THEN** 返回 `{success: True, project: {name, path, code, ...}}`

## MODIFIED Requirements

### Requirement: Project.get_project_overview 返回格式
**原格式**: 返回 `{success, project: {name, path, code, status, ...}}`

**新格式**: 返回 `{success, project: {name, path, code, ...}, business_identity: {...}, tech_environment: {...}, engineering_scale: {...}, project_status: {...}, change_ledger: {recent_changes: [...]}}`

### Requirement: Project.list_directory_tree 返回格式
**原格式**: 返回扁平列表 `{success, tree: [{name, path, type}]}`

**新格式**: 返回嵌套树结构 `{success, tree: {name, path, type: "directory", children: [{name, path, type: "file"}, ...]}}`