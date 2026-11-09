# Tasks: IDE布局 UI 重设计

- [x] Task 1: 创建深色主题 QSS 样式表
  - [x] 1.1 将HTML原型的CSS Variables映射为QSS变量/属性
  - [x] 1.2 创建 `resources/styles/ide_dark.qss` 深色主题文件，覆盖全局(QMainWindow/QWidget/QPushButton/QLabel/QTabWidget/QTableWidget/QTreeWidget/QScrollBar等)
  - [x] 1.3 定义组件级样式类（ActivityBar/Sidebar/TabBar/BottomPanel/StatusBar/StatCard/CheckerCard/QuickActionBtn等）
  - [x] 1.4 在StyleBuilder中注册新主题入口，切换当前默认主题为 `ide_dark`

- [x] Task 2: 实现 Activity Bar 组件
  - [x] 2.1 创建 `src/ui/widgets/activity_bar.py`，实现48px宽垂直图标栏（QWidget+垂直QBoxLayout）
  - [x] 2.2 使用QPushButton实现7个活动图标按钮+1个设置按钮（置于底部，使用addStretch分隔）
  - [x] 2.3 实现选中态样式：左侧2px橙色指示条+图标高亮
  - [x] 2.4 暴露 `activity_changed(str)` 信号，传参为活动ID（dashboard/project/document/change/plc-tools/spec/settings）

- [x] Task 3: 重写 Sidebar 为上下文感知组件
  - [x] 3.1 创建 `src/ui/widgets/context_sidebar.py`，实现260px宽可折叠侧边栏
  - [x] 3.2 实现 `set_activity(activity_id)` 方法，根据活动ID动态切换内容模板
  - [x] 3.3 实现7套Sidebar内容模板（与HTML原型一致）
  - [x] 3.4 保留 Section 可折叠逻辑，Badge 标签样式对齐原型
  - [x] 3.5 实现 sidebar 折叠/展开动画（宽度过渡）
  - [x] 3.6 暴露 `navigate_requested(tab_id, context)` 信号

- [x] Task 4: 实现 Tab 页签系统
  - [x] 4.1 创建 `src/ui/widgets/tab_system.py`，实现 TabBar + StackedWidget 组合
  - [x] 4.2 支持动态添加/移除/切换 Tab
  - [x] 4.3 每个 Tab 显示图标+标题+关闭按钮，仪表盘 Tab 不可关闭
  - [x] 4.4 Tab 选中态：底部2px橙色下划线样式
  - [x] 4.5 暴露 `tab_changed(tab_id)` / `tab_closed(tab_id)` 信号

- [x] Task 5: 实现底部面板组件
  - [x] 5.1 创建 `src/ui/widgets/bottom_panel.py`，实现可收起/展开的底部面板（默认200px）
  - [x] 5.2 包含三个子Tab：输出（日志流）、问题（诊断列表）、终端（命令行模拟）
  - [x] 5.3 实现面板头部：标题 + 子Tab切换 + 关闭按钮
  - [x] 5.4 输出Tab使用QPlainTextEdit + 颜色标记（info/success/warning/error）
  - [x] 5.5 问题Tab使用QTableWidget展示诊断问题
  - [x] 5.6 终端Tab使用QPlainTextEdit模拟终端输出
  - [x] 5.7 迁移现有 `diagnostic_panel` 数据到问题Tab，迁移日志到输出Tab

- [x] Task 6: 重写 MainWindow 为 IDE 五区布局
  - [x] 6.1 重构 `main_window.py`，替换QSplitter布局为IDE布局（HBox: ActivityBar + Sidebar + ContentPanel， VBox: [TabSystem + BottomPanel]）
  - [x] 6.2 连接 ActivityBar ↔ Sidebar ↔ TabSystem 的三联动导航信号
  - [x] 6.3 集成 Status Bar（复用现有QStatusBar，增强显示内容）
  - [x] 6.4 移除现有的 QDockWidget 逻辑（spec_check_dock, diagnostic_dock）
  - [x] 6.5 保留现有 Controller/EventBus 连接逻辑

- [x] Task 7: 重构 Dashboard 页样式
  - [x] 7.1 重写 `dashboard.py` UI 部分对齐原型样式：深色卡片、网格布局（4列统计+2列面板）
  - [x] 7.2 实现快速操作按钮区（6个按钮，grid布局）
  - [x] 7.3 实现最近项目列表样式
  - [x] 7.4 保留现有 `action_triggered` / `refresh_statistics` / `refresh_recent_projects` 接口不变

- [x] Task 8: 重构项目详情/文档编辑/变更管理面板样式
  - [x] 8.1 重写 `project_tree.py` 融入项目详情视图（左侧树+右侧表单布局）
  - [x] 8.2 重写 `document_editor.py` 样式对齐原型（工具栏+编辑区+变量侧栏）
  - [x] 8.3 重写 `change_management_panel.py` 样式对齐原型（工具栏+表格+状态标签）
  - [x] 8.4 重写 `spec_check_panel.py` 为检查器选择卡片+结果表格布局
  - [x] 8.5 整合 `auto_fix_panel.py` 和 `excel_export_panel.py` 为 Tab 页

- [x] Task 9: 迁移 Navigation 与 Controller 适配
  - [x] 9.1 更新 `NavigationController` 适配新的 Tab 系统（替代旧的 `navigate_to_tab`）
  - [x] 9.2 更新 `_on_action` / EventBus 回调适配新布局
  - [x] 9.3 确保所有现有功能入口（新建项目、打开项目、规范检查、版本同步等）在新布局中正常工作

- [ ] Task 10: 集成测试与验证
  - [ ] 10.1 运行 `python main.py` 验证应用启动无异常
  - [ ] 10.2 验证7个 Activity 切换及 Sidebar 联动正常
  - [ ] 10.3 验证 Tab 打开/关闭/切换正常
  - [ ] 10.4 验证底部面板输出/问题/终端 Tab 切换正常
  - [ ] 10.5 验证深色主题视觉一致性
  - [ ] 10.6 运行现有单元测试 `python -m pytest tests/ -v` 确保无回归

# Task Dependencies
- Task 2 依赖 Task 1（Activity Bar 需要 QSS 样式）
- Task 3 依赖 Task 1（Sidebar 需要 QSS 样式）
- Task 4 依赖 Task 1（Tab System 需要 QSS 样式）
- Task 5 依赖 Task 1（Bottom Panel 需要 QSS 样式）
- Task 6 依赖 Task 2, 3, 4, 5（MainWindow 需要所有子组件就绪）
- Task 7 依赖 Task 6（Dashboard 嵌入新 MainWindow）
- Task 8 依赖 Task 6（面板嵌入新 MainWindow/Content Area）
- Task 9 依赖 Task 6, 8（Controller 适配新布局）
- Task 10 依赖 Task 1-9（最终集成验证）
- Tasks 1, 2, 3, 4, 5 可并行开发（独立组件）
- Tasks 7, 8 可并行开发（独立面板页面）