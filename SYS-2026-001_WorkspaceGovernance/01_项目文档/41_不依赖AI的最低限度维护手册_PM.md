# 不依赖 AI 的最低限度维护手册

> 状态：**候选稿 / 未登记 / 未生效**（云端 Claude 起草，2026-10-10）。拟定路径 `SYS-2026-001_WorkspaceGovernance/01_项目文档/41_不依赖AI的最低限度维护手册_PM.md`，编号由本地确定。
> **本文不改变任何现行规则，不替代 `AGENTS.md`、`36_日常手册`、`40_角色与边界`。** 它只回答一个问题：*手边没有可用的 AI 时，你自己最少要会做什么，才不会把现有成果弄坏。*
> 依据：已推送的 `d3c50a8b`（M2 收口之后）。凡我没有在你机器上验证过的，都标了 **[待确认]**。

## 1. 先分清三样东西

| 东西 | 是什么 | 没有 AI 时 |
|---|---|---|
| **你的产品** | PLC、机器人、HMI 工程，本地 Python 脚本 | 照常使用，**不依赖驾驶舱运行** |
| **驾驶舱（auto-pm）** | 为了让 AI 改代码更可靠而做的任务、门禁和记录工具 | 能运行、能自检；**改动它**需要走变更单流程，没有 AI 会很吃力 |
| **AI** | 写代码、填记录的执行者 | 可换：Codex、Trae、Cursor 等，规则都在 `AGENTS.md` |

结论：**最坏情况下你失去的是"升级驾驶舱的便利"，不是你的产品。**

## 2. 每次开工前的三条命令（只读，不会改任何东西）

在工作区根目录（PowerShell）：

```powershell
$ws = "C:\Users\fubai\Documents\My_Workspace"     # 改成你的工作区根
& "$ws\.venv\Scripts\python.exe" -B -I "$ws\main.py" --version
& "$ws\.venv\Scripts\python.exe" -B -I "$ws\main.py" doctor -w "$ws"
& "$ws\.venv\Scripts\python.exe" -B -I "$ws\main.py" pm resume <项目编号> --json
```

- 第 1 条显示当前运行的是哪个版本。
- 第 2 条做环境体检。
- 第 3 条告诉你这个项目**现在能不能安全动手**：有没有未结束的任务、有没有冲突。**有冲突就先别改任何东西。**

常用的检查命令（都是只检查，不修改）：

| 想知道 | 命令 |
|---|---|
| PLC 项目结构是否合规 | `main.py plc check <项目编号>` |
| 文档与代码是否一致 | `main.py doc check` |
| Python 项目是否合规 | `main.py python check <项目编号>` |
| 变更台账是否和变更单对得上 | `main.py ledger reconcile <项目编号>`（不带修复参数） |
| 列出所有项目 | `main.py project list` |

## 3. 你绝对不要做的事

- 不要用 `git commit --no-verify`（绕过检查）。提交被 Hook 拒绝时，**读提示、照提示改**。
- 不要手工修改 `.auto-pm/continuity.db`，也不要手改 `.auto-pm/decisions/` 里的 JSON。
- 不要 `git add .`、`git reset --hard`、`git clean`、`git stash` 别人的改动。
- 不要把任何令牌、密码写进仓库（`gittoken.txt`、`*.token`、`*.secret` 已被忽略；GitHub 的 Secret scanning 已开启）。
- 不要改 `.trae/`、`.cursor/`、`.agent/` 下的规则文件，除非你明确要改。

## 4. 出了问题先看哪里

| 现象 | 先做什么 |
|---|---|
| 命令报 `launcher: 双槽均无效` | 看 `00_Infrastructure/auto_pm/active_release.json` 和 `previous_release.json` 指向的 release 目录是否真的存在。**不要自己改指针**，见 §7 |
| 提交被 Hook 拒绝 | 读提示；通常是缺变更单、台账对不上、改了越界文件 |
| 测试有失败 | 先对照"已知失败"：Windows 本地 15 项（14 个变量表样例缺失 + 1 个 `test_fixture_health`），Linux CI 35 项。**只有出现名单之外的失败才是新问题** |
| GitHub 的 Actions 页面里 `sw008-ci` 显示绿色 | 看结论文字：`PASS_KNOWN_BASELINE` 的意思是"失败的正好是已知那 35 项"，**不是全绿**；`FAIL` 才表示出现了新问题。它只是 7 分钟的早期预警，不替代你本地的完整门禁 |
| `ledger reconcile` 显示差异 | 它只读、只报告。不要手改台账，也不要手改 `continuity.db` |
| 不知道项目现在是什么状态 | `pm resume <项目编号> --json`，把输出交给任何 AI |

