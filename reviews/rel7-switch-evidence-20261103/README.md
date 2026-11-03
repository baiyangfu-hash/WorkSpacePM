# 发版 7 切换证据（供事后审计 567）

范围：卡 219 V1.1 重判（Run RUN-SW008-M3-REL7-002）和切换卡 D07m（CHG-SCPT-2026-473，Run RUN-SW008-M3-D07M-001）的证据。本 PR 只加文档证据，另带工位分支上的一个提交 0f3de3b3。

## 先说偏差与缺口（三处偏差、两处缺口）

偏差：
1. 身份检查放行已知的 `LEASE_EXPIRED`：旧脚本要求“冲突为空”，B2 与 V1.0 的过期 Run 使冲突列表恰为 `["LEASE_EXPIRED"]`，所以 D07m 卡和脚本写明只放行这一项。
2. 旧运行时（6a9f127）不让控制根当 Run 工作树，且要求控制根里范围内文件与工位起点一致。我开了工位 `.auto-pm/worktrees/m3-d07m`，在分支 `claude/d07m-station` 上走正常钩子提交了控制根里未提交的 `deployment_manifest.json` 字节（提交 0f3de3b3，仅此一个文件，见下）；`main` 未动。
3. 切换脚本最后一步（CHG-SCPT-2026-473 的 accepting→completed）没有带 `--approval-evidence-ref`，被拒后我手动补了命令（全文见下）。

缺口：
- 切换前的 orient 原文没有单独存档；留下的是判卷抽取的事实（`G3_report.txt` 第 2、3 行、`G8_orient_exception.json`）和切换前身份报告（`d07m_identity_before.json`）。
- D07m 切换卡执行前没送审计（流程缺口，协调者已记）；本审计按事后补。

## 六项证据

1. **判卷 verdict**：`gate_verdict.json`（G1~G9 全 PASS，card=f3d636eb，run=RUN-SW008-M3-REL7-002），阶段时间 `gate_status.log`（判卷 PASS 13:38:42Z，全部结束 13:38:43Z），`gates_all.exit`=0。
2. **切换前 orient**：见上“缺口”。`G3_report.txt`：conflicts=["LEASE_EXPIRED"]，orient 报的 Run=RUN-SW-2026-008-CHG-SCPT-2026-471-01，Work=WORK-MSN-415BA3D417866398（IN_PROGRESS），台账里其它过期 Run（仅记录）=RUN-SW008-A2-201-03、RUN-SW008-M3-REL7-001。
3. **D07m 卡**：`d07m_D07m_card.md`，SHA-256 `12c4e3c2c25e37df82cbde0b272d5e6a75b0ec99059a4247085240bd395b8ec7`（卡“切换后核验”一段事先写明只放行恰为 `["LEASE_EXPIRED"]` 的冲突列表，多任何别的冲突算失败）。**切换脚本里只比对冲突列表**（`d["conflicts"] in ([], ["LEASE_EXPIRED"])`），**没有再核 Run、Work、卡号**；Run/Work/卡号只在 V1.1 判卷（G3，窄例外）核过。脚本：`d07m_deploy.sh.txt`，生成器 `gen_d07m.py.txt`。V1.1 卡原字节：`card219_V1.1.md`（SHA-256 f3d636eb9cdce4e2eb597e6631e8e3567d514a28ef987ce3c34cf0c63a46b227）。
4. **补凭据命令全文与时间顺序**：
   ```
   .venv/Scripts/python.exe -B main.py change transition CHG-SCPT-2026-473 --pid SW-2026-008 --to completed --approver fubai --approval-evidence-ref user-confirmation:cmsg_01AfNxhPWkgwWYuL1EVfYC7t5zPFVx9hSbijaekjfXg5kz --verification-conclusion "<见 CHG-SCPT-2026-473.md 的“验证结论”>"
   ```
   凭据是用户 2026-11-03T13:05:19Z 在本线程的预授权消息（已用 fetch_messages 核对原话）。顺序（UTC）：预授权 13:05:19 → V1.1 判卷 PASS 13:38:42 → V1.1 收口提交 13:41:44 → 切换卡生成与只读预检（13:4x）→ 切换（指针备份目录时间戳）13:52:31 → 后核验与 Checkpoint/Run/Work 关闭（同一次脚本，13:5x）→ 手动补凭据完成 CHG-473（约 13:56）→ 回执 13:56:44。脚本前两次在批准处因缺凭据被拒，之后脚本里加上了批准与决策的凭据参数（卡 SHA 不变）。
5. **0f3de3b3 文件清单**：仅 `00_Infrastructure/auto_pm/deployment_manifest.json`（1 个文件，8407 行新增——该提交把控制根里未提交的清单字节原样记入）。工位里没有写台账（`.auto-pm/continuity.db`）或发布指针（`active_release.json`、`previous_release.json`）。
6. **账本备份与切换后 resume**：`d07m_db_backup.txt`（切换前 SQLite 备份 sha256=cc35c121d3340d26a4a214c83707c6eb8e0992a30d9afff23e9ce2ff46dbdfc8，不用于恢复，库文件本身未入 PR）；切换后核验 `d07m_post_checks.txt`（含 4 项目对账 0/0/0、事件链 6301 条无断点）；切换后 B2 结算完成后的 `pm resume`：`pm_resume_after_settle_B2_*.json`（冲突为空）。

## 其它文件
`d07m_deploy*.out` 为脚本各次运行输出（去掉了告警行）；`pointer_backup/` 为切换前的指针与清单备份；`CHG-SCPT-2026-473.md` 为切换变更单；`d07m_user_switch_confirmation.txt`、`d07m_acceptance_receipt.txt` 为授权记录与回执。
