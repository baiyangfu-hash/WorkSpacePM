# auto-pm V2.0 统一工作台全量整合 Spec（基于深度代码分析重写）

## Why

本 spec 基于对 SW-2026-001/004/005/006/007/008 **实际源码的深度分析**（非 PRD 声明），识别出以下核心问题：

### 问题 1：008 自身存在 4 个功能性 Bug，基础不牢

经源码核查，当前 auto-pm (SW-2026-008) 存在 4 个阻断性 Bug，必须在任何新功能开发前修复：

| Bug | 位置 | 现象 | 根因 |
|-----|------|------|------|
| Bug-1 | [auto_pm/change/change_service.py:300-305](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/change/change_service.py) | `_get_project_path` 找不到项目目录 | 假设目录名=project_id，实际是 `{project_id}_{project_name}` |
| Bug-2 | [auto_pm/db/sync.py:192](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/db/sync.py) | `_sync_changes` 同步变更单失败 | 在 `04_变更管理` 查找，实际路径是 `00_项目管理/04_变更管理/01_变更单/CHG-*/` |
| Bug-3 | [auto_pm/gui/static/index.html:152-178](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/gui/static/index.html) | 新建变更单弹窗枚举不匹配 | domain 含 INTF 非法、nature 含 FIX 非法、scope 选项与 IMPACT_SCOPES 完全不匹配 |
| Bug-4 | [auto_pm/cli/project.py:242](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/cli/project.py) | `retrofit` 命令 `_src_path` 推断错误 | python 项目写入 `templates/python-standard`，实际是 `python-tool` |

### 问题 2：源工具 GUI 技术栈混乱，无法直接复用

| 工具 | PRD 声明 | 实际源码 | 复用决策 |
|------|----------|----------|----------|
| SW-2026-001 | （未明确） | **tkinter**（[02_开发文件/src/ui/main_window.py](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-001_PLC变量表解析工具/02_开发文件/src/ui/main_window.py)） | 弃用 tkinter，逻辑层复用，UI 重写为 PySide6 |
| SW-2026-004 | PySide6 | **PyQt5**（实际源码） | 弃用 PyQt5，逻辑层复用，UI 重写为 PySide6 |
| SW-2026-005 | （未明确） | **pywebview + HTML** | 弃用 pywebview，UI 重写为 PySide6 |
| SW-2026-006 | V0.3.0 规划 GUI | **GUI 完全未实现**（当前 V0.2.0） | 从零构建 PySide6 GUI |
| SW-2026-008 | pywebview | **pywebview + 单页 HTML/JS** | 弃用，重写为 PySide6 |

**结论**：5 个源工具的 GUI 层均不可直接复用，统一以 PySide6 原生桌面重写。逻辑层（Service/DAO/Parser）按可复用资产审查结果选择性复用。

### 问题 3：源工具存在死代码/空壳/未实现声明，不能盲目"拷贝"

| 工具 | 死代码/空壳 | 未实现声明 | 处理 |
|------|-------------|------------|------|
| SW-2026-001 | `src/variable/`（死代码从未被使用）、`src/converter/`（空壳，`GenericConverter.convert()` 直接 return） | 批量解析、格式自动识别、跨格式转换（PRD REQ 声明但未实现） | 死代码弃用不复用；未实现功能需可行性分析后决定是否开发 |
| SW-2026-004 | — | 影响分析未持久化（[impact_service.py:48](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-004_Python项目管理工具/03_主程序/01_主程序核心代码/src/services/impact_service.py)）、邮件通知未实现、UserStore 硬编码（[auth.py:36-47](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-004_Python项目管理工具/03_主程序/01_主程序核心代码/src/api/auth.py)）、API 路由权限不一致 | 未实现功能需评估是否纳入整合范围 |
| SW-2026-005 | — | 变更单编辑缺失、扫描深度不一致（[project_overview_service.py:55](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-005_PLC项目管理工具/03_主程序/01_主程序核心代码/src/services/project_overview_service.py) depth=1 vs plc_project_service depth=4） | 扫描深度统一为 4，变更单编辑补齐 |
| SW-2026-006 | — | GUI 完全未实现、`--config`/`--quiet` 选项未实现（[cli.py:11-20](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-006_规范管理工具/02_源代码/specmgr/cli.py)）、SHC-002 严重级别与 PRD 不符（实际 WARNING，PRD 声明 ERROR） | GUI 从零构建；SHC-002 级别按 PRD 修正为 ERROR |
| SW-2026-008 | Python 子命令仅占位 | GUI 缺失变更单详情和状态流转 UI、测试覆盖率 62% | Python 子命令补齐；GUI 缺失 UI 补齐 |

