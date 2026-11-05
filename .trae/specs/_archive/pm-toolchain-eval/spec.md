# pm-workflow 工具链：合并评估与方案 Spec

## Why

SW-2026-004（Python项目管理工具）和 SW-2026-005（PLC项目管理工具）是两个已有工具。用户希望评估能否综合这两个工具来配合 pm-workflow 技能管理项目，替代手写的 bootstrap 脚本和 hooks，避免"重新造工具链"。

## 现有工具对比

### SW-2026-004 — 全功能桌面应用

| 维度 | 实际情况 |
|------|---------|
| 架构 | PyQt5 GUI + Flask API + Click CLI + SQLite (15 张表) |
| 规模 | ~220 个源文件，20+ 次 spec-driven 迭代，V2.5.x 稳定版 |
| 交付物 | PyInstaller 单 EXE，~225MB |
| 核心能力 | 总库管理、项目 CRUD、模板管理、变更管理（完整审批流）、插件系统、规范中心、进度管理、报告生成 |
| 项目模型 | 数据库驱动的 Project 实例，5 大业务线（SW/DJ/ZD/XT/WX） |

### SW-2026-005 — 轻量 PLC 看板

| 维度 | 实际情况 |
|------|---------|
| 架构 | PyWebView GUI (SPA) + Click CLI，无数据库，直接读 Markdown 文件 |
| 规模 | ~40 个源文件，61 个测试，V9.0.0 |
| 核心能力 | 从立项表 Markdown 解析项目信息生成看板，变更单创建/流转/门禁 |
| 数据源 | `0100_PLC自动化/` 下的 Markdown 文档（立项表 + 变更单 + 台帐） |

### pm-workflow 工具链的实际需求

| 需求 | 复杂度 | 当前方案 |
|------|--------|---------|
| 项目初始化（bootstrap） | 低 | PowerShell 脚本 ✅ 已完成 |
| Spec Snapshot | 低 | 内嵌 bootstrap ✅ 已完成 |
| hooks（sessionStart/agentStop/sessionEnd） | 低 | 4 个独立 PS 脚本 ✅ 已完成 |
| handoff drafts（apply-handoff） | 低 | PS 脚本 + AI 写回 ✅ 已完成 |
| 项目类型检测（software vs plc） | 低 | 需修复检测逻辑 ⚠️ |
| 旧项目补完（retrofit） | 中 | 尚未实现 ❌ |
| 忽略规则管理 | 低 | 工作区 .gitignore ✅ |

### 合并可行吗？

**技术上可行，但战略上不划算：**

1. **SW-2026-004 太重**：225MB 的 PyQt5 桌面应用，依赖 SQLite、15 张表、插件系统、Flask API。pm-workflow 工具链只需要轻量级文件系统操作（创建目录、写 Markdown、复制模板）。

2. **SW-2026-005 太窄**：PLC-only，且以"读"为主（看板展示），不是"写"工具（初始化项目）。

3. **工具链操作是系统级，不是应用级**：hooks 脚本需要在 agent 生命周期事件中自动触发，不应依赖用户手动启动 GUI 应用。

4. **SW-2026-004 的数据模型与 PM_SESSION 不兼容**：004 使用 SQLite + ORM 存储项目数据，pm-workflow 使用 PM_SESSION.md 作为唯一真源。强行合并会产生双重真源问题。

## What Changes

- **不合并**两个已有工具
- **新建轻量 CLI 工具** `pm-mgr`，作为 pm-workflow 的专用命令行伴侣
- 将当前手写的 PowerShell 逻辑（bootstrap + hooks 复制）迁移到 Python
- 复用 specmgr（SW-2026-006）的代码风格和项目结构
- 保留已有 bootstrap-project-continuity.ps1 作为备用方案

## Impact

