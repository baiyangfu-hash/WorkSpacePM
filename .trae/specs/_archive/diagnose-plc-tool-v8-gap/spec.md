# SW-2026-005 深度诊断：V8.0.0重构完成度审计 & 工作空间Bug根因分析

**诊断日期**: 2026-06-03  
**诊断范围**: 全量源码审计（~40 Python源文件、~30 前端文件、28 测试文件）  
**参照基准**: V8.0.0 全栈重构技术方案（[diagnose-plc-tool-v6 spec](file:///c:/Users/fubai/Desktop/My_Workspace/.trae/specs/diagnose-plc-tool-v6/spec.md)）、V7.0.0架构设计文档

---

## 一、核心发现：V8.0.0 重构"纸面完成"但存在严重功能缺陷

V8.0.0 的 [tasks.md](file:///c:/Users/fubai/Desktop/My_Workspace/.trae/specs/diagnose-plc-tool-v6/tasks.md) 和 [checklist.md](file:///c:/Users/fubai/Desktop/My_Workspace/.trae/specs/diagnose-plc-tool-v6/checklist.md) 全部勾选为已完成，但实际代码存在以下重大问题：

### 1.1 核心Bug：UI无法打开工作空间（P0 — 阻塞）

**根因**: `WebViewBridge` 通过 `APIGateway._dispatch("workspace", method, ...)` 调用4个工作空间方法，但 `WorkspaceService` 仅实现了其中1个，另外3个方法缺失或定义在其他Service中。

| WebViewBridge 调用 | 路由目标 | 实际位置 | 状态 |
|:--|:--|:--|:--|
| `mount_workspace(path)` | `workspace` 域 → `WorkspaceService` | **不存在于任何Service** | ❌ UNKNOWN_METHOD |
| `get_workspace_summary(path)` | `workspace` 域 → `WorkspaceService` | `ProjectService.get_workspace_summary` | ❌ UNKNOWN_METHOD（跨域） |
| `generate_workspace_report(path)` | `workspace` 域 → `WorkspaceService` | `ProjectService.generate_workspace_report` | ❌ UNKNOWN_METHOD（跨域） |
| `check_workspace(path)` | `workspace` 域 → `WorkspaceService` | `WorkspaceService.check_workspace` | ✅ 正确 |

此外，`WorkspaceDashboardService` 也缺少 `get_dashboard_stats` 方法，而 `WebViewBridge` 调用了它。

**影响**: 当用户在UI中点击"挂载工作空间"时，`ipcMountWorkspace` → `_pyapi('mount_workspace', ...)` → `WebViewBridge.mount_workspace()` → `APIGateway._dispatch("workspace", "mount_workspace")` → 返回 `{"success": False, "error": "服务 workspace 无方法 mount_workspace", "error_code": "UNKNOWN_METHOD"}`。用户看到"挂载失败"的toast提示。

### 1.2 次要Bug：ProjectService 缺失12个路由方法

`WebViewBridge` 向 `project` 域调用了 17 个方法，但 `ProjectService` 仅实现了 5 个：

| 方法 | 状态 |
|:--|:--|
| `create_project` | ✅ 存在 |
| `load_project_from_path` | ✅ 存在 |
| `get_workspace_summary` | ✅ 存在（但路由到错误域） |
| `generate_workspace_report` | ✅ 存在（但路由到错误域） |
| `load_workspace_from_path` | ✅ 存在 |
| `get_project_overview` | ❌ 缺失 |
| `get_project_detail` | ❌ 缺失 |
| `open_project` | ❌ 缺失 |
| `close_project` | ❌ 缺失 |
| `save_project_info` | ❌ 缺失 |
| `list_directory_tree` | ❌ 缺失 |
| `get_recent_projects` | ❌ 缺失 |
| `run_version_check` | ❌ 缺失 |
| `generate_chg` | ❌ 缺失 |
| `generate_ifc` | ❌ 缺失 |
| `export_excel_single` | ❌ 缺失 |
| `export_excel_batch` | ❌ 缺失 |

**说明**: 这些方法在Mock模式下有实现（`MockDataProvider`），所以前端开发时Mock模式可以正常工作，但真实模式下全部失败。

### 1.3 V8.0.0 重构"纸面完成"但实际未完成的项目

| V8.0.0 任务 | 声称状态 | 实际状态 | 证据 |
|:--|:--|:--|:--|
| 删除 lib/ 目录 | ✅ 完成 | ❌ 未完成 | `lib/` 目录完整存在，含pywebview/cffi/pythonnet/clr_loader等vendorized依赖 |
| 删除重复 bottle.py | ✅ 完成 | ❌ 未完成 | `lib/bottle.py` 仍存在 |
| VERSION 统一为 8.0.0-dev | ✅ 完成 | ❌ 未完成 | `constants.py` 中 `VERSION = "6.0.0"` |
| WebViewBridge 从 1700→400 行 | ✅ 完成 | ✅ 完成 | 实际 412 行，IPCBridge 已重命名为 WebViewBridge |
| APIGateway._dispatch 路由 | ✅ 完成 | ⚠️ 部分 | 路由框架存在，但大量方法缺目标 |
| 前端 JS 模块化 | ✅ 完成 | ⚠️ 部分 | `app.js`/`store.js` 存在，但视图仍使用全局函数（`onMountWorkspace` 等） |
| CSS 内联样式消除 | ✅ 完成 | ❌ 未完成 | workspace.js 仍大量使用 `style="..."` |
| CI/CD workflow | ✅ 完成 | ❌ 未完成 | `.github/workflows/` 目录不存在 |
| .pre-commit-config.yaml | ✅ 完成 | ⚠️ 部分 | 文件存在于项目根但非主程序目录 |

### 1.4 前端代码质量问题

- **50+ 全局函数**: `onMountWorkspace`、`onCheckWorkspace` 等全部裸露在 `window` 上
- **innerHTML 字符串拼接**: `renderWorkspaceBrowse()` 等视图仍用字符串拼接HTML
- **内联样式**: 工作空间视图有大量 `style="..."` 属性
- **无构建工具**: JS 文件通过 `<script>` 标签按加载顺序隐式依赖

### 1.5 测试现状

- **791 passed / 16 skipped** — 所有CLI测试通过
- 测试覆盖了 CLI 命令（check/fix/sync/doc/excel/health/info/deps），但**未覆盖GUI/IPC/WebViewBridge 路径**
- 无端到端测试覆盖 workspace mount/unmount 完整链路

---

## 二、偏离基线分析

### 2.1 版本号漂移

| 位置 | 声明版本 | 实际版本 |
|:--|:--|:--|
| V8.0.0 spec | 8.0.0-dev | — |
| `src/core/constants.py` | 6.0.0 | 6.0.0 |
| `config/app_config.json` | 6.0.0 | 6.0.0 |
| PRD文档 | V6.1.0 | — |
| 架构设计文档 | V7.0.0 | — |

V8.0.0 spec 声称 VERSION 已统一为 `8.0.0-dev`，但实际代码仍是 `6.0.0`。

### 2.2 架构设计 vs 实现偏离

| V7.0.0 设计目标 | 当前实现 | 偏差 |
|:--|:--|:--|
| Repository 数据访问层 | 已实现 `Repository` 类，但并非所有 Service 通过它访问 | 中度 |
| APIGateway 统一 IPC | 路由框架已建立，但大量方法缺失目标 | 严重 |
| 前端模块化 | `app.js`/`store.js` 存在但全局函数未消除 | 中度 |
| CSS 变量体系 | 变量已定义，但内联样式未消除 | 中度 |
| 异常层次全覆盖 | 已建立，92处 broad Exception 仍存在 | 轻微 |

---

## 三、影响范围

### 受影响的功能
- **工作空间挂载/卸载** — 完全不可用（P0阻塞）
- **工作空间摘要/报告** — 不可用（API路由错误）
- **Dashboard 统计** — 部分不可用（`get_dashboard_stats` 缺失）
- **项目打开/详情/浏览** — 12个方法缺失，项目详情页不可用
- **变更管理（GUI路径）** — 可能受影响（通过ChangeServiceV2路由，需要验证）

### 受影响代码
- `src/services/workspace_service.py` — 缺少 `mount_workspace`
- `src/services/project_service.py` — 缺少12个GUI方法
- `src/services/workspace_dashboard_service.py` — 缺少 `get_dashboard_stats`
- `src/ui/webview_window.py` — WebViewBridge 路由指向了不存在的方法
- `src/ui/api_gateway.py` — 路由框架正确，但 Service 方法缺失
- `ui_prototype/js/ipc.js` — 前端调用可能因后端错误返回而失败

---

## 四、修复优先级

### P0 — 阻塞（立即修复）
1. **实现 `WorkspaceService.mount_workspace()`** — 工作空间挂载核心功能
2. **修复 `get_workspace_summary` 和 `generate_workspace_report` 路由** — 将 `WebViewBridge` 中的路由改为 `project` 域，或在 `WorkspaceService` 中添加代理方法

### P1 — 重要（本迭代）
3. **实现 `ProjectService` 缺失的12个GUI方法** — 项目详情/打开/浏览等核心功能
4. **实现 `WorkspaceDashboardService.get_dashboard_stats()`** — Dashboard统计
5. **清理 `lib/` 目录** — 或至少确保 `VENDOR_VERSIONS.md` 记录完整

### P2 — 优化（后续迭代）
6. **版本号统一为 8.0.0-dev** — 对齐V8.0.0 spec
7. **前端全局函数收敛到 App 命名空间**
8. **CSS 内联样式迁移到 CSS 类**
9. **CI/CD workflow 创建**
10. **端到端测试覆盖 GUI/IPC 链路**

---

## 五、不可破坏行为清单（回归基准）

以下场景在修复过程中必须保持通过：

| # | 场景 | 验证方式 |
|:--|:--|:--|
| R1 | CLI `check` 命令正常执行 | `pytest tests/test_cli.py` |
| R2 | CLI `sync` 命令正常执行 | `pytest tests/test_sync_engine.py` |
| R3 | CLI `doc gen` 命令正常执行 | `pytest tests/test_document_service.py` |
| R4 | 变更单创建/状态转换 | `pytest tests/test_change_service_v2.py` |
| R5 | Repository 原子读写 | `pytest tests/test_repository.py` |
| R6 | WebViewBridge 窗口创建不崩溃 | 手动启动 GUI |
| R7 | Mock 模式下所有前端功能正常 | `PLC_MOCK_DATA=1 python main.py` |
| R8 | 791个现有测试全部通过 | `pytest tests/ -q` |