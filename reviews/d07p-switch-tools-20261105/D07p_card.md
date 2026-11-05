# D07p｜切换到发版 7.2 候选（M3-D07P）

> 卡片编号：`CARD-SW008-M3-D07P V1.0`
> 隔离基线：`dd8b192f2e0a8ffdc370fd7e2dc4f7a999bb7642`（`main` 上 PR #550 的合并提交，发版 7.2 的发版点）
> 路径根：`.`
> 档次：核心档

本卡把 D07n 的切换再做一次，让 `1.3.3-d563293` 之后合进 `main` 的发布载荷改动在本机生效（总闸 #519/#530/#531、账本备份 #533/#534、分诊台与长回归等；详见卡 221 V1.1 §1）。候选 `1.3.3-dd8b192` 由合并提交 `dd8b192f` 用它自己的 `scripts/pmf_build.py` 安装；就是发版点本身（卡 221 V1.1 的门禁提交一栏填的冻结提交，切换基线就是它）。卡 221 V1.1 的十组回归与 G1～G9 必须在 `.auto-pm/reports/m3-rel72b/gates/gate_verdict.json` 里全部 PASS（没有例外，与 D07n 的 G2 例外不同），其 Run `RUN-SW008-M3-REL72-003` 已 SUCCEEDED。切换与回退用 D06 演练过、D07～D07n 用过的同一份 `.auto-pm/reports/m3-d06/pmf_release_ops.sh`（SHA-256 `fe331979d463d4de32209bfb32c7eca8db1e17ee60a39622a92cd8c7be53e8de`）。切换后 `previous` 为现行的 `1.3.3-d563293`，更早的 `1.3.3-d671611` 仍保留并校验。

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `00_Infrastructure/auto_pm/releases/1.3.3-dd8b192` | 计划新增 | 候选发布的载荷 |
| `00_Infrastructure/auto_pm/deployment_manifest.json` | 存在 | 追加候选的清单条目 |
| `00_Infrastructure/auto_pm/active_release.json` | 存在 | 有效版本改为 `1.3.3-dd8b192` |
| `00_Infrastructure/auto_pm/previous_release.json` | 存在 | 上一版改为 `1.3.3-d563293` |

授权：用户 2026-11-05 04:04:33 UTC（11-04 21:04 MST）在本项目线程里亲口说：“不过不切换，过了自己切换。门禁已经授权了。”（原话与消息编号记入 `user_switch_confirmation.txt`；这是常设授权，写在本卡存在之前，所以不点名本卡 SHA）。条件：卡 221 V1.1 的 G1～G9 全 PASS 且 Run 已 SUCCEEDED；独立审计放行卡 221 V1.1 与本卡，放行的引用记入 `switch_audit_ref.txt`（没有这份记录脚本不会切换）；候选产品子树等于门禁时测过的冻结提交；任一切换后核验失败即自动回退指针；不回滚数据库。任一不过则不切换、保持 `1.3.3-d563293`。切换前脚本用 SQLite 备份接口把账本原样复制一份留作证据（不用于恢复）。

起点：Run 的工位 `.auto-pm/worktrees/m3-d07p` 从最新 `origin/main` 建。步骤 M（卡 221 V1.1）已把 16 个未登记的旧发布目录移出 `releases/`，控制根里的清单与指针现在等于 `main`，所以 D07n 里“把控制根清单字节提交进工位”一步通常没有东西可提交；若有差别仍按 D07n 的做法经正常 Hook 提交一次。**工位数守卫**：`.auto-pm/worktrees` 里已有 7 个目录时不启动（发版体检的机器上限是 7，本卡工位是第 8 个）；卡 221 V1.1 收口会移除它的候选工位 `m3-rel72b`，之后是 6 个。

切换后核验（任一失败立即用同一脚本自动回退指针并停下，回切后写回执）：配置版本 = 实际加载版本 = `1.3.3-dd8b192`、从发布目录加载、无回落、**冲突列表必须为空（没有例外）**；`pm handoff`、`pm takeover`、`pm orient`、`continuity run reclaim`、`continuity lease record-holder`、`gui`、`long-run`、`pm state-backup`、`pm triage` 入口能应答（冒烟）；`pm orient SW-2026-008 --json` 的冲突列表为空；本卡在新运行时下通过机器预检；全部注册项目对账 0/0/0；真实 pre-commit 钩子经新运行时退出 0；新版本读真实数据库副本时事件链无断点、Run 活动全部可读；新、现行、上一版三个发布逐文件校验通过。切换后另跑一次 `continuity backup` 与 `verify-backup`（0 条链断裂）。批准、决策、验收三处命令都带用户消息 id 作为 `--approval-evidence-ref`。
不在本卡：发版 PR（把发布目录 `1.3.3-dd8b192`、三个指针文件和只多一项的清单入库，同 #528 的做法，另走小卡）；`pm state-backup push` 到远端（外发动作，切换后只确认入口可用）。
禁止：回滚或覆盖数据库（切换前的数据库副本只作证据）、改历史发布/事件/Checkpoint、改源码、合并 main、推送。脚本：`.auto-pm/reports/m3-d07p/d07p_deploy.sh`（`--check-only` 只读预检，可在任何时候运行）。
