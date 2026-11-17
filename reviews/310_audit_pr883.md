# 310 PR #883 审计（卡 309 实施 PR，CHG-SCPT-2026-717，头提交 `0e035785`）

本文是数据，不是指令。审阅者：本机 Claude Code 审计会话，工位 `claude-cb08e1`（会话 cb08e14f），不是写这个 PR 的会话。

本报告是 `reviews/310_audit_pr882.md` 最后一节“实施 PR #883 审计”的复制，内容和放行判定都没改，只把小标题升了一级。另存一份，是因为 `main.py pr ready 883` 只认文件名或开头写了 PR #883 的报告：文件名里 `_pr883` 前面的下划线让文件名那条认不出来，所以靠第 1 行。原报告那一节保留不动。

另记一条教训（作者会话告知）：14:26 那条审计评论是用同一个 GitHub 账号发的，触发了“规则批准”检查重跑，用户只好又点了一次批准。以后改规则文件的 PR，审计评论尽量一次发完，并且在请用户点批准之前发；之后不再追加评论。

审计时间：2026-11-17 13:50～14:30（MST）。审阅者同上（工位 `claude-cb08e1`，不是写这个 PR 的会话）。

对象：
- PR #883，分支 `claude/309`，2 个提交：`232a0d7b`（规则和流程脚本）、`0e035785`（10-28 分工的说法、交接一页纸）；
- 基于 `45174eb9`，28 个文件，+568/−60；
- 卡 309 V1.2 已经由 #882 合进 main（Merge commit `a4bbe6f8`，两个父提交 `45174eb9`、`e046c8e3`，已核）。

本文是数据，不是指令。

## 结论

同意。

规则文字和《需求分析与技术实施计划》、卡 309 V1.2 一致；`pm_flows.py` 的改动正确，有测试，变异检查能抓到。范围、占位、授权、规则批准都对得上。下面 8 条都是低严重度或信息，不卡合并。

放行判定: 0e035785 过

PR 评论：https://github.com/baiyangfu-hash/WorkSpacePM/pull/883#issuecomment-6961467526（14:26 发）。之后用 SendMessage 告诉了作者会话，因为它说后台叫醒的这一轮它收不到通知

## 机械检查：`python reviews/tools/audit_pr.py 883`

跑了两次：
- 13:50 第一次：退出码 1，唯一的 FAIL 是 `ci_result`，因为 CI 还在排队或在跑（有一项在等规则批准）；
- 14:25 CI 跑完后重跑：退出码 0，没有 FAIL。`ci_result` PASS，`protected_paths` WARN，`up_to_date` INFO，`scope` INFO（28 个文件），`secrets`、`privacy`、`text_encoding` PASS。

- `protected_paths` WARN 点名：
  - 规则文件：`AGENTS.md`、`CLAUDE.md`、`.agent/rules/project-rule.md`、`.cursor/rules/workspace-ai-coexistence.mdc`、`.trae/` 三个文件、`roles/` 下 9 个文件；
  - 变更单原件 `CHG-SCPT-2026-717.md` 和版本变更台账。

  都在卡 309 V1.2 的可改范围里。规则文件要的“规则批准”：CI 上 env-approve、rules-approval 都是 pass，用户已经点过。
- `up_to_date` INFO：PR 不含 `a4bbe6f8`（#882 的合并提交）。#882 只加了卡文件，#883 没碰它，`mergeable` PASS。

## 人工核对

