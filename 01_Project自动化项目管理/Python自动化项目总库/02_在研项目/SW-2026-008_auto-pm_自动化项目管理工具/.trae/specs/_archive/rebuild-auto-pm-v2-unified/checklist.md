# Checklist — auto-pm V2.0 验收检查点

> 聚焦 V2.0（PySide6 UI 基座 + 项目中心 + 项目CRUD对齐004）的验收。
> V2.1~V2.5 验收检查点待对应版本任务细化后补充。

> **V2.0.1 状态同步（2026-06-22）**：
> - V2.0 阶段 A~F 已全部交付（GUI-V2.0-测试执行报告.md 已确认）
> - V2.0.1-A（site 编码修复）+ V2.0.1-C（042/016 规范对齐 19 项冲突修复）已完成
> - 测试覆盖：688 passed，覆盖率 81%
> - 下方检查点中 `[ ]` 标记为 V2.0 设计时检查点，实际已通过 V2.0.1 测试报告验证（详见 `09_整改项/GUI-V2.0-测试执行报告.md`）
> - 待办项：mypy strict + ruff 检查通过（阶段 F 最后一项）

## 文档先行（阶段 A）

- [ ] PRD V2.0 已重写，包含多角色用户模型、PySide6 技术栈决策、项目中心式导航说明
- [ ] PRD V2.0 已删除 Non-Goals 中排除 SW-2026-001/006 的条目，路线图更新为 V2.0~V2.5
- [ ] PRD V2.0 已新增总库管理需求（导入/分类/搜索/多业务线 SW/DJ/ZD/XT/WX）
- [ ] DES V2.0 已重写，包含 PySide6 架构、模块划分、数据流、导航状态机
- [ ] INT V2.0 已更新，包含 CLI 命令清单与 Service 接口定义

## PySide6 主框架（阶段 B）

- [ ] `auto_pm/ui/` 包结构已创建（main_window/widgets/views/models）
- [ ] QMainWindow 主窗口可启动，显示侧边栏导航 + 主区域 + 顶部工具栏 + 底部状态栏
- [ ] 侧边栏包含项目列表/规范中心/模板管理/报告中心/系统设置导航项（V2.0 仅项目列表可用，其余占位）
- [ ] QStackedWidget 可切换主区域（项目列表页 / 项目工作区 / 全局功能页）

## 项目列表首页（阶段 B，对齐004总库管理）

- [ ] 项目卡片网格正确渲染（项目ID/名称/技术栈徽标/版本/阶段/变更数/业务线）
- [ ] 统计栏显示项目总数/各阶段分布/各技术栈分布/各业务线分布
- [ ] 搜索框支持按项目编号/名称模糊搜索
- [ ] 筛选器支持技术栈 + 阶段 + 业务线（SW/DJ/ZD/XT/WX）组合筛选
- [ ] 空状态/加载中/错误状态界面均可用

## 项目工作区与概览（阶段 C）

- [ ] 点击项目卡片可进入项目工作区，显示 Tab 导航
- [ ] V2.0 激活「概览」Tab，其余 Tab（变更/规范/变量表/文档/检查）占位显示「V2.x 交付」
- [ ] 项目工作区头部显示项目ID+名称+路径+技术栈+阶段徽标+编辑/删除按钮
- [ ] 概览 Tab 显示项目元数据信息网格（来自 .copier-answers.yml）
- [ ] 概览 Tab 显示立项表六块信息（业务身份/技术环境/工程规模/工程状态/变更台账/资源风险，来自 *_PROJ-*.md）
- [ ] 概览 Tab 显示变更概览计数 + 最近活动列表

## 项目 CRUD 对齐004（阶段 D）

- [ ] 新建项目对话框字段完整（编号/名称/技术栈/模板/描述/作者/业务线）
- [ ] 模板选择与技术栈联动正确（PLC→plc-standard/plc-syslib-fb；Python→python-tool）
- [ ] 新建项目路径预览正确（02_在研项目/{id}_{name}/）
- [ ] 新建项目 dry-run 预览模式可用
- [ ] 新建项目调用 Copier 生成骨架 + 写入 .copier-answers.yml + PM_SESSION + sync DB
- [ ] 编辑项目元数据可写回 .copier-answers.yml + 同步 DB
- [ ] 删除项目带二次确认（红色警告 + 输入项目编号确认）
- [ ] 项目导入功能可用（选择目录 → 检测/补全 .copier-answers.yml → 入库 + 业务线分类）
- [ ] CLI `auto-pm project import <path>` 可用
- [ ] CLI `auto-pm project list --business-line` 业务线筛选可用
- [ ] CLI `auto-pm gui` 启动 PySide6 主窗口

## 数据层与旧代码清理（阶段 E）

- [ ] SQLite ProjectRepository 含 business_line 字段
- [ ] SyncService 增量同步适配新字段
- [ ] GUI 优先读 DB 缓存，缺失时回退文件系统扫描
- [ ] `auto_pm/gui/static/`（index.html/app.js/style.css）已删除
- [ ] `auto_pm/gui/app.py`、`auto_pm/gui/api.py`（pywebview 桥接）已删除
- [ ] Pydantic Project 模型含 business_line 字段（Literal["SW","DJ","ZD","XT","WX"]）
- [ ] DTO 模型适配 PySide6 视图层（ProjectCardDTO/ProjectDetailDTO）

## 测试（阶段 F）

- [x] 项目CRUD单元测试通过（import/classify/search 新方法）
- [x] PySide6 GUI 冒烟测试通过（主窗口启动/列表渲染/进入工作区/新建项目流程）
- [x] 业务线分类与筛选测试通过
- [x] CLI 回归测试通过（project/plc/change 命令不破坏）
- [ ] mypy strict + ruff 检查通过
- [x] 测试覆盖率 ≥ V2.0 目标值（71%，275 测试通过）

## 文档同步（阶段 F，开发结束后）

- [x] PRD V2.0 已同步实际实现偏差
- [x] DES V2.0 已同步实际模块结构
- [x] INT V2.0 已同步实际 CLI/Service 接口
- [x] README 已更新（PySide6 启动方式、依赖变更 PySide6 替换 pywebview）

## 虚拟环境与规范合规

- [x] 所有 Python 命令在 `.venv` 激活后运行（工作空间 venv 路径：c:\Users\fubai\Desktop\My_Workspace\.venv\）
- [ ] 代码遵循 210 Python 编程规范（命名/风格/架构）
- [ ] 代码遵循 211 代码审查规范
- [ ] 代码遵循 220 项目打包规范（pyproject.toml 依赖锁定）
- [ ] Git 提交信息遵循 git-commit-message 规范
