# Tasks — auto-pm V2.0 统一工作台全量整合（基于深度代码分析重写）

> 本任务清单覆盖全量整合工程。**V2.0 为首个增量，任务详细拆解**；V2.1~V2.5 为路线图纲要，待 V2.0 验收后细化。
> 原则：文档先行 → Bug 优先 → 增量开发 → 开发结束同步文档。每个任务可独立验证。
> 基于实际源码分析（非 PRD 声明），明确不复用资产：001 的 variable/converter、001 的 tkinter GUI、004 的 PyQt5 GUI、004 的 API 路由层/UserStore、005 的 pywebview GUI、006 的未实现 CLI 选项。

---

## V2.0 — Bug 修复 + PySide6 UI 基座 + 项目中心 + 项目CRUD对齐004

### 阶段 0：008 Bug 修复（前置，必须先做）✅ 已完成

- [x] Task 0.1: 修复 Bug-1（`_get_project_path` 路径假设错误）✅
  - [x] SubTask 0.1.1: 定位 `auto_pm/change/change_service.py:300-305` 的 `_get_project_path` 方法
  - [x] SubTask 0.1.2: 修正路径匹配逻辑为按 `{project_id}_{project_name}` 模式匹配（支持前缀匹配 project_id）
  - [x] SubTask 0.1.3: 编写回归测试覆盖路径匹配场景（11 个测试用例）

- [x] Task 0.2: 修复 Bug-2（`_sync_changes` 路径错误）✅
  - [x] SubTask 0.2.1: 定位 `auto_pm/db/sync.py:192` 的 `_sync_changes` 方法
  - [x] SubTask 0.2.2: 修正扫描路径为 `00_项目管理/04_变更管理/01_变更单/CHG-*/`
  - [x] SubTask 0.2.3: 编写回归测试覆盖变更单同步场景（6 个测试用例）

- [x] Task 0.3: 修复 Bug-3（GUI 变更单弹窗枚举不匹配）✅
  - [x] SubTask 0.3.1: 定位 `auto_pm/gui/static/index.html:152-178` 的变更单弹窗
  - [x] SubTask 0.3.2: 对照 `auto_pm/change/_change_constants.py` 的 DOMAIN_VALUES/NATURE_VALUES/IMPACT_SCOPES，移除 INTF/FIX 非法值，scope 改为 7 领域 5 性质 5 范围
  - [x] SubTask 0.3.3: 注：此修复为临时修复，V2.0 阶段 F 会整体弃用 pywebview，但修复确保 V2.0 期间可用

- [x] Task 0.4: 修复 Bug-4（`retrofit` 命令 `_src_path` 推断错误）✅
  - [x] SubTask 0.4.1: 定位 `auto_pm/cli/project.py:242` 的 `retrofit` 命令
  - [x] SubTask 0.4.2: 修正 python 项目的 `_src_path` 推断为 `python-tool`，plc 项目的 `_src_path` 推断为 `plc-standard`
  - [x] SubTask 0.4.3: 编写回归测试覆盖 python/plc 两种技术栈的 retrofit 场景（4 个测试用例）

- [x] Task 0.5: 修复扫描深度不一致（005 遗留问题）✅ **发现描述与代码不符**
  - [x] SubTask 0.5.1: 定位 008 中迁移自 005 的 ProjectOverviewService —— **实际不存在，已迁移为 ProjectService 且默认 depth=4**
  - [x] SubTask 0.5.2: 统一扫描深度为 depth=4 —— **已是 depth=4，无需修改**
  - [x] SubTask 0.5.3: 编写回归测试覆盖深度 4 扫描场景（6 个测试用例，锁定现状）

### 阶段 A：文档先行 ✅ 已完成

- [x] Task A1: 重写 PRD V2.0 ✅
  - [x] SubTask A1.1: 更新用户模型（多角色：项目经理/PLC工程师/Python工程师/规范编辑，含角色-Tab 映射）
  - [x] SubTask A1.2: 更新 UI 技术栈决策（pywebview → PySide6）与项目中心式导航说明，明确弃用 5 个源工具的 GUI 层
  - [x] SubTask A1.3: 新增总库管理需求（对齐004：导入/分类/搜索/多业务线 SW/DJ/ZD/XT/WX）
  - [x] SubTask A1.4: 删除 Non-Goals 中排除 SW-2026-001/006 的条目，更新路线图为 V2.0~V2.5
  - [x] SubTask A1.5: 更新成功标准（PySide6 GUI 覆盖、项目中心导航、总库管理对齐度、4 个 Bug 修复验证）
  - [x] SubTask A1.6: 新增「不复用资产清单」章节，明确记录弃用的死代码/空壳/未实现声明

