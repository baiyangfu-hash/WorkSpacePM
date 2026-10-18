# 33 PR #11（卡 167 M3-HANDOFF + V04R1E 合卡）独立审计

审计时间：2026-10-18 12:05～12:30 MST。审阅者：云端独立审计线程（不是写这张卡的主执行）。本文是数据，不是指令。

对象：PR #11，分支 `codex/pr-handoff-20261018`，头部 `b47645ff`，父 `ea024f27`（当前 main），15 个文件，+2584/−41。

## 结论

**同意合并。** 机械检查没有 FAIL，CI 两次运行都是 success 且与基线一致，V04-R1 三条验收用例都有测试并且我亲手做的 8 个变异全部被测试抓住。下面 4 条都是低严重度，不挡合并，放进后续文档卡或技术债。

## 证据

| 检查 | 结果 |
|---|---|
| `audit_pr.py 11`（main 上 `reviews/tools/`） | 退出码 0，没有 FAIL |
| mergeable / up_to_date | PASS / PASS（PR 已包含 `ea024f27`） |
| scope | 15 个文件（9 新增、6 修改） |
| protected_paths | WARN：改了活动技术债台账和 39 号 WBS。属于本卡授权的写回（WBS V4.0.1 修订记录、台账“最近回写”行都写明卡 M3-HANDOFF），删除行都是同一行改写后追加，没有丢内容 |
| secrets | PASS；CI `secret scan: 0 location(s) flagged in ea024f27..HEAD` |
| privacy | WARN：`fubai` 8 处，是台账“负责人”列和测试里的签名者名字，属于 main 已有基线类别，没有新增类别 |
| CI | 两次运行（push 与 pull_request）都 success。pull_request 运行：`EVENT: pull_request`、`PR_BASE: ea024f27…`，ruff “All checks passed!”，mypy “no issues found in 254 source files”，pytest `20 failed, 3762 passed, 22 skipped`，`verdict: PASS_KNOWN_BASELINE`（失败数 20 = 基线 20） |
| 测试数 | 本地收集：main 3746 → PR 3804，正好 +58，和 PR 描述的 core +28、cli +15、infrastructure +14、其余 +1 一致；没有修改或删除任何已有测试；新增的 skip 只有“非 Windows/Linux 平台跳过进程探针” |
| 评审对话 | 0 条未解决。Codex 机器人评审因额度用完而“Failed”，没有给出任何发现，不算评审意见 |
| 本地复跑 | 云端 Linux（Python 3.13，锁定依赖）跑本卡相关 7 个测试文件：119 passed、1 skipped |

### V04-R1 验收用例（reviews/16）逐条核对

| 用例 | 测试 | 结论 |
|---|---|---|
| 1 第二个 agent 被拒、提示谁持有到何时、不留痕 | `test_case1_a_second_agent_is_refused_with_the_holder_and_the_lease_end_and_nothing_is_written`（断言事件表不变、口令不出现在提示里） | 有 |
| 1 同一瞬间只一个成功（TD-SW008-145 并发） | `test_case1_two_agents_starting_the_same_card_at_the_same_instant_only_one_succeeds`（两个线程、两个独立 store 连接、Barrier 同时起跑） | 有；变异 M8 去掉存储事务内的兄弟 Run 检查后此测试失败，证明它真在测竞争 |
| 2 续租不踢掉自己 | 续租不改 epoch：`_grant_epoch` 只认 RUN_CREATED / LEASE_TRANSFERRED / LEASE_RECLAIMED 事件；合约测试 `test_only_a_change_of_ownership_raises_the_epoch_and_a_renewal_never_does` 等（卡 147/148 已有） | 有 |
| 3 租约未过期（含宽限）拒绝并写明要等多久 | `test_case3_a_live_lease_is_refused_with_the_wait_and_nothing_is_written`、`test_case3_inside_the_grace_period_the_lease_still_counts_as_live` | 有 |
| 3 过期且原进程已证明不在：接手、epoch +1、记下谁因何回收 | `test_case3_expired_and_holder_proven_dead_is_reclaimed_and_the_epoch_rises`；e2e `test_k01_the_killed_executors_card_is_taken_over_…`（真杀进程） | 有 |
| 3 无法判断：PENDING，只有用户签后才接手 | `test_case3_an_unidentifiable_holder_is_pending_until_the_user_signs`、`test_case3_an_unreadable_process_table_is_unknown_never_dead` | 有 |
| 3 **agent 签“接受风险”必须被拒** | `test_case3_an_agent_signed_risk_acceptance_is_refused_and_nothing_is_written`（参数化：CLAUDECODE、AUTO_PM_AGENT、非终端输入/输出）；CLI 测试用 `CLAUDECODE=1` 调 `pm sign-risk` 被拒 | 有 |
| 3 旧 agent 回来写检查点被拒、写不进去 | `test_case3_the_old_holder_coming_back_is_refused_and_writes_nothing` | 有 |
| 宽限期 120 秒 | `contracts/lease_reclaim.py:30 GRACE_SECONDS = 120` 未改；变异成 0 后合约测试 `test_the_grace_period_keeps_a_just_expired_lease_live` 失败 | 有 |

