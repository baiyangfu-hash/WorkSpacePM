# 发版 7 门禁工具（审计用，草稿）

只含工具与卡草稿，不含发布内容；不开 PR。来源：笔记本 `.auto-pm/reports/m3-rel7/`（被 git 忽略），这里是为云端审计留的副本。

- `219_M3-REL7_第七次发版候选门禁实施卡_PM.md`：卡草稿，SHA-256 见线程（带最终例外的彩排尚待重跑，卡的“演练事实”一栏已如实写明）。
- `rel7_gates.py.txt`（审计副本，运行时是 .py）：判卷脚本。窄例外写死在这里：`KNOWN_STUCK_RUN`、`orient_ok`、`orient_cases`；G8 判卷要求 26 个反例全部符合预期。
- `G8_orient_exception_cases_result.json`：26 个反例按当前代码算出的结果（got 与 expected 逐条相等）。
- `rel7_exception_patch.py.txt`、`derive_rel7.py.txt`：把例外加进判卷脚本的派生工具。
- `rel7_config.json`、`reference_manifest.json`：冻结提交 `d671611a` 与参考字节指纹。

## 2026-11-02 16:30 MST 更新（审计 558 意见已改，脱离会话启动）

- 删掉旧宽分支（派生脚本里残留的早期补丁，现已清除；补丁脚本重复应用会拒绝）；`orient_ok` 要求：冲突恰为 `['LEASE_EXPIRED']`、orient 返回的 `run.run_id` 恰为已知 Run、同一份 orient JSON 里的 `work_id` 恰为已知 Work 且 `IN_PROGRESS`、卡号恰为 `CARD-SW008-M3-REL7`；`orient_extract` 对 run 不是字典等一律取不到并判 FAIL；例外信息在 G3 报告里单独一行；G8 现为 26 个例外反例（18 判定 + 8 提取）。
- `rehearsal4_evidence.txt`：带最终例外的彩排（脱离会话启动）判卷 G1～G9 全 PASS 的证据，含真实 orient 的 `run.run_id`。
- `rel7_detach_patch.py.txt`、`detach_run/gate_status/mem_guard/keepawake.py.txt`、`rel7_gates_all.sh`、`run_g2.sh`、`rel7_launch.sh`：正式门禁改为脱离会话的后台进程，每阶段/每组写状态文件，内存到 40GB 挂起并写告警。

## 2026-11-02 16:35 MST 更新（558 复核后的追加项）

- `rel7_launch.sh` 已加进指纹清单（`tools/rel7_launch.sh`）；启动前清残留（`unset PG_G PG_WT GATE_GROUPS`，删除 `gates_all.exit`、`DONE`、`FAILED`）；支持 `--dry-run`（不创建 Run、不跑真门禁，用占位门禁检验脱离启动、状态文件、防休眠、内存保护的收尾）。`launch_dryrun_status.log` 是一次干跑的状态文件。
- 一并放上分支：`rel7_1_approve_start.sh`、`rel7_2_close_commit.sh`、`rel7_3_chg_close.sh`、`rel7_4_close_worktree.sh`、`m2_lease_renew.sh`、`m2_renew_loop.sh`，方便核对续租循环怎么结束（`STOP_RENEW` 文件 / 门禁结束标记）。
- `mem_guard` 不监视门禁进程本身，只在 `DONE`/`FAILED` 出现（状态目录或其上一级目录）或 8 小时到点时退出，注释已写明。
- 租约总时长余量：卡 §1 第 11 条（实测第六版 168.5 分钟对 180 分钟上限，余量 11.5 分钟，需用户本人延长）。
