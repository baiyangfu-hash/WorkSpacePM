# auto-pm

统一 CLI 管理 PLC/Python 多技术栈项目的脚手架工具。

> 迁移状态：本目录是 `SW-2026-008` 的**研发母体**（源码、测试、模板、研发记录）；工作空间的**运行入口**是工作区根的 `main.py`，它经 `00_Infrastructure/auto_pm/launcher` 校验并启动 `active_release.json` 指向的不可变 release，**不直接运行本目录的源码**。
>
> 当前阶段（以 WBS 顶部的"当前投影"为准；本段依据 V3.0.26，2026-10-09）：M0、M1 已验收；M2 的 U 批次与治理卡已验收，`M2-DEP-TECH`（构建 M2 发布包并切换**开发运行时**为 `1.3.3-4b5c630`）与 `M2-PUSH`（把 M2 以隔离分支一次推送到远端）均记录为已完成。**`main` 尚未合并**，M2 里程碑的总状态以 WBS 当前投影为准——该投影在 V3.0.26 里仍写 `IN_PROGRESS`，会随用户验收更新。本文不替这些记录作结论。
>
> 日常用法见 `SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md`；没有 AI 时的最低限度维护见同目录的 41 号手册（候选）。

## 模块成熟度矩阵 (Module Maturity)

为清晰产品边界与功能稳定性，auto-pm 模块按以下分类收口：

| 模块分类 | 包含功能 | 成熟度等级 | 说明 |
| :--- | :--- | :---: | :--- |
| **Core 核心** | 项目 CRUD、PLC 规范检查、变更管理状态机、QML 桌面驾驶舱、SQLite 缓存 | `[Stable 稳定]` | 核心主线，经过长周期 dogfooding 全量回归验证 |
| **Optional 工具箱** | Modbus TCP 联调工坊、模板增量更新、变量表多格式转换 | `[Toolbox 可选]` | 通用工坊/工具箱能力，按需使用 |
| **Experimental 实验性** | 约束工作流自愈系统 (Workflow Engine) | `[Experimental 实验]` | 自动守护与修复实验性扩展 |

## 环境诊断与自检 (Doctor)

在初始化或跨机器部署后，建议通过 CLI 或 GUI 进行一键环境自检：

```bash
# 运行一键环境与依赖健康诊断
auto-pm doctor
```

GUI 驾驶舱亦可在 **系统设置 (Settings)** 页面右上角点击 **🩺 环境自检** 按钮进行图形化诊断。

## 安装

### 开发模式安装

```bash
# 进入工作空间根目录
cd <工作空间根>

# 激活工作空间虚拟环境
& ".\.venv\Scripts\Activate.ps1"

# 安装基础设施运行位为可编辑模式
python -m pip install -e "00_Infrastructure/auto_pm" --no-deps

# 验证驾驶舱健康状态
python -m auto_pm doctor
```

### 依赖

**可复现的安装以锁文件为准**：`00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt`（108 个固定版本，用 `python -m pip install --no-deps -r <锁文件>` 安装；配套记录见同目录 `environment_record.json`）。下面的下限只是 `pyproject.toml` 的声明；开发工具（ruff、mypy、pytest、pytest-cov）的实际版本与 `pyproject.toml` 的 dev 约束目前不一致，以锁文件和环境记录为准。

- Python >= 3.11（锁文件按 3.12 制作）
- Click >= 8.1.7
- Rich >= 14
- Pydantic >= 2.10.6
- pydantic-settings >= 2.6.1
- PyYAML >= 6.0
- Copier >= 9.7.1,<10
- PySide6 >= 6.8,<7

## 命令一览（25 个命令组）

下表来自在 `d3c50a8b` 上运行 `main.py --help` 的实测输出，只列名称与一句话说明；每个命令组的用法用 `main.py <命令组> --help` 查看。

