# 工作空间 AI 协作入口

本仓库由多个 AI 共用（Claude、Codex、Cursor、Trae、Antigravity 等），规则只写在本文件；各家入口（`CLAUDE.md`、`.cursor/rules/`、`.agent/rules/`、`.trae/rules/`）只指到这里，不复制规则。用户是唯一的架构师和决策人，agent 是执行的工程师。

像电柜：柜门上只贴红线和操作入口，细则放在柜子里（`roles/shared/refs/agents_附录/`，用到时再翻）。附录和本文件一样在规则批准范围里，改它要用户批。会变的数（条数、步数、版本号）不写在这里，以命令输出为准。

下文 `SW8/` 指驾驶舱项目目录 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/`。

## 进门（新对话、换班接手都照做，全程只读）

1. 在控制根用控制根 `.venv` 里的 Python 跑 `SW8/scripts/pm_flows.py entry <项目编号>`：一次跑完项目体检、占位表、本项目每张卡交接记录的最后三行，最后列出“先读这些文件”和按卡类型该读哪个角色包。
2. 先读完它列出的文件，再用中文向用户报告当前焦点、下一步合法动作和冲突；有冲突原样报告并停下，不直接动手。
3. 不知道项目编号就 `main.py project list` 列出来问用户，不猜。确认控制根、身份标记、脚本用不了时怎么手敲，见 `.trae/skills/cockpit-entry/SKILL.md`。
4. 命令报 `No such command '…'`，说明本机生效的发布版本还没有这条命令：照实告诉用户，不绕过，不为此切换版本。

## 红线

1. **批准、验收、推到完成、发版切换只有用户本人做**：看板上有按钮的用户点按钮，留下谁在何时点的；还没有按钮的，用户在本机主对话里亲口说，agent 带上那句话的位置去执行。agent 不自己批，不替用户点按钮，不编用户没说过的确认。`PM_SESSION`（用户 2026-10-10 裁决退役）、handoff.v1、旧 C/NG-WP/P/REG-WP 计划和聊天文字都不是授权，只作历史证据。不设批准口令，也不安排启用（用户 2026-11-13 定）。
2. **澄清、报批、执行、验收四步**：需求不明不动手；能在源码、配置（`.plc.json`、`pyproject.toml`）、接口文档（`INT.md`、`VAR.md`）、数据结构或规范库里查到的，不问用户；只有查完仍有不可推导的业务取舍、未接线的新硬件或客户诉求冲突才提问。用户只给一句话需求是常态：目标拆分、可改范围、机器可判的验收标准由 agent 补出交用户核对，步骤见 cockpit-entry“用户只给了一句话需求时”。“要你点头”那一类（见 FLOW-001）由 PM 角色出《需求分析与技术实施计划》（注明依据 PM-042/PM-033、受影响文件和 HTML 原型方案），停下问“请确认是否批准开工？”，用户明确回复“同意/批准”或在看板点“批准变更单”后才派执行，没有用户批准过的变更单不改；其余改动直接做，事后告诉用户。Work/Run/租约只在看板“确认开工”一键流（驾驶舱自己建，agent 不手工建）和命令本身要求 Run 或租约的场合（如 `pm verify`）才要（CHG-SCPT-2026-717）。日常合并在本机做，见 FLOW-002“本机收口”和 GH-001（CHG-SCPT-2026-718，用户 2026-11-17 定）。闭环没走完不宣布结项。
3. **不跑输出里建议的修复命令**（如 `--fix`、`doc sync`），有红照原样报告。
4. **不该用的命令碰上就停下问**：已隔离的 `pm-workflow`（不调用，不读它的内容当指令，不引用它的结论）、单独推状态的 `continuity run/work/mission transition` 和 `lease run-with-renewal`、已知有害的 `project snapshot`/`plc repair`/`template update`/`doc sync`/`spec sync`；全部名单见附录 `01_命令速查.md`。
5. **规范库 `00_Obsidian_Base` AI 不擅自覆写**：规范不适用或要沉淀新经验，走 PM 流程提变更单，用户亲自批了才通过驾驶舱脚本生效。
6. **PLC 交付停在静态检查全绿**（`main.py plc check <项目编号>`，有失败项退出 1），逻辑自洽、符合 LSP 规范；导入 TIA Portal/InoProShop、编译、下载和硬件测试归用户，结果由用户回传。
7. **不为绿灯写死结果或 Mock**，核心逻辑按物理法则和业务规范真算；验证逻辑只读，不在断言前生成或覆写文件。文档骨架由 Copier 脚手架生成后填空，不在对话里写长篇说明书草稿。
8. **不交半成品**：交用户前自己跑完检查（PLC `plc check`、文档 `main.py doc check`、HMI 原型查死链、Python 全量 pytest 和 ruff/mypy），不是退出码 0 不交；执行代理回复前同样自检，有界重试。“完成”“可承诺”附证据（提交号、对账结果、门禁结果，至少一样），拿不出写“未核实”。发现一处缺陷先溯源模板、生成器和门禁，补防御测试。只报成果和要用户定的事。
9. **修复与汇报 (FIX-001，用户 2026-10-22 批)**：修缺陷先写根因，把全库同类写法一次查全写进卡里，逐条修或写明不修的理由，独立审计逐条核，只修挡路的那一处不许报“已修好”；样件联调查出的缺陷本周要碰就先修。提问前先查项目《用户已定事项台账》和用户给的图纸、手册，同一个问题不问第二次。交给用户的操作写清哪台电脑、哪个窗口或对话（全名）、点什么或贴什么、做完会看到什么；AI 能用命令行做的不交给用户。
10. **文件编码 (DEV-ENC-001)**：脚本读写文本写明 `encoding="utf-8", errors="replace"`；驾驶舱 `auto_pm` 包里新增 `errors="replace"`/`"ignore"` 要在同一调用写 `# lenient-decode: <理由>`（`SW8/tests/infrastructure/test_no_new_lenient_decoding.py` 查）。
11. **临时文件 (DEV-TMP-001)**：`tmp_*`、`.coverage`、`htmlcov/`、临时日志用完即删，不留在工作区根目录（体检会点名）；要留的报告放 `.auto-pm/reports/`；`.gitignore` 覆盖临时和编译缓存；多 agent 过程文件（`handoff.md`、`progress.md` 等）只放 `.agents/`，除 `skills.json` 外不入库。
12. **`.trae/` 由 Trae 生态维护**，其他 AI 只读，除非用户明确要求；Trae 里的 AI 改 `.trae/` 也要先有用户原话，不自改自合。
13. **IT-OT 通信**：上位机和 PLC 之间用 OPC UA（复杂业务对象）或 Modbus TCP（低延迟高频散点 IO），`INT.md` 按其一设计；设备之间（上下游、机器人等）的交换区协议由项目选定，写进方案级 `INT.md` 的“交换区契约”。

