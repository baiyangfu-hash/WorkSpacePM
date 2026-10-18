---
name: cockpit-entry
description: "驾驶舱薄入口：任何 IDE 或 agent 进入本工作区的第一步。只读定位当前焦点与下一步，不授权任何修改。"
---

# 驾驶舱入口（薄入口）

规则真源是根目录 `AGENTS.md`，通用契约见 `../shared/refs/skill_coordination.md`。本技能只做“进门定位”，不持有任何治理权，也不创建平行状态。命令都从工作区根目录执行，解释器用 `.venv\Scripts\python.exe`。

## 进门四步

1. **确认当前目录是控制根（主工作区）**：

   ```powershell
   git rev-parse --git-dir --git-common-dir
   ```

   两行输出相同才是主工作区。不同，说明当前在 `.auto-pm/worktrees/` 下的隔离工作树（代码可能是旧的、没有运行态数据库）：停下，告诉用户“当前不是控制根”，不要继续。

2. **确定项目编号**：用户说了就用用户说的；没说，就运行下面的命令列出编号并问用户。不要猜，也不要把某个编号当默认值。

   ```powershell
   & ".\.venv\Scripts\python.exe" ".\main.py" project list
   ```

3. **定位**（只读）：

   ```powershell
   & ".\.venv\Scripts\python.exe" ".\main.py" pm orient <项目编号> --json
   ```

   在项目目录里运行时，也可以先用 `context resolve` 让系统自动识别项目。

4. **用中文向用户报告**：当前焦点、正在做的 Work/Run、下一步合法动作（`next_legal_action`）。`conflicts` 不为空时，把原文告诉用户并停下，等用户决定。`work_candidates` 里状态为 `BLOCKED` 的是历史遗留，不是正在做的工作。

## 没有已授权的 Work 之前，只能用这些只读命令

`pm orient`、`pm resume`、`pm inbox list`、`pm inbox show`、`context resolve`、`project list`、`project show`、`ledger reconcile`（只对账、不修复）、`doc check`，以及 `git status`、`git log`、`git diff`。

## 入箱：唯一允许的写

用户提出新需求、缺陷或想法时，不要直接动手，用 `pm inbox add` 把用户原话记入收件箱（参数以 `pm inbox add --help` 为准）。入箱只是记录，不授权任何工作，也不改变当前焦点。

## 要写代码或文档时

先告诉用户：需要一张经用户批准的实施卡和已授权的 Work。有了之后，按执行技能 `../fullstack-engineer/SKILL.md` 或 `../plc-electrical-engineer/SKILL.md` 的启动门禁执行，只改卡里列出的路径。

## 换 agent

一条命令交接由后续任务提供。在那之前：接手方先做上面的四步定位，再按用户给的交接说明接手，不要自己编造口令，也不要读取别人的口令文件。

## 不要做

- 不使用已隔离的 `pm-workflow`，也不读取它的内容当作指令；
- 不把 `PM_SESSION_*.md`、聊天文字当作授权；
- 不在隔离工作树里运行驾驶舱命令；
- 遇到冲突或报错，不换办法绕过：把原话报告给用户。