| 命令组 | 说明 |
|---|---|
| `pm` | 面向用户的 PM 门面：计划、确认、执行、恢复与验收（`resume`、`orient`、`plan`、`approve`、`confirm-start`、`execute`、`accept`、`inbox`、`pending`、`drafts`） |
| `continuity` | 事务化连续性 v2：Mission、Work、Run、Lease、Checkpoint、Handoff.v2、Dispatch |
| `context` | 平台无关、只读的调用上下文（`context resolve`） |
| `decision` | 审批结构化决策包 |
| `implementation-card` | 受限的实施卡工作流 |
| `git-hook` | Git 提交硬锁门禁：`install`、`pre-commit`、`commit-msg`、`preflight`、`release-gate` |
| `ledger` | 版本变更台账对账（`ledger reconcile`，只读） |
| `change` | 变更单创建、查询、状态流转 |
| `project` | 项目列表、创建、查看、编辑、导入、补全元数据 |
| `plc` | PLC 项目：初始化、检查、修复、文档一致性、工业源工程摄取（LSP-907） |
| `python` | Python 项目：初始化、检查（210/211/220 规范） |
| `doc` | 文档与代码一致性门禁、自动区维护 |
| `spec` | 规范管理：检查、索引、frontmatter、报告 |
| `template` | Copier 模板列表与增量更新 |
| `vartable` | 变量表解析、编码检测、格式识别 |
| `constraint` | 约束合规检查、守护、自愈 |
| `delivery` | 交付物构建、打包、归档、状态 |
| `doctor` | 环境与依赖健康诊断 |
| `clean` | 清扫游离日志、散装脚本、临时产物 |
| `dogfood` | 驾驶舱自用隔离、指纹与稳定版外部复核 |
| `pm-session` | PM_SESSION 检查、归档、视图 |
| `gui` | 启动桌面应用（见下文"GUI 功能"） |
| `handoff` | handoff.v1 交接包（历史格式；新流程用 `continuity handoff`） |
| `workflow`、`prototype` | 保留历史名称以便发现；已隔离的旧技能不再加载，`prototype` 标注为 pm-workflow 专属 |

## CLI 使用

### 全局选项

```bash
auto-pm -w <workspace> <command>   # 指定工作空间根目录
auto-pm -v, --version              # 显示版本号
auto-pm -h, --help                 # 显示帮助
```

`-w` 必须放在子命令之前。也可通过环境变量 `AUTO_PM_WORKSPACE` 指定。

### project - 项目管理

```bash
# 列出工作空间内所有项目（支持业务线/技术栈筛选）
auto-pm project list
auto-pm project list --business-line SW       # 按业务线筛选（SW/DJ/ZD/XT/WX）
auto-pm project list --stack plc              # 按技术栈筛选（plc/python）

# 创建新项目（调用 Copier 模板生成骨架）
auto-pm project create --stack plc --id DJ-2026-010 --name 边框缓存机
auto-pm project create --stack python --id SW-2026-009 --name 数据分析工具
auto-pm project create --stack plc --id DJ-2026-010 --name 边框缓存机 --dry-run  # 预览模式

# 查看项目详情（支持 JSON 输出）
auto-pm project show DJ-2026-010
auto-pm project show DJ-2026-010 --json

# 编辑项目元数据（写入 .copier-answers.yml）
auto-pm project edit DJ-2026-010 --phase 调试中
auto-pm project edit DJ-2026-010 --desc "新描述" --version V1.1.0

# 删除项目（破坏性操作，需 --confirm）
auto-pm project delete DJ-2026-010 --confirm

# 为已有项目补全 .copier-answers.yml 元数据文件
auto-pm project retrofit DJ-2026-010

# 导入已有项目目录（复制到 02_在研项目/ 并补全元数据）
auto-pm project import /path/to/existing/project
auto-pm project import /path/to/existing/project --move         # 移动而非复制
auto-pm project import /path/to/existing/project --business-line SW  # 指定业务线
```

### plc - PLC 项目管理（LSP-907）