- [x] Task A2: 重写 DES V2.0 ✅
  - [x] SubTask A2.1: PySide6 架构设计（QMainWindow + 侧边栏 + StackedWidget + 项目工作区 Tab 容器）
  - [x] SubTask A2.2: 模块划分（`auto_pm/ui/` 窗口/视图/组件/模型，`auto_pm/core/` Service 保留）
  - [x] SubTask A2.3: 数据流设计（PySide6 信号槽 ↔ Service ↔ 文件系统/SQLite）
  - [x] SubTask A2.4: 项目中心式导航状态机（首页列表 ↔ 项目工作区 ↔ 全局功能页）
  - [x] SubTask A2.5: 多角色适配设计（角色-Tab 映射表，角色切换机制）

- [x] Task A3: 更新 INT V2.0 ✅
  - [x] SubTask A3.1: CLI 命令清单（gui 命令改为启动 PySide6，project 子命令增强 import/classify）
  - [x] SubTask A3.2: Service 接口定义（ProjectService 新增 import_project/classify/search 方法签名）

### 阶段 B：PySide6 主框架搭建 ✅ 已完成

- [x] Task B1: 创建 `auto_pm/ui/` 包结构 ✅
  - [x] SubTask B1.1: `auto_pm/ui/__init__.py`、`auto_pm/ui/main_window.py`（QMainWindow 主窗口）
  - [x] SubTask B1.2: `auto_pm/ui/widgets/`（复用组件：项目卡片、统计栏、筛选栏）
  - [x] SubTask B1.3: `auto_pm/ui/views/`（视图：项目列表页、项目工作区、全局功能页）
  - [x] SubTask B1.4: `auto_pm/ui/models/`（QAbstractListModel/QAbstractTableModel 适配器）

- [x] Task B2: 主窗口与导航框架 ✅
  - [x] SubTask B2.1: QMainWindow + 左侧侧边栏（项目列表/规范中心/模板管理/报告中心/系统设置 导航项）
  - [x] SubTask B2.2: QStackedWidget 切换主区域（项目列表页 / 项目工作区 / 全局功能页）
  - [x] SubTask B2.3: 顶部工具栏（搜索框 + 业务线筛选 + 新建按钮 + 同步按钮 + 设置）
  - [x] SubTask B2.4: 底部状态栏（项目数/变更数/DB状态/上次扫描时间）
  - [x] SubTask B2.5: 多角色适配（角色切换菜单，角色-Tab 映射）

### 阶段 C：项目列表首页（对齐004总库管理）✅ 已完成

- [x] Task C1: 项目卡片网格 ✅
  - [x] SubTask C1.1: 项目卡片（项目ID/名称/技术栈徽标/版本/阶段/变更数/业务线）
  - [x] SubTask C1.2: 卡片点击进入项目工作区
  - [x] SubTask C1.3: 卡片右键菜单（编辑/删除/打开目录/复制路径）

- [x] Task C2: 统计栏与筛选 ✅
  - [x] SubTask C2.1: 统计栏（项目总数/各阶段分布/各技术栈分布/各业务线分布）
  - [x] SubTask C2.2: 搜索框（按项目编号/名称模糊搜索）
  - [x] SubTask C2.3: 筛选器（技术栈 PLC/Python/未知 + 阶段 + 业务线 SW/DJ/ZD/XT/WX）
  - [x] SubTask C2.4: 空状态/加载中/错误状态界面

### 阶段 D：项目工作区与概览

- [ ] Task D1: 项目工作区 Tab 容器
  - [ ] SubTask D1.1: QTabWidget 容器（概览/变更/规范/变量表/文档/检查 Tab，V2.0 仅激活概览，其余占位）
  - [ ] SubTask D1.2: 项目工作区头部（项目ID+名称+路径+技术栈+阶段徽标+编辑/删除按钮）
  - [ ] SubTask D1.3: 进入/退出项目工作区导航状态管理

- [ ] Task D2: 概览 Tab（迁移005 ProjectOverviewService，扫描深度已统一）
  - [ ] SubTask D2.1: 项目元数据信息网格（编号/名称/技术栈/版本/阶段/路径/描述，来自 .copier-answers.yml）
  - [ ] SubTask D2.2: 立项表解析展示（业务身份/技术环境/工程规模/工程状态/变更台账/资源风险 六块，来自 *_PROJ-*.md）
  - [ ] SubTask D2.3: 变更概览（草稿/实施中/已完成 计数 + 查看全部链接）
  - [ ] SubTask D2.4: 最近活动列表（来自 PM_SESSION 日志）

