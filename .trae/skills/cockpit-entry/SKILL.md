---
name: cockpit-entry
description: "驾驶舱薄入口：任何 IDE 或 agent 进入本工作区的第一步。只读定位当前焦点与下一步，不授权任何修改。"
---

# 驾驶舱入口（薄入口）

规则真源是根目录 `AGENTS.md`，通用契约见 `../shared/refs/skill_coordination.md`。本技能只做“进门定位”，不持有任何治理权，也不创建平行状态。命令都从工作区根目录执行（先切换到根目录再运行），解释器用 `.venv\Scripts\python.exe`。

## 身份标记

驾驶舱靠环境变量 `AUTO_PM_AGENT`（值写基名，冒号后是备注）认出调用方是 agent：不带标记会被当成用户本人。Claude Code 和 Codex 自带环境变量可被自动认出，其他 agent（Trae、Cursor、VS Code 里的 AI 等）必须自己声明。下面各步里写的 `main.py` 都按这个方式运行：

- 通用：`.\00_Infrastructure\bin\pm-as-agent.ps1 <基名> <命令参数>`，例如 `.\00_Infrastructure\bin\pm-as-agent.ps1 cursor pm orient <项目编号> --json`；基名取自 `AGENTS.md` WS-001 表（claude、trae、cursor、vscode、codex、antigravity）。它只在这一条命令期间设置变量，结束即还原。
- Trae 里的 AI：`.\.trae\bin\pm-as-trae.ps1 <命令参数>`，等价于 `& ".\.venv\Scripts\python.exe" ".\main.py" <命令参数>`，只是这一条命令期间带上 `AUTO_PM_AGENT=trae:cn`，结束即还原。命令只认冒号前面那段（trae），冒号后面的 `cn` 只是备注，国际版同样适用；效果和上面的通用脚本取 `trae:cn` 相同。
- 非 Windows 的 shell：只对单条命令设置，如 `AUTO_PM_AGENT=cursor python main.py pm orient <项目编号> --json`。

要用户批准的命令（名单见 `AGENTS.md` FLOW-002“点动”）：用户亲口批准了，带上那句话的位置去跑（`--approval-evidence-ref user-confirmation:<用户那条消息的时间或编号>`）；用户没说过的不跑，交给用户。`pm sign-risk` 带 agent 标记一律被拒，只能交给用户在自己的终端跑。

## 进门（AGENTS.md“进门”一节的细则）

1. **确认当前目录是控制根（主工作区）**：

   ```powershell
   git rev-parse --path-format=absolute --git-dir --git-common-dir
   ```

   两行输出相同才是主工作区（`--path-format=absolute` 让两行都是完整路径，在子文件夹里运行也不会误判；需要 Git 2.31 以上，`git --version` 可查）。不同，说明当前在 `.auto-pm/worktrees/` 下的隔离工作树（代码可能是旧的、没有运行态数据库）：停下，告诉用户“当前不是控制根”，不要继续。

2. **确定项目编号**：用户说了就用用户说的；没说，就运行下面的命令列出编号并问用户。不要猜，也不要把某个编号当默认值。

   ```powershell
   & ".\.venv\Scripts\python.exe" ".\main.py" project list
   ```

3. **进门一条命令**（只读）：

   ```powershell
   & ".\.venv\Scripts\python.exe" ".\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\scripts\pm_flows.py" entry <项目编号>
   ```

   它依次跑项目体检（第一步就是 `pm orient`）、占位表 `claim list`，再对登记路径落在本项目里、还没放下的每张卡跑 `claim log`，最后列出每张卡交接记录的最后三行和“先读这些文件”。

   脚本用不了时，在根目录按顺序手敲：`main.py pm orient <项目编号> --json`、`main.py claim list`，再对本项目的每张卡 `main.py claim log <卡号>`；完整步骤也可以用 `pm_flows.py steps entry` 列出。任何一条报 `No such command '…'`，说明本机生效的发布版本还没有这条命令：照实告诉用户；没有 `orient` 时改用同样只读的 `pm resume <项目编号> --json`；不要为此切换或部署版本。

   不知道项目编号时，也可以在根目录用 `context resolve --path <项目目录>` 让系统识别项目。

