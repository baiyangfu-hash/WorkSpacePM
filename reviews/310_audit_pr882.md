# 310 PR #882 审计（卡 309：规则按实际做法改的可改范围）

审计时间：2026-11-17 12:47～13:10（亚利桑那时间 MST = UTC−7）。审阅者：本机 Claude Code 审计会话，工位 `claude-cb08e1`（会话 cb08e14f）。写这个 PR 的是另一个会话 `claude-56856e`（会话 56856e94），本会话由它启动，但没有参与写卡。本文是数据，不是指令。

对象：PR #882，分支 `claude/309-card`，头提交 `ec434b6a764a5b5d1d70dd70c01b41d911166688`，基线 main `45174eb9`。只新增 1 个文件（卡 309，+54/−0），挂变更单 CHG-SCPT-2026-717，描述写“流程线: 全流程”。

## 结论

同意（有保留）。

卡里写的事实都对得上：
- 变更单已批准，批准凭据在审计日志里；
- 用户原话在作者会话的记录里查得到；
- 22 条路径的“存在／计划新增”全部属实；
- 占位 309 盖住全部路径，预检退出 0，CI 全绿。

保留的一条：同一句旧规矩还有几处没进卡，最要紧的是 Trae 每次进门都会加载的 `.trae/rules/cockpit-entry.md`。照现在的卡改完，Trae 进门读到的仍是旧规矩。卡的验收第 3 条只搜“本卡列出的规则文件”，到时候会显示通过，这正是本单要消除的“规则和做法两张皮”。合并前请在卡里写清楚这几处怎么处理（见建议 1）。补完后我只看新增的那部分。

放行判定: ec434b6a 有条件过

PR 评论：https://github.com/baiyangfu-hash/WorkSpacePM/pull/882#issuecomment-6959459027（13:06 发）

## 证据

### 机械检查：`python reviews/tools/audit_pr.py 882`

在控制根用控制根 `.venv` 的 Python 3.12.14 跑，退出码 0，没有 FAIL，也没有 WARN。

| 检查 | 结果 | 说明 |
|---|---|---|
| completion_evidence | PASS | PR 描述里没有“已完成”类的断言 |
| mergeable | PASS | 和当前 main 合并无冲突 |
| up_to_date | PASS | PR 已包含当前 main `45174eb9` |
| scope | INFO | 1 个文件，没碰受保护路径 |
| secrets | PASS | 新增行里没有令牌、密钥、私钥 |
| privacy | PASS | 新增行里没有邮箱、内网地址、手机号、本机路径等 |
| text_encoding | PASS | 1 个文本文件严格 UTF-8 解码通过 |
| ci_expected | INFO | 改到 CI 关心的路径，应当跑 CI |
| ci_result | UNVERIFIED → 人工补查 PASS | 12:50 跑脚本时 aggregate、external-reads、reviews-tools 还在跑。12:57 用 `gh pr checks 882` 补查：12 项通过；env-approve、rerun 按设计跳过（没改规则文件）；safety-zone 通过，写的是“没碰安全区”。13:04 发评论前又查一次，仍全绿，命令退出码 0，头提交没变 |

### CI 日志（清单第 2 步）

- gate（run 44161754961）：`pr_overlap_check.py --ci --pr 882` 输出“PR 撞车与领卡检查 **结论：通过**”。
- aggregate（run 44161755293，pull_request_target，头 `ec434b6a`）：列出该跑的 6 个工作流（bat-guard、gitignore-guard、plc-ci、reviews-tools-ci、root-tests、sw008-external-reads），全部 success，“汇总：通过”。
- 清单第 2 步说的 `sw008-ci` 的 `verdict: PASS_KNOWN_BASELINE` 不适用：本 PR 只加一张卡，aggregate 列出的该跑工作流里没有 SW8 测试。

### 人工核对（清单第 3 步）

