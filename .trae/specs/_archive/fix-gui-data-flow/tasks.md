# Tasks — GUI 数据流修复

## P0: 修复状态管理（阻塞所有数据渲染）

- [x] Task 1: 修复 store.js 与所有 JS 文件的状态管理不兼容
  - [x] 1.1 修改 `store.js`，将 `window.state` 从 read-only getter 改为 Proxy 对象，使 `state.xxx = value` 赋值自动调用 `Store.set('xxx', value)`
  - [x] 1.2 修改 `store.js`，使 `state.xxx` 读取自动调用 `Store.get('xxx')`
  - [x] 1.3 验证：`test_frontend_store.py` 10 个测试全部通过
  - [x] 1.4 验证：`state.workspaceProjects.length` 能正确读取

## P1: 修复后端事件推送

- [x] Task 2: 后端 `mount_workspace` 成功后发送 `workspace_opened` 事件
  - [x] 2.1 在 `WebViewBridge._route()` 中增加事件推送逻辑：方法返回 `success=True` 时，查找对应事件并 `_emit`
  - [x] 2.2 `mount_workspace` 成功后 `_emit("workspace_opened", data)`
  - [x] 2.3 验证：`_EVENT_MAP` 包含 5 个事件映射

## P2: 修复数据格式不匹配

- [x] Task 3: 修复 `get_dashboard_stats` 不传 workspace_path
  - [x] 3.1 修改 `ipc.js` 中 `ipcGetDashboardStats()` 函数，传入 `state.workspacePath` 作为参数
  - [x] 3.2 验证：`test_gui_ipc.py::TestDashboardStats` 全部通过

- [x] Task 4: 修复 `get_project_overview` 前后端数据格式不匹配
  - [x] 4.1 修改 `ProjectService.get_project_overview()` 返回格式，增加 `business_identity`、`tech_environment`、`engineering_scale`、`project_status`、`change_ledger` 字段
  - [x] 4.2 从 Project 对象和资产扫描结果中提取对应字段
  - [x] 4.3 验证：`test_gui_ipc.py::TestProjectOverview` 全部通过

- [x] Task 5: 修复 `list_directory_tree` 返回扁平列表
  - [x] 5.1 修改 `ProjectService.list_directory_tree()` 返回嵌套树结构（`{name, path, is_dir, children: [...]}`）
  - [x] 5.2 验证：`test_gui_ipc.py::TestListDirectoryTree` 全部通过

## P3: 测试

- [x] Task 6: 补充后端 IPC 集成测试
  - [x] 6.1 创建 `tests/test_gui_ipc.py`，测试 `mount_workspace` → `get_dashboard_stats` → `get_project_overview` → `get_project_detail` → `list_directory_tree` 完整链路
  - [x] 6.2 使用临时目录创建测试项目结构（含 project.json + .plc_project.json），验证所有 API 返回格式正确
  - [x] 6.3 验证：`pytest tests/test_gui_ipc.py -v` 14/14 全部通过

- [x] Task 7: 补充前端单元测试
  - [x] 7.1 创建 `tests/test_frontend_store.py`，用 Python 验证 Store 的 Proxy 行为契约
  - [x] 7.2 测试 `state.xxx = value` 赋值后 `Store.get('xxx')` 返回正确的等价行为
  - [x] 7.3 验证：`pytest tests/test_frontend_store.py -v` 10/10 全部通过

- [x] Task 8: 回归验证 — 确保所有现有测试通过
  - [x] 8.1 运行 `pytest tests/ -q` — 815 passed, 16 skipped, 0 failed
  - [x] 8.2 所有测试套件通过（test_api_gateway, test_workspace, test_workspace_governance 等）

## P4: 文档同步

- [x] Task 9: 更新架构设计文档
  - [x] 9.1 更新 `007_架构设计文档_ARCH-V7.0.0.md` → `ARCH-V8.0.0`，记录前端状态管理 Proxy 桥接方案
  - [x] 9.2 更新 IPC 通信章节，记录自动事件推送机制

- [x] Task 10: 更新发布说明
  - [x] 10.1 创建 `RELEASE_NOTES_V8.0.0.md`，记录 V8.0.0 GUI 数据流修复

# Task Dependencies

```
Task 1 (状态管理) ──→ Task 3,4,5 (数据格式，依赖状态可读写)  ✅
Task 2 (事件推送) ──→ 独立 ✅
Task 1,2,3,4,5 ──→ Task 6,7 (测试) ✅
Task 6,7 ──→ Task 8 (回归验证) ✅
Task 9,10 (文档) ✅
```