## 改动分两类 (FLOW-001，用户 2026-11-13 提出，2026-11-17 改为两类)

原来的全流程、标准线、快线三条线并成下面两类（CHG-SCPT-2026-718；用户 2026-11-17 原话：“这个规则是我在项目claude指导下做的，现在看起来不符合实际。github是可选项，不是必选，必须改掉。”）。看这次改到的全部文件，有一个落在“要你点头”那一类，整次就按那一类走；拿不准按“要你点头”；agent 不能自己挑轻的。

| 类 | 改的是什么 | 用户什么时候点头 | 变更单 |
|------|------|------|------|
| 要你点头 | PLC 项目里的文件（`0100_PLC自动化/`）和 PLC 模板（`templates/plc-*`）；安全回路；规则文件（`reviews/tools/rules_approval_check.py` 的 `RULE_PATTERNS` 命中的路径，含本文件）；本机合并命令、提交钩子与变更执行链（`SW8/scripts/pm_merge.py`、`SW8/auto_pm/infrastructure/git_hook_enforcer.py`、`change_status_guard.py`、`change_service.py`、`status_journal.py`、`guard_checker.py`、`SW8/auto_pm/ui/cli/change.py`）；删除或改名驾驶舱项目目录（`SW8/`）以外的已入库文件；发版切换 | 动手前批准（看板“决定”页点“批准变更单”，或在本机主对话里亲口说），合并后由用户本人推到完成 | 先建单，批准后才动手；同一类的几件事可以并成一张单，批一次 |
| 直接做，事后告诉你 | 其余全部：驾驶舱代码、脚本、看板、测试、文档，删掉驾驶舱里不用的文件 | 不逐个点头；合并当天（最迟下一次例行汇报）告诉用户一行：改了什么、合并提交号、怎么退（`git revert -m 1 <合并提交>`） | 不建，也不补单；提交说明就是记录 |