### 问题 4：跨项目功能重复（不只 004/005 变更管理）

经全面核查，识别出 **4 类跨项目功能重复**，必须去重整合：

| 重复类型 | 涉及工具 | 重复表现 | 整合决策 |
|----------|----------|----------|----------|
| **变更管理** | 004 vs 005 vs 008 | 三维分类/状态机/台账/CRUD 重复 | 以 005 实现为唯一基础（已迁移至 008），吸收 004 独有能力（传播链/影响分析/结构化审批记录） |
| **变量表解析** | 001 vs 004 的 plc_variable_parser 插件 | 001 是完整多格式解析器，004 的插件是简化版 | 以 001 为唯一实现，004 的插件弃用 |
| **规范检查** | 005 的 LSP-907 vs 006 的通用健康检查 | 005 是 PLC 特定规范检查，006 是通用规范健康检查 | 006 为通用规范中心，005 的 LSP-907 作为特定规范检查器接入 006 框架 |
| **项目管理** | 004 vs 005 vs 007 | 004 是 Python 项目管理，005 是 PLC 项目管理，007 是 pm-mgr | 008 统一为项目中心式，按技术栈区分（PLC/Python），007 的 detect/retrofit/snapshot 并入项目 CRUD |

### 问题 5：UI 落后，多角色适配不足

当前 008 的 pywebview + 单页 HTML/JS（[index.html](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/gui/static/index.html) 仅项目列表+详情+几个弹窗），远落后于 004 的 PyQt5 桌面应用（八大模块：总库/模板/监控/变更/插件/规范/报告/设置）。使用者兼任项目管理、PLC 程序设计、Python 程序设计、规范管理文档编辑多个角色，当前 UI 无角色适配，功能堆叠混乱。

需将 5 个工具全量吸收为单一工具，以 PySide6 原生桌面 + 项目中心式 UI 重构，多版本渐进式交付，文档先行。

## What Changes

### 架构与 UI
- **BREAKING**：UI 技术栈从 pywebview + HTML/JS 迁移到 PySide6 原生桌面（统一技术栈，5 个源工具的 tkinter/PyQt5/pywebview/未实现 GUI 均弃用）
- **BREAKING**：导航范式改为「项目中心式」——首页项目列表 → 进入项目工作区 → Tab 导航（概览/变更/规范/变量表/文档/检查）
- 保留 CLI 层（技能调用入口）与 SQLite 索引缓存层
- 多角色适配：通过项目工作区 Tab 与全局功能页区分角色工作流（PLC 工程师→变量表/检查 Tab；Python 工程师→文档/检查 Tab；项目经理→概览/变更 Tab；规范编辑→规范中心全局页）

### 008 自身 Bug 修复（V2.0 前置任务，必须先做）
- **Bug-1**：`_get_project_path` 修正为按 `{project_id}_{project_name}` 模式匹配
- **Bug-2**：`_sync_changes` 修正扫描路径为 `00_项目管理/04_变更管理/01_变更单/CHG-*/`
- **Bug-3**：GUI 变更单弹窗枚举对齐 `_change_constants.py` 的 DOMAIN_VALUES/NATURE_VALUES/IMPACT_SCOPES（移除 INTF/FIX，scope 改为 7 领域 5 性质 5 范围）
- **Bug-4**：`retrofit` 命令 `_src_path` 推断逻辑修正（python 项目→`python-tool`，plc 项目→`plc-standard`）

### 功能全量吸收（基于实际源码，非 PRD 声明）

#### 吸收 SW-2026-001（变量表解析，V2.3）
**可复用资产**（经审查后复用）：
- `src/parser/` 5 个解析器（autoshop/codesys/scl/intdoc/work3）——逻辑层完整，直接迁移
- `src/exporter/exporter.py`——CSV/JSON/Excel 导出，直接迁移

