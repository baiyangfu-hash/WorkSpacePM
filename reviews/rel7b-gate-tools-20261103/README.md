# 发版 7 V1.1（重判）门禁工具与卡（审计用，不开 PR）

来源：笔记本 `.auto-pm/reports/m3-rel7b/`（被 git 忽略），这里是给云端审计留的副本；`.py` 存成 `.py.txt`（提交钩子会把 reviews/ 下的 .py 当生产代码），`.log` 存成 `.txt`（仓库忽略 `*.log`）。

## 这是什么

V1.0（`RUN-SW008-M3-REL7-001`，审计 558 放行的 `claude/rel7-gate-tools-20261102` 上的工具）11-02 22:01 起跑、11-03 02:12 MST 判卷：十个输出全部退出码 0、各组失败数 0；G1、G3～G9 PASS，G2 FAIL——唯一原因是卡里声明的差值是空的（按当时批准的“先跑后补”）。V1.1 按第四～六次发版 V1.1 的先例重判：同一个冻结提交 `d671611a`、同一套判卷合同、同一张变更单 `CHG-SCPT-2026-472`；十组输出与三次 r09 重跑逐字节复用（`reuse_manifest.sha256` 核对），只重跑 baseline/install/fast 与判卷；声明差值改为实测差值。

## 与 V1.0 的差异（`V1.0_vs_V1.1_diff.txt`）

- 路径/标签：`m3-rel7`→`m3-rel7b`、V1.0→V1.1、Work/Run/Decision/检查点 `-002`、Decision 后缀 `M3REL702`、分支 `claude/m3-rel7b`。
- `rel7_gates_all.sh`：把“九组回归 + r09 三次重跑”换成“复用 `RUN-SW008-M3-REL7-001` 的输出”（先要求 `ALL_DONE`、十组退出码全 0、`transient_3.exit` 为 0，再复制并 sha256 核对）。
- `rel7_launch.sh`：没有租约延长（V1.1 约 15 分钟，远小于 3 小时）；带外锚点指向本分支与本目录里的 `rel7_1_approve_start.sh`。
- `rel7_config.json`：`expected_deltas`、`expected_skips` 为实测差值：rest +9；change +10；infrastructure +87（跳过 +6）；cli +126（跳过 +1）；core +760（跳过 +8）；qml +1。
- `rel7_gates.py`：只有路径/标签不同，判卷逻辑（含写死的 G3 窄例外与 26 个反例）与 V1.0 相同；其余工具（run_g2、detach_run、gate_status、mem_guard、keepawake、adjust_counts、gen_project）逐字节相同，`install_files.py` 只有卡号/版本不同。
- 卡正文：版本行、§1 第 7 条（复用证据）、第 11 条（租约）、新增第 13 条（V1.0 实跑结果与它留下的记录）、§3 第 3 条、实施批准行。

## 要请审计评估的两点

1. **V1.0 的治理 Run/Work/Decision 原样保留**：它的租约在 3 小时+1 小时上限处过期（core 实跑 2 小时 53 分），已部署版本无法结算（命令行两条规则互相矛盾，#496 的修复要发版 7 切换后才生效），所以不能按先例由所有者把它记为失败；V1.1 沿用 V1.0 的变更单、新建 `-002` 的 Work/Run/Decision。已核实：`pm orient` 仍只报 B2 的那个 Run（`RUN-SW-2026-008-CHG-SCPT-2026-471-01`），没有报告 V1.0 的 Run，所以 G3 窄例外照常适用；账本里 V1.0 的 Run 在判卷时会出现在“过期 RUNNING Run（信息性）”清单里，不影响判定。启动脚本能否在 V1.0 的 Run 仍为 RUNNING 的情况下创建新 Work/Run，已读代码核对（`start_run` 只拒同一 Work 已有非终态 Run、同一项目有“持有租约”的 Run；过期的不算持有），但没法在不写账本的情况下实测。
2. **批准凭据**：用户在主执行线程的预授权（消息 `cmsg_01AfNxhPWkgwWYuL1EVfYC7t5zPFVx9hSbijaekjfXg5kz`）“同意审计核过的发版 7 重判卡（V1.1）直接开跑；G1~G9 全 PASS 后切换发版 7；有任何一项不通过就不切换”，在审计放行后由我核对卡 SHA 等于放行的那个、读消息核对作者与正文，再写 `approval_refs.env`。

## 预检（推送前，离线）

`rel7_1_approve_start.sh --check-only` 通过（合成凭据，跑完删除；清单 19 项匹配、卡预检 passed、对账 0/0/0）；`rel7_launch.sh --dry-run` 通过（`launch_dryrun/`）；V1.1 彩排判卷 G1～G9 全 PASS（`rehearsal_evidence.txt`）。

## 2026-11-03 06:35 MST：563 放行后改卡（协调者裁 B）的修改

审计 563 放行的是 ca721483（卡 SHA 3d555ac5…）。其后发现并改掉“明知不实”的说法，卡与工具重新生成：

- REP（合同报告）§2 表：把“差值是 GitHub release-pregate 在 Windows 上对现行版本的冻结提交与本候选各实跑一次、逐组相减得出，记录 `x`”改成“差值取自 V1.0 的正式 Run `RUN-SW008-M3-REL7-001` 实跑的各组计数相对基线的差，十组输出逐字节复用；它只证明各组零失败、其余计数不变，不证明没有丢测试”；占位的 `x`（派生参数 MEASURED_FROM/DRILL_CI）已删。
- 卡 §1 第 4 条（原来写着 release-pregate 与 163c7a3b/6a9f1275 的运行）对齐 §1 第 7 条；§1 第 5 条（原来引用第六版的冻结分支与运行）改为 `sample-drill` 对 `d671611a` 的推送运行 41516806516（success，已核实）。
- 卡里其余 V1.0 旧说法：实施批准行残留的“晚上 9:00 起跑”、§6 的执行顺序与 G2 行（改为复用并核对 V1.0 输出）、§8 第 2 步（原写“创建变更单”，改为沿用 CHG-SCPT-2026-472）、第 4 步（原写“完整重跑门禁”）。
- 判卷脚本 G2 说明、收口提交信息模板、规格背景里“release-pregate 相减”的说法同步改为“V1.0 正式 Run 实测”。判卷逻辑（含 G3 窄例外与 26 个反例）不变。
- 新卡 SHA-256 与新批准脚本 SHA-256 见线程；与上一次放行版本（ca721483）的差异见 `git diff ca721483 HEAD`。
- 预检：`--check-only` 通过（合成凭据）、`--dry-run` 通过、彩排（最终工具）判卷 G1～G9 全 PASS，`rehearsal_evidence.txt` 末尾说明了“G2 VERDICT: FAIL”末行的来源（最后一个反例变体残留）。
