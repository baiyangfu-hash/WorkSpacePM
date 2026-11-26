---
version: "V2.1.0"
status: "正式发布"
created: "2026-08-17"
updated: "2026-11-26"
spec_id: "USER_GUIDE"
project_id: "SW-2026-008"
title: "auto-pm 自动化项目管理工具 - 用户操作指南与排障手册"
---

# auto-pm 自动化项目管理工具 - 用户操作指南与排障手册 (USER_GUIDE V2.1.0)

> **面向对象**：现场电气工程师、PLC 研发工程师、全栈软件开发、项目经理（PM）、AI 协作助手  
> **适用版本**：auto-pm 1.3.3+ 工作空间基础设施现役运行位（GUI + 总控屏 + CLI + AI Agent 协同）
> **运行源码入口**：工作空间根目录 `.\.venv\Scripts\python.exe .\main.py`（由 `00_Infrastructure/auto_pm/active_release.json` 指向现役发布包）；本项目目录保留文档、交付物、总控屏脚本与 WBS/变更证据。

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
  # 工作空间根入口会优先加载 00_Infrastructure/auto_pm
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
| `change` | `change.py` | 创建变更单（生成 CHG-*.md 文件并更新台账） |
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
| `project` | `project.py` | 删除项目（破坏性操作，强烈建议使用 archive 代替） |
| `project` | `project.py` | 归档项目（物理迁移并建立历史归档台账） |
| `project` | `project.py` | 从归档目录恢复项目回活跃在研目录 |
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

---

## 6. 现役驾驶舱（1.3.3）进门流、门禁分档与排障补充

### 6.1 进门定位、单机轻轨交接与 WBS 进度核算

1. **新会话进门**：在控制根运行 `pm_flows.py entry <项目编号>`。一次就能看到项目体检、项目计划状态、本机交接和「先读」文件。只做体检时用 `checkup`。下面以 `SW-2026-008` 为例：

   ```powershell
   .\.venv\Scripts\python.exe -B '.\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\scripts\pm_flows.py' entry SW-2026-008
   ```
2. **单机轻轨交接（PM-056）**：日常单机模式下，在隔离工位内通过 `SW8/scripts/pm_handoff.py set-focus` / `log` 更新 `<项目>/{04|11}_监控/交接交换区/`（`focus.json` 与 `journal.jsonl`），并用 `pm_handoff.py validate <项目编号> --root <工位> --require-exists` 校验；禁止直接写控制根交接区。
3. **WBS 项目计划表**：在「项目计划状态」找到任务和卡号，按交接的「先读」打开计划表、实施卡和回执。计划状态按 `main`、分支和证据现算。里程碑进入「待用户验收」后，由用户本人确认，通过后把确认时间和凭据登记在计划表末尾的「验收记录」。记录入库后，计划状态显示「已达成」。

### 6.2 三级门禁分档（L1 / L2 / L3）

提交前统一在控制根运行 `.\.venv\Scripts\python.exe .\main.py gate precheck --worktree <工位> --defer-full [--json]` 自动判档：

- **L1（本地快速闭环）**：命中文档路径规则且分档结果为 L1，或命中已核实样板路径。通过本机自检与 `gate precheck` 后可由 `pm_merge.py merge <工位>` 合入 `main`。
- **L2（云端按组门禁）**：例如总控屏目录的 README，按目录规则属于 L2。先推送工位分支，再从控制根用 `.\.venv\Scripts\python.exe -B .\main.py gate start --worktree <工位>` 派发。
- **L3（云端全量与插件）**：例如核心模块、受保护规则和本机交接 JSON 文件。在 `gate start` 加 `--full`。命中 `FLOW-001` 的「要你点头」范围时，还须按 `AUD-001` 取得独立审计。

L2/L3 的本机轻量检查通过后，`--defer-full` 仍可能返回 `UNVERIFIED` 和退出码 `1`，表示还需托管门禁。派发后保存任务号，从控制根运行 `.\.venv\Scripts\python.exe -B .\main.py gate status <任务号>` 对账。状态为 `passed` 且回执对应同一候选和 `main` 基线后，再走本机合并。

### 6.3 高频实操排障清单

| 常见现象 | 根因 | 处置措施 |
|---|---|---|
| 报 `RUNTIME_IDENTITY_UNVERIFIED` | 直接调用了 `SW8\main.py` 而非根目录入口 | 始终在控制根调用 `.\.venv\Scripts\python.exe .\main.py` |
| 变更单报 `D-154` 审批失效 | `--to approved` 后又修改了 `§5` 涉及文件 | 批准前务必在 `§5.1/§5.2` 填齐精确文件路径 |
| `implementation-card precheck` 拒绝 | 实施卡 `> 依据：` 行出现了 `CHG-...` | 变更单号只放 `> 变更单：` 行，`> 依据：` 只填规范号 |
| `gate start` 首次派发即失败 | 工位分支尚未推送到 `origin` | `gate start` 前先执行 `git -C <工位> push -u origin <分支>` |
| `change transition --to completed` 拒流转 | `--verification-conclusion` 缺少“通过”或含“不通过” | 结论文案必须明确含“通过”且不含“不通过” |
| Windows 本机 `mypy` 报缺模块或错误 | 未在 `SW8/` 下带隔离参数，或把 `pm_merge.py` 与 `tests/` 混跑 | 在 `SW8/` 下用 `--platform win32 --no-incremental --no-sqlite-cache --cache-dir=/dev/null`，并与 `pm_merge.py` 分开校验 |
| 零依赖 CI 脚本上线后缺包 | 仅用 `python -I` 仍能看到 `.venv/Lib/site-packages` | 必须用 `python -I -S` 验证纯标准库隔离 |
| 发版或本地钩子报缺 `dirname` | Git for Windows 的 `usr\bin` 未在 `PATH` 中 | 执行前将 `C:\Program Files\Git\usr\bin` 加入当前终端 `PATH` |
