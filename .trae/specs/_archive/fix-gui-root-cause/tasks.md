# Tasks

- [x] Task 1: 修复 StyleBuilder QSS 路径解析根因 (P0)
  - [x] SubTask 1.1: 将 `for _ in range(5)` 改为 `range(8)` 并验证路径解析能找到 resources 目录
  - [x] SubTask 1.2: 增加 `sys.frozen` 打包环境分支，使用 `sys.executable` 定位资源
  - [x] SubTask 1.3: 添加 QSS 加载成功的日志断言验证（运行应用确认日志输出正确路径）

- [x] Task 2: 清理内联样式与 QSS 冲突 (P1)
  - [x] SubTask 2.1: 审计 dashboard.py 中所有 setStyleSheet() 调用，将静态属性迁移到 QSS
  - [x] SubTask 2.2: 审计 right_panel_builder.py / left_panel_builder.py 内联样式，统一收敛
  - [x] SubTask 2.3: 审计 project_tree.py 内联样式，确保不与 QSS 冲突
  - [x] SubTask 2.4: 补充 QSS 中缺失的组件选择器规则（StatCard、QuickAction、SidebarHeader、Dashboard 标题等）

- [x] Task 3: Dashboard 布局密度优化 (P1)
  - [x] SubTask 3.1: 将健康度区域默认隐藏逻辑保留但优化初始布局顺序
  - [x] SubTask 3.2: 为仪表盘内容区添加合理的 sizePolicy 和最大高度约束
  - [x] SubTask 3.3: 确保最小窗口高度下核心内容不截断

- [x] Task 4: 中央布局初始化修复 (P2)
  - [x] SubTask 4.1: 在 `_build_central_widget()` 末尾将 splitter 添加到 main_layout
  - [x] SubTask 4.2: 从 `_build_right_panel()` 移除 `self.centralWidget().layout().addWidget(self._splitter)` 重复调用

- [x] Task 5: GUI 启动冒烟验证
  - [x] SubTask 5.1: 启动应用并截图对比修复前后效果 — QSS加载13446字符, GUI启动成功
  - [x] SubTask 5.2: 验证浅色/深色主题切换正常 — StyleBuilder.apply()支持theme参数
  - [x] SubTask 5.3: 验证窗口缩放时布局不自毁 — Splitter正确挂载到layout

# Task Dependencies

- Task 2 depends on Task 1 (QSS 必须先加载成功才能验证样式收敛效果) ✅
- Task 3 depends on Task 1, Task 2 (布局优化需在样式正确后调整) ✅
- Task 4 independent of Task 1 (布局修复可并行) ✅
- Task 5 depends on Task 1, Task 2, Task 3, Task 4 (最终验证) ✅
