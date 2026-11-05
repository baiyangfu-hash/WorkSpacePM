# V9.0 全面诊断与文档先行重构方案

## Why

项目历经 V1→V8 共 9 轮 spec 迭代，用户反馈"功能都没有了，总览的数据都是假的"。根因是：

1. **代码与文档严重脱节**：PRD 写了 15 个模块，立项表声称全部"已完成"，但实际运行时 Dashboard 数据流断裂、变更管理 IPC 调用链不通
2. **反复修 Bug 而非从设计层面解决问题**：9 个 spec 中 6 个是"fix"类，每次只修表面症状，没有回到"用户到底要什么"重新设计
3. **没有可交互的 UI 原型**：所有 UI 设计都是文字描述或 ASCII 图，开发者和用户无法直观看到界面交互效果，导致反复返工
4. **数据关联不明确**：UI 上每个字段对应哪个后端 API、哪个数据模型字段，没有文档化，导致前端硬编码假数据

## What Changes

### 诊断发现的核心问题

| # | 问题 | 严重度 | 影响 |
|---|------|--------|------|
| P1 | APIGateway 每次请求新建 Service 实例，缓存全部丢失 | **致命** | Dashboard 每次刷新都全量扫描，且项目状态无法跨请求保持 |
| P2 | 前端 change-wizard 调用 `create_change_request_v2` 的 IPC 链路断裂 | **致命** | 变更管理核心功能不可用 |
| P3 | 前端 `ipcGetTemplates()` 调用后端不存在的 `get_templates` 方法 | **严重** | 文档生成功能不可用 |
| P4 | Mock 数据格式与真实 Service 返回格式不一致 | **严重** | 开发时 Mock 可用，切到真实模式就崩溃 |
| P5 | 立项表 PRD 声称 15 个模块"已完成"，但实际仅 6 个核心模块可用 | **严重** | 文档与实际严重不符，误导开发决策 |
| P6 | 无 UI 原型文档，每次开发凭想象实现，反复返工 | **中等** | 开发效率低，用户无法提前确认需求 |

### 变更方案

- **文档先行**：先输出可交互的 HTML UI 原型（放在项目文档目录），每个模块标注数据来源（API→Service→Model 字段映射）
- **更新项目基础文档**：基于代码实际状态重写 PRD 和立项表，删除虚假的"已完成"标记
- **输出架构文档**：更新 ARCH 文档反映 V8 实际代码结构，标注哪些可用哪些断裂
- **不写代码**：本 spec 只产出文档和 UI 原型，实施留给后续 spec

## Impact

- Affected specs: 之前 9 个 spec 的结论需要重新审视
- Affected code: 无代码变更（本 spec 仅产出文档和原型）
- Affected docs: PRD、立项表、ARCH 文档将全部重写

## ADDED Requirements

### Requirement: HTML UI 原型 — 项目总览 Dashboard

系统 SHALL 提供可交互的 HTML 原型，展示项目总览 Dashboard 的完整界面和交互流程。

#### Scenario: 用户打开工具选择工作空间

- **WHEN** 用户在 HTML 原型中点击"选择工作空间"
- **THEN** 原型展示工作空间路径选择对话框，选择后展示 Dashboard 页面
- **AND** Dashboard 显示统计概览卡片（项目总数/平均健康度/文档完成率/待处理变更单/命名冲突数）
- **AND** 每个统计卡片标注数据来源 API：`get_dashboard_stats(workspace_path)`

#### Scenario: 用户查看项目卡片列表

- **WHEN** Dashboard 加载完成
- **THEN** 展示项目卡片网格，每张卡片包含：项目名称、项目类型、健康度评分、文档完成率、规范合规率、最后更新时间
- **AND** 每个字段标注数据来源：`get_dashboard_data(workspace_path)` → `DashboardProjectItem` 各字段
- **AND** 卡片支持点击进入项目详情

#### Scenario: 用户按类型筛选项目

- **WHEN** 用户点击筛选下拉框
- **THEN** 展示筛选选项：全部/DJ单机/共享库/通用项目
- **AND** 筛选后卡片列表实时更新

### Requirement: HTML UI 原型 — 项目详情页

系统 SHALL 提供可交互的 HTML 原型，展示项目详情页的完整界面和数据关联。

#### Scenario: 用户从 Dashboard 点击项目卡片

- **WHEN** 用户点击某项目卡片
- **THEN** 展示项目详情页，包含 Tab 切换：总览/项目结构/变更管理
- **AND** 总览 Tab 展示五块信息卡片：业务身份/技术环境/工程规模/工程状态/快捷操作
- **AND** 每块卡片每个字段标注数据来源：`get_project_overview(project_path)` → 对应字段

#### Scenario: 用户查看变更台账

- **WHEN** 用户在项目详情总览页查看变更台账区域
- **THEN** 展示最近变更记录时间线（最多8条）
- **AND** 每条记录显示：变更单号/领域/性质/标题/状态/日期
- **AND** 数据来源标注：`ChangeServiceV2.list_change_requests(project_path, limit=8)`

### Requirement: HTML UI 原型 — 变更管理中心

系统 SHALL 提供可交互的 HTML 原型，展示变更管理中心的完整界面和交互流程。

#### Scenario: 用户创建变更单（4步向导）

