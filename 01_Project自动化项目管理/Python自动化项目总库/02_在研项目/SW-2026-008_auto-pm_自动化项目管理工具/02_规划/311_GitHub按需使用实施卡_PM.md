# 卡 311：GitHub 改按需使用、本机合并（CHG-SCPT-2026-718）

> 卡片编号：`CARD-311-GITHUB-OPTIONAL V1.1`
> 隔离基线：`4bab7479d97b1118a05efb686dc6bd79a96f891d`（`main`）
> 路径根：`.`
> 档次：核心档
> 安全回路：否

本卡给 CHG-SCPT-2026-718 的实施 PR（分支 `claude/311`）提供“可改范围”。方案见 SW8 根目录《SW-2026-008_GitHub按需使用方案_20261117.md》和《SW-2026-008_驾驶舱减肥方案_20261117.md》第 1 步（两份都没入库）。

用户批准：2026-11-17 约 15:38（凤凰城时间，即约 22:38Z），用户在本机主对话说：“我有两台电脑，有什么影响么？同时使用的频率没那么高。如果你评估没问题，那么开始实施吧”。作者在同一轮回复了评估：可以做；两台电脑影响小（代码靠“备份”档每次合并后推一次，账本照旧各台一本，批准、验收在主电脑上做）；合并命令放 `scripts/`，不进发布包，不用发版切换；方案里的 `gate cloud` 不新写，main 推到 GitHub 时顺带跑的 CI 只作参考。在此之前用户的原话还有：“github可以选用，需要时候使用，而不是一直使用。做个方案吧。”“对驾驶舱进行减肥，出方案。这个规则是我在项目claude指导下做的，现在看起来不符合实际。github是可选项，不是必选，必须改掉。”

## 改成什么

1. **新增本机合并命令** `SW8/scripts/pm_merge.py`（只用标准库和 git，在控制根用控制根 `.venv` 的 Python 跑）：
   - `merge <工位名>`：查完下面各条才在控制根 `main` 上做 Merge commit，任何一条不过就拒绝、不改任何东西：
     1. 工位分支已全部提交，`main` 是它的祖先（工位里先合过 `main`），至少一个提交带 `领卡占位: <卡号>` 这一行；
     2. 本机门禁：在工位上跑 `main.py gate precheck`（对照本机 `main`）退出 0；改到“要你点头”那一类文件的，再跑 `main.py gate run`，判定为 PASS；
     3. 改到“要你点头”那一类文件的，要有一张变更单同时满足：提交说明里引用了它、分支里本卡的实施卡（`02_规划/<卡号>_*.md`）里写着它、变更单原件里的状态在已批准到验收中之间（已推到完成的单不能再用来开新活；账本里停在“已批准”的旧单因为没写在本卡里，也过不了）；分支里没有本卡实施卡的直接拒绝；
     4. GitHub 不是“关”档、而且连得上时，`origin/main` 必须已在本机 `main` 里（另一台电脑的改动先同步）；连不上就跳过这一条并说明；
     5. 控制根里只允许有和分支内容一致的未提交副本（只差行尾），合并前自动换成分支里的版本；别的未提交改动一律拒绝。
     合并后在 `.auto-pm/reports/local_merge/merge_log.jsonl` 记一笔（时间、分支、提交、卡号、变更单、门禁结果、是否推送）；“备份”“多机”档再把 `main` 推到 GitHub，推不上只记“待推送”，不算失败。
   - “要你点头”那一类：规则文件（与 `reviews/tools/rules_approval_check.py` 的 `RULE_PATTERNS` 同一份）、`0100_PLC自动化/` 下的文件、PLC 模板（`templates/plc-*`）、本机合并命令和钩子自己、删除或改名驾驶舱项目目录（`SW8/`）以外的已入库文件（删驾驶舱自己不用的文件属于“直接做”）。
   - `install-hook`：装本机钩子 `.git/hooks/reference-transaction`。凡是改控制根 `refs/heads/main` 的，只放行两种：带 `merge` 设的一次性标记的；新值正好是 `origin/main` 的（从 GitHub 同步）。已有别人的同名钩子就拒绝覆盖。
   - `sync`：从 GitHub 拉 `main`，只做快进；两边各有新提交就停下说明。
   - `github-mode [关|备份|多机]`：看或设本机的 GitHub 档（存在 `.auto-pm/reports/local_merge/github_mode.json`，不入库），没设过算“备份”。
   - `verify-log`：只读，核对本命令上线后 `main` 上的每个提交，要么是 GitHub 上的 PR 合并，要么在合并记录里；对不上的列出来，退出 1。