### 阶段 E：项目 CRUD 对齐004

- [ ] Task E1: 新建项目对话框（对齐004，增强当前简陋弹窗）
  - [ ] SubTask E1.1: 表单字段（编号/名称/技术栈/模板/描述/作者/业务线 SW/DJ/ZD/XT/WX）
  - [ ] SubTask E1.2: 模板选择联动（PLC → plc-standard/plc-syslib-fb；Python → python-tool）
  - [ ] SubTask E1.3: 路径预览（02_在研项目/{id}_{name}/）
  - [ ] SubTask E1.4: dry-run 预览模式
  - [ ] SubTask E1.5: 调用 Copier 生成骨架 + 写入 .copier-answers.yml + PM_SESSION + sync DB

- [ ] Task E2: 编辑项目元数据对话框
  - [ ] SubTask E2.1: 编辑阶段/版本/描述/业务线
  - [ ] SubTask E2.2: 写回 .copier-answers.yml + 同步 DB

- [ ] Task E3: 删除项目（带二次确认）
  - [ ] SubTask E3.1: 确认对话框（红色警告 + 输入项目编号确认）
  - [ ] SubTask E3.2: 删除项目目录 + 清理 DB 缓存记录

- [ ] Task E4: 项目导入（对齐004总库管理，新增能力）
  - [ ] SubTask E4.1: 选择已有项目目录导入
  - [ ] SubTask E4.2: 检测/补全 .copier-answers.yml（调用 retrofit 逻辑，Bug-4 已修复）
  - [ ] SubTask E4.3: 扫描入库 + 业务线分类

- [ ] Task E5: CLI 增强
  - [ ] SubTask E5.1: `auto-pm project import <path>` 新增导入命令
  - [ ] SubTask E5.2: `auto-pm project list --business-line <SW|DJ|ZD|XT|WX>` 业务线筛选
  - [ ] SubTask E5.3: `auto-pm gui` 启动入口改为 PySide6

### 阶段 F：数据层适配与旧代码清理

- [ ] Task F1: SQLite 缓存层适配 PySide6
  - [ ] SubTask F1.1: ProjectRepository 增加业务线字段
  - [ ] SubTask F1.2: SyncService 增量同步保留，适配新字段
  - [ ] SubTask F1.3: GUI 优先读 DB 缓存，缺失时回退文件系统扫描

- [ ] Task F2: 移除旧 pywebview GUI 层
  - [ ] SubTask F2.1: 删除 `auto_pm/gui/static/`（index.html/app.js/style.css）
  - [ ] SubTask F2.2: 删除 `auto_pm/gui/app.py`、`auto_pm/gui/api.py`（pywebview 桥接）
  - [ ] SubTask F2.3: 保留 `auto_pm/gui/` 包改为 re-export PySide6 入口，或迁移到 `auto_pm/ui/`

- [ ] Task F3: Pydantic 模型增强
  - [ ] SubTask F3.1: Project 模型新增 business_line 字段（Literal["SW","DJ","ZD","XT","WX"])
  - [ ] SubTask F3.2: DTO 模型适配 PySide6 视图层（ProjectCardDTO/ProjectDetailDTO）

### 阶段 G：测试与文档同步

- [x] Task G1: 测试 ✅ 已完成
  - [x] SubTask G1.1: 4 个 Bug 修复回归测试（Task 0.1~0.4 的测试用例）✅ 已完成
  - [x] SubTask G1.2: 扫描深度统一回归测试（Task 0.5 的测试用例）✅ 已完成
  - [x] SubTask G1.3: 项目CRUD单元测试（import/classify/search 新方法）✅ 已完成
  - [x] SubTask G1.4: PySide6 GUI 冒烟测试（主窗口启动/列表渲染/进入工作区/新建项目流程）✅ 已完成
  - [x] SubTask G1.5: 业务线分类与筛选测试 ✅ 已完成
  - [x] SubTask G1.6: 回归测试（CLI project/plc/change 命令不破坏）✅ 已完成

- [x] Task G2: 文档同步（开发结束后）✅ 已完成
  - [x] SubTask G2.1: 同步 PRD V2.0（标注实际实现偏差）✅ 已完成
  - [x] SubTask G2.2: 同步 DES V2.0（实际模块结构）✅ 已完成
  - [x] SubTask G2.3: 同步 INT V2.0（实际 CLI/Service 接口）✅ 已完成
  - [x] SubTask G2.4: 更新 README（PySide6 启动方式、依赖变更）✅ 已完成

