# WorkSpacePM：从这里开始

这个仓库是用户本人的工作空间，用户是唯一的架构师和决策人（`AGENTS.md` 开头）：放 PLC 项目、Python 项目，以及管这些项目的工具“驾驶舱”（auto-pm，项目号 SW-2026-008）。驾驶舱管变更单、技术债台账、门禁和交付，AI 和 agent 的改动都要经过它留痕、过检查、能回退。多个 AI（Claude、Codex、Cursor、Trae 等）共用这个仓库（`AGENTS.md` 开头）。

本页只讲四件事：这是什么、东西放在哪、有哪些能力、进门去哪查。**本页不写规矩、不写状态、不列能力**：规矩只在 `AGENTS.md`（细则在它的附录），命令以命令总目录为准，现在到哪了以 WBS 为准，能力以功能清单为准。本页和它们说的不一样时，以它们为准。

## 1. 进门先看哪里

| 想知道什么 | 看这里 |
|---|---|
| 规矩（所有 AI 共用的唯一真源：进门、红线、三条流程线、工位、订卡、审计） | `AGENTS.md`；细则在附录 `roles/shared/refs/agents_附录/`（命令速查、快线与退回、工位细则、理念与长条文） |
| 进门第一步（只读定位，各家 AI 怎么声明身份） | `.trae/skills/cockpit-entry/SKILL.md` |
| 进门一条命令（体检、占位表、每张卡的交接记录，全按顺序跑完） | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/pm_flows.py entry <项目号>`（怎么跑、跑不了时手敲哪几条，见上一行的 SKILL.md） |
| 有哪些命令（指令手册） | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/06_交付物/003_命令总目录_COMMANDS.md`；每条命令归“读”还是“写”、谁能跑，以 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/cockpit_board/flow/commands_map.json` 为准 |
| 现在到哪了、下一步做什么 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/驾驶舱开发基线_20261114/02_里程碑与WBS.md` |
| 有哪些能力、哪些能用 | `docs/功能清单.md`（见第 3 节） |
| 问题登记在哪 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` |
| 用户已经定了的事、必须用户亲口同意的事 | `docs/handover/`（入口 `docs/handover/README.md`） |
| 工作空间里登记了哪些项目 | `SYS-2026-001_WorkspaceGovernance/workspace_registry.json` |
| PR 怎么审 | `AGENTS.md` 的“独立审计 (AUD-001)”；脚本 `reviews/tools/audit_pr.py`，清单 `reviews/21_audit_checklist.md` |

## 2. 东西放在哪

| 目录 | 放什么 |
|---|---|
| `00_Infrastructure/auto_pm/` | 驾驶舱的发布载荷：各发布版在 `00_Infrastructure/auto_pm/releases/` 下，本机用哪一版由 `00_Infrastructure/auto_pm/active_release.json` 指定（上一版记在 `00_Infrastructure/auto_pm/previous_release.json`）；装环境的脚本和依赖锁定文件在 `00_Infrastructure/auto_pm/environment/` |
| `00_Infrastructure/bin/` | `00_Infrastructure/bin/pm-as-agent.ps1`：在 Windows 上给一条驾驶舱命令临时声明 agent 身份 |
| `00_Obsidian_Base全局规范文件仓库/` | 全局规范库（Obsidian），注册表 `00_Obsidian_Base全局规范文件仓库/spec_registry.json` |
| `0100_PLC自动化/` | PLC 项目（DJ-2026-xxx）、共享库 `0100_PLC自动化/01_SharedLibraries/`、PLC 通用规范 `0100_PLC自动化/00_通用规范/`（含无 AI、断网时的人工路线 `0100_PLC自动化/00_通用规范/无AI离线手册.md`） |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/` | Python 项目；驾驶舱源码、测试、规划、台账都在 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/` |
| `SYS-2026-001_WorkspaceGovernance/` | 工作空间治理：项目登记表、治理基线和计划 |
| `.github/workflows/` | GitHub 上跑的检查，有的跑在 GitHub 的 Windows 机器上；每个文件开头的注释写了它管什么 |
| `reviews/` | 审计报告、审计和 PR 检查用的脚本（`reviews/tools/`） |
| `roles/`、`.trae/skills/`、`.agents/skills.json` | AI 技能；注册了哪几个以 `.agents/skills.json` 为准 |
| `docs/` | 交接手册 `docs/handover/`、设计说明 `docs/design/`、功能清单 `docs/功能清单.md` |
| `tests/` | 仓库根的测试（启动器、发布入口、批处理守护、PLC 模板对齐等），由 `.github/workflows/root-tests.yml` 跑 |
| 根目录 `main.py` | 驾驶舱根入口：用 `00_Infrastructure/auto_pm/active_release.json` 指的发布版运行驾驶舱命令；不带参数时打开桌面驾驶舱 |

## 3. 有哪些能力

能力只记在一处：`docs/功能清单.md`。每样能力写明状态（能用、不能用、未核实）、核的版本、日期和怎么核的；本页不抄。

GitHub 上的检查和云端门禁（包括在 GitHub 的 Windows 机器上手动跑的全量门禁 `.github/workflows/gate-full.yml`、发布候选预门禁 `.github/workflows/release-pregate.yml`，以及 `.github/workflows/sw008-ci.yml` 里跑在 Windows 上的作业）也算能力，同样以功能清单为准。功能清单还没有这一节时，先看 `.github/workflows/` 下各文件开头的注释。

## 4. 装环境 → 自检 → 定位

换电脑、换云服务商、换 AI agent，都照这三步。

> 💡 **Git 中文路径防乱码**：建议执行一次 `git config --global core.quotepath false`，防止中文目录显示为八进制转义。

**第一步：装环境。** 没有 `.venv`，或 `.venv` 不是 Python 3.12，就装：
- **Windows**：在工作空间根目录双击 **`setup_env.bat`**。它只认 Python 3.12（依赖锁定文件只覆盖 3.12）；已有的 `.venv` 不是 3.12 时停下并提示，不删除它；按锁定文件 `00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt` 用 `--no-deps` 精确安装，再跑 `pip check`。
- **Linux / 云端 / macOS**：在工作空间根目录执行 `sh 00_Infrastructure/auto_pm/environment/setup_env.sh`，步骤和 `setup_env.bat` 一样、用同一份锁定文件。云端会话（或设了 `AUTO_PM_INSTALL_SYSLIBS=1`）缺 Qt 系统库时会自己 `apt-get` 装（要 root）。根目录 `requirements.txt` 不再列依赖，只指向这份锁定文件。锁定文件冻结于 Windows、Python 3.12；macOS 和其他 Python 版本没有完整验证。

**第二步：自检。** 装完（或开新会话时）跑一遍。检查脚本只用 Python 标准库，`.venv` 没装好时也能跑：
- **Windows**：`python 00_Infrastructure\auto_pm\environment\env_check.py`（`python` 不行就用 `py -3`）；
- **Linux / 云端 / macOS**：`python3 00_Infrastructure/auto_pm/environment/env_check.py`，或等价的 `sh 00_Infrastructure/auto_pm/environment/cloud_selfcheck.sh`。

只读，不改任何东西。查：`.venv` 是 Python 3.12、开发依赖和 Qt 能导入、不是浅克隆。退出码 **0 才能开工**；非 0 就照 `[失败]` 行下面的“补救”命令做，再跑一遍。装好后想看更多体检项，用 `python main.py doctor`。

**第三步：定位。** AI agent 先读 `AGENTS.md` 和 `.trae/skills/cockpit-entry/SKILL.md`，照它做只读定位，再动手。

**换云服务商或换 agent 时，哪些跟着仓库走、哪些要在那家云的设置页自己填：**

| 跟着仓库走（克隆即得） | 要在那家云自己的设置页填 |
|---|---|
| `00_Infrastructure/auto_pm/environment/setup_env.sh`、`00_Infrastructure/auto_pm/environment/env_check.py`、`00_Infrastructure/auto_pm/environment/cloud_selfcheck.sh`、依赖锁定文件、`AGENTS.md`、`CLAUDE.md` | 安装脚本（粘贴下面那几行）；网络放行（至少能访问 PyPI，装 Qt 系统库还要能访问系统包源）；以 root 运行（`apt-get` 要用） |

安装脚本（假定起始目录是“放仓库的那一层”；不是的话，改成进入仓库根目录再执行）：
```bash
cd WorkSpacePM   # 仓库目录名；起始目录就是仓库根时，这一行去掉
git fetch --unshallow origin 2>/dev/null || true   # 浅克隆补成完整历史，失败不拦
AUTO_PM_INSTALL_SYSLIBS=1 sh 00_Infrastructure/auto_pm/environment/setup_env.sh \
  || echo "[警告] setup_env.sh 没成功；进会话后运行 env_check.py 看缺什么"
