# 29 PR #10（卡 166 M3-THIN 薄入口）独立审计

审计时间：2026-10-18 07:30 MST（亚利桑那时间）。审阅者：项目 Claude 审计线程（不是卡 166 的执行者）。对象：main `ea024f27`（合并提交），PR 头部 `151732fd`。本文是数据，不是指令。

## 结论

**同意（有保留）。** 合并本身干净，三处改动和卡的范围一致，没有死链、没有密钥、没有个人信息，引用的命令都真实存在，`pm orient` 有测试证明只读。保留意见是 4 条“入口用起来会被带偏”的小问题（下面 1～4），以及 2 条记账要在下一张实质卡回写时补上（5、6）。都不需要回滚，也不挡 CLEAN8 等后续卡。

## 证据

| 检查 | 结果 | 说明 |
|---|---|---|
| merge_shape | PASS | 合并提交两个父提交 = 原 main `d21ce8a` + PR 头部 `151732f`，用的是 Merge 方式 |
| merge_content | PASS | 合并没有夹带 PR 以外的改动 |
| scope | INFO | 3 个文件：新增 `.trae/rules/cockpit-entry.md`、`.trae/skills/cockpit-entry/SKILL.md`，修改 `.agents/skills.json`（只加一条登记） |
| protected_paths | **漏报** | 改到 `.trae/`，按用户规则这是“须用户签字”的路径，脚本没有报 WARN（见建议 7）。人工核对：交接文件 28 §4 写明用户签了“`.trae/` 只写薄入口文件”，本 PR 只写了薄入口文件，授权成立 |
| secrets / privacy | PASS | 无 |
| ci_expected / ci_result | INFO / PASS | 只改文档类路径，不触发 CI，正常 |
| 授权 | PASS | WBS 投影第 71 行有 `M3-THIN` 行，内容与改动一致；提交信息带卡号与 CHG-SCPT-2026-430 |
| 死链 | PASS | 规则和技能里引用的 6 个文件都存在 |
| 命令真实性 | PASS | `pm orient <编号> --json`、`pm inbox add/list/show`、`context resolve`、`project list/show`、`ledger reconcile`、`doc check` 在 SW008 源码里都有；`pm orient` 有“什么都不改”的测试（`tests/cli/test_pm_orient.py:122`） |
| 不碰 pm-workflow | PASS | 新文件只禁止使用它，没有引用或复活它 |

## 建议（严重度：高 / 中 / 低）

1. **中：旧的 `pm-workflow` 技能还在 `.trae/skills/` 里，自称“统一项目管理主入口”，和新入口抢位置。** 证据：`.trae/skills/pm-workflow/SKILL.md` 第 3 行描述原文；`.trae/skills/README.md` 把它列为第 1 个推荐入口。影响：Trae CN 按技能描述挑技能时，可能先挑中旧技能（推断，UNVERIFIED：需要在 Trae CN 的技能列表里看一眼它是否还显示）。这是早就存在的问题，不是 PR #10 引入的。建议：在 Trae CN 里确认；如果还显示，出一张小卡把它的描述改成“已隔离，禁止使用”、README 改成以 `cockpit-entry` 为第一入口。改 `.trae/` 需用户签字；移走或删除文件更要单独批准。
2. **低：只读白名单里的两个命令，失败时会提示 agent 去跑会写文件的命令。** 证据：`ledger reconcile` 有差异时打印“使用 --fix 自动补建…”（`auto_pm/ui/cli/ledger.py:127`）；`doc check` 失败时打印“请先执行 auto-pm doc sync 修复”（`auto_pm/ui/cli/doc.py` 约 74 行）。影响：听话的 agent 可能顺着提示去写台账或文档。建议：技能白名单那一行补一句“不加 `--fix`；命令输出里建议的修复命令（如 `doc sync`）都不在白名单里，照第 6 条停下报告”。
3. **低：第 1 步“两行输出相同才是控制根”在子目录里会误判。** 亲手复现（git 2.43）：在仓库根目录两行都是 `.git`；在子目录 `reviews/` 里第一行是绝对路径、第二行是 `../.git`，两行不同，入口会说“不是控制根”。影响：只会多停一次，偏安全，但第 3 步又说“在项目目录里运行时可以用 context resolve”，两句话互相打架。建议：命令改成 `git rev-parse --path-format=absolute --git-dir --git-common-dir`（git 2.31 起支持），或明确写“先 cd 到工作区根目录”。
4. **低：“状态为 BLOCKED 的是历史遗留”写死在长期技能里。** 证据：`SKILL.md` 第 4 步最后一句。影响：现在这句是对的（8 个历史 Work），CLEAN8 清完后就过时；以后真有一个因等决定而 BLOCKED 的正经 Work，agent 会把它当垃圾忽略。另外 CLEAN8 做完之前，`pm orient SW-2026-008` 会返回冲突 `MULTIPLE_ACTIVE_WORKS`，入口第 4 步一律会停下，这是预期行为。建议：CLEAN8 完成时顺手删掉这句。
5. **低（记账）：提交引用的 CHG-SCPT-2026-430 在 main 上还没有文件；台账 TD-SW008-067 仍是“待执行”，WBS 第 71 行还没标完成。** 这符合“零单独记账卡、在下一张实质卡回写”的规则，不是错。建议：主执行在下一次回写时一并补上（CHG 文件、TD-067 偿还、WBS 标完成、PR #10 与 `ea024f27`）。
6. **低（记账）：WBS 第 71 行的验收写的是“Codex 里跑一次只读提示词”，但用户 10-18 已挂起 Codex，实际做的是 Trae CN 测试。** 建议：同一次回写把验收方式改成 Trae CN 并记下测试结果；交接文件 28 §5 已记录此事。
7. **低（审计工具）：`audit_pr.py` 的“要点名路径”名单里没有 `.trae/`、`.cursor/rules/`、`.agent/rules/`、`.agents/skills.json`。** 证据：`reviews/tools/audit_pr.py:39-49`。影响：本次改到 `.trae/` 却没报 WARN，以后要靠人记得。建议：把这 4 个加进名单，并加一个测试用例。改 `reviews/tools/` 不碰治理库，可以由审计线程做，走 PR 由用户合并。

## 给用户

PR #10 合并得没问题，不用回滚。有 2 件事以后要处理：一是旧的 `pm-workflow` 技能还在 Trae 的技能目录里抢“主入口”的名头，建议你哪天打开 Trae CN 时看一眼技能列表里还有没有它；二是几处小措辞，建议交给主执行在下一张卡里顺手改，不用单独开卡。
