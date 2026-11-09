# SW-2026-005 V7架构迭代计划 Spec

## Why

PRD-V6.1.0 定义了 25 项验收标准，当前代码满足 16 项（64%），部分满足 5 项（20%），未满足 4 项（16%）。同时 ARCH-V7.0.0 识别出 6 项关键架构缺陷（异常层次缺失、数据访问层缺失、API网关缺失、Mock数据混杂、前端状态管理薄弱、路由器缺失）。需要通过分阶段迭代，先补齐 P0 功能缺口，再推进架构重构。

## What Changes

- 修复 IPC 桥接绕过 ChangeServiceV2 导致台帐不更新的 Bug（AC-02.7）
- 补齐变更列表状态筛选 UI（AC-03.3）
- 新增变更审批操作 UI（AC-03.4）
- 补齐变更传播链和关联变更单输入 UI（AC-04.2/04.3）
- 实现变更统计面板与图表（AC-05.1）
- 实现变更汇总报告导出（AC-05.2）
- 实现变更响应时间指标（AC-05.3）
- 实现高优先级变更高亮显示（AC-05.4）
- 新增 `src/core/exceptions.py` 统一异常层次结构
- 新增 `src/core/repository.py` 数据访问层
- 新增 `src/ui/api_gateway.py` API 网关
- 新增 `src/ui/mock_data.py` Mock 数据分离
- 新增 `ui_prototype/js/store.js` 集中状态管理
- 新增 `ui_prototype/js/router.js` 视图路由
- 重构 `src/core/constants.py` 枚举元数据机制
- 重构 `src/core/event_bus.py` 异常日志
- 重构 `src/ui/webview_window.py` IPC 桥接拆分
- 删除前端死代码文件（layout.js 等）

## Impact

- Affected specs: PRD-V6.1.0 全部 5 个 User Story, ARCH-V7.0.0 全部 5 个 Phase
- Affected code:
  - 后端: `src/core/`, `src/services/`, `src/ui/webview_window.py`, `src/models/`
  - 前端: `ui_prototype/js/`, `ui_prototype/css/`, `ui_prototype/index.html`
  - 测试: `tests/` 新增 3 个测试文件

## ADDED Requirements

### Requirement: P0 功能缺口修复

系统 SHALL 修复 3 项 P0 级功能缺口，确保核心业务流程闭环。

#### Scenario: IPC 创建变更单后台帐正确更新
- **WHEN** 用户通过 GUI 创建变更单
- **THEN** 版本变更台帐自动追加一行引用记录
- **AND** 台帐记录包含变更单号、领域、性质、范围、状态、申请日期

#### Scenario: 变更列表支持状态筛选
- **WHEN** 用户在变更列表页选择状态筛选条件
- **THEN** 列表仅显示符合筛选条件的变更单
- **AND** 支持多状态组合筛选

#### Scenario: 变更审批操作记录完整
- **WHEN** 用户对审批中的变更单执行审批操作
- **THEN** 系统记录审批人、审批意见、审批时间
- **AND** 审批记录不可删除只能追加

### Requirement: P1 功能补齐

系统 SHALL 实现 US-04/US-05 的全部验收标准。

#### Scenario: 传播链和关联变更单可输入
- **WHEN** 用户创建 CROSS/SAFE 级别变更单
- **THEN** 向导显示传播链动态表单
- **AND** 每行包含影响域下拉、影响说明、关联变更单编号

#### Scenario: 变更统计面板展示图表
- **WHEN** 用户打开变更管理中心统计页
- **THEN** 显示本月变更总数、按领域分布饼图、按状态分布柱状图

#### Scenario: 变更汇总报告可导出
- **WHEN** 用户点击导出变更报告按钮
- **THEN** 系统生成 Markdown 格式的变更汇总报告

#### Scenario: 高优先级变更高亮
- **WHEN** 变更列表中存在 URGENT/CRITICAL 级别变更
- **THEN** 对应行高亮显示

### Requirement: ARCH-V7 Phase0 核心层重构

系统 SHALL 建立项目级异常层次结构、枚举元数据机制、EventBus 异常日志、Config 线程安全。

#### Scenario: 异常层次结构可用
- **WHEN** Service 层抛出业务异常
- **THEN** 异常类型为具体的子类（如 ChangeNotFoundError）
- **AND** IPCBridge 捕获后转换为标准错误响应

#### Scenario: 枚举元数据单一定义源
- **WHEN** 访问 ChangeDomain.ELEC.description
- **THEN** 返回 "电气"
- **AND** 无分离的描述映射表

### Requirement: ARCH-V7 Phase1 数据访问层

系统 SHALL 通过 Repository 层统一文件系统操作，Service 不直接 open/write 文件。

#### Scenario: Repository 缓存生效
- **WHEN** 多次查询同一项目卡片数据
- **THEN** TTL 内直接返回缓存结果
- **AND** 超时后重新计算

### Requirement: ARCH-V7 Phase2 IPC 层重构

系统 SHALL 将 IPCBridge 拆分为 APIGateway + MockDataProvider，API 精简为 21 个核心端点。

#### Scenario: APIGateway 路由请求
- **WHEN** 前端调用 `IPC.call('workspace.mount', {path: '...'})`
- **THEN** APIGateway 路由到 WorkspaceService.mount
- **AND** 返回 `{success: true, data: ...}` 标准响应

### Requirement: ARCH-V7 Phase3 前端重构

系统 SHALL 建立 Store + Router 前端架构，删除死代码，补全 CSS 变量体系。

#### Scenario: Store 集中状态管理
- **WHEN** Store.set('workspace', data) 被调用
- **THEN** 所有订阅 workspace:changed 的组件收到通知

#### Scenario: Router 视图切换
- **WHEN** Router.navigate('dashboard') 被调用
- **THEN** 旧视图 destroy() 被调用，新视图 render() + mount() 被执行

## MODIFIED Requirements

### Requirement: IPCBridge 创建变更单流程

原 IPCBridge `_create_change_request_v2()` 直接构建 CR 并写文件，绕过 Service 层。修改为调用 `ChangeServiceV2.create_change_request()`，确保台帐更新和事件发射。

## REMOVED Requirements

（无移除项）
