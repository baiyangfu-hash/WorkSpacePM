# Checklist

## 迭代1：基础框架 + 项目列表重构

### 模块目录结构
- [ ] 8 个模块包及 __init__.py 已创建
- [ ] 现有 ui/ 文件已迁移到对应模块包
- [ ] 所有 import 路径已更新
- [ ] 现有 275 个基线测试无回归

### 角色系统删除
- [ ] `auto_pm/ui/roles.py` 已删除
- [ ] MainWindow 无 `_role_menu`、`apply_role()`、`_on_role_changed()`
- [ ] ProjectWorkspaceView/GlobalView 无 `apply_role()` 调用
- [ ] 所有 Tab 默认可见
- [ ] 角色相关测试已删除，剩余测试通过

### NavigationTree 模块
- [ ] `navigation/nav_model.py` 已创建，NavNode 数据类定义完整
- [ ] `navigation/nav_tree.py` 已创建，继承 QTreeWidget
- [ ] 树形结构包含：PLC总库/Python总库 + 4个阶段子节点 + 6个功能节点
- [ ] 阶段子节点显示项目计数徽标
- [ ] 点击总库节点 → 发射 `project_filter_requested(stack, None)`
- [ ] 点击阶段子节点 → 发射 `project_filter_requested(stack, phase)`
- [ ] 点击功能节点 → 发射 `page_switch_requested(page_id)`
- [ ] nav_tree 单元测试通过

### 后端桥接
- [ ] `ProjectRepository.list_by_phase(phase)` 已实现
- [ ] `ProjectService.list_projects_filtered(stack, phase, business_line)` 已实现
- [ ] `ProjectInfo` 含 `file_mtime` 字段
- [ ] Service 层单元测试通过

### ProjectListView 分组视图
- [ ] `project_list/view_controls.py` 视图切换+排序+分组下拉已实现
- [ ] `project_list/group_header.py` 可折叠分组标题已实现
- [ ] `project_list/list_view.py` 支持 4 种分组模式
- [ ] `project_list/card_view.py` 卡片网格按分组渲染
- [ ] `project_list/table_view.py` 列表表格支持列排序
- [ ] `set_filter(stack, phase)` 方法响应 NavigationTree 信号

### ProjectCard 增强
- [x] 卡片显示变更数
- [x] 卡片显示修改时间
- [x] 卡片显示描述摘要
- [x] `ProjectService.list_projects_with_change_count()` 已实现

### MainWindow 集成
- [ ] navList 已替换为 NavigationTree
- [ ] NavigationTree 信号连接到 ProjectListView.set_filter
- [ ] 状态栏显示工作空间路径
- [ ] 状态栏"上次扫描"显示实际时间

### 迭代1 GUI 交互测试
- [ ] 测试：点击 PLC总库节点 → 列表只显示 PLC 项目
- [ ] 测试：点击 PLC总库>调试中 → 列表只显示 PLC 调试中项目
- [ ] 测试：切换分组维度为"总库+阶段" → 分组结构正确
- [ ] 测试：切换卡片/列表视图 → 显示模式正确
- [ ] 测试：搜索框输入 → 实时过滤
- [ ] 测试：业务线下拉筛选 → 联动生效
- [ ] 测试：点击项目卡片 → 进入工作区
- [ ] GUI 操作截图/日志已录制

## 迭代2：变更管理

### 后端 ChangeService 补全
- [ ] `list_all_changes(status, domain)` 已实现（跨项目查询）
- [ ] `update_change_request(change_number, **kwargs)` 已实现
- [ ] `delete_change_request(change_number)` 已实现（文件+DB）
- [ ] Service 层单元测试通过

### CreateChangeDialog
- [ ] `dialogs/create_change_dialog.py` 已创建
- [ ] 表单字段完整（项目/领域/性质/范围/申请人/背景/必要性/紧急度/计划日期）
- [ ] 调用 ChangeService.create_change_request()
- [ ] 发射 `change_created(project_id)` 信号

