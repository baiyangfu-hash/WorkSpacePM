# Tasks

## 迭代总览

按后端支撑度分 4 个迭代，每个迭代结束必须运行 GUI 交互测试：

| 迭代 | 主题 | 后端状态 | 预计模块 |
|------|------|---------|---------|
| 迭代1 | 基础框架 + 项目列表重构 | 后端已有/部分桥接 | navigation, widgets, project_list |
| 迭代2 | 变更管理（最高优先级缺口） | 后端已就绪 | workspace.change_tab, dialogs, change_center |
| 迭代3 | PLC 检查 + 文档 | 后端已就绪 | workspace.check_tab, workspace.doc_tab |
| 迭代4 | 全局功能页 + 后端补全 | 后端需新建 | global_pages, ReportService |

---

## 迭代1：基础框架 + 项目列表重构

- [ ] Task 1.1: 创建 UI 模块目录结构
  - [ ] SubTask 1.1.1: 创建 navigation/, project_list/, workspace/, change_center/, dialogs/, global_pages/, widgets/, models/ 8 个包及 __init__.py
  - [ ] SubTask 1.1.2: 将现有 ui/ 文件迁移到对应模块包（main_window.py 保留在 ui/ 根）
  - [ ] SubTask 1.1.3: 更新所有 import 路径，确保现有测试通过

- [ ] Task 1.2: 删除角色系统
  - [ ] SubTask 1.2.1: 删除 `auto_pm/ui/roles.py`
  - [ ] SubTask 1.2.2: 从 MainWindow 移除 `_role_menu`、`apply_role()`、`_on_role_changed()`
  - [ ] SubTask 1.2.3: 从 ProjectWorkspaceView/GlobalView 移除 `apply_role()` 调用，所有 Tab 默认可见
  - [ ] SubTask 1.2.4: 删除角色相关测试，运行现有测试确认无回归

- [ ] Task 1.3: 开发 NavigationTree 模块
  - [ ] SubTask 1.3.1: 创建 `navigation/nav_model.py` - NavNode 数据类（type: stack/phase/function, label, badge_count, filter_data）
  - [ ] SubTask 1.3.2: 创建 `navigation/nav_tree.py` - QTreeWidget 子类，构建树形结构（PLC总库/Python总库 + 阶段子节点 + 功能节点）
  - [ ] SubTask 1.3.3: 实现项目计数徽标更新（从 ProjectService.list_projects_cached() 聚合）
  - [ ] SubTask 1.3.4: 发射 `project_filter_requested(stack, phase)` 和 `page_switch_requested(page_id)` 信号
  - [ ] SubTask 1.3.5: 编写 nav_tree 单元测试（构建树、点击节点、信号发射）

- [ ] Task 1.4: 后端桥接 - ProjectService 筛选方法
  - [ ] SubTask 1.4.1: `ProjectRepository.list_by_phase(phase)` 新增
  - [ ] SubTask 1.4.2: `ProjectService.list_projects_filtered(stack=None, phase=None, business_line=None)` 新增（下推到 Repository）
  - [ ] SubTask 1.4.3: `ProjectInfo` 增加 `file_mtime: float = 0.0` 字段，扫描时填充
  - [ ] SubTask 1.4.4: 编写 Service 层单元测试

- [ ] Task 1.5: 重构 ProjectListView 分组视图
  - [ ] SubTask 1.5.1: 创建 `project_list/view_controls.py` - 视图切换+排序+分组下拉控件
  - [ ] SubTask 1.5.2: 创建 `project_list/group_header.py` - 可折叠分组标题组件
  - [ ] SubTask 1.5.3: 重构 `project_list/list_view.py` - 支持 4 种分组模式（stack_bl/stack_phase/bl/phase）
  - [ ] SubTask 1.5.4: 创建 `project_list/card_view.py` - 卡片网格视图（按分组渲染）
  - [ ] SubTask 1.5.5: 创建 `project_list/table_view.py` - 列表表格视图（QTableWidget，支持列排序）
  - [ ] SubTask 1.5.6: 实现 set_filter(stack, phase) 方法，响应 NavigationTree 信号