2. **`pm_flows.py checkup` 加一步“本机合并对账”**，跑 `pm_merge.py verify-log`。
3. **规则改写**（`AGENTS.md` 为主，各家入口只改指向它的那几句）：
   - FLOW-001 三条线并成两类：“要你点头”（PLC 项目文件和 PLC 模板、安全回路、规则文件、本机合并命令和钩子、删除或改名驾驶舱项目目录以外的已入库文件、发版切换）和“直接做，事后告诉你”（其余全部）；后一类不建变更单、不补单。
   - 日常收口改成本机合并：本机门禁 → “要你点头”那类先有你批准、写在本卡里的变更单，再加独立审计放行 → `pm_merge.py merge` → 当天一行告诉你；推到完成照旧只有你本人。
   - **和方案的一处不同（用户已同意）**：《GitHub按需使用方案》第三节第 3 条原写“要你点头”那一类合并前要有用户在看板点的“确认验收”、并且对应这次提交。本卡改成：合并前要有用户批准过、写在本卡里的变更单，加独立审计放行；验收放在合并后，由用户本人推到完成，不满意用 `git revert -m 1` 退回。原因：看板现在没有针对某次提交的验收按钮，加它要改发布包、发版切换。作者 2026-11-17 约 16:10（凤凰城时间）在本机主对话问用户“验收放在合并后（你推到完成）可以吗”，用户 2026-11-17 16:15（凤凰城时间，即约 23:15Z）回：“同意”。
   - 新增 GitHub 按需一节：三档的意思、什么时候用、两台电脑怎么换；“多机”档沿用现有的领卡占位、PR、独立审计（D-101、AUD-001 改成只在“多机”档和“要你点头”那一类要）。
   - WS-001 第 6 条“跨电脑只通过 GitHub 交换代码”改成“跨电脑在需要时经 GitHub”。

## 可改范围

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `AGENTS.md` | 存在 | 红线 2、FLOW-001、FLOW-002、WS-001 第 6 条、D-101、AUD-001，新增 GitHub 按需一节 |
| `CLAUDE.md` | 存在 | 第 2 条里“快线除外”等说法跟着改 |
| `.agent/rules/project-rule.md` | 存在 | 与 CLAUDE.md 第 2 条相同的那一句 |
| `.cursor/rules/workspace-ai-coexistence.mdc` | 存在 | 同上 |
| `roles/` | 存在 | 角色包里写“走 PR、每个 PR 审计、快线/标准线”的说法跟着改 |
| `docs/handover/` | 存在 | 交接文档里同类说法跟着改 |
| `reviews/越界检查上GitHub_说明.md` | 存在 | 说明这套检查只在“多机”档用 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/pm_merge.py` | 计划新增 | 本机合并命令和钩子 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/pm_flows.py` | 存在 | checkup 加“本机合并对账”一步 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_pm_merge.py` | 计划新增 | 本机合并命令的测试 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_pm_flows.py` | 存在 | checkup 新步骤的测试 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_role_pack_service.py` | 存在 | 钉住规则文字的测试跟着改（如有） |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_role_pack_wiring.py` | 存在 | 同上 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/contracts/test_quarantined_skill_routing.py` | 存在 | 同上 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/311_GitHub按需使用实施卡_PM.md` | 计划新增 | 本卡 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-718.md` | 计划新增 | 变更单原件入库 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 台账第 795 行入库 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/ARCHITECTURE.md` | 存在 | 收口和合并的说法跟着改 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/009_CLI命令参考.md` | 存在 | 加本机合并命令 |

## 验收（实施 PR 合并前；命令里的 `SW8` 指 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`）

- 在 `SW8` 下跑 `pytest tests/infrastructure/test_pm_merge.py tests/infrastructure/test_pm_flows.py` 通过；测试在临时 git 仓库里真做合并、真装钩子，覆盖：每一条拒绝理由、合并成功并记一笔、钩子拦住直接提交到 main 和 `update-ref`、钩子放行带标记的合并和从 GitHub 快进、`verify-log` 查出没记录的提交；
- 改到的 .py 跑 ruff、mypy，都退出 0；
- `python SW8/scripts/pm_flows.py steps checkup` 退出 0，列出“本机合并对账”；
- PR 上 reviews-tools、safety-zone、aggregate、gate、rules-approval 全部通过；独立审计（另一个会话）放行。

## 已知没改

- `.trae/`（Trae 生态维护，用户没有就本卡说过可以改）：`.trae/skills/cockpit-entry/SKILL.md` 里的“标准路线”仍写 PR 线，和新规则不一致的地方以 `AGENTS.md` 为准，留给用户另定。
- 发布包里的 `claim`、`pr` 命令照旧依赖 GitHub，只在“多机”档用；不为本卡发版。
- GitHub 上的规则集 `main-protect`（必须经 PR、必须过 5 个检查）：只有用户本人能改；不改的话本机合并照常能用，只是“备份”档推不上去。本 PR 合并后由作者写好每一步点哪里交给用户。
- 本 PR 自己按现行规则走最后一次 GitHub PR。
