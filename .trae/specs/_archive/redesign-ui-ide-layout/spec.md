# PLC项目管理工具 IDE布局 UI 重设计 Spec

## Why
当前SW-2026-005项目使用的是传统PyQt5工业风格界面（基于QSplitter的双栏布局+QSS），而HTML原型`ui_prototype/index.html`展示了一个更现代的VSCode启发的IDE布局（Activity Bar + 动态侧边栏 + Tab页签 + 底部诊断面板）。需要将主界面重构为IDE布局，统一设计语言，提升操作效率和视觉一致性。

## What Changes
- **BREAKING** 主窗口布局从 QSplitter 双栏改为 IDE 五区布局（Activity Bar + Sidebar + Content + Bottom Panel + Status Bar）
- 引入 Activity Bar（左侧48px图标条），替代当前侧边栏顶部的隐式导航——7个活动视图入口：仪表盘、项目管理、文档管理、PLC工具、变更管理、规范中心、设置
- Sidebar 改为上下文感知式，随 Activity 切换而动态渲染不同内容（与原型一致）
- Content Area 引入多 Tab 页签系统，支持同时打开多个功能页并独立关闭
- 新增底部面板（输出/诊断），统一收容当前散落在QDockWidget中的诊断面板和规范检查面板
- 全局采用深色工业风主题（CSS Variables → QSS 映射），主题色为橙色(#E86100)
- 各功能面板（Dashboard/Project/Change/Spec等）UI样式对齐原型设计
- Status Bar 增强，显示项目路径、规范状态、编码等信息
- 保留现有 Service/Controller 层不变，仅重构 View 层

## Impact
- Affected specs: 无（纯UI层重构）
- Affected code: 
  - `main_window.py` — 主窗口布局完全重写
  - `industrial_sidebar.py` — 重写为 Activity Bar + 上下文侧边栏
  - `dashboard.py` — 样式对齐原型
  - `project_tree.py` — 融入新侧边栏
  - `spec_check_panel.py` — 移入底部面板
  - `diagnostic_panel.py` — 移入底部面板
  - `change_management_panel.py` — 样式对齐原型
  - `document_editor.py` — 样式对齐原型
  - `st_editor.py` — 样式对齐原型
  - `auto_fix_panel.py` — 移入内容区
  - `excel_export_panel.py` — 移入内容区
  - Builders (`LeftPanelBuilder`, `RightPanelBuilder`, `DockPanelBuilder`, `StyleBuilder`) — 重构或替换
  - 新增 CSS Variables → QSS 映射工具
  - 新增 Tab 管理组件
  - 新增 Activity Bar 组件
  - 新增 Bottom Panel 组件
  - 新增深色主题 QSS (`resources/styles/ide_dark.qss`)

## ADDED Requirements

### Requirement: IDE 五区主布局
系统 SHALL 使用 IDE 风格的主窗口布局，包含五个区域：Title Bar（可选）、Activity Bar、Sidebar、Content Area（含Tab Bar）、Bottom Panel、Status Bar。

#### Scenario: 启动应用默认布局
- **WHEN** 用户启动 PLC项目管理工具
- **THEN** 主窗口以 IDE 布局展示，Activity Bar 选中"仪表盘"，Sidebar 显示仪表盘相关导航，Content Area 显示仪表盘欢迎页，Bottom Panel 显示输出日志，Status Bar 显示"就绪"

### Requirement: Activity Bar 活动导航
系统 SHALL 在窗口左侧提供48px宽的 Activity Bar，包含7个活动图标按钮：仪表盘(📊)、项目管理(📁)、文档管理(📝)、变更管理(🔄)、PLC工具(⚡)、规范中心(✅)、设置(⚙)。设置按钮置于底部。

#### Scenario: 点击活动图标切换视图
- **WHEN** 用户在 Activity Bar 点击"规范中心"图标
- **THEN** Activity Bar 高亮该图标，Sidebar 切换为规范检查器列表，Content Area 切换为规范检查选择页

### Requirement: 上下文感知 Sidebar
系统 SHALL 提供宽度260px的可折叠 Sidebar，根据当前选中的 Activity 动态切换显示内容。Sidebar 包含可折叠的 Section 分组和可选的 Badge 标签。

#### Scenario: 切换到项目管理活动
- **WHEN** 用户点击 Activity Bar 中的"项目管理"图标
- **THEN** Sidebar 显示项目浏览树、项目列表及"新建项目"/"打开项目"操作项

#### Scenario: 折叠/展开 Sidebar
- **WHEN** 用户点击 Sidebar 头部的折叠按钮
- **THEN** Sidebar 收起为0宽度，Content Area 扩展填充空间

### Requirement: Tab 页签系统
系统 SHALL 在 Content Area 顶部提供 Tab Bar，支持多页签同时打开。每个 Tab 显示图标+标题+关闭按钮。仪表盘 Tab 不可关闭。

#### Scenario: 从 Sidebar 点击打开新功能页
- **WHEN** 用户在 Sidebar 点击"语法检查"
- **THEN** Content Area 新增一个"语法检查"Tab 并切换到该页

#### Scenario: 关闭非仪表盘 Tab
- **WHEN** 用户点击某个 Tab 的关闭按钮
- **THEN** 该 Tab 被关闭，自动切换到相邻 Tab

### Requirement: 底部诊断面板
系统 SHALL 在 Content Area 下方提供可收起的底部面板（默认200px），包含"输出"/"问题"/"终端"三个子Tab。规范检查结果和诊断信息统一在此展示。

#### Scenario: 查看规范检查问题
- **WHEN** 用户运行规范检查后点击底部面板的"问题"Tab
- **THEN** 底部面板显示问题列表，包含严重度图标、文件名、行号、规则编号、描述

### Requirement: 深色工业风主题
系统 SHALL 提供深色主题作为默认主题，CSS变量映射到QSS。主要颜色：背景#1E1E1E、面板#2D2D30、侧边栏#1A1A1A、主题色#E86100。

#### Scenario: 深色主题视觉一致性
- **WHEN** 用户查看主窗口任意区域
- **THEN** 所有组件（按钮、输入框、表格、卡片）统一使用深色配色方案

### Requirement: Dashboard 仪表盘页
系统 SHALL 提供仪表盘首页，包含：欢迎标题、4个统计卡片（项目数/文档模板/规范通过率/待处理变更）、快速操作按钮区、最近项目列表。

#### Scenario: 仪表盘数据刷新
- **WHEN** 仪表盘页被激活
- **THEN** 统计卡片显示当前最新数据

### Requirement: 项目详情页
系统 SHALL 提供项目详情视图，左侧为项目文件树（280px），右侧为项目信息表单（编号/类型/名称/版本/路径/描述）+ 保存/刷新按钮。

#### Scenario: 查看项目信息
- **WHEN** 用户从项目树选择某个项目
- **THEN** 右侧详情面板展示该项目的表单信息

### Requirement: 变更管理列表页
系统 SHALL 提供变更单列表视图，包含工具栏（新建/刷新/版本同步/搜索）和变更单表格（编号/标题/项目/状态/日期/操作）。

#### Scenario: 查看变更单列表
- **WHEN** 用户切换到变更管理活动
- **THEN** 显示变更单列表，状态使用彩色标签（草稿/进行中/已审批/已驳回）

### Requirement: 规范检查页
系统 SHALL 提供规范检查选择视图，7个检查器卡片可选择/取消。选中卡片显示绿色边框，未选中显示虚线半透明。底部显示检查结果表格。

#### Scenario: 选择检查器并运行
- **WHEN** 用户勾选3个检查器并点击"开始检查"
- **THEN** 系统运行选中的检查器并在结果表格中展示结果

## MODIFIED Requirements
无现有需求被修改。

## REMOVED Requirements

### Requirement: QDockWidget 诊断面板
**Reason**: 诊断面板和规范检查面板当前作为独立QDockWidget悬浮/停靠，交互体验差，不符合IDE布局。
**Migration**: 诊断面板内容移入底部面板的"问题"/"终端"Tab；规范检查面板内容移入 Content Area 的规范检查Tab和底部面板的"输出"Tab。