# Tasks

## Phase 0: P0 功能缺口修复 + 核心层重构

- [x] Task 1: 修复 IPC 创建变更单绕过 Service 层的 Bug（AC-02.7）
  - [x] SubTask 1.1: 重构 `webview_window.py` 的 `_create_change_request_v2()` 方法，改为调用 `ChangeServiceV2.create_change_request()`
  - [x] SubTask 1.2: 验证台帐更新逻辑被正确触发
  - [x] SubTask 1.3: 补充集成测试覆盖 IPC → Service → 台帐更新链路

- [x] Task 2: 新增 `src/core/exceptions.py` 异常层次结构
  - [x] SubTask 2.1: 定义 PLCToolError 基类及 5 大子类（StorageError/ChangeManagementError/WorkspaceError/SpecCheckError/ConfigError）
  - [x] SubTask 2.2: 在 ChangeServiceV2 中替换 ValueError/FileNotFoundError 为具体异常类型
  - [x] SubTask 2.3: 在 IPCBridge 中统一捕获异常并转换为 `{success: false, error, error_code}` 响应
  - [x] SubTask 2.4: 新增 `tests/test_exceptions.py` 单元测试

- [x] Task 3: 重构 `src/core/constants.py` 枚举元数据机制
  - [x] SubTask 3.1: 为 ChangeDomain/ChangeNature/ChangeScope/ChangeStatusV2 添加 description/icon 属性
  - [x] SubTask 3.2: 删除 `change_request_v2.py` 中的 `except ImportError` 备用枚举定义
  - [x] SubTask 3.3: 删除 `change_template_renderer.py` 中的重复映射方法
  - [x] SubTask 3.4: 删除 constants.py 中的分离描述映射表（BUSINESS_LINE_DESC 等）

- [x] Task 4: 重构 `src/core/event_bus.py` 异常日志
  - [x] SubTask 4.1: 将 `except Exception: pass` 改为 `except Exception as e: logger.error(..., exc_info=True)`
  - [x] SubTask 4.2: 添加事件命名空间（workspace:mounted, change:created, project:opened）

- [x] Task 5: 补齐变更列表状态筛选 UI（AC-03.3）
  - [x] SubTask 5.1: 在 `change-list.js` 工具栏添加状态筛选下拉框
  - [x] SubTask 5.2: 修改 `list_change_requests` IPC 调用传递 filter 参数
  - [x] SubTask 5.3: 添加筛选交互样式

- [x] Task 6: 新增变更审批操作 UI（AC-03.4）
  - [x] SubTask 6.1: 在 `change-list.js` 详情面板添加审批操作按钮
  - [x] SubTask 6.2: 新增审批对话框组件（审批人/意见/动作选择）
  - [x] SubTask 6.3: 新增 IPC 端点 `transition_change_status_v2` 传递审批记录
  - [x] SubTask 6.4: 审批记录追加到 change_request 的 approval_history

## Phase 1: P1 功能补齐 + 数据访问层

- [x] Task 7: 补齐变更传播链和关联变更单输入 UI（AC-04.2/04.3）
  - [x] SubTask 7.1: 在 `change-wizard.js` Step3 影响分析区域增加传播链动态表单
  - [x] SubTask 7.2: 每行包含影响域下拉、影响说明输入、关联变更单编号输入
  - [x] SubTask 7.3: 支持添加/删除传播链行

- [x] Task 8: 新增 `src/core/repository.py` 数据访问层
  - [x] SubTask 8.1: 实现 Repository 类（read_file/write_file/list_files/get_cached/set_cached/invalidate）
  - [x] SubTask 8.2: 实现内存缓存（TTL 5分钟）
  - [x] SubTask 8.3: 实现 list_files 的 exclude 规则
  - [x] SubTask 8.4: 新增 `tests/test_repository.py` 单元测试

- [x] Task 9: 实现变更统计面板（AC-05.1）
  - [x] SubTask 9.1: 引入 Chart.js 库到 ui_prototype
  - [x] SubTask 9.2: 新增 `change-stats.js` 视图，调用 `get_change_statistics` 绘制图表
  - [x] SubTask 9.3: 在导航栏添加"统计"入口

- [x] Task 10: 实现变更汇总报告导出（AC-05.2）
  - [x] SubTask 10.1: 在 ChangeServiceV2 中新增 `export_report()` 方法
  - [x] SubTask 10.2: 新增 IPC 端点 `export_change_report`
  - [x] SubTask 10.3: 前端添加导出按钮和交互

- [x] Task 11: 实现变更响应时间指标（AC-05.3）
  - [x] SubTask 11.1: 在 `get_change_statistics()` 中增加响应时间计算逻辑
  - [x] SubTask 11.2: 统计面板展示响应时间指标