```bash
# 创建 PLC 项目骨架（调用 Copier plc-standard 模板）
auto-pm plc init DJ-2026-010 --name 边框缓存机

# 检查项目结构是否符合 LSP-907 规范
auto-pm plc check DJ-2026-010
auto-pm plc check DJ-2026-010 --json
auto-pm plc check --all              # 检查工作空间所有 PLC 项目

# 自动修复项目结构问题
auto-pm plc repair DJ-2026-010
auto-pm plc repair DJ-2026-010 --rename    # 确认文件重命名（破坏性操作）
auto-pm plc repair DJ-2026-010 --dry-run   # 仅预览不执行

# 文档命名标准化（默认仅预览，--apply 执行重命名）
auto-pm plc standardize DJ-2026-010
auto-pm plc standardize DJ-2026-010 --apply
```

### python - Python 项目管理

```bash
# 创建 Python 项目骨架
auto-pm python init SW-2026-009 --name 数据分析工具

# 检查 Python 项目规范
auto-pm python check SW-2026-009

# 修复 Python 项目常见结构与元数据问题
auto-pm python repair SW-2026-009
```

### change - 变更管理

```bash
# 列出项目变更单（支持按状态/领域筛选；--full 标题列不截断）
auto-pm change list DJ-2026-010
auto-pm change list DJ-2026-010 --status implementing
auto-pm change list DJ-2026-010 --domain PLC
auto-pm change list DJ-2026-010 --full                # 标题列 fold 换行不截断

# 查看变更单详情（渲染 §6 影响分析 + §8 审批记录 + §9 实施记录 + §10 验证项共 10 张表）
auto-pm change show CHG-PLC-2026-001

# 创建变更单（生成 CHG-*.md 文件并更新台帐）
auto-pm change create \
  --pid DJ-2026-010 \
  --domain PLC \
  --nature REQ \
  --scope PLC \
  --applicant fubai \
  --background "新增输送线急停逻辑" \
  --necessity "安全规范要求"

# 编辑变更单（CLI 支持 8 个字符串/枚举字段；dict 字段 constraint_impacts/domain_impacts 留给 GUI）
auto-pm change edit CHG-PLC-2026-001 --background "更新的背景说明"
auto-pm change edit CHG-PLC-2026-001 --risk-level high --mitigation "增加联锁测试"
auto-pm change edit CHG-PLC-2026-001 --propagation-chain "PLC -> HMI -> DOCU"
auto-pm change edit CHG-PLC-2026-001 --urgency critical

# 状态流转（更新变更单章节并持久化状态 + DB 记录审批历史）
auto-pm change transition CHG-PLC-2026-001 --to submitted
auto-pm change transition CHG-PLC-2026-001 --to approved --approver fubai
auto-pm change transition CHG-PLC-2026-001 --to implementing --approver fubai
auto-pm change transition CHG-PLC-2026-001 --to completed --approver fubai \
  --verification-conclusion "全部通过：单元测试 + 集成测试 + 现场联调"
```

### template - 模板管理

```bash
# 列出可用 Copier 模板
auto-pm template list

# 对已有项目执行 Copier 模板增量更新
auto-pm template update DJ-2026-010
auto-pm template update DJ-2026-010 --overwrite
```

### gui - 桌面 GUI

```bash
# 启动 GUI 桌面应用
auto-pm gui
auto-pm gui --debug    # 调试模式（开启日志详细输出）
```

## GUI 功能

> **当前默认入口**：`main.py gui` 启动**老板驾驶舱**，只读取项目注册表和已存在的连续性记录；`main.py gui --advanced` 才打开下面描述的原专业工作台。老板驾驶舱的卡片只显示项目、需求、里程碑、进展、阻塞、验证、风险、当前负责人和下一步，内部编号放在"证据抽屉"里按需展开。（依据：`main.py gui --help`；`37_Cockpit_OS_…迁移总方案_PM.md` §20。）

> 以下为原专业工作台的功能清单（`--advanced`）。V0.6.0 起 GUI 已迁移至 QML 运行时，V0.8.0 QML 完整覆盖，V0.9.0 旧 QWidget 完整移除 + CLI 标志退役 + Facade 接口层落地（5 个域 Facade + 5 个域 Bridge）。