**弃用资产**（死代码/空壳，不复用）：
- `src/variable/`——死代码，从未被使用，弃用
- `src/converter/`——空壳，`GenericConverter.convert()` 直接 return，弃用，V2.3 重新实现转换逻辑

**未实现功能可行性分析**（PRD REQ 声明但未实现，需评估）：
- 批量解析（REQ-001 声明）：**可行**，V2.3 实现，遍历目录多文件解析
- 格式自动识别（REQ-002 声明）：**可行**，V2.3 实现，按文件扩展名+内容特征识别
- 跨格式转换（REQ-003 声明）：**可行**，V2.3 实现，解析为统一中间模型后导出目标格式（重新实现 converter，不复用空壳）

**UI 重写**：tkinter → PySide6，作为项目工作区「变量表」Tab + 全局工具入口

#### 吸收 SW-2026-004（Python 项目管理，V2.0/V2.1/V2.4）
**可复用资产**：
- `src/core/_change_constants.py`——三维分类常量+SCOPE_APPROVAL_MAP（仅参考，008 已有 005 实现）
- `src/services/change_service.py`——21 个方法（仅参考传播链/影响分析/结构化审批记录独有能力）
- 总库管理逻辑（导入/分类/搜索/多业务线 SW/DJ/ZD/XT/WX）——V2.0 迁移
- 模板管理、插件系统、报告中心、系统设置——V2.4 迁移

**弃用资产**：
- PyQt5 GUI 层——弃用，重写为 PySide6
- `src/api/auth.py` UserStore 硬编码——弃用，V2.5 重新设计用户管理
- API 路由层（大部分无 auth_required）——弃用，PySide6 直接调用 Service

**未实现功能处理**：
- 影响分析未持久化——V2.1 重新实现，持久化到 DB
- 邮件通知未实现——**不纳入整合范围**（桌面应用无需邮件通知，GUI 内通知即可）
- API 路由权限不一致——**不纳入整合范围**（PySide6 直接调用 Service，无 API 层）

#### 吸收 SW-2026-005（PLC 项目管理，V2.0 已部分迁移，V2.1 增强）
**可复用资产**（008 已迁移，需修复/增强）：
- `change_management_service.py`——完整状态机+门禁，已迁移至 008
- `plc_project_service.py`——LSP-907 检查/修复/标准化，已迁移至 008
- `project_overview_service.py`——立项表解析，已迁移至 008

**需修复**：
- 扫描深度不一致（`project_overview_service.py:55` depth=1 vs `plc_project_service` depth=4）——V2.0 统一为 depth=4
- 变更单编辑缺失——V2.1 补齐

**弃用资产**：
- pywebview GUI 层——弃用，重写为 PySide6

#### 吸收 SW-2026-006（规范管理，V2.2）
**实际版本**：V0.2.0（非 PRD 声明的 V1.1.0）

**可复用资产**：
- `specmgr/core/checker_base.py`——**实际 10 个检查器**（SHC-001~010，非 PRD 声明的 8 个），逻辑层完整，直接迁移
- `specmgr/core/` 其他模块——spec_registry 管理、索引生成、Frontmatter 管理、报告生成，直接迁移
- `specmgr/cli.py`——CLI 逻辑迁移，但 `--config`/`--quiet` 选项需补齐实现

**需修复**：
- SHC-002 严重级别与 PRD 不符（实际 WARNING，PRD 声明 ERROR）——V2.2 按 PRD 修正为 ERROR
- `--config`/`--quiet` 选项未实现——V2.2 补齐

**从零构建**：
- GUI 完全未实现——V2.2 从零构建 PySide6 规范中心页（仪表盘/健康检查/索引/Frontmatter/报告/设置）

#### 吸收 SW-2026-007（pm 工作流工具链，已取代）
- pm-mgr 已被 auto-pm 取代
- detect/retrofit/snapshot 能力并入项目 CRUD（008 已有 retrofit，需修复 Bug-4）

### 旧工具归档
- SW-2026-001/004/005/006/007 在 auto-pm 对应版本交付验证通过后标记归档

### 功能重复整合策略（去重，非两套并存）

#### 1. 变更管理去重（004 vs 005 vs 008）

经核查，SW-2026-004 与 SW-2026-005 的变更管理存在大量功能重复。当前 008 已完整迁移 005 的变更管理实现（`auto_pm/change/` 7 模块）。整合策略如下：