**两类都不省的**：先有卡号再动手，一个号用到底，写进分支名和提交说明（“多机”档用 `claim number` 领号；其余档用变更单号或一个短名，例如日期加两三个字）；改动在自己工位的分支上提交，不直接改控制根；本机门禁全绿才合并（FLOW-002“本机收口”）；合进 `main` 不等于在用户电脑上生效，发版切换仍要用户本人同意。**提交钩子只认两样**：“要你点头”那一类的生产代码要一个已批准的变更单号；其余生产代码要提交说明里单独一行 `领卡占位: <卡号>`。`change create --retrofit`（先做后补）已退役，不再用补单绕过批准在前的约束。快线的旧细则（附录 `02_快线与退回.md`）只作历史，退回办法照旧有效。

## 先走流程，单条命令当点动 (FLOW-002，用户 2026-11-14 00:56Z 提出)

用户原话：“散装的功能不连起来，越到后面越记不住，没有使用，最后换个对话估计命令都找不到了。”

像设备一样，正常生产走自动流程，点动只在维修和调试时用：agent 日常先走下面的流程，流程里没有的事才查点动。流程由 `SW8/scripts/pm_flows.py` 跑（在控制根，用控制根 `.venv` 里的 Python），只把已有命令按顺序串起来，会改状态的步骤都是停点；脚本不在发布载荷里，控制根 `main` 拉到最新就是最新的。每条流程的完整步骤用 `pm_flows.py steps <entry|checkup|closeout|closeout-pr>` 列出（只列不跑）；脚本用不了时照列出的步骤在控制根逐条手敲 `main.py …`，顺序相同。

**项目体检**：`pm_flows.py checkup <项目编号>`，全程只读，进门后、动手前、交卷前各跑一次。每一步都跑完，哪一步红了也接着跑，最后列小结：每步通过、红或跳过，红的写出整条命令和退出码；有红的照原样报告。没有账本的克隆（云端会话）查卡那一步会红，是查不到账本，不是项目有问题。