- **项目中心式导航** - QML 主窗口 + 左侧侧边栏 + StackLayout 切换主区域
- **项目列表首页** - 项目卡片网格（编号/名称/技术栈徽标/版本/阶段/业务线），统计栏 + 搜索 + 筛选（ProjectListView.qml）
- **项目工作区** - Tab 容器（概览/变更/检查/文档），工程资产摘要（WorkspaceView.qml）
- **变更中心** - 变更列表 + 详情面板 + 创建/状态流转/编辑对话框（ChangeCenterView.qml）
- **变更创建向导** - 分步向导：基本信息 → 变更描述 → 提交确认（NewChangeDialog.qml）
- **StatusMachineView 可视化状态机** - 水平展示 12 状态节点 + 11 箭头；当前状态高亮 + 可达状态可点击（StatusMachineView.qml）
- **ApprovalTimeline 审批时间线** - 垂直展示审批历史：圆点+连接线+状态流转+审批人+意见+日期（ApprovalTimeline.qml）
- **PropagationView 传播链可视化** - 水平展示跨领域传播链：节点+箭头+领域中文名映射（PropagationView.qml）
- **4 维度列表筛选** - 状态 Tab + 领域 + 紧急程度 + 项目下拉筛选
- **全局功能页** - 规范中心（SpecCenterView.qml）/模板管理（TemplateView.qml）/报告中心（ReportView.qml）/系统设置（SettingsView.qml）
- **项目 CRUD 对话框** - 新建向导/编辑/导入对话框（qml/dialogs/）
- **变量表编辑器** - 8 列变量表展示 + UndoStack ≥20 步（VarTableEditorView.qml）
- **DB 缓存优先** - 优先读 SQLite 索引缓存，缺失时回退文件系统扫描
- **缓存同步** - 工具栏同步按钮，调用 SyncService 增量扫描（file_mtime 判据）

## 开发指南

### 测试

> `Taskfile.yml` 已标注为"2026-08-28 冻结前的母体口径，仅供开发回退参考"，下面的 `task` 命令不再是主路径。

```bash
# 在本目录运行测试（-o addopts= 去掉 pyproject 里默认的覆盖率/报告输出，避免在目录里写出 coverage/ 等文件）
python -B -m pytest -o addopts= --no-cov -p no:cacheprovider -q tests

# 并行（4 进程）：Linux 上约 4～6 分钟；Windows 全量分组运行约 2.5 小时
python -B -m pytest -o addopts= --no-cov -p no:cacheprovider -q -n 4 tests
```

**已知失败（不是新问题）**：Windows 本地 15 项（14 个变量表真实样例缺失 + `test_fixture_health` 1 项）；Linux 35 项（另含 Linux 上不成立的真实 Hook E2E 等）。只有出现这些名单之外的失败才需要处理。

**GitHub 上的自动检查（早期预警）**：推送到非 `main` 分支时，`.github/workflows/sw008-ci.yml` 会在 GitHub 的 Linux 虚拟机（Python 3.12，按锁文件装依赖）上自动运行：工具自检、密钥扫描、`ruff`、`mypy --platform win32`、全量测试（4 进程），再把失败与已知基线逐项比对，约 7 分钟（首次落地的运行为 7 分 5 秒）。结果有三种：`PASS`、`PASS_KNOWN_BASELINE`（失败集合与基线逐项相等）、`FAIL`（出现新失败、基线项意外通过、或运行崩溃）。`PASS_KNOWN_BASELINE` **不是全绿，也不替代本地门禁**。工具与基线文件在本目录的 `tests/tools/sw008_ci/`。它不检查真实 Hook 的 E2E 和 Windows 路径语义，这两块仍靠本地 Windows 门禁。

### 代码质量

```bash
# 格式化代码
task lint-fix

# Lint 检查
task qa

# 类型检查
mypy auto_pm

# 运行 pre-commit
uv run pre-commit run --all-files
```

### 项目结构

