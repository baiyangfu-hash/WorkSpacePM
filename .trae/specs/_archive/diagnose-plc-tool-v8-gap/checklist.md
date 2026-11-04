# Checklist — 工作空间Bug修复 & 路由完整性验证

## P0: 工作空间挂载

- [x] `WorkspaceService.mount_workspace()` 方法存在，返回 `{"success": True, "workspace_path": ..., "projects": [...], "stats": {...}}`
- [x] 传入有效工作空间路径 → 返回子项目列表，`success=True`（由现有 `load_workspace_from_path` 逻辑保证）
- [x] 传入无效/不存在路径 → 返回 `success=False` 含错误信息
- [ ] 前端 `ipcMountWorkspace()` 调用后 `state.workspaceProjects` 正确填充（需GUI手动验证）
- [ ] 前端工作空间浏览视图正确渲染项目列表（需GUI手动验证）

## P0: 路由修复

- [x] `get_workspace_summary` 可通过 `WebViewBridge` 正常调用并返回数据（代理到 `ProjectService`）
- [x] `generate_workspace_report` 可通过 `WebViewBridge` 正常调用并返回数据（代理到 `ProjectService`）
- [x] `WebViewBridge` 中 `get_workspace_summary` 路由目标正确（`workspace` 域，通过代理方法）

## P0: Dashboard 统计

- [x] `WorkspaceDashboardService.get_dashboard_stats()` 方法存在
- [x] 调用返回 `{"success": True, "statistics": {...}}` 格式
- [ ] 前端 `ipcGetDashboardStats()` 调用后 `state.dashboardStats` 正确填充（需GUI手动验证）

## P1: ProjectService 方法补齐

- [x] `get_project_overview(project_path)` 存在且返回有效数据
- [x] `get_project_detail(path)` 存在且返回有效数据
- [x] `open_project(path)` 存在且加载项目到缓存
- [x] `close_project()` 存在且清理当前项目状态
- [x] `save_project_info(info_json)` 存在且持久化项目信息
- [x] `list_directory_tree(project_path)` 存在且返回目录树
- [x] `get_recent_projects()` 存在且返回最近项目列表
- [x] `run_version_check(project_path)` 存在且返回版本检查结果
- [x] `generate_chg(project_path, output_dir)` 存在且返回变更文档路径
- [x] `generate_ifc(project_path, output_dir)` 存在且返回接口文档路径
- [x] `export_excel_single(params)` 存在且返回Excel文件路径
- [x] `export_excel_batch(project_path)` 存在且返回Excel文件列表

## 回归验证

- [x] `pytest tests/ -q` 全部通过（791 passed, 16 skipped）
- [x] `test_api_gateway.py` 通过
- [x] `test_workspace.py` 通过
- [x] `test_workspace_governance.py` 通过
- [ ] Mock 模式 (`PLC_MOCK_DATA=1`) 下前端功能正常（需GUI手动验证）
- [ ] 真实模式下工作空间挂载完整链路可用（需GUI手动验证）