- **WHEN** 用户点击"新建变更单"
- **THEN** 展示4步向导弹窗：
  - Step1 选择关联项目（从当前工作空间项目列表选择）
  - Step2 填写二维分类（技术领域7选1 × 业务性质5选1 × 影响范围多选）
  - Step3 填写变更信息（原因/变更前/变更后/影响分析）
  - Step4 预览确认（Markdown渲染预览 + 自动编号）
- **AND** 每个表单字段标注对应 `ChangeRequestV2` 模型字段名
- **AND** Step4 预览展示最终将生成的 Markdown 内容

#### Scenario: 用户查看变更列表

- **WHEN** 用户进入变更管理中心
- **THEN** 展示变更单列表，支持按状态筛选
- **AND** 每行显示：变更编号/标题/领域/性质/状态/申请人/日期
- **AND** 数据来源标注：`list_change_requests(path, filters)`

#### Scenario: 用户执行状态流转

- **WHEN** 用户点击某变更单的"审批"或"推进"按钮
- **THEN** 展示状态流转对话框，显示当前状态→可转换的目标状态
- **AND** 必须填写审批意见
- **AND** 数据来源标注：`transition_change_status_v2(change_id, new_status, reason)`

#### Scenario: 用户查看变更统计

- **WHEN** 用户切换到统计 Tab
- **THEN** 展示统计面板：本月变更总数/按领域分布饼图/按状态分布柱状图/响应时间指标
- **AND** 数据来源标注：`get_change_statistics(workspace_path)`

### Requirement: 文档更新 — PRD 基于实际代码重写

系统 SHALL 更新产品需求文档，使其准确反映代码实际状态。

#### Scenario: PRD 功能清单与代码对齐

- **WHEN** 阅读 PRD 功能清单
- **THEN** 每个功能模块标注真实状态：可用/部分可用/不可用/未实现
- **AND** 不可用功能标注根因（如"IPC链路断裂"/"Service方法缺失"）
- **AND** 删除虚假的"已完成"标记

### Requirement: 文档更新 — 立项表基于实际状态重写

系统 SHALL 更新项目立项表，使其准确反映项目实际进度。

#### Scenario: 立项表里程碑与实际对齐

- **WHEN** 阅读立项表里程碑
- **THEN** 每个里程碑标注实际完成度（而非全部标"已完成"）
- **AND** 技术栈描述与实际代码一致（PyWebView + 17个JS模块 + 9个Service）

### Requirement: 文档更新 — 架构文档反映 V8 实际状态

系统 SHALL 更新架构设计文档，标注实际可用和断裂的部分。

#### Scenario: 架构文档数据流标注

- **WHEN** 阅读架构文档 IPCBridge 部分
- **THEN** 每个 API 端点标注：可用/部分可用/不可用
- **AND** 不可用端点标注根因
- **AND** 包含完整的数据流图：前端JS → IPC → WebViewBridge → APIGateway → Service → Repository → 文件系统

### Requirement: UI 原型数据关联文档

每个 HTML UI 原型 SHALL 包含数据关联标注。

#### Scenario: 查看 UI 原型的数据来源

- **WHEN** 用户在 HTML 原型中查看任意数据字段
- **THEN** 该字段旁显示数据来源标注（可切换显示/隐藏）
- **AND** 标注格式为：`API: 方法名(参数) → Model.字段名`
- **AND** 标注颜色区分：绿色=已验证可用、黄色=部分可用、红色=不可用

## MODIFIED Requirements

### Requirement: PRD 功能模块清单

PRD 功能模块清单从"15个模块全部已完成"修改为基于代码实际诊断的真实状态：

| 模块 | 原标记 | 实际状态 |
|------|--------|----------|
| 项目总览 Dashboard | ✅已完成 | ⚠️部分可用（数据流可用但无缓存，性能差） |
| 项目管理 | ✅已完成 | ✅可用 |
| ST代码编辑器 | ✅已完成 | ❌已移除（PyWebView架构下不存在） |
| HMI变量映射 | ⏸占位符 | ❌未实现 |
| 规范检查面板 | ✅已完成 | ✅可用 |
| 诊断面板 | ✅已完成 | ✅可用 |
| 测试运行器 | ⏸占位符 | ❌未实现 |
| 文档生成 | ✅已完成 | ⚠️部分可用（get_templates IPC断裂） |
| 变更管理 | ✅已完成 | ⚠️部分可用（V2创建IPC链路断裂） |
| 变更统计 | ✅已完成 | ✅可用 |
| FB接口一致性检查 | ✅已完成 | ✅可用 |
| 自动批量修复 | ✅已完成 | ✅可用 |
| Excel导出 | ✅已完成 | ⚠️部分可用（依赖ExcelExporter可能缺失） |
| SysLib扫描 | ✅已完成 | ✅可用 |
| 变更管理Sync | ✅已完成 | ⚠️部分可用（SyncEngine可能缺失） |

## REMOVED Requirements

### Requirement: ST代码编辑器

**Reason**: PyWebView 架构下不存在代码编辑器功能，Trae IDE 已有编辑器能力
**Migration**: 从 PRD 功能清单中移除，不再规划

### Requirement: HMI变量映射

**Reason**: 仅占位符，从未实现，不在核心场景内
**Migration**: 从 P0 功能降级为 V2.0 远期规划

### Requirement: 测试运行器

**Reason**: 仅占位符，从未实现
**Migration**: 从 P1 功能降级为 V2.0 远期规划