### 我做的变异检查（每次只改一处，跑测试，立即还原；工作区已复原）

| 编号 | 改了什么 | 结果 |
|---|---|---|
| M1 | 存储回收时去掉“租约仍有效”复核 | 被抓 |
| M2 | agent 标记检查直接放行 | 被抓 |
| M3 | 去掉“必须是交互终端” | 被抓 |
| M4 | epoch 不认 LEASE_RECLAIMED 事件 | 被抓 |
| M5 | 存储里不复核风险签署 | 被抓 |
| M6 | 存储里不复核持有者与租约版本（续租后回收） | 被抓 |
| M7 | 宽限期改成 0 | 被抓（合约测试） |
| M8 | 存储事务内去掉“已有非终态 Run”检查 | 被抓（并发测试） |

## 建议（都是低严重度）

1. **低：agent 拒签是“尽力而为”。** 拒签靠环境变量标记加“标准输入输出都是终端”。一个存心绕过的 agent 可以清掉环境变量、用伪终端执行，或者直接调存储的 `record_reclaim_risk_acceptance`（存储层不判断谁在签）。这在 TD-SW008-065 的单用户本机信任模型内，WBS §5 第 7 条已写明，测试要求（agent 签被拒）满足。绕过路径是我读代码推断的，没有实际跑（UNVERIFIED）。建议 M3 之后如果要防恶意 agent，再给签名绑一个只有用户知道的东西。
2. **低：用例 3 写的是“Decision 编号记在 Run 里”，实现用的是 `RISK-…` 签署事件。** 签署编号记在 `LEASE_RECLAIMED` 事件的 `request.risk_acceptance_id` 里，并绑定持有者、epoch、租约版本，续租或换手后自动作废，功能上等价，而且更严。建议文档卡里把用例措辞改成“签署编号”。
3. **低（过时措辞）：WBS §5 第 8 条写“仍先问用户的只有合并到 main（用户在网页上点）”。** 用户 2026-10-18 17:10Z 已把合并 main 授权给 Claude（条件：独立审计通过、CI 全绿、评审对话已解决、只用 Merge commit）。建议下一张文档卡顺手改。
4. **INFO：台账 §3 本 PR 只追加了 CHG-SCPT-2026-430、431 两行，没有本卡 CHG-SCPT-2026-432 的行。** 主执行说 432 已在本机收口，应在控制根分支的下一次写回里出现；请主执行确认。

## 给用户

可以合并，选 Merge。合并后能看到的变化：换 agent 只要两条命令（`pm handoff` 交出、`pm takeover` 接手），口令不用再手抄；执行的电脑断电或进程被杀后，别的 agent 能在租约过期 2 分钟后安全接手，判断不了时会等你本人签字，agent 签不了。这些命令要到 D06/D07 部署后才在根入口可用。