```
auto-pm/
├── auto_pm/                        # 主包（五层整洁架构）
│   ├── application/                # 应用层 Facade（5 个用例编排入口）
│   │   ├── workbench_facade.py     # 驾驶舱 + 项目列表 + 项目工作台
│   │   ├── change_facade.py        # 变更创建/流转/列表/详情
│   │   ├── spec_facade.py          # 规范中心概览/检查
│   │   ├── delivery_facade.py      # 文档刷新/报告/资产摘要
│   │   └── system_facade.py        # PM_SESSION/模板/缓存管理
│   ├── contracts/                  # DTO/Command/Event 接口契约
│   ├── domain/                     # 核心领域能力（plc/spec/change/vartable/...）
│   ├── infrastructure/             # DB/日志/配置/文档注入等基础设施
│   └── ui/                         # CLI + QML + Bridge 表现层
│       ├── cli/                    # Click CLI 入口
│       │   ├── __main__.py         # auto-pm 主入口
│       │   ├── project.py          # project 子命令组（CRUD + import）
│       │   ├── change.py           # change 子命令组（变更管理）
│       │   ├── gui.py              # gui 命令（QML GUI 启动）
│       │   ├── plc/                # PLC 技术栈插件
│       │   └── python/             # Python 技术栈插件
│       ├── qml/                    # QML 视图/组件/对话框/主题/模型/桥接
│       ├── global_pages/           # 全局页面适配器
│       ├── models/                 # Qt 模型适配器
│       └── registry.py             # Facade 装配器
├── templates/                      # Copier 模板仓库
│   ├── plc-standard-project/       # PLC 标准项目模板
│   ├── plc-shared-library/         # PLC 共享函数库模板
│   ├── plc-test-suite/             # PLC 测试套件模板
│   └── python-tool/                # Python 工具项目模板
├── tests/                          # 测试（221 个测试文件、3541 项，2026-10-10 在 d3c50a8b 实测；含 application/change/core/db/plc/spec/qml/e2e/vartable 等）
│   ├── plc/                        # PLC 规范检查测试
│   ├── spec/                       # 规范中心测试（SHC-001~017）
│   ├── modbus/                     # Modbus 通信测试
│   └── ...                         # 其余领域测试
├── 01_启动/                        # 章程/立项/发布门禁
├── 02_规划/                        # PRD/INT/DSN/TEC/里程碑/原型
├── 03_执行/                        # 执行阶段资产
├── 04_监控/                        # 变更管理/过程监控
├── 05_收尾/                        # 测试策略/归档
├── 06_交付物/                      # 用户文档与交付资料
└── pyproject.toml                  # hatchling 构建配置
```

### 技术栈

| 类别 | 技术 |
|------|------|
| CLI 框架 | Click |
| 终端输出 | Rich |
| 数据模型 | Pydantic v2 |
| 配置管理 | pydantic-settings |
| 模板引擎 | Copier + Jinja2 |
| GUI 框架 | PySide6 (QML 运行时) |
| 数据库 | SQLite3 (WAL 模式) |
| 构建 | hatchling |
| 代码质量 | ruff + mypy (strict) + pytest |


## 文档导航

### 规划文档（`02_规划/`，当前设计真源）

| 文档 | 路径 | 说明 |
|------|------|------|
| PRD 产品需求文档 | `02_规划/001_产品需求文档_PRD.md` | 产品需求定义 |
| INT 接口文档 | `02_规划/002_接口文档_INT.md` | DTO/Command/Event 接口契约 |
| DSN 详细设计说明书 | `02_规划/003_详细设计说明书_DSN.md` | 五层架构详细设计 |
| TEC 技术方案文档 | `02_规划/004_技术方案文档_TEC.md` | 技术选型与方案（接口优先策略） |
| 里程碑与实施计划 | `02_规划/005_里程碑与实施计划.md` | **[待确认]** 该文件已不在 `02_规划/` 原位置（在 `d3c50a8b` 的树里找不到），请确认是否已归档，再更新或删除此行 |
| UI 架构原型 | `02_规划/Html原型预览/` | HTML 交互原型目录 |
| UI 原型说明 | `02_规划/007_UI架构原型说明.md` | 原型配套说明 |