| 能力 | 004 | 005 | 008现状 | 整合决策 |
|------|-----|-----|---------|----------|
| 三维分类(Domain×Nature×Scope) | ✅ | ✅ | ✅已迁移005 | **以005为唯一实现**（005严格遵循CHG-040/PM-042，7领域5性质5范围） |
| 审批流程状态机 | ✅(草稿→提交→审批→实施→完成) | ✅(更完整:含pending_acceptance/accepting/返工) | ✅已迁移005 | **以005为唯一实现**（005状态机更完整，含验收返工路径） |
| 版本变更台账 | ✅ | ✅ | ✅已迁移005 | **以005为唯一实现** |
| 变更单CRUD | ✅(DB持久化) | ✅(文件真源) | ✅已迁移005 | **以005文件真源为主**，DB作缓存 |
| 门禁规则 | ❌ | ✅(PM-042 V2.2.0 §5.3) | ✅已迁移005 | **005独有，保留** |
| CHG-040模板章节写入 | ❌ | ✅(§8/§9/§10) | ✅已迁移005 | **005独有，保留** |
| 传播链追踪 | ✅ | ❌ | ❌ | **吸收004**（V2.1新增） |
| 影响分析 | ✅(impact模型,未持久化) | ❌ | ❌ | **吸收004并修复持久化**（V2.1新增，持久化到DB） |
| 结构化审批记录 | ✅(approval_dao) | ❌(写入MD表格) | ❌ | **吸收004**（V2.1新增，DB缓存审批历史） |
| 缺陷管理 | ✅(defect_dao) | ❌ | ❌ | **吸收004**（V2.4规划，关联变更单） |
| 库变更管理 | ✅(library_change_dao) | ❌ | ❌ | **吸收004**（V2.4规划，SysLib场景） |

**结论**：V2.1 变更管理增强**不是"对齐004"**（004的变更管理不如005规范），而是**"以005现有实现为唯一基础，吸收004的传播链/影响分析/结构化审批记录"**。三维分类/状态机/台账/门禁不重复实现。

#### 2. 变量表解析去重（001 vs 004 的 plc_variable_parser 插件）

| 能力 | 001 | 004 插件 | 整合决策 |
|------|-----|----------|----------|
| 多格式解析（Autoshop/Work3/Codesys/SCL/INT doc） | ✅ 完整 | ❌ 简化版 | **以001为唯一实现** |
| 编码检测 | ✅ | ❌ | **以001为唯一实现** |
| 重建/转换 | 空壳（converter 未实现） | ❌ | **V2.3 重新实现**（不复用空壳） |
| 批量解析 | ❌ 未实现 | ❌ | **V2.3 新开发** |
| 格式自动识别 | ❌ 未实现 | ❌ | **V2.3 新开发** |

**结论**：以 001 为变量表解析的唯一实现，004 的 plc_variable_parser 插件弃用。001 的死代码（variable/）和空壳（converter/）弃用，转换功能 V2.3 重新实现。

#### 3. 规范检查去重（005 的 LSP-907 vs 006 的通用健康检查）

| 能力 | 005 | 006 | 整合决策 |
|------|-----|-----|----------|
| 通用规范健康检查（SHC-001~010） | ❌ | ✅ 10个检查器 | **以006为唯一实现** |
| PLC 特定规范检查（LSP-907） | ✅ | ❌ | **作为006框架的特定检查器接入** |
| spec_registry 管理 | ❌ | ✅ | **以006为唯一实现** |
| 索引生成 | ❌ | ✅ | **以006为唯一实现** |
| Frontmatter 批量管理 | ❌ | ✅ | **以006为唯一实现** |

**结论**：006 为通用规范中心的唯一实现，005 的 LSP-907 检查器作为 006 框架的特定规范检查器接入（V2.2 实现）。

#### 4. 项目管理去重（004 vs 005 vs 007）

