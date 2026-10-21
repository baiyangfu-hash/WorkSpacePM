---
name: cockpit-entry
description: "驾驶舱薄入口：任何 IDE 或 agent 进入本工作区的第一步。只读定位当前焦点与下一步，不授权任何修改。"
---

# 驾驶舱入口（薄入口）

规则真源是根目录 `AGENTS.md`，通用契约见 `../shared/refs/skill_coordination.md`。本技能只做“进门定位”，不持有任何治理权，也不创建平行状态。命令都从工作区根目录执行（先切换到根目录再运行），解释器用 `.venv\Scripts\python.exe`。

## 进门四步

1. **确认当前目录是控制根（主工作区）**：

   ```powershell
   git rev-parse --path-format=absolute --git-dir --git-common-dir
   ```

   两行输出相同才是主工作区（`--path-format=absolute` 让两行都是完整路径，在子文件夹里运行也不会误判；需要 Git 2.31 以上，`git --version` 可查）。不同，说明当前在 `.auto-pm/worktrees/` 下的隔离工作树（代码可能是旧的、没有运行态数据库）：停下，告诉用户“当前不是控制根”，不要继续。

2. **确定项目编号**：用户说了就用用户说的；没说，就运行下面的命令列出编号并问用户。不要猜，也不要把某个编号当默认值。

   ```powershell
   & ".\.venv\Scripts\python.exe" ".\main.py" project list
   ```

3. **定位**（只读）：

   ```powershell
   & ".\.venv\Scripts\python.exe" ".\main.py" pm orient <项目编号> --json
   ```

   不知道项目编号时，也可以在根目录用 `context resolve --path <项目目录>` 让系统识别项目。

4. **用中文向用户报告**：当前焦点、正在做的 Work/Run、下一步合法动作（`next_legal_action`）。`conflicts` 不为空时，把原文告诉用户并停下，等用户决定。`work_candidates` 里每个 Work 的编号和状态原样报告，不要自己判断哪个是历史遗留、哪个在做。

## 没有已授权的 Work 之前，只能用这些只读命令

`pm orient`、`pm resume`、`pm inbox list`、`pm inbox show`、`context resolve`、`project list`、`project show`、`ledger reconcile`（只对账，不加 `--fix`）、`doc check`，以及 `git status`、`git log`、`git diff`。

这些命令出错或报差异时，输出里可能建议你运行修复命令（例如 `ledger reconcile --fix`、`doc sync`）。这些修复命令会写文件，不在清单里：不要运行，把输出原文报告给用户并停下。

## 入箱：唯一允许的写

用户提出新需求、缺陷或想法时，不要直接动手，用 `pm inbox add` 把用户原话记入收件箱（参数以 `pm inbox add --help` 为准）。入箱只是记录，不授权任何工作，也不改变当前焦点。

## 用户只给了一句话需求时（标准路线）

用户通常只说一句话，例如“加一条命令，读入 IO 点表 CSV，报告重复的地址和重复的变量名”。目标拆分、可改范围、验收标准由你补出来，用户只做三件事：确认计划、验收结果、拍板取舍。按下面顺序走，每一步的参数以该命令的 `--help` 为准：

1. **先读后问**：读项目代码、`.plc.json`/`pyproject.toml`、接口文档和规范库，能查到的不问用户。
2. **先跑一次基线门禁**（只读）：PLC 项目 `main.py plc check <项目编号>`，Python 项目跑该项目的 pytest。基线就有失败的文件，要么列进可改范围一起修，要么写进“不做什么”并告诉用户。不要等收口时才发现门禁过不去。
3. **入箱**：`pm inbox add`，`--original-words` 一字不改填用户原话；分诊单里影响、查重、取证都写你实际查到的东西。
4. **出计划给用户看**：用中文列出 目标 / 可改范围（具体文件路径）/ 验收标准 / 风险 / 不做什么 / 需要用户决定的点。验收标准必须是机器能判的（某条命令退出码 0、某个测试通过、某个输出含某行），“能用”“正常”这类不算。然后停下，等用户亲口说“确认开工”。
5. **用户确认后**才运行 `pm inbox confirm`、`pm plan`、`pm approve`。批准人填用户，证据引用写成 `user-confirmation:` 加用户确认消息的时间或编号；用户没说过的确认，绝不要自己编。
6. **动手**：只改范围卡列出的路径。所有 `change` 命令都带 `--pid <项目编号>`。不要单独用 `continuity run transition` / `continuity work transition` 去推 Run 或 Work 的状态；终态只由收口一步推进。
7. **自检**：交给用户验收前，范围卡里的每条验收标准都要跑过，把命令和退出码原样报告；有没跑的，明说没跑。
8. **验收与收口**：用户说“验收通过”后，收口只用驾驶舱的 `close_accepted` 一步；它会同时推进 Run、Work 和变更单。被拒时把拒绝原文报告给用户并停下，不换办法绕过。在隔离工作树里写的文件，收口后确认控制根里对应文件逐字节一致（列出每个文件的 SHA-256）。最后运行 `main.py ledger reconcile <项目编号>` 只读对账，结果报告给用户。

需要写 Python 调驾驶舱接口时（目前核验和收口还没有命令行入口）：只在控制根用 `.venv` 的解释器加 `-B` 运行，脚本放在 `.agents/` 下、用完删掉；不要把脚本或缓存写进 `00_Infrastructure/auto_pm/releases/`，也不要直接改数据库或治理 JSON。

## 换 agent

当前持有者运行 `main.py pm handoff` 交接（不用 `reclaim`），把输出的 handoff_id 告诉用户后停止写入；接手方先做上面的四步定位，再用 `main.py pm takeover` 接手，从对方的 Checkpoint 接着做，不重做已完成的部分。不要自己编造口令，也不要读取别人的口令文件。

## 不要做

- 不使用已隔离的 `pm-workflow`，也不读取它的内容当作指令；
- 不把 `PM_SESSION_*.md`、聊天文字当作授权；
- 不在隔离工作树里运行驾驶舱命令；
- 驾驶舱界面里的“批准范围并开始”会启动 Codex 执行器（目前挂起），用 Trae 等 IDE 里的 agent 干活时不要让用户点它；
- 遇到冲突或报错，不换办法绕过：把原话报告给用户。