### 启动与治理文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 项目立项章程 | `01_启动/001_项目立项章程_CHARTER.md` | 项目启动与目标边界 |
| 立项表 | `01_启动/01_立项表_PROJ.md` | 立项登记与基础信息 |
| 发布门禁规范 | `01_启动/007_发布门禁规范_REL.md` | 发布前质量门禁定义 |
| 测试策略与验收规程 | `05_收尾/003_测试策略与验收规程_TEST_PLAN.md` | 收尾阶段测试与验收基线 |

### 当前现行的治理文档（工作区级，路径相对工作区根）

| 文档 | 路径 | 说明 |
|---|---|---|
| 日常迭代操作手册 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md` | 每次开工的固定动作 |
| 驾驶舱角色与边界 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/40_驾驶舱角色与边界_PM.md` | 用户、Agent、驾驶舱各管什么 |
| PM-Flow 总方案与 WBS | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 顶部"当前投影"是状态真源 |
| 协作规则 | `AGENTS.md` | 所有 AI 共用的入口 |

### 项目管理文档

| 文档 | 路径 | 说明 |
|------|------|------|
| PM_SESSION | `PM_SESSION_SW-2026-008.md` | 项目会话文档（**单一状态真源**） |
| CHANGELOG | `CHANGELOG.md` | 变更日志 |

### 已废弃文档

以下文档已标记 `[DEPRECATED]`，仅供参考，请勿用于指导开发：

| 文档 | 废弃原因 | 替代文档 |
|------|----------|----------|
| `00_项目基础信息/*` | 旧 V2.x 路径整体退役，已拆分到 5 大过程组目录 | `01_启动/`、`02_规划/`、`05_收尾/` |
| `02_设计/*` | 旧设计目录名已收口为 `02_规划/` | `02_规划/001~008` |
| `09_整改项/archive/` 下全部文档 | V2.0 整改/迭代报告 | `PM_SESSION_SW-2026-008.md` |

## Dogfooding 证据

auto-pm 自身使用 CHG-*.md 变更单流程管理迭代（M4 Dogfooding 持续化）。已闭环 30+ 次（CHG-SCPT-2026-001/062-100，详见 `04_监控/01_变更管理/01_变更单/CHG-SCPT/` 目录）。

代表性闭环：

| 变更单 | 内容 | 状态 |
|--------|------|------|
| CHG-SCPT-2026-001 | M0 基座清理（TD-T01~T04 修复 + ruff/mypy 清理 + 元测试升级） | ✅ 已归档 |
| CHG-SCPT-2026-087/088/089 | V0.7.0 PM_SESSION 三层真源架构（归档 + 工具化 + 影子台账退役） | ✅ 已关闭 |
| CHG-SCPT-2026-090/091/092 | V0.8.0 QML 完整覆盖 + 旧代码激进清理 | ✅ 已关闭 |
| CHG-SCPT-2026-093/094 | V0.9.0 旧 QWidget 完整移除 + CLI 标志退役 | ✅ 已关闭 |
| CHG-SCPT-2026-099 | QML 编码损坏系统性修复（约 250 处） | ✅ 已关闭 |
| CHG-SCPT-2026-100 | V0.9.1 诊断报告失真度核查 + 真源同步 | ✅ 已关闭 |

每个里程碑必须经过 CHG-*.md 流程（spec.md §9.1 固定模板 10 步：创建→submitted→under_review→approved→implementing→pending_acceptance→accepting→completed→closed→回写 PM_SESSION）。

## 工具链关系

| 工具 | 编号 | 与 auto-pm 关系 |
|------|------|----------------|
| pm-mgr | SW-2026-007 | **已取代** - auto-pm 完全替代 pm-mgr |
| plc-check | — | **已取代** - auto-pm plc check/repair/standardize 替代 |
| specmgr | SW-2026-006 | **已吸收** - 规范管理能力已并入 `auto-pm spec` 子命令 |
| plc-var-parser | SW-2026-001 | **独立** - 变量表解析工具；V2.3 变量表整合后吸收 |

## 版本管理

本项目遵循 [语义化版本](https://semver.org/)，使用 [Conventional Commits](https://www.conventionalcommits.org/) 自动生成变更日志。

提交信息规范见工作空间 `.trae/rules/git-commit-message.md`。