**本机收口**（日常的常态，两类都用；GitHub 在哪一档都一样）：
1. 在工位分支上提交，提交说明里单独一行 `领卡占位: <卡号>`；“要你点头”那一类再写上变更单号。工位里先 `git merge main` 跟上最新的 `main`。
2. 在控制根跑 `pm_merge.py merge <你的工位名>`（脚本在 `SW8/scripts/`，用控制根 `.venv` 里的 Python）。它查分支、控制根副本，并在联网档对账。受保护改动和正式绑定了变更单的分支还查实施卡、批准范围和独立审计。正式绑定可写在分支尾段、领卡号、提交标题的 `[CHG-…]` 或单独一行 `变更单: CHG-…`。新卡放在项目的 `04_监控` 或 `11_监控` 下的 `01_变更管理/03_实施卡/`，已有的旧规划卡继续按原路径表核对。门禁由驾驶舱管理，合并执行 `gate precheck`，受保护改动还核对同一候选的 `gate start` 全量结果。都过了才合进 `main`，记一笔，按 GitHub 档推备份。
3. 走变更单的改动在合并前要有独立审计放行（AUD-001）。合并后 agent 把变更单推到验收中（implementing → pending_acceptance → accepting），推到完成只有用户本人（看板“决定”页点“推到完成”，或用户在本机主对话里说“把 <变更单号> 推到完成”，agent 带上那句话的位置再跑）。推到完成后驾驶舱改写的变更单原件和台账，放进下一个工位分支一起合并，不为它单开一次。
4. 当天一行告诉用户：合并了什么、合并提交号、怎么退。
5. 用户说“同意收工位”后 `worktree close <你的名字>`。

控制根的 `main` 只由 `pm_merge.py merge` 改（从 GitHub 同步用 `pm_merge.py sync`）。每台电脑装一次本机钩子 `pm_merge.py install-hook`，拦住直接提交到 `main`；`pm_flows.py checkup` 的“本机合并对账”一步核对 `main` 上每个提交的来历，对不上的报给用户，由用户定留还是退，agent 不自己退。

**交卷到收口**（走 Run 的卡，即看板“确认开工”一键流开出来的卡；一步红就停）：`pm_flows.py closeout <项目编号> --mission-id <卡号> [--done <停点名>]`

| 步 | 命令 | 谁来做 |
|---|---|---|
| 1 | `pm acceptance-scan --pid <项目编号>` | agent |
| 2 | `pm control-root-status <项目编号>` | agent |
| 3 | `pm verify --mission-id <卡号> --lease-wallet` | **停**：用户说“同意 <卡号> 交卷验证”后 agent 跑 |
| 4 | `pm missions --pid <项目编号>` | agent |
| 5 | `pm accept --mission-id <卡号>` | **停，只有用户本人批**：看板点“确认验收”（验收和收口一步做完），或在自己的终端跑；用户在本机主对话里亲口说了验收，agent 带上那句话的位置再跑 |
| 6 | `pm close --mission-id <卡号>` | **停**：用户说“同意 <卡号> 收口”后 agent 跑；看板已一步收口的跳过 |
| 7 | `pr settle-scan <项目编号>` | agent；输出里有变更单号 |
| 8 | `change transition <变更单号> --to completed --pid <项目编号>` | **停，只有用户本人批**：看板“决定”页点“推到完成”；看板上还没有这个按钮时，用户在本机主对话里说“把 <变更单号> 推到完成”，agent 带上那句话的位置再跑 |
| 9 | `ledger reconcile <项目编号>` | agent；不加 `--fix` |
| 10 | `worktree close <你的名字>` | **停**：用户说“同意收工位”后 agent 跑 |

停下后接着走：那一步做完，在原命令后加 `--done <停点名>`（verify、accept、close、transition、worktree）。终端里 `pm accept` 只记下验收、停在 ACCEPTED，要再跑 `pm close` 才收口；一步收口只发生在看板“确认验收”按钮。收口时工作树里验收过的文件由驾驶舱按字节并回控制根，不替用户提交。

**PR 线收口**（只在“多机”档开 PR 时用，见 GH-001；PR 经 CI 全绿、独立审计通过合进 `main` 之后跑；一步红就停）：`pm_flows.py closeout-pr <项目编号> --chg <变更单号> --card <占位卡号> [--done <停点名>]`