| 能力 | 004 | 005 | 007 | 008现状 | 整合决策 |
|------|-----|-----|-----|---------|----------|
| 项目 CRUD | ✅ Python项目 | ✅ PLC项目 | ❌ | ✅ 已整合 | **008统一，按技术栈区分** |
| 总库管理（导入/分类/搜索/多业务线） | ✅ | ❌ | ❌ | ❌ | **吸收004**（V2.0） |
| 立项表解析 | ❌ | ✅ | ❌ | ✅ 已迁移 | **以005为唯一实现** |
| 项目概览 | ❌ | ✅ | ❌ | ✅ 已迁移 | **以005为唯一实现** |
| detect/retrofit/snapshot | ❌ | ❌ | ✅ | ✅ 已有retrofit（有Bug-4） | **007已被008取代**，修复Bug-4 |
| 标准化管理（LSP-907） | ❌ | ✅ | ❌ | ✅ 已迁移 | **以005为唯一实现** |

**结论**：008 统一为项目中心式，按技术栈区分（PLC/Python），007 的能力并入项目 CRUD。

### 多版本渐进式路线图

| 版本 | 主题 | 核心交付 |
|------|------|----------|
| **V2.0** | Bug 修复 + PySide6 UI 基座 + 项目中心 + 项目CRUD对齐004 | 008的4个Bug修复（前置）、PySide6主框架、项目列表/工作区/概览Tab、总库管理（导入/分类/搜索/多业务线）、扫描深度统一 |
| **V2.1** | 变更管理增强（去重整合004/005） | 以005现有实现为基础，吸收004的传播链追踪、影响分析（持久化）、结构化审批记录（DB缓存）；变更单编辑补齐；GUI变更管理增强（创建向导/状态流转/列表筛选） |
| **V2.2** | 规范中心整合（吸收006） | spec_registry、10项健康检查（SHC-001~010，修正SHC-002级别）、索引生成、Frontmatter、报告、--config/--quiet补齐、GUI规范中心页（从零构建）、LSP-907作为特定检查器接入 |
| **V2.3** | 变量表解析整合（吸收001） | 多格式解析（复用001 parser）、编码检测、重建/转换（重新实现，不复用空壳）、变量编辑、批量解析（新开发）、格式自动识别（新开发）、项目工作区变量表Tab |
| **V2.4** | 模板管理 + 插件系统 + 报告中心 + 缺陷/库变更 | 模板CRUD/版本、插件市场/SDK、项目/统计/进度/变更报告、缺陷管理、库变更管理（吸收004独有） |
| **V2.5** | 系统设置 + 用户管理 + 打包分发 + 收尾 | 配置/备份、用户管理（重新设计，不复用004硬编码）、PyInstaller exe、性能优化、旧工具归档、全量文档同步 |

### 开发流程
- 文档先行：每版先更新 PRD/DES/INT，开发结束后同步文档
- 增量开发：每版可独立交付验证
- Bug 优先：V2.0 首先修复 008 的 4 个 Bug，再做新功能

## Impact

- **Affected specs**：
  - SW-2026-008 PRD V1.1.0 → 重写为 V2.0（UI技术栈、用户模型、项目中心导航、总库管理对齐004、Bug修复前置）
  - SW-2026-001/004/005/006/007 → 逐步归档（对应版本交付后）
- **Affected code**：
  - `auto_pm/change/change_service.py`（修复 Bug-1：`_get_project_path`）
  - `auto_pm/db/sync.py`（修复 Bug-2：`_sync_changes` 路径）
  - `auto_pm/gui/static/index.html`（修复 Bug-3：枚举对齐，但 V2.0 整体弃用 pywebview）
  - `auto_pm/cli/project.py`（修复 Bug-4：`retrofit` `_src_path`）
  - `auto_pm/gui/`（pywebview → PySide6 整层重写）
  - `auto_pm/cli/gui.py`（启动入口改为 PySide6）
  - `auto_pm/core/project_service.py`（增强总库管理能力）
  - `auto_pm/services/project_overview_service.py`（扫描深度统一为 depth=4）
  - 新增 `auto_pm/ui/`（PySide6 窗口/视图/组件）
  - 新增 `auto_pm/spec_center/`（V2.2 吸收006）
  - 新增 `auto_pm/var_table/`（V2.3 吸收001，不含死代码 variable/ 和空壳 converter/）
  - 新增 `auto_pm/template_mgr/`、`auto_pm/plugin/`、`auto_pm/report/`（V2.4）
