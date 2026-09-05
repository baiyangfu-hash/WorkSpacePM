---
version: "V2.1.0"
status: "正式发布"
created: "2026-08-17"
updated: "2026-09-01"
spec_id: "USER_GUIDE"
project_id: "SW-2026-008"
title: "auto-pm 自动化项目管理工具 - 用户操作指南与排障手册"
---

# auto-pm 自动化项目管理工具 - 用户操作指南与排障手册 (USER_GUIDE V2.1.0)

> **面向对象**：现场电气工程师、PLC 研发工程师、全栈软件开发、项目经理（PM）、AI 协作助手  
> **适用版本**：auto-pm V1.2.3+ 工作空间基础设施运行位（GUI + CLI + AI Agent 协同）
> **研发母体**：SW-2026-008 项目目录（源码、测试、模板和发布配置真源）；**稳定部署**：`00_Infrastructure/auto_pm`（受控稳定制品、启动器和双槽指针）。

---

## 1. 系统架构与双模启动

`auto-pm` 是专为非标自动化与工业全栈项目研发打造的双模管理驾驶舱，既提供现代化深度磨砂深色视觉 GUI，又提供完备的 Headless 命令行接口（CLI）。

```text
                                auto-pm 混合驾驶舱架构
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │  【前端接入层】                                                              │
    │    ├── PyQt6 / QML 现代化工业深色驾驶舱 (桌面客户端)                          │
    │    ├── Headless 命令行工具 (CLI: python -m auto_pm ...)                    │
    │    └── AI Context 桥接总线 (.auto-pm/ai_context.json & ai_feedback.json)   │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │  【业务领域层 (Domain)】                                                     │
    │    ├── Project (生命周期/模板脚手架)   ├── PLC (53项门禁/SCL Linter/逆向)    │
    │    ├── Spec (单一真源/全库索引/快照)    ├── Change (CHG单据/台账对账)        │
    │    ├── VarTable (14种变量表自动探测)    └── Delivery (现场核验/交付清单)     │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │  【基础设施层 (Infrastructure)】                                             │
    │    ├── SQLite 本地嵌入式数据仓库        ├── Copier 模板渲染引擎              │
    │    ├── Git 版本与子模块跟踪            └── YAML/JSON/Markdown AST 解析器    │
    └─────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 启动方式
- **GUI 驾驶舱启动**：
  ```powershell
  python main.py
  # 研发与测试从 SW-2026-008 研发母体执行；稳定运行由 00_Infrastructure/auto_pm 的受控部署入口加载。
  ```
- **CLI 命令行入口**：
  ```powershell
  python -m auto_pm -w "<工作空间根目录>" <子命令> [参数]
  ```

---

## 2. CLI 全量命令参考字典 (Command Reference)

<!-- AUTO_DOC_START: CLI_COMMANDS -->
| 命令分组 | 模块源文件 | 核心职责说明 |
|:---|:---|:---|
| `change` | `change.py` | 列出项目变更单 |
| `change` | `change.py` | 查看变更单详情 |
| `change` | `change.py` | 创建变更单（生成 CHG-*.md 文件并更新台帐） |
| `change` | `change.py` | 变更单验证（对账门禁 + 实质内容门禁） |
| `change` | `change.py` | 状态流转（更新变更单章节并持久化状态） |
| `change` | `change.py` | 编辑变更单字段（支持 §4 基本字段 + §6 影响分析字符串字段） |
| `delivery` | `delivery.py` | 构建交付物。 |
| `delivery` | `delivery.py` | 打包交付物为 ZIP。 |
| `delivery` | `delivery.py` | 列出归档版本及说明。 |
| `delivery` | `delivery.py` | 清理旧归档，保留最近 N 个。 |
| `delivery` | `delivery.py` | 查看当前交付物状态。 |
| `git_hook` | `git_hook.py` | 执行 pre-commit 台账一致性校验。 |
| `git_hook` | `git_hook.py` | 执行 commit-msg 生产代码关联单据强校验。 |
| `git_hook` | `git_hook.py` | 安装/激活工作区 Git 物理门禁钩子 (.git/hooks/pre-commit 与 commit-msg)。 |
| `ledger` | `ledger.py` | 对账：扫描项目 CHG 文件 vs 版本变更台账记录 |
| `project` | `project.py` | 列出工作空间内所有项目 |
| `project` | `project.py` | 创建新项目（调用 Copier 模板生成骨架） |
| `project` | `project.py` | 查看项目详情 |
| `project` | `project.py` | 只读采集项目事实包，供 PM 决策与后续派发门禁使用。 |
| `project` | `project.py` | 硬拒绝缺失、过期、篡改或与当前项目不一致的事实包。 |
| `project` | `project.py` | 编辑项目元数据（写入 .copier-answers.yml） |
| `project` | `project.py` | 删除项目（破坏性操作，需 --confirm） |
| `project` | `project.py` | 为已有项目补全元数据文件（.copier-answers.yml 及 PLC 标志文件） |
| `project` | `project.py` | 刷新 PM_SESSION 的 Spec Snapshot 版本号（对齐 spec_registry.json） |
| `project` | `project.py` | 导入外部项目目录到工作空间的 02_在研项目/ 下 |
| `project` | `project.py` | 为已有项目安装 Git Pre-commit 提交门禁与自愈钩子 |
| `project` | `project.py` | 为已有项目卸载 Git Pre-commit 提交门禁钩子 |
| `project` | `project.py` | 查看项目 Git Pre-commit 提交门禁的安装状态 |
| `session` | `session.py` | 检查 PM_SESSION 文件健康状态 |
| `session` | `session.py` | 归档指定章节的早期内容到归档文件 |
| `session` | `session.py` | 从 PM_SESSION 生成只读视图 |
| `spec` | `spec.py` | 运行规范健康检查（SHC-001~010） |
| `spec` | `spec.py` | 生成规范索引文件 |
| `spec` | `spec.py` | 检查/同步规范 frontmatter |
| `spec` | `spec.py` | 生成规范元数据汇总报告 |
| `spec` | `spec.py` | 规范注册表专项 lint 检查（5条注册表级规则） |
| `template` | `template.py` | 列出可用模板 |
| `template` | `template.py` | 对已有项目执行 Copier 模板增量更新 |
<!-- AUTO_DOC_END: CLI_COMMANDS -->

### 2.1 项目生命周期 (`project`)
| 命令语法 | 功能描述 | 典型示例 |
|:---|:---|:---|
| `project list` | 列出当前工作空间所有识别到的业务项目 | `python -m auto_pm -w "." project list` |
| `project show <ID>` | 查看指定项目的详细元数据与门禁状态 | `python -m auto_pm -w "." project show DJ-2026-009` |
| `project create --pid <ID> --name <名称> --type <类型>` | 基于标准模板脚手架新建项目工程 | `python -m auto_pm -w "." project create --pid DJ-2026-010 --name 汇川分拣机 --type plc-standard` |
| `project retrofit <ID>` | 针对老旧工程执行缺失目录与规范基准无损回填 | `python -m auto_pm -w "." project retrofit DJ-2026-009` |

### 2.2 PLC 自动化工程治理 (`plc`)
| 命令语法 | 功能描述 | 典型示例 |
|:---|:---|:---|
| `plc check <ID>` | 执行 53 项全量门禁检查（目录、PRD四件套、SCL规范、快照） | `python -m auto_pm -w "." plc check DJ-2026-009` |
| `plc repair <ID>` | 一键无损修复 PLC 工程结构与缺失 PRD 骨架 | `python -m auto_pm -w "." plc repair DJ-2026-009` |
| `plc parse-vartable <ID>` | 逆向解析源工程中的 14 份变量表并生成标准 `io_points.csv` | `python -m auto_pm -w "." plc parse-vartable DJ-2026-009` |

### 2.3 全局规范治理 (`spec`)
| 命令语法 | 功能描述 | 典型示例 |
|:---|:---|:---|
| `spec index` | 根据 `spec_registry.json` 自动编译生成全库 `00_INDEX` 与 `README.md` | `python -m auto_pm -w "." spec index` |
| `spec check` | 扫描全工作空间规范一致性、Frontmatter 合规性与死链 | `python -m auto_pm -w "." spec check` |
| `spec sync` | 同步全局规范注册表与快照版本 | `python -m auto_pm -w "." spec sync` |

### 2.4 变更与台账管理 (`change` & `ledger`)
| 命令语法 | 功能描述 | 典型示例 |
|:---|:---|:---|
| `change create --pid <ID> --title <标题> --domain <领域>` | 新建标准 12 章节结构化变更单 | `python -m auto_pm -w "." change create --pid DJ-2026-009 --title "SCL算法深化" --domain PLC` |
| `ledger reconcile <ID>` | 执行变更单与 `01_版本变更台帐.md` 的双向对账校验 | `python -m auto_pm -w "." ledger reconcile DJ-2026-009` |

### 2.5 快速原型与系统诊断 (`prototype` & `doctor`)
| 命令语法 | 功能描述 | 典型示例 |
|:---|:---|:---|
| `prototype init --pid <ID> --topology <拓扑>` | 一键生成 1280x800 HMI 触控原型脚手架 | `python -m auto_pm -w "." prototype init --pid DJ-2026-009 --topology both` |
| `doctor` | 检查本地 Python、Qt、Git、Copier 依赖运行环境完整性 | `python -m auto_pm -w "." doctor` |

---

## 3. GUI 驾驶舱深度实操指南 (SOP)

### 3.1 业务项目大厅 (Project Hall)
1. **项目网格浏览**：展示当前所有项目卡片，清晰呈现项目编号、所属事业线、当前门禁等级（G1~G4）；
2. **快速检索过滤**：支持按技术栈（PLC/Python/Web）或项目状态进行多维度即时搜索；
3. **点击进入工作台**：点击任意项目卡片，平滑过渡进入专属项目工作台。

### 3.2 项目工作台 (Workbench)
- **概览 Tab**：查看项目 Charter、当前节拍目标（CT）、工位拓扑图；
- **检查 Tab (Checker)**：点击“重新运行检查”按钮，实时触发 53 项门禁扫描；如存在黄色警告或红色缺失，点击“一键修复”自动无损补齐骨架；
- **变更 Tab (Change)**：右侧面板直接发起变更流程，支持可视化选择影响范围（LOCAL/MODULE/SYSTEM/SAFE）并一键生成变更单；
- **变量表与 IO 映射 Tab (VarTable)**：加载多达 3,000+ 点位的工业点表，支持按工站过滤、批量修改数据类型、重命名与导出西门子/汇川 DB 文件。

### 3.3 规范中心 (Spec Center)
- **规范检索与浏览**：左侧树状列出项目管理域、PLC 自动化域、Python 开发域所有规范；
- **真源与快照比对**：直观展示项目当前引用的规范版本与全局最新版本之间的差异；
- **一键更新索引**：点击顶部“同步索引”按钮，即可在后台触发 `auto-pm spec index` 完成全库索引编译。

### 3.4 AI 上下文协同通道 (AI Context Bridge)
- 当用户在 GUI 界面点击“调用 AI 处理”时，驾驶舱会自动将当前选中的项目、变更单、页面状态序列化至 `.auto-pm/ai_context.json`；
- AI 助手读取该上下文后直接执行精准操作，并将执行结果写回 `.auto-pm/ai_feedback.json`，GUI 界面自动侦听并弹出执行成功提醒。

---

## 4. 故障诊断与排障手册 (Troubleshooting & FAQ)

| 常见故障现象 | 潜在根本原因 | 标准处置措施 (SOP) |
|:---|:---|:---|
| **GUI 启动报 Qt 平台插件错误** | 本地 PyQt6 运行环境未正确安装 | 运行 `pip install PyQt6`，或运行 `python -m auto_pm doctor` 诊断依赖 |
| **PLC 检查提示 `spec_snapshot` 不匹配** | 全局规范已升级，但项目本地快照未同步 | 运行 `python -m auto_pm -w "." plc repair <项目ID>` 更新项目本地快照 |
| **规范索引新增了条目但未显示** | 仅修改了 Markdown 未重新编译索引 | 运行 `python -m auto_pm -w "." spec index` 刷新全局索引 |
| **SCL Linter 报告死锁或语法警告** | SCL 代码中存在无限循环或未声明的变量作用域 | 按照 `LSP-905` 规范检查 VAR 声明，确保全局变量通过 `GlobalVars.stXxx` 访问 |

---

## 5. 一页纸工程师速查表 (CheatSheet)

```text
================================ auto-pm 核心速查表 ================================
【检查项目门禁】: python -m auto_pm -w "." plc check <项目ID>
【一键无损修复】: python -m auto_pm -w "." plc repair <项目ID>
【编译规范索引】: python -m auto_pm -w "." spec index
【新建变更单据】: python -m auto_pm -w "." change create --pid <项目ID> --title <标题>
【对账版本台账】: python -m auto_pm -w "." ledger reconcile <项目ID>
【生成HMI原型】 : python -m auto_pm -w "." prototype init --pid <项目ID> --topology both
===================================================================================
```