- [x] Task 1.6: 增强 ProjectCard
  - [x] SubTask 1.6.1: 卡片增加变更数、修改时间、描述摘要字段
  - [x] SubTask 1.6.2: 后端 `ProjectService.list_projects_with_change_count()` 新增（JOIN changes 表）
  - [x] SubTask 1.6.3: 卡片数据从 ProjectCardDTO 填充

- [ ] Task 1.7: MainWindow 集成
  - [ ] SubTask 1.7.1: 替换 navList(QListWidget) 为 NavigationTree(QTreeWidget)
  - [ ] SubTask 1.7.2: 连接 NavigationTree 信号到 ProjectListView.set_filter
  - [ ] SubTask 1.7.3: 状态栏增加工作空间路径显示
  - [ ] SubTask 1.7.4: 状态栏"上次扫描"显示实际时间（从 ScanLogRepository.get_latest()）

- [ ] Task 1.8: 迭代1 GUI 交互测试
  - [ ] SubTask 1.8.1: 测试 NavigationTree 节点点击 → ProjectListView 筛选生效
  - [ ] SubTask 1.8.2: 测试分组维度切换 → 分组结构正确
  - [ ] SubTask 1.8.3: 测试卡片/列表视图切换
  - [ ] SubTask 1.8.4: 测试搜索框 + 业务线筛选联动
  - [ ] SubTask 1.8.5: 测试项目卡片点击 → 进入工作区
  - [ ] SubTask 1.8.6: 录制 GUI 操作截图/日志作为交付物

## 迭代2：变更管理（最高优先级缺口）

- [ ] Task 2.1: 后端 - ChangeService 补全
  - [ ] SubTask 2.1.1: `ChangeService.list_all_changes(status=None, domain=None)` 新增（跨项目查询，封装 Repository.list_all）
  - [ ] SubTask 2.1.2: `ChangeService.update_change_request(change_number, **kwargs)` 新增
  - [ ] SubTask 2.1.3: `ChangeService.delete_change_request(change_number)` 新增（删除文件+DB记录）
  - [ ] SubTask 2.1.4: 编写 Service 层单元测试

- [ ] Task 2.2: 开发 CreateChangeDialog
  - [ ] SubTask 2.2.1: 创建 `dialogs/create_change_dialog.py` - 表单（项目/领域/性质/范围/申请人/背景/必要性/紧急度/计划日期）
  - [ ] SubTask 2.2.2: 调用 ChangeService.create_change_request()
  - [ ] SubTask 2.2.3: 发射 `change_created(project_id)` 信号

- [ ] Task 2.3: 开发 TransitionDialog
  - [ ] SubTask 2.3.1: 创建 `dialogs/transition_dialog.py` - 状态流转确认对话框（含备注输入）
  - [ ] SubTask 2.3.2: 调用 ChangeService.transition_status()

- [ ] Task 2.4: 开发 ChangeTab（项目工作区）
  - [ ] SubTask 2.4.1: 创建 `workspace/change_tab.py` - 变更列表 + 筛选 + 创建按钮
  - [ ] SubTask 2.4.2: 调用 ChangeService.list_change_requests(project_id, status, domain)
  - [ ] SubTask 2.4.3: 点击变更单 → 展开详情（背景/必要性/影响）
  - [ ] SubTask 2.4.4: 状态流转按钮 → 弹出 TransitionDialog
  - [ ] SubTask 2.4.5: 替换 ProjectWorkspaceView 的变更占位 Tab

- [ ] Task 2.5: 开发 ChangeCenterView（全局页）
  - [ ] SubTask 2.5.1: 创建 `change_center/change_list_panel.py` - 左侧变更单列表
  - [ ] SubTask 2.5.2: 创建 `change_center/change_detail_panel.py` - 右侧详情面板
  - [ ] SubTask 2.5.3: 创建 `change_center/center_view.py` - 左右分栏容器
  - [ ] SubTask 2.5.4: 状态 Tab 筛选（全部/草稿/待审批/实施中/已完成/已归档）
  - [ ] SubTask 2.5.5: 调用 ChangeService.list_all_changes(status, domain)