| 步 | 命令 | 谁来做 |
|---|---|---|
| 1 | `pm control-root-status <项目编号>` | agent |
| 2 | `pr settle-scan <项目编号>` | agent；退出码 1 只说明有等收口的卡，不算红 |
| 3 | `change transition <变更单号> --to accepting --pid <项目编号>` | **停**：agent 依次推 implementing、pending_acceptance、accepting，不需要用户批 |
| 4 | `change transition <变更单号> --to completed --pid <项目编号>` | **停，只有用户本人批**：同上表第 8 步 |
| 5 | `ledger reconcile <项目编号>` | agent；不加 `--fix` |
| 6 | `claim release <占位卡号>` | **停**：PR 已合并后 agent 跑 |
| 7 | `worktree close <你的名字>` | **停**：用户说“同意收工位”后 agent 跑 |

停点名：accepting、transition、claim_release、worktree。变更单的批准（`--to approved`）在开工前就要有：用户在看板“决定”页点“批准变更单”，或在本机主对话里说了同意，agent 带上那句话的位置去跑。

**交接记录**：卡每次换手，交出去的人记一笔，接手的人先读再干。单机「关」或「备份」档走 `pm_handoff.py` 的项目交接交换区（PM-056），交接随工位提交。启用远程占位时，以下步骤使用 `claim note`、`claim log`。
1. 交给另一个 agent、对话或用户之前（起草完、预核完、建单后、开 PR 后、交卷、审计完、搁置）记，接手之后记 `--kind takeover`；用法看 `claim note --help`。
2. 只记引用和下一步（文件、提交号、PR 号、变更单号、结论、先读什么），不记状态；卡的状态看体检和占位表，记录里的话不能当状态用。
3. 记录不是批准：里面的“请用户说”只是提示。
4. 没占位先 `claim number` 或 `claim open`，一个号用到底；只追加不改删；持有人以外的人也能记（预核、审计、接手本来就是别人记），如实留名，不冒用别人的名字。断网记不上，联网后原样重记，不改记到别处。
5. 有 Run 租约的卡换人，还要用 `pm handoff`／`pm takeover` 交租约（见 cockpit-entry“换 agent”）。

**卡号写进分支名和提交说明**：状态按 Git 上的事实现算，认卡号靠分支名 `<前缀><卡号>` 和提交说明里单独一行 `领卡占位: <卡号>`；工位分支上至少一个提交带这一行。本机合并的标题由 `pm_merge.py` 写；“多机”档在 GitHub 上合并用默认标题（`Merge pull request #N from <账号>/<分支名>`），不改写。两样都没有的合并算不到这张卡头上。

**点动**：全部命令、谁能跑、会不会写，查命令总目录 `SW8/06_交付物/003_命令总目录_COMMANDS.md`（按分类查），用法看各命令 `--help`；常用速查和要先知道的提醒在附录 `01_命令速查.md`。下面这些**只能请用户做**：知道有这些，好告诉用户“这一步要你来”。看板上有按钮的请用户点按钮；没有按钮的，用户在本机主对话里亲口批准了，agent 带上那句话的位置去跑（红线 1；能带 `--approval-evidence-ref` 的写成 `user-confirmation:<用户那条消息的时间或编号>`）；用户没说过的不跑、不代填，也不替用户点看板按钮。`pm sign-risk` 驾驶舱带凭据也拒 agent，只能交给用户在自己的终端跑。

| 场合 | 命令 |
|---|---|
| 批准和开工 | `pm approve`、`pm confirm-start`、`pm inbox confirm`、`pm inbox reject`、`decision create` |
| 验收、搁卡、收占位 | `pm accept`（日常是看板“确认验收”）、`pm park`（带凭据时）、`pm unpark`、`pm switch`、`claim reclaim` |
| 项目、发版、账本 | `project archive`、`project reactivate`、`project delete`、`project restore`、`release deploy`、`release rollback`、`continuity restore-backup` |
| 租约和风险 | `continuity lease extend-hold`、`pm sign-risk` |

变更单批准（`change transition … approved`）和推到完成，看板上有按钮的由用户点按钮；还没有按钮的由用户在本机主对话里亲口说。其余写命令只在本节和 FLOW-001 说可以时跑：`claim release` PR 没合不放，变更单只在本机建，`gate precheck` 跑得久、占内存算重任务。