4. **先读完交接记录列出的文件，再用中文向用户报告**：当前焦点、正在做的 Work/Run、下一步合法动作（`next_legal_action`）。`conflicts` 不为空时，把原文告诉用户并停下，等用户决定。`work_candidates` 里每个 Work 的编号和状态原样报告，不要自己判断哪个是历史遗留、哪个在做。

## 变更单被批准之前，只能用这些只读命令

`pm orient`、`pm resume`、`pm inbox list`、`pm inbox show`、`pm triage`（只读：开着的卡和收件箱按建议顺序排好，每条写明下一步）、`context resolve`、`project list`、`project show`、`ledger reconcile`（只对账，不加 `--fix`）、`doc check`、`gate precheck`、`claim list`、`claim log`，AGENTS.md FLOW-002 的 `pm_flows.py entry`、`checkup`、`steps`（脚本只串命令分类表里归“读”的命令），以及 `git status`、`git log`、`git diff`。按 `AGENTS.md` FLOW-001，“要你点头”一类在批准前另可建变更单（`change create`）；“多机”档按 D-101 领卡占位（`claim number`、`claim open`），除此之外不写。

门禁分档（`gate precheck` / `gate start [--full]`）与角色分诊决策见 `roles/shared/refs/skill_coordination.md`。

这些命令出错或报差异时，输出里可能建议你运行修复命令（例如 `ledger reconcile --fix`、`doc sync`）。这些修复命令会写文件，不在清单里：不要运行，把输出原文报告给用户并停下。

## 入箱：唯一允许的写

用户提出新需求、缺陷或想法时，不要直接动手，用 `pm inbox add` 把用户原话记入收件箱（参数以 `pm inbox add --help` 为准）。入箱只是记录，不授权任何工作，也不改变当前焦点。

## 用户只给了一句话需求时（标准路线）

用户通常只说一句话，例如“加一条命令，读入 IO 点表 CSV，报告重复的地址和重复的变量名”。目标拆分、可改范围、验收标准由你补出来，用户只做三件事：确认计划、验收结果、拍板取舍。按下面顺序走，每一步的参数以该命令的 `--help` 为准：

1. **先读后问**：读项目代码、`.plc.json`/`pyproject.toml`、接口文档和规范库，能查到的不问用户。
2. **先跑一次基线门禁**（只读）：PLC 项目 `main.py plc check <项目编号>`，Python 项目跑该项目的 pytest。基线就有失败的文件，要么列进可改范围一起修，要么写进“不做什么”并告诉用户。不要等收口时才发现门禁过不去。
3. **建单**：按 `AGENTS.md` FLOW-001 分两类——“要你点头”那一类先在控制根用 `main.py change create --pid <项目编号> …` 建变更单、批准后才动手；“直接做”那一类不建单，提交说明写 `领卡占位: <卡号>` 就行。`change create --retrofit`（先做后补）已退役，不要再用。
4. **出计划给用户看**：用中文列出这几项：
   - 需求原文（照抄用户原话）、目标、可改范围（具体文件路径）、本次预计改动的文件；
   - 是否涉及安全回路：碰到急停、安全门、光栅、联锁、安全继电器、双手启动中的任何一样，就写“是”，否则写“否”；
   - 验收标准，每条配上对应的命令和期望退出码；
   - 风险、回退办法、不做什么、需要用户决定的点。

   验收标准必须是机器能判的，比如某条命令退出码 0、某个测试通过、某个输出含某行；“能用”“正常”这类不算。安全回路填“是”的按安全区走：先仿真，再请用户在 PR 上写“安全签字 + 提交号”，然后才能合并。列完停下，问“请确认是否批准开工？”，等用户亲口说“同意”。
5. **用户同意后**，才把变更单推到已批准：
   - 先跑 `change transition <变更单号> --to submitted`，再跑 `--to under_review`；
   - 最后跑 `--to approved --approver <用户> --approval-evidence-ref user-confirmation:<用户那条消息的时间或编号>`。

   用户在看板“决定”页点了“批准变更单”的，不用做这一步。用户没说过的同意，绝不要自己编。
6. **领卡、开工位、动手**：
   - 先跑 `main.py claim list` 看占位表，和别人不重叠才 `main.py claim open <卡号或 auto> --paths … --goal …`；
   - 再用 `main.py worktree open <agent> <卡号>` 开工位，只在工位里改，只改占位登记的路径；
   - 所有 `change` 命令都带 `--pid <项目编号>`；
   - 界面的“批准范围并开始”、`pm execute`、`run_approved_planning` 都会启动已挂起的 Codex 执行器，不要点，也不要调。
