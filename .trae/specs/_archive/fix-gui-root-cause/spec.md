# GUI 根因修复 Spec

## Why

CLI 测试已全部通过（565 通过 / 0 失败），但实际运行 GUI 时界面显示存在严重问题：布局拥挤、样式缺失、文字渲染异常。用户截图显示应用虽然能启动，但视觉质量远未达到可用标准。需要彻底分析根因并一次性解决所有 GUI 层面的问题。

**根因诊断结论**: `StyleBuilder.apply()` 中的 QSS 文件路径解析逻辑存在 **路径遍历层数不足** 的关键 bug，导致 686 行的 Material Design QSS 样式表从未被加载，整个应用运行时仅使用约 10 行的 fallback 样式。

## What Changes

- **修复 StyleBuilder 路径解析 bug**（P0 — 根因）: `for _ in range(5)` 应为 `range(6)` 或改用更健壮的资源定位策略，确保 `material_light.qss` / `material_dark.qss` 能被正确加载
- **清理内联样式冲突**（P1）: 大量组件使用 `setStyleSheet()` 硬编码样式，与全局 QSS 产生冲突或覆盖，需统一收敛到 QSS 或确保优先级正确
- **优化 Dashboard 布局密度**（P1）: 当前仪表盘堆叠了标题区+4卡片+6按钮+最近项目+5健康度卡片=18个区块，在默认窗口高度下严重超限
- **修复中央布局初始化顺序**（P2）: `_build_central_widget()` 创建 splitter 但未立即加入 layout，依赖后续 `_build_right_panel()` 补充，可能导致初始布局抖动
- **Dock 面板空间优化**（P2）: 底部两个 Dock（诊断+规范检查）水平堆叠占用过多垂直空间

## Impact

- Affected specs: GUI 启动与导航、项目打开链路、整体视觉质量
- Affected code:
  - `src/ui/builders/style_builder.py` — **核心修复目标**
  - `src/ui/dashboard.py` — 内联样式 + 布局优化
  - `src/ui/main_window.py` — 布局初始化顺序
  - `src/ui/builders/left_panel_builder.py` — 内联样式
  - `src/ui/builders/right_panel_builder.py` — 内联样式
  - `src/ui/widgets/project_tree.py` — 内联样式
  - `resources/styles/material_light.qss` — 可能需要的补充规则

## ADDED Requirements

### Requirement: 修复 QSS 资源加载根因

系统 SHALL 确保 `StyleBuilder.apply()` 在开发环境和打包环境下均能正确定位并加载 `material_{theme}.qss` 样式文件。

#### Scenario: QSS 文件成功加载

- **WHEN** 应用启动调用 `StyleBuilder.apply(window, "light")`
- **THEN** SHALL 从 `resources/styles/material_light.qss` 读取完整 686 行样式内容
- **THEN** SHALL 将样式应用到顶层窗口及其所有子控件
- **THEN** 日志输出 `已加载主题样式: <完整路径>` 而非 `主题文件读取失败`

#### Scenario: 打包环境兼容

- **WHEN** 应用通过 PyInstaller 打包后运行（`sys.frozen == True`）
- **THEN** SHALL 从可执行文件所在目录的相对路径定位资源文件
- **THEN** 不应依赖 `__file__` 回溯路径策略

### Requirement: 消除内联样式与 QSS 冲突

系统 SHALL 减少组件级 `setStyleSheet()` 硬编码样式调用，将通用视觉属性统一收敛到全局 QSS，仅保留必须动态计算的属性（如颜色变量）在内联中。

#### Scenario: 组件样式统一由 QSS 驱动

- **WHEN** 任何 QWidget 子类使用 `setStyleSheet()`
- **THEN** 仅用于无法通过 QSS 选择器表达的动态属性
- **THEN** 静态属性（字体大小、颜色、间距、圆角）全部由 QSS 定义

### Requirement: Dashboard 布局适配窗口高度

系统 SHALL 确保 Dashboard 页面在最小支持窗口高度（800px）下不出现内容截断或过度拥挤。

#### Scenario: 最小窗口下 Dashboard 完整可见

- **WHEN** 窗口高度为 800px（减去菜单栏+工具栏+状态栏+Dock ≈ 650px 可用）
- **THEN** 仪表盘核心内容（统计卡片+快捷操作）完全可见
- **THEN** 最近项目和健康度区域可通过滚动访问而非强制展开

### Requirement: 中央布局初始化完整性

系统 SHALL 在 `_build_central_widget()` 中完成 splitter 到 layout 的挂载，不依赖后续 builder 方法的执行顺序。

#### Scenario: Splitter 初始化即可用

- **WHEN** `_build_central_widget()` 执行完毕
- **THEN** `centralWidget().layout()` 已包含 splitter
- **THEN** 后续 `_build_left_panel()` 和 `_build_right_panel()` 仅负责向 splitter 添加子控件

## MODIFIED Requirements

### Requirement: StyleBuilder 资源定位策略

现有 `StyleBuilder.apply()` 使用固定 5 层回溯策略定位资源目录。**修改为**: 使用可配置的最大回溯层数（如 8 层），并在每次迭代中检查 `resources` 目录是否存在；若找到则立即停止。同时增加打包环境的 `sys.frozen` 分支处理。

## REMOVED Requirements

无。