- Affected specs: 不涉及现有规范修改
- Affected code:
  - 新建：`.trae/skills/pm-workflow/tools/pm_mgr/` 目录
  - 新建：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-007_pm工作流工具链/` 项目
  - 不修改：`bootstrap-project-continuity.ps1`（保留作为备用/回退方案）

## ADDED Requirements

### Requirement: 项目初始化
pm-mgr SHALL 支持从模板初始化新项目。

#### Scenario: 初始化软件项目
- **GIVEN** 空目录 `my-project/`
- **WHEN** 运行 `pm-mgr init my-project --type software --id SW-2026-XXX --name "我的项目"`
- **THEN** 创建完整的 software 项目骨架（目录结构 + PM_SESSION + hooks + 骨架文件 + 文档模板 + Spec Snapshot）

#### Scenario: 初始化 PLC 项目
- **GIVEN** 空目录 `my-plc/`
- **WHEN** 运行 `pm-mgr init my-plc --type plc --id DJ-2026-XXX --name "我的PLC项目"`
- **THEN** 创建完整的 PLC 项目骨架

### Requirement: 旧项目补完
pm-mgr SHALL 支持为已有项目注入连续性机制，不修改现有目录结构。

#### Scenario: 为活跃项目注入 hooks
- **GIVEN** 已有项目（如 SysLib），含 PM_SESSION 和 .plc.json
- **WHEN** 运行 `pm-mgr retrofit SysLib`
- **THEN** 仅添加 `.github/hooks/` + `.trae/handoffs/`，在 PM_SESSION 中补全 Spec Snapshot 区块，不动任何现有文件

#### Scenario: 跳过已归档项目
- **GIVEN** 项目 PM_SESSION 中 lifecycle 为 "archived"（如 DJ-2026-000）
- **WHEN** 运行 `pm-mgr retrofit DJ-2026-000`
- **THEN** 提示项目已归档，跳过操作

### Requirement: 项目类型检测
pm-mgr SHALL 通过多信号判据自动识别项目类型。

#### Scenario: 从 .plc.json 检测 PLC 项目
- **GIVEN** 目录含 `.plc.json`
- **WHEN** 运行 `pm-mgr detect <path>`
- **THEN** 输出 `plc`

#### Scenario: 从 pyproject.toml 检测 software 项目
- **GIVEN** 目录含 `pyproject.toml`
- **WHEN** 运行 `pm-mgr detect <path>`
- **THEN** 输出 `software`

#### Scenario: 从 .scl 文件检测 PLC 项目（回退信号）
- **GIVEN** 目录不含 `.plc.json` 但含 `*.scl` 文件
- **WHEN** 运行 `pm-mgr detect <path>`
- **THEN** 输出 `plc`

#### 检测优先级
1. `.plc.json` 存在 → plc
2. `pyproject.toml` 存在 → software
3. `*.scl` / `*.db` 存在 → plc
4. `main.py` / `package.json` 存在 → software
5. PM_SESSION 内容 → 从 `project_root` 路径或上下文推断

### Requirement: 健康检查
pm-mgr SHALL 检查项目连续性机制是否完整。

#### Scenario: 全部完整
- **GIVEN** 项目含 PM_SESSION + hooks/ + handoffs/
- **WHEN** 运行 `pm-mgr check <path>`
- **THEN** 报告所有检查项通过

#### Scenario: 缺失 hooks
- **GIVEN** 项目含 PM_SESSION 但无 hooks/
- **WHEN** 运行 `pm-mgr check <path>`
- **THEN** 报告缺失 `.github/hooks/`，建议运行 `pm-mgr retrofit`

### Requirement: Spec Snapshot 独立操作
pm-mgr SHALL 支持独立更新项目的 Spec Snapshot。

#### Scenario: 刷新 Snapshot
- **GIVEN** 项目含 PM_SESSION
- **WHEN** 运行 `pm-mgr snapshot <path>`
- **THEN** 从 `spec_registry.json` 重新读取版本号并覆盖 PM_SESSION 中的 Spec Snapshot 表格

### Requirement: 忽略规则
pm-mgr SHALL 在操作时遵循工作区 `.gitignore`，特别是 `.plc-out/` 等自动生成目录在"目录是否为空"判定时不计入。

## 架构决策

### 为什么不用 SW-2026-004/005？

| 原因 | 说明 |
|------|------|
| 规模不匹配 | 004 是 220 文件的全栈桌面应用，工具链只需 ~10 个文件 |
| 技术栈冲突 | 004 用 SQLite + ORM，工具链需要文件系统操作 |
| 角色不同 | 004 是用户手动操作的 GUI 应用，工具链是 AI/脚本自动调用的 CLI |
| PM_SESSION 认知缺失 | 004/005 都不知道 PM_SESSION 作为项目真源的概念 |
| 交付物膨胀 | 004 打包后 225MB，工具链应 `<1MB` 纯 Python |

### 新工具 `pm-mgr` 的设计原则

- **纯 Python CLI**，参考 specmgr（SW-2026-006）的代码风格
- **文件系统操作**，无数据库，不引入重型依赖
- **可独立运行**，也可被 pm-workflow 技能调用
- **幂等性**：retrofit/init 重复运行不产生副作用
- **对现有项目零侵入**：retrofit 只添加文件，不修改现有内容

## CLI 接口草案

```
pm-mgr <subcommand> [options]

init <dir>          初始化新项目
  --type software|plc  (必填)
  --id <project_id>    (必填)
  --name <name>        (必填)
  --owner <owner>      (默认: Pending)
  --oneliner <text>    (默认: Pending)

retrofit <dir>       为已有项目注入连续性机制
  --force              跳过生命周期检查

check <dir>          检查项目连续性健康状态
  --fix                自动修复可修复的问题

detect <dir>         检测项目类型

snapshot <dir>       刷新 Spec Snapshot
```

## 交付计划

| 阶段 | 内容 | 可验证 |
|------|------|--------|
| Phase 1 | init 命令（替代 bootstrap PS 脚本） | 用临时目录验证 software + plc |
| Phase 2 | retrofit 命令（旧项目注入 hooks） | 对 SysLib 执行 retrofit，验证只添加文件 |
| Phase 3 | check + detect 命令 | 对 4 种项目类型验证 |
| Phase 4 | snapshot 命令 | 验证 Spec Snapshot 刷新 |
| Phase 5 | 集成到 pm-workflow 技能 | 替换 Step 3G 中的 bootstrap 调用 |
