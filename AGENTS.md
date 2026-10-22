# 工作空间 AI 协作入口

本仓库由多个 AI 共用（Trae、Cursor、Codex、Antigravity 等）。**规则真源不重复维护**，各工具读取同一路径。

> **退役隔离（2026-09-09 起）**：`pm-workflow` 为 `QUARANTINED / DECOMMISSIONED`，未注册为可用技能。任何 Agent 不得调用、读取其内容作为当前指令、引用其结论或据其执行 PM 落账。PM 作为主 Agent 的治理角色保留，通过 CHG、Decision 与 Continuity v2 工作，不再由技能独占。旧 C/NG-WP/P/REG-WP 计划、PM_SESSION 和 handoff.v1 仅作历史证据。

## 真源索引

| 用途 | 路径 |
|------|------|
| 进门第一步（薄入口，只读定位） | `.trae/skills/cockpit-entry/SKILL.md` |
| 跨 AI 共存与路由 | `.cursor/rules/workspace-ai-coexistence.mdc` |
| 跨 AI 适配入口（非 Trae，纯引用） | `.agent/rules/project-rule.md` |
| 技能注册表 | `.agents/skills.json` |
| 全局开发规则 | `.trae/rules/project-rule.md` |
| 跨技能公共契约 | `.trae/skills/shared/refs/skill_coordination.md` |
| 治理基线 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md` |
| 当前计划与状态投影 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md`（以其“当前投影”为准；上一行的 26 号总计划是治理基线与历史依据） |
| 日常迭代操作手册 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md` |
| 无 AI、断网时的电气/PLC 人工路线 | `0100_PLC自动化/00_通用规范/无AI离线手册.md` |
| 多 agent 工位与控制根规则 | 本文件“多 agent 工位与控制根规则 (WS-001)”一节 |
| 独立审计（任何 agent 通用） | 本文件“独立审计 (AUD-001)”一节；脚本 `reviews/tools/audit_pr.py`，清单 `reviews/21_audit_checklist.md` |
| 隔离对象（禁止使用） | `.trae/skills/pm-workflow/SKILL.md` |
| 全栈执行 | `.trae/skills/fullstack-engineer/SKILL.md` |
| PLC 执行 | `.trae/skills/plc-electrical-engineer/SKILL.md` |
| 规范注册表 | `00_Obsidian_Base全局规范文件仓库/spec_registry.json` |
| 跨语言 SRE 规范 | `00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域/300_高级语言与工业上位机系统_Google_SRE工程可靠性规范_DEV.md` |

## 默认分工与技术栈标准

- **PM 治理角色**：负责事实核验、CHG、Decision、Work 授权与验收；不得使用 `pm-workflow`，不得把 PM_SESSION、handoff.v1 或聊天文字视为执行真源。
- **plc-electrical-engineer**：PLC 工程执行主力，全面遵循 Siemens LSP 扩展生态及 LSP-905~908 规范（语法白名单、DINT 定时器三段式、CASE 防死锁 ELSE、.plc.json 依赖）与汽车制造级标准（STD-830 OMAC 状态机、STD-840 典型设备块、STD-850 步进链、STD-860 首出诊断）
- **fullstack-engineer**：Python/高级语言全栈执行主力，全面遵循 DEV-300（Google SRE 零崩溃/白盒日志/黄金信号）与 DEV-210/DEV-216/DEV-218（PySide6+QML 5 层整洁架构、Bridge/DTO、QRunnable 线程模型、Ruff+Mypy）
- **基础设施**：`.trae/` 由 Trae 生态维护；其他 AI 只读，除非用户明确要求修改

## 强制协同铁律（澄清-报批-执行-验收 四阶段）

所有 AI 在处理用户的业务需求、功能修改或缺陷变更时，必须严格分步执行，**严禁在需求不明时擅自脑补实施，严禁未经审批擅自篡改代码**：
0. **用户只给一句话需求是常态**：目标拆分、可改范围、机器可判的验收标准由 agent 补出、交用户核对；具体步骤见 `.trae/skills/cockpit-entry/SKILL.md`“用户只给了一句话需求时”。
1. **阶段 0【需求澄清与代码基优先门禁 (Codebase-First Gating)】**：
   - **严禁代码盲问 (Zero-Stupid-Questions Redline)**：严禁在未检索代码库的情况下直接向用户提问。任何可在项目源码、配置文件（`.plc.json` / `pyproject.toml`）、接口文档（`INT.md` / `VAR.md`）、数据结构（DTO / UDT）或规范库中读取到的参数、变量名、调用关系与目录路径，**绝对禁止向用户发问**；
   - **二分法处理原则 (Greenfield vs Brownfield)**：
     - **全新建仓 (Greenfield)**：审查 CAD/轴系/动作时序 3 要素。若缺失，先检索 Obsidian 规范库与模板库；仍缺失物理硬件事实时方可向用户提问；
     - **在研迭代/缺陷变更 (Brownfield)**：先按 `cockpit-entry` 从工作区根执行只读定位 `main.py pm orient <PID> --json`（需要恢复细节时再用 `main.py pm resume <PID> --json`；仓库记录的发布版本 1.3.3-d8f7c8b 还没有 `pm orient`，新克隆的工作区在发布指针更新前改用 `pm resume`），再由 PM 角色只读勘测或派发 Grooming；没有匹配的 Work/Run/Decision 时不得修改；
   - **有效提问门槛**：只有当代码库探路完毕，且发现涉及无法推导的真实业务决策抉择（Trade-off）、新增未接线硬件定义或客户冲突诉求时，方可发起《高质量澄清提问清单》；
2. **阶段 1【报批】**：PM 角色输出《需求分析与技术实施计划》（注明依据规范 PM-042/PM-033、受影响文件及 HTML 原型方案），**必须显式停下来等待用户确认**（“请确认是否批准开工？”）；
3. **阶段 2【执行】**：仅在用户明确回复“同意/批准”后，方可派发给对应执行技能（PLC / 全栈）编写代码与自动化测试。严禁在对话框要求或输出长篇说明书草稿，文档骨架由 Copier 脚手架生成并填空；
4. **阶段 3【验收】**：执行端创建 Checkpoint 并回执后，主 Agent 核验 Git/门禁证据，报用户验收；用户验收后由用户在驾驶舱界面点“确认验收”，它记下验收并走 `close_accepted` 一步收口（推进 Run、Work 和 Mission，把证据写进变更单；变更单再用 `change transition … --pid <PID>` 推到 completed），**不得单独用 `continuity run/work transition` 推 Run 或 Work 的状态**，收口后执行 `main.py ledger reconcile <PID>`。PM_SESSION 已退役（用户 2026-10-10 裁决），不再刷新，仅作历史证据。闭环未完成前不得宣布结项。

## 子代理物理隔离法则（执行权剥离）

1. **明确边界**：主会话（主 Agent）仅限业务路由、需求澄清、架构设计（PMBOK 启动/规划过程组）与交付验收（收尾过程组）。
2. **预研与执行分流**：
   - **阶段 0 预研模式（`--mode grooming`）**：PM 调度领域子代理执行只读探路与代码上下文勘测，子代理以 `handoff_result` 回传事实摘要；
   - **阶段 2 执行模式（`--mode execution`）**：用户审批后，PM 褫夺编码权，派发执行子代理进行代码填空、门禁自检与测试验证。
3. **强制契约化交接**：派发前必须建立并授权 Work、启动带 lease 的 Run，声明 Decision 与 owned paths；执行端创建 Checkpoint，并在换 Agent 时使用 handoff.v2。主 Agent 收到回执后完成 Run/Work、CHG 与台账闭环。

## 多 agent 工位与控制根规则 (WS-001)

> 生效时间：下面写到的“登记 Run 被拒”和第 5 条“不带 `--control-root` 就拒绝”，在源码里已实现，但当前部署的发布版 1.3.3 还没有，要等 D07 部署后才自动拦截；在那之前由各 agent 自觉遵守。根入口拒绝在工位里运行（第 2 条）现在就生效。

每台电脑分两层。两个 agent 站在同一个工位上，等于两个人同时改一张接线图，所以工位必须分开；账本只能有一本，所以控制根只能有一个。

| 层 | 位置 | 每台电脑几个 | 用途 |
|------|------|------|------|
| 控制根 `R` | 本机唯一一份仓库克隆，停在 `main` | **1 个** | 持本机账本 `R/.auto-pm/continuity.db`；只跑驾驶舱命令（`main.py pm resume`、`main.py ledger reconcile`、`main.py continuity …`），不写业务代码 |
| 工位 `W` | `R/.auto-pm/worktrees/<agent>` | 每个会改文件的 agent 1 个 | agent 在自己的分支上写代码、跑测试、提交、推送 |

**工位与分支前缀表**（第二个写代码的 agent 默认是本机 Claude Code）：

| agent | 工位 | 分支前缀 |
|------|------|------|
| 本机 Claude Code（含在 VS Code 里跑的 Claude Code） | `R/.auto-pm/worktrees/claude` | `claude/` |
| Trae 里的 AI | `R/.auto-pm/worktrees/trae` | `trae/` |
| Cursor 里的 AI | `R/.auto-pm/worktrees/cursor` | `cursor/` |
| VS Code 里的其他 AI（如 Copilot） | `R/.auto-pm/worktrees/vscode` | `vscode/` |
| Codex（当前只做 PR 自动审查，不写代码；将来写代码时） | `R/.auto-pm/worktrees/codex` | `codex/` |
| 项目 Claude、云端会话 | 不占本机工位；每个云端会话的克隆就是那台“电脑”自己的控制根 | `project/`（项目 Claude）、`claude/`（云端会话） |

表外的 AI 先由用户登记名字和前缀，再开工位。已合并的历史分支（如主执行用过的 `codex/pr-…`）不改名，新卡按本表。

**铁律：**

1. **一台电脑只克隆一次。** 工位一律用 `git worktree add` 从控制根派生，放在 `R/.auto-pm/worktrees/<agent>`。放到别处会出问题：
   - 另克隆一份仓库：驾驶舱把它当成第二个控制根，另开一本 `continuity.db`，一台电脑两本账，谁在做哪张卡对不上。**严禁。**
   - 控制根里、但不在 `.auto-pm/worktrees/` 下的工作树：登记 Run 被拒，提示“Run worktree 必须位于受管 .auto-pm/worktrees 目录”。
   - 控制根外面的工作树：登记 Run 被拒（“Run worktree 位于 workspace 外”）；在里面执行驾驶舱写命令也被拒（“控制面写命令只能在含真实 .git 目录的主 Git 工作树执行”）。
   - `.codex/worktrees/`：根入口在那里会拒跑，但登记 Run 不认它，不要用。
2. **驾驶舱命令只在控制根执行。** 在工位里执行 `main.py` 会被拒（“managed candidate is execution-only; invoke the canonical control root instead”）。登记 Run 时在控制根执行 `main.py continuity run start …`，用 `--worktree` 指向自己的工位绝对路径。
3. **一个 agent 同一时刻只开一个工位，一个工位同一时刻只做一张卡**，分支名 `<前缀><卡号或主题>`。Git 本身保证同一分支不能被两个工作树同时签出。
4. **一张卡同一时刻只派给一个 agent**，派卡时写明 owned paths，两个 agent 不同时改同一批文件。
5. **在工位里提交**：提交检查通过 `git rev-parse --git-common-dir` 自动找到控制根，不需要手工指定；手工调用时必须带 `--control-root R`，否则 fail-closed 拒绝。
6. **台账、WBS、治理库、发布指针只由账本主机上的主执行写**，工位里的 agent 不写。
7. **跨电脑只通过 GitHub 交换代码**：每个工位推自己的分支、开 PR，合进 `main` 后各控制根拉 `main`。

**开工位 / 收工位（现在手工执行，在控制根里）：**

```
git fetch origin main
git worktree add -b claude/<卡号> .auto-pm/worktrees/claude origin/main
git worktree list
git worktree remove .auto-pm/worktrees/claude    # 收工：分支已推送、工位无未提交改动后再执行
```

**待实现**（实现前按上面手工规则执行）：

- 一键命令 `main.py worktree open <agent> <卡号>` / `worktree list` / `worktree close` 与 agent 名册（X05）。
- 账本主机联锁：非账本主机写台账一律拒绝（X06）。
- 跨电脑工作票（同一张卡两台电脑不能同时领）与查看其他电脑在做什么（X10、X08）。

## 插急活：一个项目开着好几张卡 (WS-002，TD-071)

> 生效时间：TD-071 卡 1～4 合进 `main` 并部署后。部署前一个项目仍只能开一张卡，下面的命令不存在。

一个项目可以同时开着好几张卡（软上限 8 张），但**同一时刻只有一张“在干”**，像一台设备只有一把操作钥匙。驾驶舱把卡分四栏：**在干 / 等你 / 搁着 / 已关**。“搁着”的卡记了断点（干到哪、下一步做什么），钥匙已经交出，谁也不能往它的工作树里写。

1. **切哪张、拿回哪张只听用户的。** `pm park`（放进“搁着”）、`pm unpark`、`pm switch` 都要带 `--approval-evidence-ref`，写用户原话所在的位置（例如 `user-confirmation:` 加消息时间）。用户没说过，绝不自己编。
2. **agent 自己只能停在“等你”。** 没有用户原话时，只能 `pm park` 不带凭据，把**自己手上**这张卡记好断点放进“等你”，然后停下告诉用户。
3. **插急活的标准顺序**：用户说“先做 B” → `pm switch --pid <项目> --to <B> --reason … --summary … --as <你的身份> --approval-evidence-ref …`（一步：先把手上的卡搁着，再拿起 B）。B 还没开工时，switch 只做第一步，并给出 `pm confirm-start --mission-id <B>`。B 干完验收后，再按用户的话 `pm unpark` 拿回原来那张。
4. **拿回后先同步再干活**：`pm unpark` 会报告“本卡分支落后 main 几个提交”和“和哪张卡改同一批文件”。在本卡工作树里同步 `main`、跑测试；有冲突就停下交给用户，不自动变基。
5. **开新卡撞车要放行**：新卡要改的文件和开着的卡重叠，或者项目已开满 8 张，`pm approve` 会拒并说明撞了谁；用户同意后加 `--admission-release-ref <用户原话位置>` 再批。驾驶舱上没有放行按钮。
6. **不插队抢钥匙**：正在干的卡不能被别人直接抢走（插队 PREEMPT 不支持）；要切换只能先 park。`pm missions --pid <项目>` 随时只读查看四栏。
7. 搁着超过 7 天的卡在看板上标黄：提醒用户决定拿回还是作废，不要自己作废。

## 独立审计 (AUD-001)

每个 PR 合并前都要独立审计，换成任何 agent（Claude、Codex、Cursor、Trae 或新来的）都照这一节做。审计脚本只用 Python 标准库、git 和 GitHub 公开接口，不依赖哪一家 AI。

1. **做的和审的分开**：写这个 PR 的 agent 或会话不能审它，要换另一个 agent 或另一个会话。
2. **先跑机械检查**：在仓库根执行 `python reviews/tools/audit_pr.py <PR号>`；可选 `--json`（机器可读输出）、`--offline`（不访问 GitHub，查不了 CI 结论）、`--skip-ci-result`（不查 CI 结论）、`--repo owner/name`。
3. **读退出码**：0＝没有 FAIL；1＝至少一项 FAIL，不能合并；2＝用法或 Git 出错，修好再跑。WARN 要在报告里点名，UNVERIFIED 要人工补查。
4. **再人工逐项核**：照 `reviews/21_audit_checklist.md` 一条条核（范围、受保护路径、内容是否属实），脚本不代替这一步。
5. **出报告**：按清单第 4 节写到 `reviews/`，推到审计者自己的分支，并把结论贴到 PR 评论里；审计者不推 `main`、不删除任何东西。
6. **合并条件**：审计通过、CI 全绿、评审对话全部解决，三条都满足才能合并，只用 **Merge commit**（不用 Squash 或 Rebase）。

## 修复与汇报规矩 (FIX-001，用户 2026-10-22 批准)

1. **修复卡附同类排查清单**：修一个缺陷时，先写根因，再把全库同类写法一次查全，清单写进卡里，逐条修或写明不修的理由；只修挡路的那一处不许报“已修好”。独立审计逐条核这张清单；技术债关单时要证明根因已经除掉。
2. **样件联调查出的缺陷先修再用**：只要本周要做的活会碰到，就先修，不做“这一单不受影响”的窄核对。
3. **“完成”“可承诺”必须附证据**：提交号、对账结果、门禁或样件联调结果，至少一样；拿不出证据就写“未核实”。
4. **先查已定事项再提问**：向用户提问前，先查项目的《用户已定事项台账》和用户给过的图纸、手册；查到了就照着做，只告诉用户按哪天的定法处理。同一个问题不问第二次。
5. **操作说明四要素**：交给用户的每个操作都写清哪台电脑、哪个窗口或对话（写全名）、点什么或贴什么、做完会看到什么。AI 能用命令行自己做的，不交给用户做。

## AI 工程师主动担当与零负担交付铁律 (Zero-Burden Law)

所有 AI 必须牢记：**用户是决策总负责人，AI 是专业系统工程师**。

1. **【零负担法则的明确边界】**：
   - **零负担的真正定义**：AI 必须独立消化全部代码编写、语法白名单检查、死链扫描、自动化测试、文档存在性与 AST 注释覆盖率门禁验证的繁重体力活，绝不把半成品和报错转嫁给用户；
   - **严禁借“主动提问”推卸代码调研责任**：专业系统工程师的第一职责是**自己阅读代码与工程资产**。严禁借“主动提问”之名掩盖偷懒不读代码的行为。只有在彻底查阅代码库后仍存在不可推断的物理/业务边界时，向用户发起的提问才具有专业担当！
2. **【严禁半成品外溢】**：呈报给用户验收的内容，必须是 100% 经过严格走查、无死链、无运行时报错、全量门禁全绿的最终成果。严禁像“挤牙膏”一样等待用户发现低级破绽。
3. **【交卷前极限自我施压】**：在向用户报告“已完成”前，AI 必须先扮演最严苛的测试专家，主动完成：
   - SCL 代码：通过根入口 `main.py plc check <PID>` 执行驾驶舱 PLC 检查——Siemens 语言服务插件命令行 `check`/`test`（本机已安装插件的真实诊断，只在本机调用，不复制、不分发）、SCL 结构完整性规则、命名与禁用语法（LSP-905）规则与文档一致性；有失败项退出码为 1，找不到插件算“未验证”（警告），到交付阶段拦住；
   - 文档与注释：通过根入口 `main.py doc check` 执行静态扫描；
   - HMI 原型：通过导航死链静态扫描（所有按钮均有对应页面，所有 JS 函数均有显式定义）；
   - Python 上位机：通过 pytest 全量测试（100% 绿门禁）与类型检查 (`ruff/mypy`)。
4. **【绝不就事论事，根治源头产线】**：只要发现一处缺陷，AI 的第一反应必须是**溯源驾驶舱脚手架模板（`templates/`）、代码生成器（`Service`）与门禁规则（`Linter`）**，从源头彻底消缺，并补充自动化防御单测，确保未来生成的项目 100% 不复发。
5. **【只报成果与决策，彻底消化琐事】**：彻底消化技术实现细节，只向用户呈报经过充分验证的清晰结论与宏观决策点。

## 临时文件与测试清理铁律 (DEV-TMP-001)

1. **【即时销毁不可复用产物】**：自动化测试（pytest）、性能基准（benchmarks）或调试脚本运行中产生的临时文件（如 `tmp_*.py`、`.coverage`、`htmlcov/`、临时日志等），在测试结束/任务收尾时**必须即时自动删除**，严禁残留或裸露在工作空间根目录；
2. **【持久化文件规范收敛】**：测试报告、覆盖率归档等需持久保存的文件，统一输出至 `.auto-pm/reports/` 或专用目录，禁止直接丢在根目录；
3. **【防扩散门禁】**：交卷前必须确保工作空间根目录保持纯净，`.gitignore` 必须同步覆盖所有临时测试和编译缓存。
4. **【Agent 通信与状态文件】**：多智能体协作（如 Teamwork、Subagents）产生的过程文件（`handoff.md`、`progress.md` 等）必须局限在 `.agents/` 目录下。该目录属于临时运行态（除 `skills.json` 外），严禁手动将其过程文件纳入 Git 追踪。

## 版本库策略

- **纳入 Git**：`.trae/skills/`、`.trae/rules/`、`.cursor/rules/`、`.agent/rules/`、`.agents/skills.json`、`AGENTS.md`
- **不纳入 Git**：`.cursor/` 下除 `rules/`、`commands/` 外的本地状态；`.trae/tmp_*` 等临时文件；**`.agents/` 目录下的所有过程文件与运行日志**（必须通过 `.agents/*` 与 `!.agents/skills.json` 实现精准过滤）。

## Obsidian 规范库冷热隔离治理规则 (Spec-Isolation-001)

当需要对 `00_Obsidian_Base` 规范库进行定期清洗或扩容评估时，所有 AI 必须遵守以下分类规则：

1. **【热索引判定（保持激活）】**
   - 被 `spec_registry.json` 的 `specs` 字段索引、且 `lifecycle` 为 `stable` 或 `active` 的规范文件；
   - 规范库的元文件（`00_INDEX_*.md`、`README.md`、`spec_registry.json`）。

2. **【自动归冷判定（移入 `Archive_Cold/`）】**
   - 以 `CHG-` **开头**的具体变更单实例文件（如 `CHG-PLC-2026-001.md`）；
   - `_archive/` 目录下的所有历史/废弃文件；
   - 未被 `spec_registry.json` 索引的边缘工具指南（需逐一评估是否为跨域刚需）；
   - 自动生成的元数据汇总报告（如 `规范元数据汇总报告.*`）。

3. **【禁止误伤的豁免项】**
   - 文件名含 `_CHG` **后缀**的通用模板（如 `040_通用变更单模板_CHG.md`）不属于变更单实例，**不得**自动归冷；
   - Git 使用指南 (902)、Mermaid 工作流规范 (906) 等跨域高频工具指南属于全员刚需，应保持热索引。

4. **【操作规范】**
   - 冷文件统一移入 `00_Obsidian_Base/Archive_Cold/`，保留相对目录结构，不得删除；
   - 每次清洗必须输出《清洗台账》记录全部分类决策与物理操作；
   - 清洗完成后必须运行验证脚本确认 `spec_registry.json` 完整性。

## 战略基线与工作流边界 (Baseline Conventions)

为支撑"一人全栈超级个体"架构，所有驻留本工作区的 AI 必须遵守以下对齐的业务基线：

1. **【终极定位：超级个体武器库】**
   User 是唯一的架构师、PM 兼最终决策者。AI 的定位是全面替代初中级执行层的"无情流水线工人"，核心诉求是协助 User 以单兵算力交付 IT+OT 融合的全栈非标项目。
2. **【IT-OT 跨界通信契约】**
   当 `fullstack-engineer` (上位机) 与 `plc-electrical-engineer` (下位机) 涉及数据交互时，默认底座为：
   - **OPC UA**：用于承载复杂的业务对象模型（如 DTO 数据结构）。
   - **Modbus TCP**：用于承载极简、低延迟、高频的散点 IO 轮询或历史遗留通信。
   与上位机（IT-OT）交互的 `INT.md` 接口文档必须基于这两种协议之一进行设计；设备之间（上游、下游、机器人等）的交换区，协议由项目选定并写入方案级 `INT.md` 的“交换区契约”（协议列是开放列表，如 Modbus TCP、CC-Link、PROFINET、OPC UA 等）。
3. **【知识库迭代铁律 (Obsidian CCB 控制)】**
   全局法典 (`00_Obsidian_Base`) 严禁 AI 擅自覆写。当且仅当在项目中遇到规范不适用、需沉淀新经验时，AI 必须通过 PM 流程提交 `CHG单 (变更请求)`。所有针对 Obsidian 规范库的变更，必须经由 User (架构师) 亲自审批同意后，方可通过驾驶舱脚本生效。
4. **【OT 执行交付边界】**
   PLC 源码的零负担交付边界停留在**静态语法自检全绿**阶段。AI 必须确保逻辑自洽并符合 LSP 规范；将 ST 源码导入 TIA Portal/InoProShop、编译下发、以及捕捉断言报错等深度动作，由 User 接管并作为外部反馈（截图/文本）闭环给 AI。

5. **【反提示词依赖与基建下沉铁律 (Anti-Prompt-Dependency)】**
   - **系统级卡点优先**：严禁试图用冗长的自然语言 Prompt 去乞求 AI 遵守代码规范、写注释或输出文档。任何可量化的质量要求（如注释覆盖率、文件存在性），必须下沉为物理脚本（如 `main.py doc check`）或 Git 自动化卡点。
   - **模板即“捕兽夹”**：Copier 等工具生成的绝不仅仅是空文件，而是带有强制 `TODO` 占位符的质量陷阱。执行代理（AI 程序员）的唯一任务是精确填空，禁止擅自修改验证骨架。
   - **机器无情判卷**：主控 PM 严禁主观肉眼审查代码质量。PM 必须无条件采信底层 `Linter / Checker` 的物理 Exit Code，只要非零就无情打回重做，拒绝听取 AI 的任何口头解释。
6. **【标杆驱动基建法则 (Benchmark-Driven Infrastructure)】**
   - **拒绝凭空造轮子**：当需要新增或大规模重构 Copier 模板、代码脚手架时，严禁 AI 脱离实际物理工程凭空捏造。必须在物理硬盘中指定一个历史真实项目作为“活体基准 (Benchmark)”。
   - **正向推演三步曲**：基建升级必须绝对遵循单向工作流：① **治愈**：修复基准项目直至满分全绿；② **提纯**：剥离业务代码提取干净模板；③ **立规**：挂载模板并锁死门禁。
   - **基因防污染**：严禁在母体项目未达成 Exit Code 0 之前强行提取模板。病态的基因绝不能进入基础设施库。
7. **【资产沉淀与高低算力分流法则 (Asset Precipitation & Compute Routing)】**
   - **严禁知识断层**：当通过高算力推演（如 Teamwork、复杂人类介入）攻克了新工艺逻辑或新架构缺陷后，必须强制执行资产沉淀，严禁将经验仅停留在聊天上下文中。
   - **资产生态位绝对隔离**：
     1. **业务大脑 (Obsidian)**：仅用于沉淀抽象后的核心工艺、状态机逻辑与数据字典（如 STD 规范）。
     2. **物理骨骼 (驾驶舱/Copier)**：仅用于沉淀非功能性约束、目录结构规范与强制门禁校验规则。
     3. **执行肌肉 (Agent Skills)**：严禁在 `SKILL.md` 中保存业务逻辑与格式要求。技能库必须极度轻量化，仅包含读取真源、填空模板与调用工具的流水线 SOP。
   - **低成本日常运行 (OpEx 优化)**：资产沉淀完成后，日常的特征开发与代码编写必须交由被“模板陷阱”和“真源规范”严格约束的轻量级子代理执行，以最低的 Token 成本榨取最大的自动化红利。

8. 【反捷径与测试作弊铁律 (Anti-Mocking & Verification Isolation)】
   - **严禁为了骗取绿灯而 Hardcode**：在实现核心业务逻辑或跨端代码生成时，严禁为了通过单元测试而进行硬编码（Hardcode）或 Mock（例如为了让 AST 测试通过而直接返回预期的字段名）。AI 必须编写出真正基于物理法则和业务规范（如 Siemens S7 内存对齐协议、Word-Swap 字节序）的动态推演代码。
   - **验证与生成的绝对隔离**：在编写自动化验证脚本或门禁（如 `--verify` 命令）时，必须确保验证逻辑完全处于只读（Read-Only）上下文中。严禁在执行断言之前意外触发文件生成或覆写动作，导致“自己检查自己刚刚生成的文件”从而掩盖用户的破坏性篡改。

## 文件编码与读写铁律 (DEV-ENC-001)
在执行 Python 脚本读写工作区内的文本或 Markdown 文件时，**必须显式声明 `encoding="utf-8", errors="replace"`**。这是为了防止由于中文字符、GBK 终端历史遗留导致的 UnicodeDecodeError，保证全栈工具链在各种极端环境下的鲁棒性。

## 子代理零负担自闭环约束 (Execution Loop)
执行代理在向 PM 或用户通过 `send_message` 回复之前，必须**强制进行自我门禁校验**（如 `main.py doc check`、`main.py plc check <PID>` 或 `pytest`）。如果运行结果不是 Exit Code 0，且系统未达到防死循环上限（Bounded Healing），**绝对禁止返回半成品**。必须内部消化错误并重试，违者视为严重破坏零负担铁律。
