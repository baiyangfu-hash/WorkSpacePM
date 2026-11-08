# Auto-PM 工业级 AI 研发工作台与项目管理驾驶舱

<div align="center">

**面向工业自动化、西门子 PLC SCL 编程与 Python 全栈研发的 AI-Native 智能工作台**

</div>

---

## 🌟 系统全景与三大核心支柱

Auto-PM 为工业电气工程师与软件开发者提供了从**“需求澄清 $\rightarrow$ PRD/架构设计 $\rightarrow$ SCL/Python 编码 $\rightarrow$ 变量表批量映射 $\rightarrow$ 5大阶段门禁 $\rightarrow$ 免安装交付打包”**的全生命周期工程解决方案：

```
                         Auto-PM 工业级协同研发体系
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 🖥️ 【桌面驾驶舱 (GUI Cockpit)】                                            │
  │    • 深色实底磨砂拟物面板 / 70% 焦点遮罩 / 20 维全景交互 / 双击即开          │
  ├─────────────────────────────────────────────────────────────────────────────┤
  │ 🧠 【跨 AI 协作技能矩阵 (.trae/skills/ & .cursor/rules/)】                  │
  │    • cockpit-entry：薄入口，进门先跑只读定位 pm orient（pm-workflow 已隔离） │
  │    • fullstack-engineer：Python Clean Architecture 5层整洁架构、自动化测试   │
  │    • plc-electrical-engineer：西门子 S7-1200/1500、SCL 代码生成、变量表/IO   │
  ├─────────────────────────────────────────────────────────────────────────────┤
  │ ⚙️ 【底层规则与门禁引擎 (auto_pm CLI)】                                      │
  │    • 3800+ 项自动化测试 / SCL 规范 Linter / 阶段门禁 G1~G4 / 动态自动寻根    │
  ├─────────────────────────────────────────────────────────────────────────────┤
  │ 📚 【Obsidian 全局规范知识库 (00_Obsidian_Base/)】                          │
  │    • 30+ 工业研发规范 / spec_registry 注册表 / 毫秒级自动索引重构与自愈      │
  └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 极速上手指南 (Quick Start)

> 当前版本（1.3.3）没有免安装包：旧的 V1.1.0 打包产物只留在 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/06_交付物/archive/` 作历史存档，不再适用。所有电脑都按下面的源码方式安装。

### 源码克隆与环境初始化

#### 1. 克隆代码仓库
```bash
git clone <repository_url> My_Workspace
cd My_Workspace
```

> 💡 **Git 中文路径防乱码提示**：建议在终端执行一次 `git config --global core.quotepath false`，防止中文目录显示为八进制转义。

#### 2. 装环境 → 自检 → 定位（换电脑、换云服务商、换 AI agent 都照这三步）

**第一步：装环境。** 没有 `.venv`，或 `.venv` 不是 Python 3.12，就装：
- **Windows**：在工作空间根目录双击 **`setup_env.bat`**。脚本只接受 Python 3.12（依赖锁定文件只覆盖 3.12）；自动创建专属 `.venv`（已有的 `.venv` 不是 3.12 时会停下并提示，不会删除它）；按依赖锁定文件 `00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt` 以 `--no-deps` 精确安装全部桌面 GUI、CLI 与单测依赖包，并运行 `pip check`。
- **Linux / 云端 / macOS**：在工作空间根目录执行 `sh 00_Infrastructure/auto_pm/environment/setup_env.sh`，步骤与 `setup_env.bat` 相同、用同一份锁定文件。云端会话缺 Qt 系统库时它会自己 `apt-get` 装（需要 root）。根目录 `requirements.txt` 已不再列依赖，只指向这份锁定文件；锁定文件冻结于 Windows、Python 3.12，CI 在 Linux 上安装的是同一份，macOS 和其他 Python 版本没有完整验证。

**第二步：自检。** 装完（或开新会话时）跑一遍，确认环境真的能用：
- **Linux / 云端**：`sh 00_Infrastructure/auto_pm/environment/cloud_selfcheck.sh`。只读，不改任何东西；退出码 **0 才能开工**，非 0 就照它打印的 `[失败]` 行下面的"补救"命令做，再跑一遍。
- **Windows**：目前没有等价的自检脚本（登记为 D-156 卡②，做成 `main.py` 自带的同一个入口）；在那之前，以 `setup_env.bat` 末尾 `pip check` 通过为准。

**第三步：定位。** 环境没问题后，AI agent 先读 `AGENTS.md` 和 `.trae/skills/cockpit-entry/SKILL.md`，按它做只读定位，再动手。没有已授权的 Work、Run 与有效租约之前只允许只读命令。

**换云服务商 / 换 agent 时，哪些跟着仓库走、哪些要在云端设置页自己填：**