7. **自检、提交、开 PR**：
   - 计划里的每条验收标准都要跑过，把命令和退出码原样报告；有没跑的，明说没跑；
   - 提交说明里单独写一行 `领卡占位: <卡号>`；
   - 任务卡先入库，入库前 `main.py implementation-card precheck` 要退出 0；入库后用 `main.py pr open <agent> <卡号> --task-card <卡的路径>` 开 PR，PR 描述写 `流程线:`、`领卡占位:` 和可改范围；
   - 改规则文件的 PR，要用户在 GitHub 点“规则批准”。
8. **审计、合并与收口**：
   - 由另一个会话按 `AGENTS.md` AUD-001 审计；CI 全绿、审计通过后，用 Merge commit 合并；
   - 合并后在控制根跑 `pm_flows.py closeout-pr <项目编号> --chg <变更单号> --card <卡号>`：推到验收中由 agent 跑；推到完成要用户本人在看板点“推到完成”，或在本机主对话里亲口说（`AGENTS.md` 红线 1）；最后对账、放下占位、收工位。

### 走 Run 的卡

看板“确认开工”一键流开出来的卡，以及命令本身要求 Run 或租约的卡，第 3～8 步照下面做，收口用 `pm_flows.py closeout`（`AGENTS.md` 红线 2、FLOW-002）：

3. **入箱**：`pm inbox add`，`--original-words` 一字不改填用户原话；分诊单里影响、查重、取证都写你实际查到的东西。
4. **出计划给用户看**：用中文列出 需求原文（照抄用户原话）/ 目标 / 可改范围（具体文件路径）/ 本次预计改动的文件 / 是否涉及安全回路 / 验收标准及每条对应的命令和期望退出码 / 风险 / 回退办法 / 不做什么 / 需要用户决定的点。验收标准必须是机器能判的（某条命令退出码 0、某个测试通过、某个输出含某行），“能用”“正常”这类不算。**是否碰安全回路（急停、安全门、光栅、联锁、安全继电器、双手启动）必须写明“是”或“否”**；填“是”按安全区走，先仿真、再请用户在 PR 上写“安全签字 + 提交号”后才能合并。然后停下，等用户亲口说“确认开工”。
5. **用户确认后**才运行 `pm inbox confirm`、`pm plan`、`pm approve`。批准人填用户，证据引用写成 `user-confirmation:` 加用户确认消息的时间或编号；用户没说过的确认，绝不要自己编。

   `pm plan` 必须带齐七栏：`--original-request`（照抄用户原话）、`--scope`、`--declared-dirty`、`--safety-circuit 是|否`、每条 `--acceptance` 配一条 `--check "命令 => 退出码"`、`--risk`（写真实风险，不能写“无”）、`--rollback`。`--declared-dirty` 逐个列出本次要改的文件，必须是可改范围的子集，不许留空。`pm approve` 带全参数时同样七栏都要带。缺哪栏驾驶舱会直接列出来，按提示补齐即可，不要绕过。
6. **动手**：只改范围卡列出的路径。所有 `change` 命令都带 `--pid <项目编号>`。界面的“批准范围并开始”和 `pm execute`、`run_approved_planning` 都会启动 Codex 执行器（已挂起），不要点、不要调。IDE 里的 agent 自己写代码按下面顺序走，每条命令的参数以 `--help` 为准，全部在控制根运行：
   1. `main.py pm confirm-start --mission-id <Mission 编号>`（编号从 `pm orient` 读）：Mission 转为进行中、Work 转为 IN_PROGRESS，不启动 Codex；
   2. `git worktree add --detach .auto-pm/worktrees/<名字>`（这一步是 Git 命令，不是驾驶舱命令），在这个工作树里写代码。控制根里范围内的文件如果还有没提交的改动（例如上一单收口并回的成果），下一步会被拒绝：请用户先提交，再建工作树；
   3. `main.py continuity run start … --worktree <工作树绝对路径> --lease-wallet`，`--owned`/`--declared-dirty` 列范围卡里的文件；
   4. `main.py continuity run transition --to RUNNING`，写完、自检过后再 `--to VERIFYING`。只允许这两步；SUCCEEDED、CLOSED 等终态绝不手推，Work 和 Mission 也不用 `continuity` 命令手推（驾驶舱会拒绝）；
   5. 质量验证：`main.py pm verify --mission-id <Mission 编号> --lease-wallet`。它用本 Run 自己的租约（从本机钱包读，不打印口令）跑领域门禁、生成系统证据检查点；通过后 Mission 进入“等待用户验收”，退出码 0。没通过时退出码非 0，`reason` 是原因，原样报告给用户，改好后再运行一次 `pm verify`。门禁正在跑的时候不做这一步。
   不要自己把工作树的文件拷回控制根：收口时驾驶舱会按字节并回（见第 8 步）。