- **数据真源策略**：不变。`.copier-answers.yml`（项目元数据）+ `PM_SESSION_*.md`（项目管理）+ `.auto-pm/index.db`（索引缓存）三源并存，文件系统为权威源。
- **不复用资产清单**（明确记录，避免误复用）：
  - 001 的 `src/variable/`（死代码）
  - 001 的 `src/converter/`（空壳，convert() 直接 return）
  - 001 的 tkinter GUI 层
  - 004 的 PyQt5 GUI 层
  - 004 的 `src/api/auth.py` UserStore 硬编码
  - 004 的 API 路由层（无 auth_required）
  - 005 的 pywebview GUI 层
  - 006 的 CLI `--config`/`--quiet` 未实现部分（需补齐而非复用）

## ADDED Requirements

### Requirement: 008 Bug 修复（V2.0 前置）

The system SHALL fix the 4 existing bugs in auto-pm before any new feature development in V2.0.

#### Scenario: Bug-1 修复
- **WHEN** 变更服务查找项目路径
- **THEN** `_get_project_path` 按 `{project_id}_{project_name}` 模式匹配，正确找到项目目录

#### Scenario: Bug-2 修复
- **WHEN** 同步变更单到 DB
- **THEN** `_sync_changes` 在 `00_项目管理/04_变更管理/01_变更单/CHG-*/` 路径扫描，正确同步

#### Scenario: Bug-3 修复
- **WHEN** 用户在 GUI 新建变更单
- **THEN** domain/nature/scope 枚举与 `_change_constants.py` 的 DOMAIN_VALUES/NATURE_VALUES/IMPACT_SCOPES 完全一致（无 INTF/FIX 非法值，scope 为 7 领域 5 性质 5 范围）

#### Scenario: Bug-4 修复
- **WHEN** 用户执行 `auto-pm project retrofit`
- **THEN** python 项目的 `_src_path` 推断为 `python-tool`，plc 项目的 `_src_path` 推断为 `plc-standard`

### Requirement: PySide6 项目中心式主框架

The system SHALL provide a PySide6 native desktop application with project-centric navigation: a homepage showing the project list (card grid + statistics bar + search/filter/classify), and entering a project opens a project workspace with Tab navigation (Overview/Change/Spec/VarTable/Doc/Check).

#### Scenario: 启动应用
- **WHEN** 用户运行 `auto-pm gui` 或 `python main.py`
- **THEN** 启动 PySide6 主窗口，默认显示项目列表首页

#### Scenario: 进入项目工作区
- **WHEN** 用户在项目列表点击某项目卡片
- **THEN** 进入该项目工作区，显示 Tab 导航，默认激活「概览」Tab

#### Scenario: 全局功能访问
- **WHEN** 用户需要访问规范中心/模板管理/报告中心/系统设置等全局功能
- **THEN** 通过侧边栏或顶部菜单进入，这些功能不绑定具体项目

#### Scenario: 多角色适配
- **WHEN** PLC 工程师使用工具
- **THEN** 项目工作区激活「变量表」「检查」Tab，全局可访问规范中心
- **WHEN** Python 工程师使用工具
- **THEN** 项目工作区激活「文档」「检查」Tab
- **WHEN** 项目经理使用工具
- **THEN** 项目工作区激活「概览」「变更」Tab
- **WHEN** 规范编辑使用工具
- **THEN** 全局功能页激活「规范中心」

### Requirement: 总库管理对齐 SW-2026-004

The system SHALL provide repository management capabilities aligned with SW-2026-004: project import, classification management (by business line SW/DJ/ZD/XT/WX), search and filter (by name/type/status/business line).

#### Scenario: 项目导入
- **WHEN** 用户将已有项目导入总库
- **THEN** 系统扫描项目元数据，写入 `.copier-answers.yml`（缺失时调用 retrofit 补全），同步到 SQLite 缓存

#### Scenario: 多业务线分类
- **WHEN** 用户按业务线筛选项目
- **THEN** 支持 SW(软件开发)/DJ(单机设备)/ZD(自动化整线)/XT(系统升级)/WX(维保项目) 五类筛选

### Requirement: 扫描深度统一

The system SHALL unify the scan depth across project overview and PLC project service to depth=4.

#### Scenario: 扫描深度一致
- **WHEN** ProjectOverviewService 扫描项目结构
- **THEN** 扫描深度为 4，与 PlcProjectService 一致

