# 项目详情页数据可靠性修复 Spec

## Why

用户在 PLC 项目管理工具 V6.0.0 的项目详情页发现三个关键问题：
1. **变更台账始终显示"暂无变更记录"** — DJ-2026-005 明明有 3 个变更单（CHG-DOCU-2026-001~003）却无法显示
2. **工程规模、工程状态、快捷操作的数据可靠性不足** — 存在硬编码默认值和空数据处理缺陷
3. **截图显示"变更台账"区块出现两次**，均显示"暂无变更记录"

经代码审计确认，这是 **前端重复渲染 + 后端路径不匹配 + 硬编码默认值** 三个独立根因叠加导致的系统性问题，需要彻底修复以确保长期可靠。

## What Changes

- **修复前端 `renderChangeTimeline` 重复渲染 Bug**（[project-detail.js:328](ui_prototype/js/views/project-detail.js#L328)）：删除 `renderProjectOverview()` 内部硬编码的 `renderChangeTimeline([])` 空数组调用
- **修复后端变更目录路径不匹配 Bug**（[change_service_v2.py:437](src/services/change_service_v2.py#L437)）：`list_change_requests()` 仅搜索 `01_项目管理`，但 DJ-2026-005 等项目使用 `00_项目管理`，需支持多路径兼容
- **修复 `load_change_request()` 和 `_update_ledger()` 的同类型路径问题**
- **工程状态去硬编码**：将 `compliance_rate: 85` 等默认值替换为真实 SpecCheckerService 数据或明确标记为"待检测"
- **快捷操作 `onQuickViewChanges` 补全实现**：从 toast 提示改为实际跳转到变更管理视图

## Impact

- Affected specs: 无前置 spec 依赖
- Affected code:
  - `ui_prototype/js/views/project-detail.js` — 前端渲染逻辑
  - `src/services/change_service_v2.py` — 变更服务层（路径解析）
  - `src/ui/webview_window.py` — IPC 桥接层（工程状态默认值）

## ADDED Requirements

### Requirement: 变更台账正确渲染

系统 SHALL 在项目详情页正确展示变更台账数据，满足以下规则：

#### Scenario: 变更台账只渲染一次且使用真实数据
- **WHEN** 用户打开任意有变更记录的项目详情页（如 DJ-2026-005）
- **THEN** 页面仅显示一个"变更台账"区块，且该区块内容来自后端 API 返回的真实数据（`cl.recent_changes`）
- **AND** 不再出现重复的"暂无变更记录"空区块

#### Scenario: 变更台账为空时友好提示
- **WHEN** 项目确实没有任何变更记录（目录不存在或无 .md 文件）
- **THEN** 显示唯一的"暂无变更记录"提示，不出现重复区块

### Requirement: 变更服务路径兼容

变更服务 SHALL 兼容项目中不同的目录命名约定：

#### Scenario: 支持 00_项目管理 和 01_项目管理 两种路径
- **WHEN** 项目的变更管理目录位于 `00_项目管理/04_变更管理/` 或 `01_项目管理/04_变更管理/`
- **THEN** `list_change_requests()`、`load_change_request()`、`_update_ledger()` 均能正确定位到变更文件
- **AND** DJ-2026-005 的 3 个 CHG-DOCU 变更单能被正确读取和展示

### Requirement: 工程状态数据真实性

工程状态数据 SHALL 来自真实检测而非硬编码：

#### Scenario: 合规率数据来源明确
- **WHEN** SpecCheckerService 可用时，使用其返回的真实合规率
- **WHEN** SpecCheckerService 不可用或未运行过检查时，显示 "--" 或"待检测"而非虚假的 85%
- **AND** 通过/总数/待修复数三者保持数学一致性

### Requirement: 快捷操作功能完整

所有快捷操作按钮 SHALL 有可执行的实际功能：

#### Scenario: 查看全部变更记录
- **WHEN** 用户点击"查看全部变更记录"按钮
- **THEN** 执行实际的页面跳转或弹出变更管理面板（非仅 showToast）

## MODIFIED Requirements

### Requirement: renderProjectOverview 函数职责单一化

原 `renderProjectOverview()` 函数 SHALL 只负责渲染业务身份+技术环境+工程规模+工程状态+快捷操作五张卡片，不再包含变更台账渲染。变更台账的渲染由调用方 `loadProjectOverview()` 根据API返回的真实数据决定。

### Requirement: ChangeServiceV2 目录发现策略

`ChangeServiceV2` 的目录发现策略 SHALL 从硬编码单路径改为优先级列表扫描：
1. `{project}/01_项目管理/04_变更管理/01_变更单/`
2. `{project}/00_项目管理/04_变更管理/01_变更单/`

与 `IPCBridge._extract_business_identity()` 的多路径策略保持一致。
