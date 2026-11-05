# SETTLE72｜发版 7.2 切换前的账本结算卡（8 条旧 Run＋2 条失败尝试遗留 Run）

> 卡片编号：`CARD-SW008-M3-SETTLE72 V1.0`
> 隔离基线：`26157a48f64a319b0c0e8130292f4d7a07c3b194`
> 路径根：`.`
> 安全回路: 否

发版 7.2 的运行时新增一条检查：非终态的 Run 挂在已 ACCEPTED/CLOSED/CANCELLED 的 Work 下面，`pm orient` 报冲突 `LIVE_RUN_UNDER_FINISHED_WORK`。切换卡 D07p V1.0 在 2026-11-05 06:27 MST 切到 `1.3.3-dd8b192`，切换后核验只有这一项不过，脚本自动回退了指针（现行仍是 `1.3.3-d563293`），切换卡要求冲突必须为空、没有例外。用 7.2 运行时自己的扫描（`list_live_runs_under_finished_work`，在账本的 sqlite 备份副本上只读运行）核实出下面 8 条：项目 SW-2026-008 有 6 条（`pm orient SW-2026-008` 会报）、项目 SYS-2026-001 有 2 条（`pm orient SYS-2026-001` 会报）；另加 7.2 两次失败尝试留下的 2 条（它们的租约已过期或将到期、Work 在 IN_PROGRESS，不是该冲突的触发者，一并结清，账本不留尾巴）。共 10 条目标：

| # | 目标 Run | 它的 Work | 项目 | 情况 |
|---|---|---|---|---|
| 0 | `RUN-SW008-A2-201-01` | `WORK-SW008-A2-201` | SW-2026-008 | A2-201 第一次运行（BLOCKED），其 Work 已 CANCELLED |
| 1 | `RUN-SW008-A2-201-03` | `WORK-SW008-A2-201-R2` | SW-2026-008 | A2-201-R2 第三次运行（RUNNING），其 Work 已 ACCEPTED |
| 2 | `RUN-SW008-A2-201-04` | `WORK-SW008-A2-201-R2` | SW-2026-008 | A2-201-R2 第四次运行（VERIFYING），其 Work 已 ACCEPTED |
| 3 | `RUN-SW008-PMF-C03REC-002` | `WORK-SW008-PMF-C03REC-001` | SW-2026-008 | C03REC 第二次运行（VERIFYING），其 Work 已 CANCELLED |
| 4 | `RUN-SW008-PMF-E01-001` | `WORK-SW008-PMF-E01-001` | SW-2026-008 | PMF-E01 运行（BLOCKED），其 Work 已 ACCEPTED |
| 5 | `RUN-SW008-PMF-G10-001` | `WORK-SW008-PMF-G10-002` | SW-2026-008 | PMF-G10 运行（BLOCKED），其 Work 已 ACCEPTED |
| 6 | `RUN-SYS001-PMF-WBS24-001` | `WORK-SYS001-PMF-WBS24-001` | SYS-2026-001 | WBS24 运行（VERIFYING），其 Work 已 CANCELLED（项目 SYS-2026-001） |
| 7 | `RUN-SYS001-PMF-WBS25-001` | `WORK-SYS001-PMF-WBS25-001` | SYS-2026-001 | WBS25 运行（VERIFYING），其 Work 已 ACCEPTED（项目 SYS-2026-001） |
| 8 | `RUN-SW008-M3-REL72-002` | `WORK-SW008-M3-REL72-002` | SW-2026-008 | 卡 221 V1.0 的失败 Run（RUNNING，租约已过期），其 Work 在 IN_PROGRESS |
| 9 | `RUN-SW008-M3-D07P-001` | `WORK-SW008-M3-D07P-001` | SW-2026-008 | 切换卡 D07p V1.0 的回退 Run（RUNNING，租约 07:26 MST 到期），其 Work 在 IN_PROGRESS |

做法与 M2/M3 已用过的恢复链完全相同（先例 `.auto-pm/reports/m3-settle10/`、`m2-settle/`）：每个项目一张恢复变更单（SW-2026-008 用 SCPT 域，SYS-2026-001 用 DOCU 域，各自走到 implementing）；每个项目一份恢复 Decision（`settle_expired_run`、结果 `CANCELLED`、`--target-run-id` 逐条列出本项目的目标）；**一个**提交把 Decision 文件（目标原 Decision 里还没入库的 2 份、加 2 份恢复 Decision）与控制根 `HEAD` 绑定（先例要求，此后到全部结算完成前不得再同步或提交）；然后对每条目标各起一个恢复 Work/Run（owner `claude:settle72`，owned 路径 `.auto-pm/continuity.db`，写入型 Work），用 `continuity run settle-expired` 把目标 Run 前向结算为 `CANCELLED`；原来 Work 还在 IN_PROGRESS 或 BLOCKED 的（第 8、9 条）随后转 CANCELLED，已经是 ACCEPTED/CANCELLED 的 Work 原样不动；旧口令必须被拒（第 8、9 条有口令文件才探测）；最后收掉恢复链自己的 Run/Work。目标 Run 的租约必须已过期：第 9 条（D07p V1.0 的回退 Run）租约到 2026-11-05 07:26 MST 才过期，脚本在那之前遇到它会停下并报出到期时间，之后可从原处接着跑（每步先查状态，幂等）。

运行态数据库只存在于主工作区（被 git 忽略），所以恢复链在主工作区运行；没有直接 SQL、没有补偿脚本。每个目标按运行时自己的校验逐条结算（目标 Work 必须绑定 canonical 且不可变的 Decision、其 scope 必须在原 Decision 批准的文件之内、目标租约已过期、恢复链与目标 Work/CHG 相互独立）；任何一条被运行时拒绝，脚本停下、保留现场、报出原因，不绕过、不改判据。

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `.auto-pm/continuity.db` | 运行态 | 恢复 Run 的 owned 路径；仅用于把过期 Run 结算为 CANCELLED，并把仍在 IN_PROGRESS/BLOCKED 的目标 Work 转为 CANCELLED |

唯一的 git 写入：一个只含 Decision 文件（目标原 Decision 里未入库的 `DEC-20261104-M3R72A01`、`DEC-20261105-M3D07P01`，加 2 份恢复 Decision `DEC-20261105-SETL72SW`、`DEC-20261105-SETL72SY`）的提交，加在控制根的 `main` 上，随后推到 PR 分支、经审计以 Merge commit 合并，使控制根仍能快进跟上 `origin/main`（控制根 `main` 现在落后 `origin/main`，PR 合并后才快进；合并前不要同步）。
禁止：直接 SQL、改历史事件、改产品代码、处置其他记录（其他 BLOCKED 的 Work、停在 implementing 的变更单一律原样保留，其中包括 `CHG-SCPT-2026-478`、`CHG-SCPT-2026-479`）、合并、部署、切换发布版本。恢复变更单的收口等用户验收（`settle72_2_chg_close.sh`）。
授权：待用户亲口批准（见线程里的批准原话，批准后写入 `approval_receipt.txt`，必须含本卡 SHA 的前 12 位）；用户 2026-10-18 预授权 Claude 自行收口推送。依据 PM-042、PM-033。无 UI 改动。
脚本：`.auto-pm/reports/m3-settle72/settle72_1_recovery.sh`（`--check-only` 只读预检，可随时运行）、`settle72_2_chg_close.sh`。
