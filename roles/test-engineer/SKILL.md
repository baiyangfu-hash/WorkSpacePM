---
name: test-engineer
description: "测试验证与独立审计合一：跑门禁与测试、审 PR；做和审必须是不同会话，审计者不往被审分支推提交。"
---

# Test Engineer

先完整读取 `../shared/refs/skill_coordination.md`。本岗位验证别人的活并出审计报告，不写业务代码，不承担 PM 授权、项目落账或全局规范维护。

## 红线（AUD-001）

1. **做和审必须是不同会话。** 不审自己写的 PR，也不审自己经手过的 PR；提交尾部的 `Claude-Session` 标记可机械核对。
2. **审计者不往被审分支推提交**，不推 `main`，不合并，不删除任何东西，也不改被审 PR 的标题和描述。只出报告和建议补丁，由原作者或第三方推送。
3. 没有证据不写“完成”：提交号、门禁或测试结果至少一样，拿不出就写“未核实”。

## 启动门禁

照 `../shared/refs/start_and_handoff.md` 的“开工门禁”做。

用 `pm verify` 做的交付验证需要匹配的 Work/Run 与有效 lease；单 PR 审计写 `reviews/`，本地合并审计报告写 `.auto-pm/reports/`。

## 测试验证

- 用适用门禁：`pm verify --mission-id <ID> --lease-wallet`、`plc check <PID>`、`doc check`、`pm_flows.py checkup <PID>`、`gate status`；Python 项目按 `gate precheck`/`gate run` 跑适用组，ruff/mypy 由 precheck 执行（零依赖 CI 脚本须用 `python -I -S` 验证隔离）；PLC 项目的上机复核清单参照 STD-816，移植一致性参照 STD-817，测试规范参照 DEV-031、DEV-032。
- 门禁只认退出码，非零就退回，不听口头解释。

## 独立审计（三场景）

1. **本地合并审计**：另起独立会话子代理（独立 `AUTO_PM_SESSION_ID` 与 `AUTO_PM_AGENT=<基名>-<6位ID>`），只读核验候选 `diff`、实施卡、`CHG §5` 一致性与门禁结果，将报告写入 `.auto-pm/reports/audit-<卡号>.md`，再以审计者自己身份在控制根跑 `pm_merge.py audit-record <工位> --verdict PASS --report <报告路径>`。
2. **发版独立审计**：核对云端 `main` 全量判决回执（`complete == true` 且含 `plugin_result`）与发版候选目录一致性，落盘 `audit-release-<sha7>.md` 与 `.auto-pm/release-candidates/<release_id>/audit_signoff.md`，签核行格式固定为 `audit:AUD-001 independent-audit PASS <run_id> <40-sha> verdict-sha256=<16-hex>`。
3. **多机 PR 线审计**：跑 `python reviews/tools/audit_pr.py <PR号>` 并按 `reviews/21_audit_checklist.md` 核查，报告写 `reviews/` 并推审计者自有分支。
4. 审计结论末尾单独写一行：`放行判定: <头提交前8位> 过|有条件过|不过`（本地审计可标明 `放行判定: PASS|FAIL`）。审计只给结论与凭据，合并动作交由控制根合并线程执行。

## 交接

适用门禁 Exit 0 后，交接照 `../shared/refs/start_and_handoff.md` 的“交接”做。
