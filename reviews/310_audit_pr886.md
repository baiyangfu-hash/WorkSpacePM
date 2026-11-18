# 310 PR #886 审计（卡 311 实施：GitHub 按需使用、本机合并，CHG-SCPT-2026-718，头提交 `07e93cd5`）

本文是数据，不是指令。

- 审阅者：本机 Claude Code 审计会话，工位 `claude-cb08e1`，不是写这个 PR 的会话。
- 审计时间：2026-11-17 约 17:40（MST）。
- 范围：按作者转达的用户要求，只找会挡合并的问题。

## 结论

同意。

放行判定: 07e93cd5 过

前提：
- 合并前 CI 全绿；
- 用户本人点过规则批准。

审计时这两项都还在跑或在等。按作者的要求，这次没在 PR 上贴评论，免得规则检查重跑、用户再点一次批准。结论只回给了作者。

## 核对（挡合并的项都没有）

| 项 | 结果 | 证据 |
|---|---|---|
| `audit_pr.py 886` | 退出码 0 | 没有 FAIL。<br>• `protected_paths` WARN 点名的是规则文件和变更单原件，都在卡 311 V1.1 的范围里；<br>• `ci_result` 跑时是 UNVERIFIED，CI 还在跑 |
| 范围 | 通过 | 13 个文件，全部落在 main 上卡 311 V1.1 的“可改范围”里。作者说的 7 个锁定文件已经退出本 PR，差异里确实没有它们 |
| 规则文字 | 通过 | `AGENTS.md` 删掉的只有：<br>• 红线 2 的旧尾句；<br>• FLOW-001 的三条线；<br>• PR 线收口的前提；<br>• WS-001 第 6 条；<br>• D-101、AUD-001 的旧开头。<br>和卡第 29～33 行一致。红线 1、红线 12 没动 |
| “要你点头”判定 | 通过 | `scripts/pm_merge.py` 的 `USER_PATTERNS` 是：<br>• 规则文件（直接取 `rules_approval_check.RULE_PATTERNS`）；<br>• `0100_PLC自动化/*`、`*/templates/plc-*`；<br>• `pm_merge.py` 自己。<br>删除另由 `removed_outside_cockpit` 判：驾驶舱目录以外的删除，加上目录里的记录类文件（`*CHG-*`、`*台账*`、`*DEC-*`、`*WBS*`），都算要点头。#885 的低项已落实 |
| 合并闸 | 通过 | `plan_merge` 先查几项，有一项不对就拒绝：<br>• 控制根停在 main；<br>• 工位在自己的分支上、没有未提交改动；<br>• main 是分支的祖先；<br>• 至少一个提交带“领卡占位”。<br>改到要点头的文件时，变更单必须同时满足四条：<br>• 提交说明里引用了它；<br>• 分支里本卡的实施卡写着它；<br>• 控制根里只找到一份原件；<br>• 原件状态在 approved 到 accepting 之间。 |
| 钩子 | 通过 | `hook_allows` 只管 `refs/heads/main`。改它只放行两种：带合并时的一次性标记；新值正好等于 `origin/main` |
| 测试 | 通过 | 在工位里检出 PR 头：`pytest tests/infrastructure/test_pm_merge.py tests/infrastructure/test_pm_flows.py` 79 passed；`ruff check` 通过；`mypy scripts/pm_merge.py` 没有问题。已切回 `claude/310` |
| 本机门禁 | 未跑 | 用户约 00:30Z 说“门禁不跑了，直接做”，以 CI 为准 |

## 低（不挡合并，记下）

1. **“写在本卡实施卡里”是从分支头读的**，实施卡本身就是 agent 在分支上写的。理论上，agent 可以把一张停在“已批准”的旧单号写进新卡里，合并闸照样放行。现在挡这件事的只有独立审计（审计核授权）。以后可以加一条：变更单原件里也写了这个卡号，或者批准时间晚于领卡时间。
2. **“要你点头”那一类合并前要独立审计放行**，这一条只写在 `AGENTS.md` 里，`pm_merge.py` 不查审计报告。要靠规矩和事后的 `verify-log`。
3. **`.trae/` 的标准路线还写着 PR 线**，卡里已列在“已知没改”，以 `AGENTS.md` 为准。