## 5. 备份：三层，缺一不可 **[待确认：请在你的机器上演练一次]**

1. **GitHub**（已有）：代码和治理记录。
2. **本机 `.auto-pm/backups/`**（已有做法）：连续性数据库的一致性备份。
3. **离线副本**（建议新增）：放在移动硬盘，不依赖网络和任何账号。

离线副本包含三样（通用做法，不是驾驶舱命令）：

```powershell
# a) 仓库完整历史（单个文件，可在任何装了 Git 的机器上还原）
git -C "$ws" bundle create "D:\backup\WorkSpacePM-$(Get-Date -Format yyyyMMdd).bundle" --all

# b) 连续性数据库的一致性备份（执行前确认没有任务正在运行）
& "$ws\.venv\Scripts\python.exe" -c "import sqlite3; s=sqlite3.connect(r'$ws\.auto-pm\continuity.db'); d=sqlite3.connect(r'D:\backup\continuity.db.backup'); s.backup(d); d.close(); s.close()"

# c) 依赖安装包（离线重装环境用；锁文件见 00_Infrastructure\auto_pm\environment\）
& "$ws\.venv\Scripts\python.exe" -m pip download --no-deps -r "$ws\00_Infrastructure\auto_pm\environment\requirements-lock-py312-win.txt" -d "D:\backup\wheels"
```

没有 `.auto-pm/continuity.db` 的备份，就丢失了所有"谁批准了什么、哪个任务做到哪"的记录；这份记录**不在 Git 里**。

## 6. 换一个 AI（或没有 Claude 的地方）怎么开场

把下面这段原样发给任何 AI，它就能接上：

> 在 `<工作区根>` 工作。目标项目是 `<项目编号>`，需求是"……"。先读 `AGENTS.md`、`SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md` 和 `40_驾驶舱角色与边界_PM.md`，再运行 `main.py pm resume <项目编号> --json` 做只读勘测。**先报批，未经我批准不要修改任何文件。** 不要绕过 Git Hook。

规则的真源只有这几处：`AGENTS.md`、36 号手册、40 号文档、WBS（39 号）顶部的"当前投影"。**不要根据旧聊天或归档的 WBS 开工。**

> 说明：Claude 是否在某个国家可用，取决于当地和 Anthropic 的政策，本文无法替你判断。`AGENTS.md` 本来就面向多个 AI，所以换工具不需要改规则。

## 7. 目前还没有验证过的操作 **[待确认]**

- **手工回退运行版本**：`release_annotations.json` 登记了 `1.3.3-a808fa8` 是回退合格的，但**还没有一条经过演练的、不靠 AI 的回退命令**。在有 AI 时应当演练一次并把步骤补进本文。
- **从备份还原 `continuity.db`**：同上，需要演练。
- **离线重装环境**：§5 c) 的命令是否在你的机器上完整可用，需要试一次。

## 8. 可以先放着不管的（减轻负担）

- CD（自动打包、自动部署，WBS 的 D04～D07）：自用工具暂时不需要。
- Windows 上的自动检查：本地门禁已经覆盖（GitHub 上现在只有 Linux 的最小检查 `sw008-ci`）。
- 旧的 `plc-tool-ci.yml`：指向已归档项目的旧路径，不会误跑。
- 各处 `archive/` 目录和旧的 handoff.v1 记录：只是历史证据。

## 来源

- `AGENTS.md`；`36_驾驶舱与双技术栈日常迭代操作手册_PM.md`；`40_驾驶舱角色与边界_PM.md`；`39_PM-Flow_…_WBS_PM.md` V3.0.26。
- 命令名称与选项：在 `d3c50a8b` 上运行 `main.py --help` 及各子命令 `--help` 核对（25 个命令组）。
- 已知失败名单：云端 Linux 与 GitHub runner 实测，Windows 数字来自本地回报。
- 备份目录与做法：`38_Cockpit_OS_工作区恢复与单主线收口报告_REP.md` §4。