### TransitionDialog
- [ ] `dialogs/transition_dialog.py` 已创建
- [ ] 含备注输入框
- [ ] 调用 ChangeService.transition_status()

### ChangeTab（项目工作区）
- [ ] `workspace/change_tab.py` 已创建
- [ ] 变更列表加载（调用 list_change_requests）
- [ ] 状态/领域筛选下拉
- [ ] "创建变更单"按钮 → 弹出 CreateChangeDialog
- [ ] 点击变更单 → 展开详情
- [ ] 状态流转按钮 → 弹出 TransitionDialog
- [ ] 替换 ProjectWorkspaceView 变更占位 Tab

### ChangeCenterView（全局页）
- [ ] `change_center/change_list_panel.py` 已创建
- [ ] `change_center/change_detail_panel.py` 已创建
- [ ] `change_center/center_view.py` 左右分栏已创建
- [ ] 状态 Tab 筛选（6个状态）
- [ ] 调用 list_all_changes(status, domain)
- [ ] 点击变更单 → 右侧详情面板显示
- [ ] 详情面板含状态流转按钮

### MainWindow 集成
- [ ] QStackedWidget 添加 ChangeCenterView
- [ ] NavigationTree "变更中心"节点 → 切换页面
- [ ] 新建按钮下拉含"变更单"选项

### 迭代2 GUI 交互测试
- [ ] 测试：CreateChangeDialog 填写表单 → 提交 → 变更单生成
- [ ] 测试：ChangeTab 列表加载正确
- [ ] 测试：状态筛选 → 列表过滤
- [ ] 测试：领域筛选 → 列表过滤
- [ ] 测试：点击变更单 → 详情展开
- [ ] 测试：状态流转 草稿→待审批
- [ ] 测试：状态流转 待审批→实施中
- [ ] 测试：状态流转 实施中→已完成
- [ ] 测试：ChangeCenterView 全局列表加载
- [ ] 测试：状态 Tab 切换 → 列表过滤
- [ ] 测试：点击变更单 → 详情面板显示
- [ ] 测试：详情面板状态流转
- [ ] GUI 操作截图/日志已录制

## 迭代3：PLC 检查 + 文档

### CheckTab
- [ ] `workspace/check_tab.py` 已创建
- [ ] "执行检查"按钮 → 调用 PlcChecker.check_project()
- [ ] 结果按 pass/warn/fail 分组展示
- [ ] 单项"修复"按钮 → 调用 PlcRepairer.repair_project()
- [ ] "自动修复"按钮 → dry_run 预览
- [ ] "标准化命名"按钮 → standardize_docs(apply=False) 预览
- [ ] 替换 ProjectWorkspaceView 检查占位 Tab

### DocTab
- [ ] `workspace/doc_tab.py` 已创建
- [ ] 扫描项目目录 .md 文件并分类展示
- [ ] "模板更新"按钮 → TemplateService.update_template()
- [ ] 文件点击 → QDesktopServices.openUrl() 打开
- [ ] 替换 ProjectWorkspaceView 文档占位 Tab

### 迭代3 GUI 交互测试
- [ ] 测试：CheckTab 执行检查 → 结果显示 pass/warn/fail
- [ ] 测试：点击单项"修复" → 该项状态更新
- [ ] 测试：自动修复预览 → 显示待修复项
- [ ] 测试：标准化命名预览 → 显示重命名计划
- [ ] 测试：DocTab 文档列表加载
- [ ] 测试：点击文档 → 文件打开
- [ ] 测试：模板更新按钮 → 执行更新
- [ ] GUI 操作截图/日志已录制

## 迭代4：全局功能页 + 后端补全

### ReportService
- [ ] `auto_pm/core/report_service.py` 已创建
- [ ] `get_project_overview()` 返回总项目数/stack/phase/bl 统计
- [ ] `get_change_overview()` 返回变更按状态统计
- [ ] 单元测试通过