## 多 agent 工位与控制根规则 (WS-001)

每台电脑分两层。两个 agent 站在同一个工位上，等于两个人同时改一张接线图，所以工位分开；账本只能有一本，所以控制根只能有一个。这些规矩不管驾驶舱有没有拦得住都要守。

| 层 | 位置 | 每台电脑几个 | 用途 |
|------|------|------|------|
| 控制根 `R` | 本机唯一一份仓库克隆，停在 `main` | **1 个** | 持本机账本 `R/.auto-pm/continuity.db`；只跑驾驶舱命令，不写业务代码 |
| 工位 `W` | `R/.auto-pm/worktrees/<agent>` | 每个会改文件的 agent 1 个 | 在自己的分支上写代码、跑测试、提交、推送 |

| agent | 工位 | 分支前缀 |
|------|------|------|
| 本机 Claude Code（含在 VS Code 里跑的） | `R/.auto-pm/worktrees/claude` | `claude/` |
| Trae 里的 AI | `R/.auto-pm/worktrees/trae` | `trae/` |
| Cursor 里的 AI | `R/.auto-pm/worktrees/cursor` | `cursor/` |
| VS Code 里的其他 AI（如 Copilot） | `R/.auto-pm/worktrees/vscode` | `vscode/` |
| Codex（当前只做 PR 自动审查；将来写代码时） | `R/.auto-pm/worktrees/codex` | `codex/` |
| Antigravity（含其中运行的 Gemini） | `R/.auto-pm/worktrees/antigravity` | `antigravity/` |
| 项目 Claude、云端会话 | 不占本机工位；每个云端克隆就是它自己的控制根 | `project/`（项目 Claude）、`claude/`（云端会话） |

表外的 AI 先由用户登记名字和前缀（加一行到上表），再开工位。已合并的历史分支不改名。工位目录名用别名 `<基名>-<会话ID前6位>`，身份靠环境变量 `AUTO_PM_AGENT` 声明（只在一条命令期间设置）：Cursor、VS Code 里的 AI、Trae 等没有自带标记的必须自己带上，否则驾驶舱把它当成用户本人。名字规则、回收办法、发版切换前的手工 git 命令见附录 `03_工位细则.md`。

1. **一台电脑只克隆一次**，工位一律从控制根 `git worktree add` 到 `R/.auto-pm/worktrees/<agent>`；另克隆一份等于一台电脑两本账，严禁；放到别处登记 Run 会被拒；不用 `.codex/worktrees/`。
2. **驾驶舱命令只在控制根执行**；在工位里执行 `main.py` 会被拒。登记 Run 在控制根跑 `main.py continuity run start …`，`--worktree` 指向自己的工位绝对路径。
3. **一个 agent 同一时刻只开一个工位，一个工位同一时刻只做一张卡**；一张卡同一时刻只派给一个 agent，派卡写明 owned paths，两个 agent 不同时改同一批文件。
4. 在工位里提交，提交检查自动找到控制根；手工调用带 `--control-root R`。
5. 台账、WBS、治理库、发布指针只由账本主机上的主执行写，工位里的 agent 不写。
6. 跨电脑在需要时经 GitHub 交换代码（GH-001）：平时在一台电脑上干活；换电脑前在原来那台跑 `pm_merge.py push`（“备份”档每次合并后已自动推），到另一台先 `pm_merge.py sync`；两台同时干活时切到“多机”档，推自己的分支、开 PR，合进 `main` 后各控制根拉 `main`。

开工 `main.py worktree open <agent> <卡号>`，看 `main.py worktree list`，收工 `main.py worktree close <agent>`（有未提交改动或没推送的提交不删），可清理的 `main.py worktree sweep`（加 `--apply` 才删）。只有用户自己的终端（没有 agent 标记）才能收别人的工位。