```
不要把令牌、密码写进环境变量或脚本（多数云是明文保存）。Claude Code 的 `SessionStart` 钩子（`.claude/hooks/session-start.sh`）只对 Claude Code 生效，而且不是每种会话都会执行，所以**不能只靠它**。别家云的安装脚本字段叫什么、起始目录是哪一层，未核实，以它的文档为准。

没有免安装包：旧的 V1.1.0 打包产物只在 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/06_交付物/archive/` 作历史存档，不再适用。

## 5. 启动桌面驾驶舱

两个双击入口：
- **`双击启动驾驶舱.bat`**（根目录）：在根目录运行 `python main.py`，不带参数时用 `00_Infrastructure/auto_pm/active_release.json` 指的发布版打开驾驶舱主界面（等于 `python main.py gui`）。
- **`00_Infrastructure/auto_pm/environment/双击打开驾驶舱看板.bat`**：从 SW-2026-008 源码目录打开驾驶舱总控屏（`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/pm_dashboard_gui.py`），不走发布版。

两个界面各有哪些功能能用，见 `docs/功能清单.md`。

## 6. 跑驾驶舱自己的测试

测试在 SW-2026-008 项目目录下，先进入该目录：

```bash
cd 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具

# 全量单测，和 CI（.github/workflows/sw008-ci.yml 的 Linux 作业）同一条命令：关掉 pyproject 里默认的覆盖率选项、4 进程并行
python -m pytest -q -p no:cacheprovider -o addopts= -n 4 tests

# GUI 桌面端冒烟测试
python scripts/gui_smoke_test.py --workspace <工作区根目录> --output <输出目录>
```

## 7. 规范库

全局规范库在 `00_Obsidian_Base全局规范文件仓库/`，注册表 `00_Obsidian_Base全局规范文件仓库/spec_registry.json`。AI 不擅自改规范库：规范不适用或要沉淀新经验，走变更单，用户亲自批了才生效（`AGENTS.md` 红线第 5 条）。`spec sync` 在 `AGENTS.md` 红线第 4 条“已知有害”的命令里，碰上就停下问，不要跑。

## 8. 许可证

[Apache-2.0](LICENSE)。