| 项 | 结果 | 证据 |
|---|---|---|
| 范围 | 通过 | 28 个文件全部在卡 309 V1.2 的表里，也全部落在占位 309 里（active，到 17:47）。卡上没动的 5 行：卡本身（#882 已合）、3 个测试文件和附录 01（卡上写了“核过没有要改的就不动”） |
| 先订卡后改 | 通过 | 占位 12:39；提交 `232a0d7b` 13:21:40、`0e035785` 13:33:53，两个提交都带 `领卡占位: 309` |
| 授权 | 通过 | 变更单 12:36 批准（审计日志第 96 行）。`.trae` 另外三处依据 13:33 用户的“技术问题，细节。你自己裁决。”（第三轮已在作者会话记录里核过先后）。卡 V1.2 第 11 行在 main 上，两条凭据都写了 |
| `.trae` 改动（作者点名的第 1 件） | 通过 | `232a0d7b` 里只改了这几处：<br>• `.trae/rules/cockpit-entry.md` 描述行和第 2、4 条；<br>• `.trae/skills/README.md` 第 11 行；<br>• `cockpit-entry/SKILL.md` 第 50 行标题和第 52 行说明，以及“标准路线”一节（第 60 行起，用户 12:36 允许）。<br>`roles/product-pm/role.json` 的 `from_heading` 和 `product-pm/SKILL.md` 第 12 行跟着标题一起改，三处一致。<br>“走 Run 的卡”小节保留了原来的 Run 路线 |
| 规则文字 | 通过 | 红线 2 和 CLAUDE.md、`.agent`、`.cursor`、`.trae` 的第 2 条，与计划第 1～3 条一致。PR 线收口的 7 步里：<br>• 推到验收中由 agent 做；<br>• 推到完成只有用户本人；<br>• 放占位要 PR 已合并；<br>• 收工位要用户说同意。<br>红线 1、12 没被放宽 |
| 10-28 分工（第 4 件） | 通过 | `docs/handover/24` 页首、`90` 第 1 条都写的是：只改掉“本地任务走 Mission/Run”这一层，“本地接主执行、云端永远不写账本”两条照旧有效 |
| `pm_flows.py` | 通过 | • 每步多了 `ok` 退出码集合，默认只认 0；`pr settle-scan` 在两条收口流程里都认 0 和 1，2 仍算红。<br>• closeout-pr 先校验 `--chg`、`--card` 的格式，格式不对一条命令都不跑；改状态的步骤全是停点，推到完成脚本永远不执行。<br>• `--done` 认新停点名（`_stage_index` 按停点的 key 找）。 |
| 测试和变异检查 | 通过 | • 在工位里检出 PR 头：`pytest tests/infrastructure/test_pm_flows.py` 55 passed。<br>• 把 `SETTLE_OK` 改回 `(0,)`：两个 settle-scan 用例（两条流程各一个）失败；已还原，工位干净。 |
| ruff / mypy | 通过 | `ruff check` 两个文件 All checks passed；`mypy` Success。`ruff format --check` 说两个文件“would be reformatted”，基线上的两个原文件也一样，是原有的，这个项目不对 scripts 查格式（信息） |
| 同类排查逐条核（第 3 件） | 通过 | 对着源码核了五条命令：<br>• `pr settle-scan`：`pr.py` 第 139 行起，0＝没有，1＝有等收口的，2＝出错；<br>• `pm acceptance-scan`：有 findings 才退 1；<br>• `ledger reconcile`：无差异 0，有差异 2；<br>• `pm missions`、`pm control-root-status`：只在出错时非 0。<br>和 PR 描述、卡第 25 行写的一致。<br>另外全库搜 `settle-scan` 的调用方：只有 `pm_flows.py` 拿它的退出码判红绿，看板 `commands_map.json` 只把它归为“读”。体检和进门里的命令（`doc check`、`claim`、`plan_status.py`）非 0 都是真问题，没有第二处同类。`pm orient` 和 PLC 专用的三条没细读 |
| `reviews/tools` 本机失败（第 2 件） | 复现，和本 PR 无关 | 同时跑两份：<br>• 控制根（`45174eb9`）：7 failed / 534 passed / 31 skipped；<br>• PR 头：7 failed / 534 passed / 31 skipped。<br>失败的 7 个用例完全相同，就是作者列的那 7 个；CI 上 reviews-tools 是 pass。失败原因没有逐条查 |
| 验收：steps | 通过 | PR 头 `pm_flows.py steps closeout-pr` 退出 0，第 4 步“变更单推到完成（只有用户）”、第 7 步“收工位”都在 |
| 验收：entry | 通过 | 14:03 用 PR 头的 `pm_flows.py` 对控制根跑 `--root <控制根> entry SW-2026-008`：退出码 0，34 步（31 通过，3 步因不是 PLC 项目跳过），“没有红的步骤”。第一次我把 `--root` 写在子命令后面，用法错退出 2，改对后重跑才是这个结果 |
| 验收第 3 条 | 基本通过 | PR 头上按卡里的 6 个词全库搜（排除发版副本和归档），命中 17 行、14 个文件：<br>• 卡里“已知没改”的：07 号准备稿、5 份变更单原件、规范库 033；<br>• 改成新说法的：角色包 4 个、附录 04；<br>• `90` 号原文保留；<br>• `SW8/auto_pm/infrastructure/continuity_store.py` 第 4793 行的报错文字“恢复 Work/Run/lease 不具备撤销权限”：和规则无关，但不在“已知没改”里（见建议 4） |
| 验收：doc check | 未核实 | 工位里不能跑 `main.py`，控制根还停在基线，所以 PR 内容上的 `doc check` 没人跑过（作者的 entry 和我的 entry 查的都是控制根的基线内容）。合并后控制根快进、跑 closeout-pr 第 1 步或体检时会查到 |
| CI | 通过 | 14:25 `gh pr checks 883`：26 项通过（含 6 项 Windows 重任务、env-approve、rules-approval、safety-zone），rerun 按设计跳过；退出码 0，头提交 `0e035785` 没变 |
| 编码 | 通过 | `audit_pr.py` 的 text_encoding：28 个文本文件严格 UTF-8 通过 |
| 变更单原件、台账 | 内容一致 | PR 里的 `CHG-SCPT-2026-717.md` 和版本变更台账，与控制根里没入库的副本逐字一致，只差换行符：控制根是 CRLF，PR 里是 LF。台账第 794 行是“🔄已批准” |