- [ ] Task 2.6: MainWindow 集成变更中心
  - [ ] SubTask 2.6.1: QStackedWidget 添加 ChangeCenterView 页面
  - [ ] SubTask 2.6.2: NavigationTree "变更中心"节点点击 → 切换页面
  - [ ] SubTask 2.6.3: 新建按钮下拉增加"变更单"选项

- [ ] Task 2.7: 迭代2 GUI 交互测试
  - [ ] SubTask 2.7.1: 测试 CreateChangeDialog 表单提交 → 变更单生成
  - [ ] SubTask 2.7.2: 测试 ChangeTab 列表加载 + 筛选
  - [ ] SubTask 2.7.3: 测试变更单详情展开
  - [ ] SubTask 2.7.4: 测试状态流转（草稿→待审批→实施中→已完成）
  - [ ] SubTask 2.7.5: 测试 ChangeCenterView 全局列表 + 状态 Tab 筛选
  - [ ] SubTask 2.7.6: 测试变更中心详情面板显示
  - [ ] SubTask 2.7.7: 录制 GUI 操作截图/日志

## 迭代3：PLC 检查 + 文档

- [ ] Task 3.1: 开发 CheckTab
  - [ ] SubTask 3.1.1: 创建 `workspace/check_tab.py` - 执行检查/自动修复/标准化命名按钮
  - [ ] SubTask 3.1.2: 调用 PlcChecker.check_project()，结果按 pass/warn/fail 分组展示
  - [ ] SubTask 3.1.3: 单项"修复"按钮 → 调用 PlcRepairer.repair_project(dry_run=False)
  - [ ] SubTask 3.1.4: "自动修复"按钮 → 调用 PlcRepairer.repair_project(dry_run=True) 预览
  - [ ] SubTask 3.1.5: "标准化命名"按钮 → 调用 PlcRepairer.standardize_docs(apply=False) 预览
  - [ ] SubTask 3.1.6: 替换 ProjectWorkspaceView 的检查占位 Tab

- [ ] Task 3.2: 开发 DocTab
  - [ ] SubTask 3.2.1: 创建 `workspace/doc_tab.py` - 文档列表 + 模板信息
  - [ ] SubTask 3.2.2: 扫描项目目录下的 .md 文件，分类展示（PM_SESSION/立项表/变更单/整改项）
  - [ ] SubTask 3.2.3: "模板更新"按钮 → 调用 TemplateService.update_template()
  - [ ] SubTask 3.2.4: 文件点击 → QDesktopServices.openUrl() 打开
  - [ ] SubTask 3.2.5: 替换 ProjectWorkspaceView 的文档占位 Tab

- [ ] Task 3.3: 迭代3 GUI 交互测试
  - [ ] SubTask 3.3.1: 测试 CheckTab 执行检查 → 结果展示
  - [ ] SubTask 3.3.2: 测试单项修复按钮 → 状态更新
  - [ ] SubTask 3.3.3: 测试自动修复预览
  - [ ] SubTask 3.3.4: 测试标准化命名预览
  - [ ] SubTask 3.3.5: 测试 DocTab 文档列表加载
  - [ ] SubTask 3.3.6: 测试模板更新操作
  - [ ] SubTask 3.3.7: 测试文件点击打开
  - [ ] SubTask 3.3.8: 录制 GUI 操作截图/日志

## 迭代4：全局功能页 + 后端补全

- [ ] Task 4.1: 后端 - ReportService 新增
  - [ ] SubTask 4.1.1: 创建 `auto_pm/core/report_service.py`
  - [ ] SubTask 4.1.2: `get_project_overview()` - 总项目数/按stack/按phase/按bl 统计
  - [ ] SubTask 4.1.3: `get_change_overview()` - 变更单按状态统计
  - [ ] SubTask 4.1.4: 编写单元测试

- [ ] Task 4.2: 开发 ReportPage
  - [ ] SubTask 4.2.1: 创建 `global_pages/report_page.py` - 项目概览/变更统计柱状图
  - [ ] SubTask 4.2.2: 调用 ReportService 获取数据
  - [ ] SubTask 4.2.3: 用 QProgressBar 或自定义 widget 绘制柱状图

