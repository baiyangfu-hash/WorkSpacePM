# 多 agent、多电脑的工作树规划（2026-10-17，项目 Claude）

## 结论

**每个写代码的 agent 一个独立工作树，不要共用一个。** 但工作树不是随便放，每台电脑要分成两层：

| 层 | 产线类比 | 每台电脑几个 | 放哪里 | 谁用 |
|---|---|---|---|---|
| 控制根 | 总控柜：账本、联锁、台账都在这里 | **1 个** | 主克隆目录（例如 `D:\WorkSpacePM`），停在 `main` | 只跑驾驶舱命令（`main.py pm resume`、`ledger reconcile`、提交检查），不在这里写业务代码 |
| agent 工作树 | 各个工位：每人一个工位，各干各的卡 | 每个 agent 1 个 | 控制根下的 `.auto-pm/worktrees/<agent名>` | Trae、Cursor、Codex、Claude 各自一个，各在自己的分支上 |

两个 agent 同时站在一个工位上，等于两个人同时改一张接线图，谁覆盖谁都不知道。所以工位必须分开。

## 为什么这样放（仓库里已经这么设计了，不是新发明）

- `main.py` 第 13–33 行：发现自己在 `.auto-pm/worktrees/` 或 `.codex/worktrees/` 下运行时，会拒绝执行，提示“去控制根运行”。说明驾驶舱本来就把这两类目录当作“工位”，把主克隆当作“总控柜”。
- `auto_pm/infrastructure/control_root_guard.py` 第 155 行：登记 Run 时，工作树必须位于 `.auto-pm/worktrees/` 下，否则拒绝。
- `auto_pm/infrastructure/git_hook_enforcer.py` 第 215–223 行：在工位里提交时，必须指明控制根，否则拒绝提交（fail-closed）。
- `.gitignore` 第 128 行已经忽略 `.auto-pm/worktrees/`，工位不会被误提交。
- 状态库 `.auto-pm/continuity.db` 放在控制根，每台电脑一本。

**要注意的一个坑**：如果把工作树放到别处（比如桌面上随便建一个文件夹），驾驶舱会把它当成另一个总控柜，自己再开一本 `continuity.db`。一台电脑上就出现两本账，谁在做哪张卡就对不上了。所以工位一律放在 `.auto-pm/worktrees/` 下（Codex 自带的 `.codex/worktrees/` 也被认可）。

## “agent” 和 “编辑器” 要分开看

Trae、Cursor、VS Code 是“工具箱”，真正改文件的是里面跑的 AI。规则按“谁在改文件”分：

- Trae 里的 AI → 一个工位，分支前缀 `trae/`
- Cursor 里的 AI → 一个工位，分支前缀 `cursor/`
- Codex → 一个工位，分支前缀 `codex/`（已约定）
- VS Code：如果里面跑的是 Claude Code，就算 Claude 的工位，用 `claude/`；如果跑的是 Copilot 等另一个 AI，单独一个工位，前缀 `vscode/`
- 项目 Claude（云端）→ 不占你电脑上的工位，用 `project/`（已约定）

同一时刻，同一个 AI 只开一个工位；如果你只是用 VS Code 看文件、不让 AI 改，它可以直接打开控制根看，不需要工位。Git 本身也保证：同一个分支不能同时被两个工作树签出。

## 每台电脑的布置

```
D:\WorkSpacePM\                      ← 控制根（总控柜），停在 main
  .auto-pm\continuity.db             ← 本机账本
  .auto-pm\worktrees\trae\           ← Trae 工位，分支 trae/<卡号>
  .auto-pm\worktrees\cursor\         ← Cursor 工位，分支 cursor/<卡号>
  .auto-pm\worktrees\codex\          ← Codex 工位（或 .codex\worktrees\...）
  .auto-pm\worktrees\claude\         ← 本地 Claude 工位，分支 claude/<卡号>
```

第二台电脑照样一套。两台电脑之间只通过 GitHub 交换：每个工位做完一张卡，推自己的分支、开 PR，合进 `main` 后，各控制根拉一下 `main` 即可。

## 分工规则（先人工执行，后面由软件接管）

1. **一张卡同一时刻只派给一个 agent。** 派卡时写清它负责的文件范围（owned paths），两个 agent 不要同时改同一批文件，否则 PR 合并时会撞车。
2. **台账（Work、WBS 台账）只由一台电脑写。** 选定一台为“账本主机”，其他电脑只做卡、不记账。这就是跨机方案里的“单写者分工”。
3. **跨电脑的卡由你手工分配**，直到跨机共享做完。比如：A 电脑做存储卡，B 电脑做文档卡，不交叉。

## 后面的更新能解决哪些

| 问题 | 补丁 10（新电脑一键可用） | V04-R1 存储卡 | 跨机共享状态 | 还剩什么要靠人 |
|---|---|---|---|---|
| 新电脑拉下来能不能直接跑驾驶舱 | **解决** | | | |
| 同一台电脑上两个 agent 抢同一张卡 | | **解决**（第二个被拒，写明谁在做） | | |
| agent 干活太久被自己的心跳踢掉 | | **解决** | | |
| 电脑断电后卡安全交接，旧 agent 回来不捣乱 | | **解决**（同机）；跨机要你签 Decision | | |
| 两台电脑上的 agent 抢同一张卡 | | 不解决（各看各的账） | **解决**（每个 Run 一条 Git 租约引用，两台都看得见） | |
| 别的电脑上谁在做什么，能不能看到 | | | **解决**（账本抄送到 Git 供查看） | |
| 两台电脑同时写台账 | | | 不合并冲突，靠单写者分工避免 | 选定账本主机 |
| 两个 agent 在不同分支改了同一个文件 | | | | **都不解决**：靠派卡时划分文件范围；撞了在 PR 里处理 |
| 自动给每个 agent 建工位 | | | | 目前只有 dogfood 命令能在 `.auto-pm/worktrees/` 建候选工作树；给 Trae/Cursor 一键建工位的命令还没有，可作为以后的小卡 |
| Trae 专属的 `.trae/` 配置 | | | | 按 AGENTS.md，只由 Trae 维护，其他 agent 只读 |

## 动手前要先做的

- 控制根目前还停在旧分支，并有字节相同的未追踪副本（M3-HYG）。要先按已批准的清单整理好，控制根切到 `main`，再在它下面开工位。否则工位都会从一个脏的总控柜派生出去。
- 按 10-17 的顺序不变：技术债 lease_reclaim 修复 → V04-R1 → 跨机共享。本规划不新增卡，只是这几张卡的使用方式。