7. **自检**：交给用户验收前，范围卡里的每条验收标准都要跑过，把命令和退出码原样报告；有没跑的，明说没跑。`pm verify` 之后工作树里不要再改任何文件，改了收口会被拒，要重新验证、重新验收。
8. **验收与收口**：请用户在驾驶舱界面上亲手点“确认验收”。这个按钮先记下用户验收，再走 `close_accepted` 一步收口：把工作树里验收过的文件按字节并回控制根、推进 Run、Work 和 Mission，把证据写进变更单、同步台账，但**不推进变更单状态**，也**不替用户提交 Git**。用户已经验收、但收口没完成（界面显示“重试同步”）时，你可以运行 `main.py pm close --mission-id <Mission 编号>`，它和“重试同步”是同一个收口；它只收用户已验收的任务，失败时退出码非 0，`reason` 是原因。收口完成后：
   1. 用 `change transition <单号> --to <下一状态> --pid <项目编号>` 把变更单逐步推到 `completed`；推到批准、推到完成要先有用户在看板点按钮，或在本机主对话里亲口说，再带上那句话的位置去跑（`AGENTS.md` 红线 1）；
   2. 运行 `main.py ledger reconcile <项目编号>` 只读对账，结果报告给用户；
   3. 告诉用户哪些文件已并回控制根、尚未提交，请用户提交：驾驶舱自动生成的变更单和台账改动，跟交付的代码放在同一次提交里交，不要漏交（下一单动同一批文件前必须先提交）。

   收口被拒时（界面提示或 `pm close` 的 `reason`），原样报告并停下，不换办法绕过：“隔离工作树在质量验证之后又被改动”要重新 `pm verify` 并请用户重新验收；“控制根里的此文件……可能被别人改过”要请用户先处理控制根里的那个文件；“验收结果删除了此文件”要请用户确认后亲手删除。处理好后再点“重试同步”或运行 `pm close`。

不要写临时脚本去调驾驶舱内部接口，也不要在 `00_Infrastructure/auto_pm/releases/` 里写任何文件或缓存；没有命令的步骤，停下告诉用户。不要直接改数据库或治理 JSON。

## 换 agent

- **单机日常（PM-056 轻轨）**：在工位内用 `SW8/scripts/pm_handoff.py` 的 `set-focus` / `log` 更新 `<项目>/{04|11}_监控/交接交换区/`（`focus.json`、`journal.jsonl`）并随分支提交合并；
- **多机档**：在占位卡上用 `main.py claim note` 记引用与下一棒，接手方读完后记 `--kind takeover`；
- **Run 租约卡**：持有者跑 `main.py pm handoff` 交租约、停写，接手方跑 `main.py pm takeover` 续作。不要自造口令或读他人钱包文件；详细写法与驾驶舱避坑见 `roles/shared/refs/start_and_handoff.md`。

## 不要做

- 不使用已隔离的 `pm-workflow`，也不读取它的内容当作指令；
- 不把 `PM_SESSION_*.md`、聊天文字当作授权；
- 不改、不新建 `PM_SESSION_*.md`（已退役，只作历史证据），也不把它列进可改范围或改动声明，驾驶舱会拒收；
- 不在隔离工作树里运行驾驶舱命令；
- 驾驶舱界面里的“批准范围并开始”会启动 Codex 执行器（目前挂起），用 Trae 等 IDE 里的 agent 干活时不要让用户点它；
- 遇到冲突或报错，不换办法绕过：把原话报告给用户。