- [x] Task 12: 实现高优先级变更高亮显示（AC-05.4）
  - [x] SubTask 12.1: 在 `change-list.js` 中为 URGENT/CRITICAL 变更行添加高亮 CSS class
  - [x] SubTask 12.2: 在 `change-wizard.css` 或 `change.css` 中定义高亮样式

## Phase 2: IPC 层重构

- [x] Task 13: 新增 `src/ui/api_gateway.py` API 网关
  - [x] SubTask 13.1: 实现 APIGateway 类（请求路由/参数校验/响应标准化）
  - [x] SubTask 13.2: 按域注册 Service（project/change/workspace_dashboard/spec_checker）
  - [x] SubTask 13.3: 实现 `_dispatch()` 方法统一路由
  - [x] SubTask 13.4: 新增 `tests/test_api_gateway.py` 单元测试

- [x] Task 14: 新增 `src/ui/mock_data.py` Mock 数据分离
  - [x] SubTask 14.1: 将 IPCBridge 中的 MOCK_PROJECTS/MOCK_CHECKERS/MOCK_SPEC_RESULT/MOCK_DIAGNOSTIC 提取到 MockDataProvider
  - [x] SubTask 14.2: 通过环境变量 `PLC_MOCK_DATA=1` 切换 Mock 模式

- [x] Task 15: API 精简与命名统一
  - [x] SubTask 15.1: 将 35+ API 端点精简为 21 个核心端点
  - [x] SubTask 15.2: 统一命名格式为 `{域}_{动作}` (snake_case)
  - [x] SubTask 15.3: 旧 API 保留但标记 DeprecationWarning

- [x] Task 16: 重构前端 IPC Client
  - [x] SubTask 16.1: 实现 `IPC.call('domain.method', params)` 统一调用方式
  - [x] SubTask 16.2: 删除 `ipcCall()`/`_pyapi()` 别名冗余
  - [x] SubTask 16.3: 实现单一 `__ipc_recv` 事件处理入口

## Phase 3: 前端重构

- [x] Task 17: 新增 `ui_prototype/js/store.js` 集中状态管理
  - [x] SubTask 17.1: 实现 Store 对象（get/set/on/off/_emit）
  - [x] SubTask 17.2: 封装异步操作（loadWorkspace/selectProject）
  - [x] SubTask 17.3: 迁移 state.js 和 navigation.js currentView 到 Store

- [x] Task 18: 新增 `ui_prototype/js/router.js` 视图路由
  - [x] SubTask 18.1: 实现 Router 对象（register/navigate/init）
  - [x] SubTask 18.2: View 生命周期管理（render/mount/destroy）
  - [x] SubTask 18.3: 替代 `switchView()` 模式

- [x] Task 19: 删除前端死代码
  - [x] SubTask 19.1: 删除 `js/layout.js`（IDE 布局死代码）
  - [x] SubTask 19.2: 删除 `js/handlers.js`（功能合并到 View）— 保留（仍被引用）
  - [x] SubTask 19.3: 删除 `js/checkers.js`（功能合并到 Dashboard）— 保留（仍被引用）
  - [x] SubTask 19.4: 删除 `js/utils.js`（功能合并到 Store）— 保留（仍被引用）
  - [x] SubTask 19.5: 删除未使用 CSS 文件（activity-bar/bottom-panel/content-area/responsive）— 已删除5个

- [x] Task 20: 补全 CSS 变量体系
  - [x] SubTask 20.1: 补全 variables.css 缺失变量（8个新变量）
  - [x] SubTask 20.2: 清理 index.html 内联 CSS（~760行移至 app-layout.css）
  - [x] SubTask 20.3: 组件样式使用 BEM 命名

# Task Dependencies

- Task 1 (IPC修复) → Task 6 (审批UI) : 审批UI需要正确的Service层调用链路
- Task 2 (异常层次) → Task 13 (API网关) : API网关依赖统一异常处理
- Task 3 (枚举元数据) → Task 14 (Mock分离) : Mock数据可能引用枚举描述
- Task 8 (Repository) → Task 13 (API网关) : API网关通过Repository访问数据
- Task 13 (API网关) → Task 16 (IPC Client) : 前端IPC Client需适配新API格式
- Task 17 (Store) + Task 18 (Router) → Task 19 (删除死代码) : 死代码迁移完成后才能删除
- Task 5 (状态筛选) + Task 6 (审批UI) → Task 9 (统计面板) : 统计面板需基于完整的变更数据
- Task 7 (传播链UI) 依赖 Task 3 (枚举元数据) : 传播链域下拉使用枚举元数据
- Task 9 (统计面板) + Task 10 (报告导出) + Task 11 (响应时间) + Task 12 (高亮) : US-05 四项可并行开发