- [ ] Task 4.3: 开发 TemplatePage
  - [ ] SubTask 4.3.1: 创建 `global_pages/template_page.py` - 模板列表
  - [ ] SubTask 4.3.2: 调用 TemplateService.list_templates()
  - [ ] SubTask 4.3.3: 显示模板版本/技术栈/使用项目数

- [ ] Task 4.4: 开发 SettingsPage
  - [ ] SubTask 4.4.1: 创建 `global_pages/settings_page.py` - 通用/数据库两个分区
  - [ ] SubTask 4.4.2: 工作空间路径显示（只读）+ 扫描深度配置
  - [ ] SubTask 4.4.3: 数据库统计（项目数/变更数/上次同步）+ 清除缓存/重建索引按钮

- [ ] Task 4.5: 开发 SpecCenterView（基础版）
  - [ ] SubTask 4.5.1: 创建 `global_pages/spec_center.py` - 规范目录列表（PLC 905/904/903/906, Python 210/211/220）
  - [ ] SubTask 4.5.2: 点击规范 → 打开对应 .md 文件

- [ ] Task 4.6: MainWindow 集成全局页
  - [ ] SubTask 4.6.1: QStackedWidget 添加 4 个全局页
  - [ ] SubTask 4.6.2: NavigationTree 功能节点点击 → 切换页面

- [ ] Task 4.7: 迭代4 GUI 交互测试
  - [ ] SubTask 4.7.1: 测试 ReportPage 数据加载 + 柱状图显示
  - [ ] SubTask 4.7.2: 测试 TemplatePage 模板列表
  - [ ] SubTask 4.7.3: 测试 SettingsPage 配置显示
  - [ ] SubTask 4.7.4: 测试 SettingsPage 清除缓存/重建索引
  - [ ] SubTask 4.7.5: 测试 SpecCenterView 规范列表 + 打开文件
  - [ ] SubTask 4.7.6: 录制 GUI 操作截图/日志

## 最终验收测试

- [ ] Task 5.1: 全功能 GUI 端到端测试
  - [ ] SubTask 5.1.1: 启动 GUI，验证所有导航节点可点击
  - [ ] SubTask 5.1.2: 遍历每个页面，验证无崩溃
  - [ ] SubTask 5.1.3: 项目列表 → 工作区 → 变更Tab → 创建变更单 → 状态流转 完整流程
  - [ ] SubTask 5.1.4: 项目工作区 → 检查Tab → 执行检查 → 修复 完整流程
  - [ ] SubTask 5.1.5: 变更中心全局列表 → 详情 → 状态流转 完整流程
  - [ ] SubTask 5.1.6: 录制完整 GUI 操作演示视频/截图集

- [ ] Task 5.2: 回归测试
  - [ ] SubTask 5.2.1: 运行现有 275 个基线测试，确认无回归
  - [ ] SubTask 5.2.2: 运行 Bug 回归测试（Bug-1/2/4/5/6/7）
  - [ ] SubTask 5.2.3: 覆盖率检查（目标 ≥ 80%）

- [ ] Task 5.3: 生成测试报告
  - [ ] SubTask 5.3.1: 汇总所有迭代测试结果
  - [ ] SubTask 5.3.2: 生成 `09_整改项/GUI-V2.0-测试执行报告.md`

# Task Dependencies

- Task 1.1 (模块目录) → 所有后续任务
- Task 1.2 (删除角色) → Task 1.3, 1.5, 1.7
- Task 1.3 (NavigationTree) → Task 1.7 (MainWindow集成)
- Task 1.4 (后端桥接) → Task 1.5, 1.6
- Task 1.5 (ProjectListView) → Task 1.7
- 迭代1 全部 → 迭代2/3/4 可并行
- Task 2.1 (ChangeService补全) → Task 2.4, 2.5
- Task 4.1 (ReportService) → Task 4.2
- Task 5.1 (E2E) → 依赖所有迭代完成
