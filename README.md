# Auto-PM 工业级 AI 研发工作台与项目管理驾驶舱

<div align="center">

**面向工业自动化、西门子 PLC SCL 编程与 Python 全栈研发的 AI-Native 智能工作台**

[快速上手](#-极速上手指南) • [核心特性](#-核心功能矩阵) • [AI 技能协同](#-ai-技能生态) • [规范知识库](#-obsidian-全局规范库)

</div>

---

## 🌟 系统全景与三大核心支柱

Auto-PM 为工业电气工程师与软件开发者提供了从**“需求澄清 $\rightarrow$ PRD/架构设计 $\rightarrow$ SCL/Python 编码 $\rightarrow$ 变量表批量映射 $\rightarrow$ 5大阶段门禁 $\rightarrow$ 免安装交付打包”**的全生命周期工程解决方案：

```
                         Auto-PM 工业级协同研发体系
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 🖥️ 【桌面驾驶舱 (GUI Cockpit)】                                            │
  │    • 深色实底磨砂拟物面板 / 70% 焦点遮罩 / 20 维全景交互 / 免安装即开即用    │
  ├─────────────────────────────────────────────────────────────────────────────┤
  │ 🧠 【跨 AI 协作技能矩阵 (.trae/skills/ & .cursor/rules/)】                  │
  │    • pm-workflow：需求澄清、PRD/DSN、5大过程组门禁、PM_SESSION 单一真源落账  │
  │    • fullstack-engineer：Python Clean Architecture 5层整洁架构、自动化测试   │
  │    • plc-electrical-engineer：西门子 S7-1200/1500、SCL 代码生成、变量表/IO   │
  ├─────────────────────────────────────────────────────────────────────────────┤
  │ ⚙️ 【底层规则与门禁引擎 (auto_pm CLI)】                                      │
  │    • 1585 单测安全网 / SCL 规范 Linter / 5 大阶段门禁 G1~G4 / 动态自动寻根   │
  ├─────────────────────────────────────────────────────────────────────────────┤
  │ 📚 【Obsidian 全局规范知识库 (00_Obsidian_Base/)】                          │
  │    • 30+ 工业研发规范 / spec_registry 注册表 / 毫秒级自动索引重构与自愈      │
  └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 极速上手指南 (Quick Start)

### 方式 A：免安装直接运行（适合现场工控机 / 最终使用方）

无需在电脑上安装 Python 或配置任何环境：
1. 前往 `06_交付物/` 目录获取最新的 **`auto-pm_V1.1.0_Release_*.zip`**（或从 GitHub Releases 下载）；
2. 解压压缩包后，**直接双击 `auto-pm.exe` 或 `双击启动驾驶舱.bat`** 即可秒开桌面驾驶舱！

---

### 方式 B：Git 源码克隆与开发（适合研发人员 / AI 极客）

#### 1. 克隆代码仓库
```bash
git clone <repository_url> My_Workspace
cd My_Workspace
```

> 💡 **Git 中文路径防乱码提示**：建议在终端执行一次 `git config --global core.quotepath false`，防止中文目录显示为八进制转义。

#### 2. 一键环境初始化向导 (Windows)
在工作空间根目录下，直接双击运行 **`setup_env.bat`**：
- 脚本只接受 Python 3.12（依赖锁定文件只覆盖 3.12）；
- 自动创建专属 `.venv` 虚拟环境（已有的 `.venv` 不是 3.12 时会停下并提示，不会删除它）；
- 按依赖锁定文件 `00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt` 以 `--no-deps` 精确安装全部桌面 GUI、CLI 与单测依赖包，并运行 `pip check`。

*(Linux / macOS 用户：`python3.12 -m venv .venv && source .venv/bin/activate && python -m pip install --no-deps -r 00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt && python -m pip check`。根目录 `requirements.txt` 已不再列依赖，只指向这份锁定文件；锁定文件冻结于 Windows、Python 3.12，CI 在 Linux 上安装的是同一份，macOS 和其他 Python 版本没有完整验证。)*

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

- **`pm-workflow`**：PM 总控技能，负责读取并回写 `PM_SESSION_<编号>.md`，自动调度全栈或 PLC 技能；
- **`fullstack-engineer`**：全栈开发技能，负责 Python 5 层整洁架构编码与单测；
- **`plc-electrical-engineer`**：电气工程技能，主适配西门子 S7-1200/1500 与 SCL。

---

## 📚 Obsidian 全局规范库自动联动

工作空间内置完整的 Obsidian 知识库（位于 `00_Obsidian_Base全局规范文件仓库/`）。  
在修改任何规范后，只需在根目录执行：

```bash
python -m auto_pm spec sync
```

系统将自动重新生成 `00_INDEX_全局规范索引.md` 及各业务线通用规范 README，实现知识库 100% 实时自愈与索引对齐！

---

## 🧪 自动化测试与质量验证

```bash
# 运行后端与应用层单测 (1585 passed)
pytest

# 运行 20 维全景 GUI 桌面端冒烟测试 (真机交互与快照)
python 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/gui_smoke_test.py
```

---

## 📄 开源许可证

本项目遵循 [Apache-2.0 License](LICENSE)。