| 跟着仓库走（克隆即得） | 要在那家云自己的设置页填 |
|---|---|
| `setup_env.sh`、`cloud_selfcheck.sh`、依赖锁定文件、`AGENTS.md`、`CLAUDE.md` | 安装脚本 / 初始化命令（粘贴下面那几行）；网络放行（至少能访问 PyPI，装 Qt 系统库还要能访问系统包源）；以 root 运行（`apt-get` 要用） |

安装脚本（脚本运行时的起始目录假定是"放仓库的那一层"，若不是，改成进入仓库根目录再执行）：
```bash
cd WorkSpacePM   # 仓库目录名；起始目录就是仓库根时，这一行去掉
git fetch --unshallow origin 2>/dev/null || true   # 浅克隆补成完整历史，失败不拦
AUTO_PM_INSTALL_SYSLIBS=1 sh 00_Infrastructure/auto_pm/environment/setup_env.sh \
  || echo "[警告] setup_env.sh 没成功；进会话后运行 cloud_selfcheck.sh 看缺什么"
```
不要把令牌、密码写进环境变量或脚本（多数云是明文保存）。Claude Code 的 `SessionStart` 钩子（`.claude/hooks/session-start.sh`）只对 Claude Code 生效，而且在"项目线程"这类会话里不一定被执行，所以**不能只靠它**：其他 agent、其他云都要靠上面这三步。别家云的安装脚本字段叫什么、起始目录是哪一层，未核实，以它的文档为准。

#### 3. 启动桌面驾驶舱
- **方式 1**：双击根目录下的 **`双击启动驾驶舱.bat`**；
- **方式 2**：在终端直接运行：
  ```bash
  python main.py
  ```

---

## 🛠️ 核心功能矩阵 (Features)

### 1. 业务项目大厅与工作台
- 自动扫描并识别工作空间内所有西门子 PLC 工程（如 `DJ-2026-005`）与 Python 自动化工具；
- 聚合展示项目阶段、技术栈、交付看板与资产统计。

### 2. 规范体检与一键安全修复
- 内置 LSP-905（西门子 SCL 代码规范）、DEV-030（双轨交付规范）等硬门禁；
- 一键扫描项目缺失文件，**支持一键补全结构，绝不篡改业务逻辑代码**。

### 3. 变量表与 IO 映射高能编辑器
- 支持万行级 PLC 变量与系统点表毫秒级渲染；
- 提供 **“批量改类型”** 与 **“批量改地址”**，告别繁琐的手动编辑。

### 4. 平台变更管控与 9 步闭环流转
- 标准化 12 章节工业变更单向导；
- 严格遵循 `草稿 → 评审 → 审批 → 实施 → 验证 → 关闭` 9 步生命周期。

---

## 🧠 AI 技能生态与协作 (Agent Skills)

本工作空间由 **Trae / Cursor / Antigravity / Claude** 等多个 AI 共用，规则单一真源维护于 `AGENTS.md`：

- **`cockpit-entry`**：驾驶舱薄入口，任何 agent 进门先确认控制根与项目编号、运行只读定位命令 `pm orient <项目编号> --json`（新克隆的工作区在发布指针更新前还没有这条命令，先用 `pm resume <项目编号> --json`）；
- **`pm-workflow`**：已退役隔离（2026-09-09），禁止使用；PM 是治理角色，通过 CHG、Decision 与 Continuity v2 工作，`PM_SESSION` 仅作历史证据；
- **`fullstack-engineer`**：全栈开发技能，负责 Python 5 层整洁架构编码与单测；
- **`plc-electrical-engineer`**：电气工程技能，主适配西门子 S7-1200/1500 与 SCL。

---

## 📚 Obsidian 全局规范库自动联动

工作空间内置完整的 Obsidian 知识库（位于 `00_Obsidian_Base全局规范文件仓库/`）。  
在修改任何规范后，只需在根目录执行：

```bash
python main.py spec sync
```

系统将自动重新生成 `00_INDEX_全局规范索引.md` 及各业务线通用规范 README，实现知识库 100% 实时自愈与索引对齐！

---

## 🧪 自动化测试与质量验证

驾驶舱自身的测试都在 SW-2026-008 项目目录下，先进入该目录再运行：

```bash
cd 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具

# 全量单测（约 3800 项）。这是 CI 用的命令：关掉 pyproject 里默认的覆盖率选项、4 进程并行
python -m pytest -q -p no:cacheprovider -o addopts= -n 4 tests

# GUI 桌面端冒烟测试 (真机交互与快照)
python scripts/gui_smoke_test.py --workspace <工作区根目录> --output <输出目录>
```

---

## 📄 开源许可证

本项目遵循 [Apache-2.0 License](LICENSE)。
