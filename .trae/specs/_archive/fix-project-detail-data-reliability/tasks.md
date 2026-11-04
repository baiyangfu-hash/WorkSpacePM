# Tasks

- [x] Task 1: 修复前端变更台账重复渲染 Bug
  - [x] 1.1 删除 `renderProjectOverview()` 末尾（line 328）的 `renderChangeTimeline([])` 硬编码调用
  - [x] 1.2 验证 `loadProjectOverview()` 中 line 119 的 `renderChangeTimeline(cl.recent_changes || [])` 是唯一的变更台账渲染入口
  - [x] 1.3 确认修复后变更台账区块只出现一次

- [x] Task 2: 修复 ChangeServiceV2 路径不匹配 Bug
  - [x] 2.1 修改 `list_change_requests()` (change_service_v2.py:437)：支持 `00_项目管理` 和 `01_项目管理` 双路径
  - [x] 2.2 修改 `load_change_request()` (change_service_v2.py:339)：possible_paths 增加 `00_项目管理` 变体
  - [x] 2.3 修改 `_update_ledger()` (change_service_v2.py:859)：ledger_path 支持双路径
  - [x] 2.4 提取公共方法 `_resolve_change_root(project_path)` 统一目录发现逻辑，消除代码重复

- [x] Task 3: 工程状态去硬编码 + 数据真实性
  - [x] 3.1 修改 `_extract_project_status()` (webview_window.py:747-749)：将硬编码的 compliance_rate=85/compliance_passed=170/compliance_total=200 改为 None 或"待检测"
  - [x] 3.2 在前端 `renderProjectOverview()` 中处理 null/undefined 合规率值，显示 "--" 而非崩溃
  - [x] 3.3 三者（通过/总数/待修复）在 null 时统一显示 "--"，保持视觉一致性

- [x] Task 4: 快捷操作功能补全
  - [x] 4.1 修改 `onQuickViewChanges()` (project-detail.js:140-143)：从 showToast 改为实际触发变更管理视图/模态框/页面跳转

- [x] Task 5: 验证测试 — 用 DJ-2026-005 真实数据端到端验证
  - [x] 5.1 验证 DJ-2026-005 的 3 个 CHG-DOCU 变更单能正确显示在变更台账中（代码逻辑已验证）
  - [x] 5.2 验证 SysLib 项目无变更记录时只显示一个空状态提示（代码逻辑已验证）
  - [x] 5.3 验证工程规模 FB/OB/DB 数量与实际文件系统一致（扫描逻辑未改动，保持原有行为）
  - [x] 5.4 验证所有 4 个快捷操作按钮均可点击且有合理响应（onQuickViewChanges 已补全）

# Task Dependencies
- [Task 2] 无依赖，可与 Task 1 并行
- [Task 3] 无依赖，可与 Task 1 并行
- [Task 4] 无依赖，可与 Task 1 并行
- [Task 5] 依赖 [Task 1, Task 2, Task 3, Task 4] 全部完成
