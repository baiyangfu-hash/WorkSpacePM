# Tasks — 工作空间Bug修复 & 路由完整性补齐

## P0: 修复工作空间挂载核心Bug

- [x] Task 1: 实现 `WorkspaceService.mount_workspace()` 方法
  - [x] 1.1 在 `WorkspaceService` 中添加 `mount_workspace(workspace_path)` 类方法
  - [x] 1.2 方法逻辑：调用 `ProjectService.load_workspace_from_path()` 加载子项目
  - [x] 1.3 返回格式：`{"success": True, "workspace_path": ..., "projects": [...], "stats": {...}}`（与 MockDataProvider 一致）
  - [x] 1.4 错误处理：路径不存在返回 `{"success": False, "error": "..."}`

- [x] Task 2: 修复 `get_workspace_summary` 和 `generate_workspace_report` 路由错误
  - [x] 2.1 在 `WorkspaceService` 中添加代理方法，内部调用 `ProjectService.get_workspace_summary` / `ProjectService.generate_workspace_report`
  - [x] 2.2 WebViewBridge 路由目标保持 `"workspace"` 域不变（通过代理方法桥接）
  - [x] 2.3 验证 `get_workspace_summary` 返回格式与前端期望一致
  - [x] 2.4 验证 `generate_workspace_report` 返回格式与前端期望一致

- [x] Task 3: 实现 `WorkspaceDashboardService.get_dashboard_stats()` 方法
  - [x] 3.1 添加 `get_dashboard_stats(workspace_path=None)` 类方法
  - [x] 3.2 内部调用 `get_dashboard_data()` 并提取 statistics 部分
  - [x] 3.3 返回格式与 MockDataProvider 一致：`{"success": True, "statistics": {...}}`

## P1: 补齐 ProjectService 缺失的GUI方法

- [x] Task 4: 实现 `ProjectService` 缺失的12个方法
  - [x] 4.1 `get_project_overview(project_path)` — 返回项目概览数据
  - [x] 4.2 `get_project_detail(path)` — 返回项目详细信息
  - [x] 4.3 `open_project(path)` — 打开项目（加载到缓存+返回项目数据）
  - [x] 4.4 `close_project()` — 关闭当前项目
  - [x] 4.5 `save_project_info(info_json)` — 保存项目信息
  - [x] 4.6 `list_directory_tree(project_path)` — 返回目录树结构
  - [x] 4.7 `get_recent_projects()` — 返回最近打开的项目列表
  - [x] 4.8 `run_version_check(project_path)` — 运行版本检查
  - [x] 4.9 `generate_chg(project_path, output_dir)` — 生成变更文档
  - [x] 4.10 `generate_ifc(project_path, output_dir)` — 生成接口文档
  - [x] 4.11 `export_excel_single(params)` — 导出单个FB Excel
  - [x] 4.12 `export_excel_batch(project_path)` — 批量导出Excel

- [x] Task 5: 回归验证 — 确保所有现有测试通过
  - [x] 5.1 运行 `pytest tests/ -q` — 791 passed, 16 skipped
  - [x] 5.2 运行 `pytest tests/test_api_gateway.py` — 通过
  - [x] 5.3 运行 `pytest tests/test_workspace.py` — 通过

## P2: 重构收尾（可选，后续迭代）

- [ ] Task 6: 清理 lib/ 目录或完善 VENDOR_VERSIONS.md
- [ ] Task 7: 版本号统一为 8.0.0-dev
- [ ] Task 8: 前端全局函数收敛 + CSS 内联样式迁移
- [ ] Task 9: 创建 `.github/workflows/ci.yml`

# Task Dependencies

```
Task 1 ──→ Task 2 (mount_workspace 是核心入口) ✅
Task 3 (独立，可并行) ✅
Task 4 (独立，可并行) ✅
Task 1,2,3,4 ──→ Task 5 (回归验证) ✅
Task 6~9 (可并行，后续迭代)
```