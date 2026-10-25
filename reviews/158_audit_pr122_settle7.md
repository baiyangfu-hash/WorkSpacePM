# 158 审计 PR #122（SETTLE7：卡 188 V1.1 的两份决定文件）

审计人：project Claude 会话（不是写这个 PR 的会话）。时间 2026-10-25（亚利桑那时间 MST = UTC−7）。审计头 `92b56b44a073f2b457989669ffb0b8482c794f3b`，基线 main `f474b52a`。

## 结论：过

## 机械检查
`python reviews/tools/audit_pr.py 122`：mergeable PASS；scope 2 个文件；secrets PASS；protected_paths WARN（两份决定文件，下面点名）；privacy WARN（`fubai` 2 处，main 上已有同类基线，本 PR 没有新增类别）；`ci_result` 首次 FAIL 的原因是 safety（pull_request_target）被重复 run 取消，不是测试失败，已重跑同一 run 40174075927，结果见 PR 评论。guard、plc、gate 成功，commit status `safety-zone`=success（没碰安全区）。

## 人工核对
- 范围：与 `origin/main` 的差异恰好 2 个新增文件 `.auto-pm/decisions/DEC-20261024-M3REL202.json`、`DEC-20261025-SETLREL3.json`；一个提交 `92b56b44`，无代码改动，无夹带。
- 格式：两份都是合法 JSON，`schema_version: decision_package.v1`，字段与已入库的 `DEC-20261024-SETLREL2.json`（结算 REL2-001）、`DEC-20261024-M3WB4601.json`（卡 191）逐字段同构。
- SETLREL3 授权面最小：`allowed_runtime_actions` 只有 `settle_expired_run`，`target_run_ids` 只有 `RUN-SW008-M3-REL2-002`，`allowed_outcomes` 只有 `CANCELLED`，`approved_files` 只有 `.auto-pm/continuity.db`，`conditions` 为空，和 SETLREL2 的写法一致，没有放大权限。
- 时间自洽：M3REL202 `approved_at` 03:42Z（卡开跑前），SETLREL3 07:45Z（租约 07:43Z 过期之后），先后顺序对得上 PR 描述。
- M3REL202 的 conditions 与 M3WB4601 的两条限制同文，把可改文件限定为 1 个 `…/05_收尾/010_M3_第二次发版候选构建与全量门禁_REP.md`，不授权产品文件、台账、规则、`.trae` 等。
- 未触碰 `approvers.json`，所以不触发“批准口令登记”那条。

## 未能核实（如实写明）
- 变更单 `CHG-SCPT-2026-454/456` 和运行 `RUN-SW008-M3-REL2-002` 在控制根的本机账本里，仓库里没有，我没法独立核对它们的状态；PR 描述里“Run 与 Work 已 CANCELLED、456 已关闭”是主执行的说法，标为“未核实”。
- 卡 188 §9 和 SHA-256 在卡正文里，不在本 PR 范围内，未核对。

## 合并条件
审计通过；合并方式 Merge commit（保留 `92b56b44` 原样）；CI 以 safety 重跑结果为准，评审对话 0。