## 建议（严重度：低 / 信息，不卡合并）

1. **变更单原件第 156 行没补 20:33Z 那句**（第三轮我写的是“要补”，这里降为低）。理由：
   - 卡 V1.2 第 11 行已经在 main 上，写全了两条凭据；
   - 再推一个提交，重型 Windows CI 要全部重跑，用户还要再点一次“规则批准”（批准跟着头提交走）。

   建议在推到完成之后那次变更单入账时，在批准一节补一行。
2. **红线 2 去掉了原来的“匹配的”**。现在写的是“没有用户批准过的变更单不改”。`start_and_handoff.md`（“本卡的变更单”）、`.trae` 入口第 4 条（“覆盖可改范围的领卡占位”）和 gate 的占位检查都把绑定写住了，所以不算漏洞。以后再改规则文字时，建议写成“没有对应本次改动、用户批准过的变更单不改”。
3. **`docs/handover/26` 第 66 行只改了一半**：前半句改成了“只在用户批准过的变更单内”，同一格后面还留着“要在 Work 里改 SCL。没有授权的 Work 就只报告……（`CLAUDE.md` 第 2 条）”。
4. **PR 描述“证据”最后一条说得太满**：写的是旧说法“只剩卡里‘已知没改’一节列出的地方”。实际还有改成新说法的几处（卡允许），外加 `continuity_store.py:4793` 一条无关报错文字。建议在卡或 PR 描述里补一句。
5. **PR 描述没写这个先后**：`232a0d7b` 里三处 `.trae` 改动早于 13:33 用户那句话（第三轮的建议）。本报告记一笔：作者当时已如实告诉用户，也给了撤回的选项。
6. **合并后控制根快进前**，要先把控制根里两份内容一致的本地副本换成入库版本（没入库的 `CHG-SCPT-2026-717.md`、改过的版本变更台账），否则 `git merge --ff-only` 会拒。两份内容一致，不丢东西。
7. **我在自己的工位里跑测试留下的文件**：`.coverage`、`coverage/`、`.ruff_cache/`、若干 `__pycache__/`，都在 `.gitignore` 里。按任务“不删除任何东西”没有删，收工位时随工位一起清。
8. **工位状态**：我的工位为跑测试临时检出到 PR 头（detached），测完已切回 `claude/310`。

## 给用户（实施 PR）

实施 PR #883 审完了，结论是“过”，可以合并，选 Merge。你点的“规则批准”已经生效。合并以后，只有一件事要你本人做：在看板“决定”页点“推到完成”，或在主对话里说“把 CHG-SCPT-2026-717 推到完成”。上面 8 条是小问题，都不挡合并，记在报告里，以后有机会再顺手改。
