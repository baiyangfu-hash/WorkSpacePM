# Checklist — GUI 数据流修复验证

## P0: 状态管理

- [x] `window.state` 是 Proxy 对象，`state.xxx = value` 自动调用 `Store.set('xxx', value)`
- [x] `state.xxx` 读取自动调用 `Store.get('xxx')`
- [x] `state.workspaceProjects = [{name:'test', path:'/p'}]` 后 `Store.get('workspaceProjects')` 返回 `[{name:'test', path:'/p'}]`
- [x] `state.workspaceProjects.length` 正确返回 `1`
- [x] `state.dashboardStats = {project_count: 3}` 后 `state.dashboardStats.project_count` 返回 `3`
- [x] 删除属性 `delete state.xxx` 后 `Store.get('xxx')` 返回 `undefined`

## P1: 后端事件推送

- [x] `mount_workspace` 返回 `{success: True, ...}` 时，`WebViewBridge._route()` 调用 `_emit("workspace_opened", data)`
- [x] `mount_workspace` 返回 `{success: False, ...}` 时，不发送事件
- [x] 前端 `navigation.js` 的 `__ipc_recv` 包装器能正确处理 `workspace_opened` 事件
- [x] 收到事件后自动调用 `updateSidebar()`、`updateStatusBar()`、`switchView('overview')`

## P2: 数据格式

### get_dashboard_stats
- [x] `ipcGetDashboardStats()` 调用时传入 `state.workspacePath`
- [x] 返回 `{success: True, statistics: {total_projects, avg_health_score, ...}}`
- [x] 挂载工作空间后，Dashboard 统计栏显示正确的项目数和健康度

### get_project_overview
- [x] 返回包含 `business_identity` 字段（name, version, phase, description）
- [x] 返回包含 `tech_environment` 字段（platform, plc_model, hmi, driver, communication）
- [x] 返回包含 `engineering_scale` 字段（total_blocks, fb_count, ob_count, db_count）
- [x] 返回包含 `project_status` 字段（compliance_rate, compliance_passed, compliance_total）
- [x] 返回包含 `change_ledger` 字段（recent_changes 列表）
- [x] 项目详情页"总览"Tab 正确渲染所有卡片

### list_directory_tree
- [x] 返回嵌套树结构（根节点为 `{name, path, is_dir: true, children: [...]}`）
- [x] 子目录递归嵌套在 `children` 数组中
- [x] 项目详情页"项目结构"Tab 正确渲染嵌套目录树

## P3: 测试

### 后端 IPC 集成测试 (test_gui_ipc.py)
- [x] `test_mount_valid_workspace` — 传入有效工作空间路径，返回 `success=True` 含 `projects` 和 `stats`
- [x] `test_mount_missing_workspace` — 传入不存在路径，返回 `success=False`
- [x] `test_get_dashboard_stats_with_workspace` — 传入工作空间路径，返回 `success=True` 含 `statistics`
- [x] `test_get_project_overview_business_identity` — 返回含 `business_identity` 字段
- [x] `test_get_project_detail` — 传入有效项目路径，返回含 `name`, `path`, `code` 等字段
- [x] `test_list_directory_tree_nested` — 返回嵌套树结构

### 回归测试
- [x] `pytest tests/ -q` 全部通过（815 passed, 16 skipped, 0 failed）
- [x] `pytest tests/test_api_gateway.py -v` 通过
- [x] `pytest tests/test_workspace.py -v` 通过
- [x] `pytest tests/test_workspace_governance.py -v` 通过

### 新增测试
- [x] `pytest tests/test_gui_ipc.py -v` 14/14 全部通过
- [x] `pytest tests/test_frontend_store.py -v` 10/10 全部通过

## P4: 文档

- [x] `007_架构设计文档_ARCH-V7.0.0.md` 已更新为 `ARCH-V8.0.0`，含 Proxy 桥接和事件推送章节
- [x] `RELEASE_NOTES_V8.0.0.md` 已创建，记录 V8.0.0 GUI 数据流修复