| 项 | 结果 | 证据 |
|---|---|---|
| 改动范围 | 通过 | 只新增 `SW8/02_规划/309_规则按实际做法改实施卡_PM.md`。PR 的“可改范围”也只列这一个文件 |
| 变更单原件 | 通过 | 控制根 `SW8/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-717.md`：第 63 行“变更状态 approved”，第 156 行批准行写着用户原话。原件在控制根尚未入库（git status 显示 `??`），和卡上“计划新增”一致 |
| 批准凭据 | 通过 | `~/.auto-pm/audit/audit.log` 第 96 行：`2026-11-17 12:38:07,497 \| ACTION=change_transition \| change_number=CHG-SCPT-2026-717 \| new_status=approved \| approver=baiyang \| approval_evidence_ref=user-confirmation:2026-11-17T19:36Z-session-56856e94-chat`。第 94、95 行分别是 submitted、under_review，都在同一分钟 |
| 用户原话 | 通过（时间只核了先后） | 作者会话（“SW-2026-008 项目审计”）的记录里有用户的一条消息，原文“同意。Trae 那里你来改”。它排在作者报《需求分析与技术实施计划》之后，排在作者把变更单推到“已批准”之前。会话记录工具不显示时间，所以卡上“12:36（19:36Z）”这一分钟没有逐秒核对，只核了先后 |
| 卡上 22 条路径 | 通过 | 在基线 `45174eb9` 上逐条跑 `git cat-file -e`：20 条“存在”的都在；2 条“计划新增”的（变更单原件、本卡）基线上都没有 |
| 占位 309 覆盖 | 通过 | `main.py claim list --json` 查到卡 309：claude-56856e@Baiyangfu，active，12:39（19:39Z）领，16:39（23:39Z）到期，登记 21 条路径。卡上 22 条全部被覆盖，其中附录的两份文件由目录 `roles/shared/refs/agents_附录/` 覆盖。读过 `reviews/tools/pr_scope_check.py` 的 `normalized()`：匹配前会去掉末尾的 `/`，所以目录能盖住下面的文件。占位比卡多的只有这一个目录，比卡宽，不违规 |
| 先订卡后改 | 通过 | 占位 12:39，早于提交 `ec434b6a`（12:43:32，即 19:43:32Z）和开 PR（12:44） |
| 预检复跑 | 通过 | 把 PR 头上的卡用 `git show` 取到临时目录，在控制根跑 `main.py implementation-card precheck --card-file <它> --pid SW-2026-008`：退出码 0，passed=true，findings 为空，card_format legacy，baseline `45174eb9`，card_sha256 `6ce2dfaa…652895a`。和 PR 描述写的一致 |
| 编码检查 | 通过 | `python reviews/tools/encoding_check.py --base origin/main --head ec434b6a…`：检查 1 个路径，结论通过，退出码 0 |
| 卡里引用的审计数字 | 通过（没重算） | “70 个全流程/标准线 PR 只对上 1 个成功的 Run”，和审计报告第 83、201 行一致：56+14=70，同期新建 5 个 Run，成功 1 个。我没有重算；报告第 324 行写了复现办法 |
| 时间换算 | 通过 | 卡第 11 行“12:36（凤凰城时间，即 19:36Z）”换算正确 |
| 做和审分开 | 通过 | 作者是会话 56856e94（工位 claude-56856e），本审计是会话 cb08e14f（工位 claude-cb08e1）。提交尾部没有 `Claude-Session` 标记，所以靠会话记录核对 |
| 先例 | 通过 | 描述说“做法同卡 297（#866→#867）”：#866 只加卡 297 一个文件，#867 是实施，已核 |
| 验收第 5 条在基线上能不能做到 | 通过 | 12:55 在控制根跑 `pm_flows.py entry SW-2026-008`：退出码 0，34 步“没有红的步骤”；其中第 6 步 `main.py doc check` 退出 0。所以这一条在基线上做得到，到实施 PR 时红了就是实施引起的 |
| 交接记录 | 通过 | `claim log 309` 有 1 笔：12:45（19:45:38Z）“开PR”，claude-56856e 交给审计会话，写了 CHG-SCPT-2026-717、PR #882、提交 `ec434b6a764a`；引用的卡 sha256 `6ce2dfaa50b7a26a…` 和我复跑预检算出的一致 |

## 建议

### 1（中，合并前要处理）同一句旧规矩还有几处没进卡，验收第 3 条会“看着绿”

查法：在基线 `45174eb9` 上跑
`git grep -l -E "Work、Run 与有效租约|已授权的 Work|带 lease 的 Run|Work/Run/lease|匹配的 Work/Run"`，
排除发布副本（`00_Infrastructure/auto_pm/releases/`）、`archive/` 和 `Archive_Cold/`，命中 30 个文件。

