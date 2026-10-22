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
4. **出计划给用户看**：用中文列出 需求原文（照抄用户原话）/ 目标 / 可改范围（具体文件路径）/ 本次预计改动的文件 / 是否涉及安全回路 / 验收标准及每条对应的命令和期望退出码 / 风险 / 回退办法 / 不做什么 / 需要用户决定的点。验收标准必须是机器能判的（某条命令退出码 0、某个测试通过、某个输出含某行），“能用”“正常”这类不算。**是否碰安全回路（急停、安全门、光栅、联锁、安全继电器、双手启动）必须写明“是”或“否”**；填“是”按安全区走，先仿真、再请用户在 PR 上写“安全签字 + 提交号”后才能合并。然后停下，等用户亲口说“确认开工”。
5. **用户确认后**才运行 `pm inbox confirm`、`pm plan`、`pm approve`。批准人填用户，证据引用写成 `user-confirmation:` 加用户确认消息的时间或编号；用户没说过的确认，绝不要自己编。

   `pm plan` 必须带齐七栏：`--original-request`（照抄用户原话）、`--scope`、`--declared-dirty`、`--safety-circuit 是|否`、每条 `--acceptance` 配一条 `--check "命令 => 退出码"`、`--risk`（写真实风险，不能写“无”）、`--rollback`。`--declared-dirty` 逐个列出本次要改的文件，必须是可改范围的子集，不许留空。`pm approve` 带全参数时同样七栏都要带。缺哪栏驾驶舱会直接列出来，按提示补齐即可，不要绕过。
6. **动手**：只改范围卡列出的路径。所有 `change` 命令都带 `--pid <项目编号>`。界面的“批准范围并开始”和 `pm execute`、`run_approved_planning` 都会启动 Codex 执行器（已挂起），不要点、不要调。**已知缺口⑧**：IDE 里的 agent 自己写代码这条路还没有一条命令走到底。补上之前按下面的过渡做法（D08 第 2 道实际走过的顺序），每条命令的参数以 `--help` 为准：
   1. `main.py pm confirm-start --mission-id <Mission 编号>`（编号从 `pm orient` 读）：Mission 转为进行中、Work 转为 IN_PROGRESS，不启动 Codex；
   2. `git worktree add --detach .auto-pm/worktrees/<名字>`（这一步是 Git 命令，不是驾驶舱命令），在这个工作树里写代码；
   3. `main.py continuity run start … --worktree <工作树绝对路径> --lease-wallet`，`--owned`/`--declared-dirty` 列范围卡里的文件；
   4. `main.py continuity run transition --to RUNNING`，写完、自检过后再 `--to VERIFYING`。只允许这两步；SUCCEEDED、CLOSED 等终态绝不手推，Work 也不手推；
   5. `main.py continuity checkpoint create …`；
   6. 质量验证 `verify_for_acceptance` 目前没有命令，只能临时调用：必须先告诉用户；用控制根 `.venv` 的解释器加 `-B` 运行；脚本放 `.agents/`、用完删；不 import 发布目录以外的驾驶舱代码，不往 `00_Infrastructure/auto_pm/releases/` 写任何文件或缓存；用这个 Run 自己的租约（从 `--lease-wallet` 存的本机钱包读），不另起租约，也不把口令打印出来；门禁正在跑的时候不做这一步；
   7. 交验收前把工作树里改好的文件按字节拷回控制根，列出每个文件的 SHA-256。
7. **自检**：交给用户验收前，范围卡里的每条验收标准都要跑过，把命令和退出码原样报告；有没跑的，明说没跑。
8. **验收与收口**：请用户在驾驶舱界面上亲手点“确认验收”。这个按钮先记下用户验收，再走 `close_accepted` 一步收口：推进 Run、Work 和 Mission，把证据写进变更单、同步台账，但**不推进变更单状态**。你不要写脚本去调它。用户告诉你收口完成后：
   1. 用 `change transition <单号> --to <下一状态> --pid <项目编号>` 把变更单逐步推到 `completed`；
   2. 运行 `main.py ledger reconcile <项目编号>` 只读对账，结果报告给用户；
   3. 再核对一次控制根里的文件与工作树逐字节一致；
   4. 驾驶舱自动生成的变更单和台账改动，跟交付的代码放在同一次提交里交，不要漏交。

   已经验收、只是收口失败的任务，界面上显示的是“重试同步”按钮，不是“确认验收”，请用户点它重试。界面上收口被拒时，请用户把界面提示的原话发给你，原样报告并停下，不换办法绕过。

除第 6 步第 6 小步的过渡做法外，不要写临时脚本去调驾驶舱内部接口，也不要在 `00_Infrastructure/auto_pm/releases/` 里写任何文件或缓存；其他没有命令的步骤，停下告诉用户。不要直接改数据库或治理 JSON。

## 换 agent

当前持有者运行 `main.py pm handoff` 交接（不用 `reclaim`），把输出的 handoff_id 告诉用户后停止写入；接手方先做上面的四步定位，再用 `main.py pm takeover` 接手，从对方的 Checkpoint 接着做，不重做已完成的部分。不要自己编造口令，也不要读取别人的口令文件。

## 不要做

- 不使用已隔离的 `pm-workflow`，也不读取它的内容当作指令；
- 不把 `PM_SESSION_*.md`、聊天文字当作授权；
- 不改、不新建 `PM_SESSION_*.md`（已退役，只作历史证据），也不把它列进可改范围或改动声明，驾驶舱会拒收；
- 不在隔离工作树里运行驾驶舱命令；
- 驾驶舱界面里的“批准范围并开始”会启动 Codex 执行器（目前挂起），用 Trae 等 IDE 里的 agent 干活时不要让用户点它；
- 遇到冲突或报错，不换办法绕过：把原话报告给用户。