### ReportPage
- [ ] `global_pages/report_page.py` 已创建
- [ ] 项目概览柱状图（按 stack/phase/bl）
- [ ] 变更统计柱状图（按状态）
- [ ] 调用 ReportService 获取数据

### TemplatePage
- [ ] `global_pages/template_page.py` 已创建
- [ ] 模板列表显示（名称/版本/技术栈/使用项目数）
- [ ] 调用 TemplateService.list_templates()

### SettingsPage
- [ ] `global_pages/settings_page.py` 已创建
- [ ] 通用设置（工作空间路径/扫描深度）
- [ ] 数据库统计（项目数/变更数/上次同步）
- [ ] "清除缓存"按钮 → 删除 DB 文件
- [ ] "重建索引"按钮 → 调用 sync_to_cache(force_full=True)

### SpecCenterView
- [ ] `global_pages/spec_center.py` 已创建
- [ ] 规范目录列表（PLC 905/904/903/906, Python 210/211/220）
- [ ] 点击规范 → 打开 .md 文件

### MainWindow 集成
- [ ] QStackedWidget 添加 4 个全局页
- [ ] NavigationTree 功能节点 → 切换页面

### 迭代4 GUI 交互测试
- [ ] 测试：ReportPage 数据加载 → 柱状图显示
- [ ] 测试：ReportPage 数据正确性（与 DB 一致）
- [ ] 测试：TemplatePage 模板列表显示
- [ ] 测试：SettingsPage 工作空间路径显示
- [ ] 测试：SettingsPage 数据库统计显示
- [ ] 测试：SettingsPage 清除缓存 → DB 清空
- [ ] 测试：SettingsPage 重建索引 → 数据恢复
- [ ] 测试：SpecCenterView 规范列表显示
- [ ] 测试：点击规范 → 文件打开
- [ ] GUI 操作截图/日志已录制

## 最终验收测试

### 全功能 GUI 端到端测试
- [ ] GUI 启动无崩溃
- [ ] 所有 NavigationTree 节点可点击
- [ ] 遍历每个页面无崩溃
- [ ] 完整流程：项目列表 → 工作区 → 变更Tab → 创建变更单 → 状态流转
- [ ] 完整流程：项目工作区 → 检查Tab → 执行检查 → 修复
- [ ] 完整流程：变更中心 → 全局列表 → 详情 → 状态流转
- [ ] 完整流程：报告中心 → 查看统计
- [ ] 完整流程：系统设置 → 清除缓存 → 重建索引
- [ ] 完整 GUI 操作演示已录制

### 回归测试
- [ ] 现有 275 个基线测试全部通过
- [ ] Bug-1 路径前缀匹配回归通过
- [ ] Bug-2 变更单同步路径回归通过
- [ ] Bug-4 retrofit _src_path 回归通过
- [ ] Bug-5 扫描深度统一为 4 回归通过
- [ ] Bug-6 phase 枚举校验回归通过
- [ ] Bug-7 _read_copier_answers 异常处理回归通过
- [ ] 覆盖率 ≥ 80%

### 测试报告
- [ ] 所有迭代测试结果已汇总
- [ ] `09_整改项/GUI-V2.0-测试执行报告.md` 已生成
- [ ] 报告含每个功能的交互测试截图/日志
- [ ] 报告含缺陷清单（如有）
- [ ] 报告含需求完成度核对表

## 验收标准

- [ ] 所有 P0 功能（导航/列表/变更/检查）GUI 交互测试通过
- [ ] 所有 P1 功能（文档/模板/报告/设置）GUI 交互测试通过
- [ ] 无阻断性 Bug
- [ ] 覆盖率 ≥ 80%
- [ ] 现有测试无回归
- [ ] GUI 操作演示已录制（用户可查看每个功能操作）