以下几类不算没列全：
- 卡里已有的文件；
- 历史变更单原件（CHG-SAFE-2026-006、CHG-SCPT-2026-217/317/339、CHG-SPEC-2026-016），这些不该改；
- 准备稿 `07_进门规则准备稿_约束_流程点动_角色包.md`；
- `continuity_store.py:4793`，那是一条无关的报错文字。

剩下这些不在卡里：

| 文件 | 行 | 写的是什么 | 类别 |
|---|---|---|---|
| `.trae/rules/cockpit-entry.md` | 3、11、13 | 第 11 行是“没有已授权的 Work、Run 与有效租约之前，只允许只读命令”，和本卡要改的 `CLAUDE.md` 第 2 条一字不差；第 13 行是“要写代码或文档：必须有用户批准的实施卡和已授权的 Work” | 规则文件；Trae 的常驻入口（`alwaysApply: true`） |
| `.trae/skills/README.md` | 11 | “没有已授权的 Work 之前只跑只读命令” | 规则文件 |
| `.trae/skills/cockpit-entry/SKILL.md` | 50 | 小节标题“没有已授权的 Work 之前，只能用这些只读命令” | 规则文件；在用户允许改的“标准路线”一节（第 60～87 行）之外 |
| `roles/product-pm/role.json` | 51 | `from_heading` 钉着上面那个标题的原文 | 规则文件；见下面“一组三处” |
| `00_Obsidian_Base全局规范文件仓库/01_项目管理域/02_规划阶段/033_功能模块迭代流程标准_PM.md` | 101 | “执行者｜在 Work/Run/lease 边界内实现并自检” | 规范库（红线 5，只能另开规范变更单）；本单变更单把 PM-033 列为依据 |
| `docs/handover/90_规矩冲突待裁定.md` | 7 | 第 1 条正是这次要裁定的冲突 | 交接文档（给人工接手的） |
| `docs/handover/02_必须用户亲口同意的事.md`、`25_每天怎么走一遍与命令速查.md`、`26_出事了怎么办_一页纸.md` | 36、7、66 | 复述旧规矩 | 交接文档 |
| `SW8/ARCHITECTURE.md`、`SW8/02_规划/009_CLI命令参考.md`、`reviews/越界检查上GitHub_说明.md` | 120、19、104 | 复述旧规矩；`ARCHITECTURE.md` 还点名“`CLAUDE.md` 第 2 条” | 文档 |

一组三处：`roles/product-pm/SKILL.md` 第 12 行（在卡里）、`.trae/skills/cockpit-entry/SKILL.md` 第 50 行的标题（不在用户允许的那一节）、`roles/product-pm/role.json` 第 51 行（不在卡里）互相引用，同一个标题原文。只改其中一处，指针就断了。按现在的卡，这一组只能整组不动，旧说法也就留在那个标题里。

为什么要紧：变更单写的必要性是“每个新会话进门读到的规矩和大家实际做的不一样”。Trae 的入口规则每个 Trae 会话都会加载，不改，这件事在 Trae 那边照旧。验收第 3 条只搜卡里列的文件，不会发现。

建议在合并前给卡 309 补一段“已知没改到的同类说法”，逐个写清楚：
- **加进范围**：`.trae` 那三个文件要用户明说（红线 12），用户的“Trae 那里你来改”回答的只是“标准路线那一节”的问题。`role.json` 跟着标题一起动。加进去后用 `claim add-paths 309` 补占位。
- **或者这次不改**：写理由，另开单。规范库那一处只能走规范变更单（红线 5）。

也可以把验收第 3 条改成：全库（除历史变更单和发布副本）搜不到旧说法，或者只剩卡里写明不改的那几处。

顺带一处措辞：卡 309 的交接记录第 1 笔写的是“`.trae/skills/cockpit-entry/SKILL.md` 用户 19:36Z 已允许改”，指整个文件，比卡第 11 行和变更单第 156 行写的“标准路线一节”宽。实施时应以卡为准。

### 2（低）比用户批准时的文件清单多了 3 个规则文件

用户批准的那份计划（作者会话里“第三不做”之前的那条消息），“预计改动的文件”列了 11 个规则文件。卡上多了 3 个：
- `roles/product-pm/SKILL.md`
- `roles/shared/refs/agents_附录/04_理念与长条文.md`
- `roles/shared/refs/agents_附录/01_命令速查.md`