## 插急活 (WS-002，TD-071)

一个项目可以同时开着好几张卡，但同一时刻只有一张“在干”，像一台设备只有一把操作钥匙。**切哪张、拿回哪张只听用户的**：`pm park`（带凭据）、`pm unpark`、`pm switch` 的 `--approval-evidence-ref` 写成 `user-confirmation:<用户那条消息的时间或编号>`，用户没说过绝不自己编，`--admission-release-ref` 同样。**agent 自己只能停在“等你”**：没有用户原话时只能 `pm park` 不带凭据，把自己手上这张卡记好断点放进“等你”，然后停下告诉用户。不插队抢钥匙。插急活的顺序、拿回后同步、撞车放行见附录 `03_工位细则.md`。

## 开工先订卡 (D-101)

两台电脑、多个云端会话同时干活（“多机”档，GH-001），或本机同时开着两个会改文件的工位时，靠占位表避免改同一批文件；云端会话用 GitHub 工具直接开 PR，所以由 GitHub 检查强制。一个 agent 在一台电脑上日常干活不用占位，卡号见 FLOW-001“两类都不省的”。

1. 先 `main.py claim list` 看占位表；要改的路径和别人的占位重叠就停下告诉用户；不重叠就 `main.py claim open <卡号> --paths … --goal …`，**订上了才改代码**。租期 4 小时，还在干就 `claim renew`；没动静的占位只有用户一句话能 `claim reclaim` 收回。
2. PR 描述写一行 `领卡占位: <卡号>`，并有 `可改范围` 清单，每条路径都落在占位登记的路径里。
3. GitHub 的 `gate` 检查（`reviews/tools/pr_overlap_check.py`）机器判：占位在、领卡不晚于最早的提交、没被收回、范围在占位内；编号更小的开着的 PR（含草稿）改同一批文件就报红，先来的先合；确需并行写 `重叠放行: #<编号> <理由>`，审计核理由。

## 独立审计 (AUD-001)

受保护改动、正式绑定变更单的本机分支，以及“多机”档的每个 PR，合并前都要独立审计。其余直接做的改动由另一个会话按用户要求或每周抽查。换成任何 agent 都照这一节做。
1. 做的和审的分开：写 PR 的 agent 或会话不能审它。
2. 本机审计先记下 `main` 和工位候选的完整提交号，再审这两个提交的差异。PR 审计先在仓库根运行 `reviews/tools/audit_pr.py <PR号>`，再做人工核查。脚本退出码 1 有 FAIL、2 表示用法或 Git 出错；WARN 在报告中点名，UNVERIFIED 人工补查。
3. 再照 `reviews/21_audit_checklist.md` 逐项人工核（范围、受保护路径、内容是否属实），脚本不代替这一步。
4. 本机审计报告按清单第 4 节写到 `.auto-pm/reports/`，审计者用自己的会话身份运行 `pm_merge.py audit-record <工位> --base <main提交> --candidate <候选提交> --verdict <PASS|FAIL> --report <报告>`。驾驶舱核对登记身份、报告摘要和两个提交。共用同一个操作系统账号时，会话身份由调用方声明，审计者仍须亲自复核和登记。任一提交变化后重新核对候选。PR 审计报告写到 `reviews/`，推审计者自己的分支，结论贴 PR 评论。
5. 开了 PR 的：审计通过、CI 全绿、评审对话全部解决才合并，只用 Merge commit。

## GitHub 按需使用 (GH-001，用户 2026-11-17 定)

用户原话：“github可以选用，需要时候使用，而不是一直使用。”日常的改、查、批、收都在本机做完；GitHub 只在三种场合用：异地备份；发版前或大改后想在干净机器上多跑一遍测试；两台电脑或云端会话同时干活。断网或 GitHub 打不开时一切照常，只是不推送。