### Requirement: 全量工具整合

The system SHALL fully absorb the functionality of SW-2026-001/004/005/006/007 into a single tool, with old tools archived after the corresponding version is delivered and verified.

#### Scenario: 变量表解析（V2.3）
- **WHEN** PLC 工程师在 PLC 项目工作区打开「变量表」Tab
- **THEN** 可解析 Autoshop/Work3/Codesys/SCL/INT doc 格式变量表，自动检测编码，支持重建/转换/批量编辑/批量解析/格式自动识别

#### Scenario: 规范中心（V2.2）
- **WHEN** 用户打开全局「规范中心」
- **THEN** 显示仪表盘（规范统计）、可运行 10 项健康检查（SHC-001~010，SHC-002 为 ERROR 级别）、生成索引、管理 Frontmatter、生成报告、LSP-907 作为特定检查器接入

### Requirement: 多版本渐进式交付

The system SHALL be delivered in incremental versions (V2.0~V2.5), each independently deliverable and verifiable, with documentation updated first and synced after development.

#### Scenario: 版本独立交付
- **WHEN** V2.0 完成
- **THEN** 008的4个Bug已修复 + PySide6 UI 基座 + 项目中心 + 项目CRUD对齐004 可独立验证，不依赖 V2.1+ 功能

## MODIFIED Requirements

### Requirement: 项目CRUD（增强对齐004）

原 V1.1.0 仅支持基础新建/编辑/删除/列表。V2.0 增强为对齐 SW-2026-004 总库管理：导入、分类管理、搜索过滤、多业务线、批量导入。

### Requirement: GUI 桌面应用

原 V1.1.0 采用 pywebview。V2.0 改为 PySide6 原生桌面，支持复杂表格/树形/多窗口/拖拽，项目中心式导航，多角色适配。

### Requirement: 变更管理（去重整合004/005）

原 008 已完整迁移 005 的变更管理（三维分类/状态机/门禁/台账/CHG-040章节写入）。V2.1 在此基础上吸收 004 独有能力：传播链追踪、影响分析（持久化到DB）、结构化审批记录（DB缓存）。**不重复实现** 005 已有的三维分类、状态机、台账、门禁。同时补齐变更单编辑功能。

#### Scenario: 传播链追踪（V2.1）
- **WHEN** 变更单实施时记录变更传播到的 POU/画面/IO点
- **THEN** 变更单§6影响分析章节写入传播路径，GUI 可视化展示传播链

#### Scenario: 影响分析持久化（V2.1）
- **WHEN** 用户对某变更单执行影响分析
- **THEN** 系统评估变更对相关项目/模块的影响，生成 Markdown 影响报告，并持久化到 DB（修复004未持久化问题）

## REMOVED Requirements

### Requirement: pywebview GUI 层
**Reason**: 迁移到 PySide6 原生桌面，pywebview 功能受限无法承载八大模块
**Migration**: V2.0 重写 `auto_pm/gui/` 为 `auto_pm/ui/`（PySide6），移除 `auto_pm/gui/static/` 前端文件，`cli/gui.py` 启动入口改为 PySide6 QApplication

### Requirement: Non-Goals 中排除 SW-2026-001/006
**Reason**: 全量吸收策略下，001（变量表解析）和 006（规范管理）纳入整合范围
**Migration**: V2.2 吸收006，V2.3 吸收001，PRD V2.0 删除相关 Non-Goals 条目

### Requirement: SW-2026-001 的 variable/ 和 converter/ 模块
**Reason**: `variable/` 是死代码从未被使用，`converter/` 是空壳（`GenericConverter.convert()` 直接 return）
**Migration**: V2.3 不复用这两个模块，转换功能重新实现

### Requirement: SW-2026-004 的 API 路由层与 UserStore 硬编码
**Reason**: PySide6 直接调用 Service 无需 API 层；UserStore 硬编码不安全
**Migration**: V2.0~V2.4 不迁移 API 路由层；V2.5 重新设计用户管理

### Requirement: SW-2026-004 的邮件通知
**Reason**: 桌面应用无需邮件通知，GUI 内通知即可
**Migration**: 不纳入整合范围，V2.4 实现 GUI 内通知替代