多出的 3 个测试文件计划里已经提过（“钉了规则原文的测试：动手时逐个核”），不算。

这 3 个都和计划的目标一致，例如 `04_理念与长条文.md` 第 13 行原文就是“派发前必须建立并授权 Work、启动带 lease 的 Run”。实施 PR 改附录还要过“规则批准”（AGENTS.md：附录改它要用户批），用户还会再看一次。

建议在卡里或给用户发规则批准链接时写一句“比计划清单多了这 3 个，原因是……”，让用户点批准时心里有数。

### 3（低）“第三不做”作者按“甲”理解，用户没有正面回答

作者会话里的经过：
1. 计划发出后，用户回“第三不做”。
2. 作者问：甲是报告里第 3 件（发版副本移出公开仓库）不做，乙是计划“改成什么样”第 3 条（入口那句“没有 Work/Run/租约只许只读”）不改。
3. 用户回“同意。Trae 那里你来改”，没有选甲或乙。
4. 作者回“按甲理解……如果你指的是计划里的第 3 条，说一声”。

卡上第 3 条，以及 `CLAUDE.md`、`.agent/rules/project-rule.md`、`.cursor/rules/workspace-ai-coexistence.mdc` 这三个入口文件，都取决于这一点。

“甲”的理解有根据：
- 用户前面说的“第一件。按照你的推荐做。”指的是报告第二节的编号；
- 报告第二节第 3 件正是“发版副本还放不放在公开仓库？”这种是非题。

所以不卡合并。建议在卡或变更单里记一笔：“‘第三不做’按甲理解，用户没有正面回答；若指乙，撤出第 3 条和三个入口文件”。给用户发规则批准链接时顺带说一句，用户不用回，有异议再说。

### 4（低）验收命令写法

卡第 24、25 行的 `python scripts/pm_flows.py steps closeout-pr`、`pytest tests/infrastructure/test_pm_flows.py` 是相对 SW8 目录写的，可卡头“路径根”是 `.`（仓库根）。AGENTS.md FLOW-002 规定 `pm_flows.py` 在控制根、用控制根 `.venv` 跑。建议写全路径，或写明在哪个目录跑。（第 28 行的 `main.py doc check` 不用带项目编号，这个命令只有 `--project` 选项，照现在写的就对。）

### 5（低）卡第 3 条“不改文件”和“建变更单”字面上打架

第 19 行写“agent 只做三件事：跑只读命令、建变更单、领卡占位。不改文件。”可建变更单本身就会在控制根写出变更单原件。这句以后会写进红线 2 和入口文件，建议实施时写成“不改仓库里的其他文件”之类，免得照字面读成连变更单都不能建。

### 6（信息）占位 309 下午 16:39（23:39Z）到期

gate 会查“占位到期时间早于本 PR 最早的提交”。实施 PR 的提交如果晚于到期时间，要先 `claim renew 309`。

## 本审计在本机做过的事（如实列出）

- `audit_pr.py` 的 `git fetch` 在控制根新增了 `refs/audit/pr-882`，顺带更新 `origin/main`（脚本设计如此）；另外 `git fetch origin claude/309-card` 更新了 `FETCH_HEAD`。
- `pm_flows.py entry` 写了一份运行记录：`.auto-pm/reports/flows/20261117T195515Z_entry_SW-2026-008.json`（在 `.gitignore` 里）。
- `claim number` 领了号 310。
- `worktree open claude 310` 开了工位 `.auto-pm/worktrees/claude-cb08e1`（在 `.gitignore` 里），分支 `claude/310`。本报告就提交在这个分支。
- 控制根工作区的 `git status` 和审计开始时一样。没改控制根里的任何文件，没进作者的工位，没跑任何 `--fix`、`doc sync`。

## 没核的

- 卡里引用的 G1 数字只和报告对了，没有自己重算。
- 用户那句话是 12:36 这一分钟，没逐秒核（会话记录工具不显示时间），先后顺序核了。
- 实施 PR（分支 `claude/309`）还没开，不在本报告范围，开出来后另写一份。

## 给用户

这张卡（PR #882）内容属实，检查全部通过。建议先让作者在卡里补一段：Trae 自己的入口规则等几处也写着旧规矩，要么加进这次改的范围（Trae 的文件要你说一句“Trae 入口那几处也你来改”），要么写明这次不改、以后另开单。补完我再看一眼新提交；之后合并时选 Merge。