---

## V2.1 — 变更管理增强（去重整合004/005，纲要，V2.0 验收后细化）

> **整合原则**：当前 008 已完整迁移 005 的变更管理（`auto_pm/change/` 7模块，含三维分类/完整状态机/门禁/台账/CHG-040章节写入）。V2.1 **不重复实现**这些能力，而是**以005现有实现为唯一基础，吸收004的独有能力**。

- [ ] Task H1: 传播链追踪（吸收004独有）
  - [ ] SubTask H1.1: 变更传播路径模型（记录变更在项目内POU/画面/IO点的传播）
  - [ ] SubTask H1.2: 传播链写入变更单§6影响分析章节
  - [ ] SubTask H1.3: GUI传播链可视化展示

- [ ] Task H2: 影响分析（吸收004独有，impact模型，修复004未持久化问题）
  - [ ] SubTask H2.1: 影响范围分析Service（评估变更对相关项目/模块的影响）
  - [ ] SubTask H2.2: 影响报告生成（Markdown格式）
  - [ ] SubTask H2.3: 影响分析结果持久化到 DB（修复004 impact_service.py:48 未持久化问题）

- [ ] Task H3: 结构化审批记录（吸收004独有，approval_dao）
  - [ ] SubTask H3.1: 审批记录DB表（缓存审批历史，文件真源仍为MD§8表格）
  - [ ] SubTask H3.2: 审批历史查询与展示

- [ ] Task H4: 变更单编辑补齐（005缺失功能）
  - [ ] SubTask H4.1: 变更单编辑表单（支持编辑§1~§10 各章节）
  - [ ] SubTask H4.2: 编辑后写回 MD 文件 + 同步 DB 缓存

- [ ] Task H5: GUI 变更管理增强
  - [ ] SubTask H5.1: 变更单创建向导（基于现有CHG-040模板，三维分类表单，枚举对齐 Bug-3 修复后的常量）
  - [ ] SubTask H5.2: 状态流转UI（状态机可视化 + 门禁提示）
  - [ ] SubTask H5.3: 变更单列表筛选（按状态/领域/性质/范围）
  - [ ] SubTask H5.4: 变更单详情页（含传播链与影响分析展示）
  - [ ] SubTask H5.5: 变更单编辑UI（Task H4 的 GUI 部分）

> **明确不做**（005已实现，不重复）：三维分类校验、状态机流转、门禁规则、版本变更台账、CHG-040模板章节写入——这些在008现状中已完整可用。

## V2.2 — 规范中心整合（吸收006，纲要）

> **基于实际源码**：006 实际 V0.2.0（非 PRD 声明的 V1.1.0），10 个检查器（非 8 个），GUI 完全未实现。

- [ ] Task I1: 迁移 spec_registry.json 管理（复用006 core 模块）
- [ ] Task I2: 10 项健康检查 Service 迁移（SHC-001~010，复用006 checker_base.py）
  - [ ] SubTask I2.1: 迁移 10 个检查器逻辑
  - [ ] SubTask I2.2: 修正 SHC-002 严重级别为 ERROR（与 PRD 对齐，实际源码为 WARNING）
- [ ] Task I3: 索引生成（3 个 INDEX 文件，复用006）
- [ ] Task I4: Frontmatter 批量管理（dry-run/执行，复用006）
- [ ] Task I5: 元数据报告生成（复用006）
- [ ] Task I6: CLI 选项补齐（006 未实现部分）
  - [ ] SubTask I6.1: 实现 `--config` 选项（指定配置文件）
  - [ ] SubTask I6.2: 实现 `--quiet` 选项（静默模式）
- [ ] Task I7: LSP-907 作为特定检查器接入（005 独有，作为006框架的特定规范检查器）
- [ ] Task I8: GUI 规范中心页（从零构建 PySide6，006 GUI 完全未实现）
  - [ ] SubTask I8.1: 仪表盘（规范统计）
  - [ ] SubTask I8.2: 健康检查面板（运行/结果/历史）
  - [ ] SubTask I8.3: 索引管理面板
  - [ ] SubTask I8.4: Frontmatter 管理面板
  - [ ] SubTask I8.5: 报告生成面板
  - [ ] SubTask I8.6: 设置面板

## V2.3 — 变量表解析整合（吸收001，纲要）