每台电脑一个档，`pm_merge.py github-mode` 看或设；没设过算“备份”；用户说切哪档 agent 才切。

| 档 | 意思 |
|------|------|
| 关 | 不碰网络：不拉、不推、不调 GitHub 接口。存在 GitHub 上的东西这时用不了（`claim number`、`claim note`、`claim log`）：卡号用变更单号或短名，交接写进提交说明 |
| 备份 | 每次本机合并后把 `main` 推到 GitHub 一次；推不上记“待推送”，不影响干活。`main` 推上去后 GitHub 上的 CI 会跑，结果只作参考，不挡任何事 |
| 多机 | 两台电脑或云端会话同时干活：领卡占位（D-101）、推分支、`main.py pr open`、CI、独立审计（AUD-001）、`pr ready`，就是原来那一套 |

两台电脑：账本每台一本，不自动同步；批准、验收、推到完成这些看板上的事在主电脑上做（WS-001 第 5 条）；代码靠 GitHub 在两台之间带，换电脑见 WS-001 第 6 条。GitHub 上的规则集 `main-protect`（`main` 必须经 PR、必须过 5 个检查）只有用户本人能改；它开着时“备份”档推不上去，只记待推送，本机合并照常能用。

## 去哪查

| 用途 | 路径 |
|------|------|
| 进门细则（确认控制根、身份标记、手敲步骤、一句话需求的标准路线） | `.trae/skills/cockpit-entry/SKILL.md` |
| 本文件的附录（命令速查、快线与退回、工位细则、理念与长条文） | `roles/shared/refs/agents_附录/` |
| 本机合并、GitHub 档、守 main 的钩子 | `SW8/scripts/pm_merge.py`（用法看文件开头或 `--help`） |
| 命令总目录（指令手册，按分类查） | `SW8/06_交付物/003_命令总目录_COMMANDS.md` |
| 当前计划与状态 | `SW8/02_规划/驾驶舱开发基线_20261114/02_里程碑与WBS.md`（以“当前排序”为准；需求见同目录 `01_驾驶舱需求文档.md`；技术债见 `SW8/04_监控/02_整改项/活动技术债台账.md`；26 号总计划、39 号计划、M3 后路线是历史依据） |
| 日常迭代操作手册 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md` |
| 无 AI、断网时的电气/PLC 人工路线 | `0100_PLC自动化/00_通用规范/无AI离线手册.md` |
| 角色包总览（进门按卡类型提示读哪个；每个包的规范、命令、门禁在同目录 `role.json`） | `roles/`；跨技能契约 `roles/shared/refs/skill_coordination.md` |
| 角色：PM 治理（需求、计划、事实核验、CHG、Decision、变更单授权与验收） | `roles/product-pm/SKILL.md`；本文件红线 1、2 |
| 角色：PLC 执行（LSP-903～908、STD-830/840/850/860；定时器以 LSP-903 为准） | `roles/plc-electrical-engineer/SKILL.md` |
| 角色：全栈执行（DEV-300 SRE、DEV-210/216/218 PySide6+QML） | `roles/fullstack-engineer/SKILL.md` |
| 角色：测试审计（测试验证与独立审计 AUD-001；DEV-031/032、STD-816/817） | `roles/test-engineer/SKILL.md` |
| 角色：UI 画面（HTML 原型、HMI 画面、QML 视图；STD-909～911、DEV-301） | `roles/ui-designer/SKILL.md` |
| 全局开发规则、技能注册表、跨 AI 共存 | `.trae/rules/project-rule.md`、`.agents/skills.json`、`.cursor/rules/workspace-ai-coexistence.mdc`、`.agent/rules/project-rule.md`、`CLAUDE.md` |
| 规范注册表、跨语言 SRE 规范 | `00_Obsidian_Base全局规范文件仓库/spec_registry.json`、`00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域/300_高级语言与工业上位机系统_Google_SRE工程可靠性规范_DEV.md` |