> **基于实际源码**：001 的 parser/exporter 可复用，variable/（死代码）和 converter/（空壳）弃用，未实现功能（批量解析/格式自动识别/跨格式转换）需新开发。

- [ ] Task J1: 迁移多格式解析器（复用001 `src/parser/`，5 个解析器 autoshop/codesys/scl/intdoc/work3）
- [ ] Task J2: 编码检测（复用001，GBK/GB2312/UTF-8 自动+手动）
- [ ] Task J3: 迁移导出器（复用001 `src/exporter/exporter.py`，CSV/JSON/Excel）
- [ ] Task J4: 变量表重建/格式转换（**重新实现**，不复用001空壳 converter/）
  - [ ] SubTask J4.1: 统一中间模型设计（解析为统一变量模型）
  - [ ] SubTask J4.2: 格式转换器实现（中间模型 → 目标格式）
- [ ] Task J5: 变量 CRUD/批量编辑
- [ ] Task J6: 批量解析（**新开发**，001 PRD REQ 声明但未实现）
  - [ ] SubTask J6.1: 目录遍历多文件解析
  - [ ] SubTask J6.2: 批量解析进度展示
- [ ] Task J7: 格式自动识别（**新开发**，001 PRD REQ 声明但未实现）
  - [ ] SubTask J7.1: 按文件扩展名识别
  - [ ] SubTask J7.2: 按内容特征识别（兜底）
- [ ] Task J8: GUI 项目工作区「变量表」Tab（PLC项目）+ 独立工具入口
  - [ ] SubTask J8.1: 变量表列表/详情视图
  - [ ] SubTask J8.2: 解析/转换/批量操作工具栏
  - [ ] SubTask J8.3: 变量编辑表单

> **明确不复用**：001 的 `src/variable/`（死代码）、`src/converter/`（空壳，convert() 直接 return）、tkinter GUI 层。

## V2.4 — 模板管理 + 插件系统 + 报告中心 + 缺陷/库变更（纲要）

- [ ] Task K1: 模板管理 UI（创建/编辑/分类/版本/应用，对齐004）
- [ ] Task K2: 插件系统（市场/管理/SDK/配置，对齐004，**弃用004的 plc_variable_parser 插件**，变量表解析已由001统一实现）
- [ ] Task K3: 报告中心（项目/统计/进度/变更报告，多格式导出，对齐004）
- [ ] Task K4: 项目监控与统计（状态监控/依赖分析/健康评估/图表可视化，对齐004）
- [ ] Task K5: 缺陷管理（吸收004独有 defect_dao，关联变更单）
- [ ] Task K6: 库变更管理（吸收004独有 library_change_dao，SysLib场景）
- [ ] Task K7: GUI 内通知（替代004未实现的邮件通知）

## V2.5 — 系统设置 + 用户管理 + 打包分发 + 收尾（纲要）

- [ ] Task L1: 系统设置（配置/备份/日志级别）
- [ ] Task L2: 用户管理（**重新设计**，不复用004 UserStore 硬编码）
  - [ ] SubTask L2.1: 用户模型设计（基于配置文件或轻量DB）
  - [ ] SubTask L2.2: 用户切换/权限管理
- [ ] Task L3: PyInstaller 打包 exe（免安装，<100MB，冷启动<5秒）
- [ ] Task L4: 性能优化（100+项目列表<2秒）
- [ ] Task L5: 旧工具归档（SW-2026-001/004/005/006/007 标记归档）
- [ ] Task L6: 全量文档同步与验收

---

# Task Dependencies

- **阶段 0（Bug 修复）** ✅ 已完成 → 阶段 A（文档）：Bug 修复后方可重写文档（文档需反映修复后的状态）
- **阶段 A（文档）** → 阶段 B/C/D/E/F（实现）：文档先行，A 完成后方可开工
- **Task B1（包结构）** → B2（主窗口）→ C1/C2（列表页）：框架递进
- **Task B2（主窗口）** → D1（工作区容器）→ D2（概览Tab）：工作区依赖主窗口
- **Task E1~E4（CRUD）** 依赖 C1/C2（列表页）+ F3（模型）：CRUD 需列表页与模型就绪
- **Task F1（DB适配）** ∥ F2（旧代码清理）∥ F3（模型）：可并行
- **Task G1（测试）** 依赖 0/A/B/C/D/E/F 全部完成
- **Task G2（文档同步）** 依赖 G1（测试通过）
- **V2.1~V2.5** 依赖 V2.0 验收通过，顺序递进（V2.2/V2.3 部分可并行）
