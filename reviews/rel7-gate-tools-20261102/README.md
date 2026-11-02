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

## 2026-11-02 16:40 MST：租约延长的授权凭据

用户本人在主执行线程写了“同意发版 7 门禁租约延长 1 小时”（消息 `cmsg_01AfNxhPWkgwWYuL1EVfYC7tJPaJZwt3hvXGtUMyCqBguG`，已用消息读取核实作者是用户）；`rel7_launch.sh` 在创建 Run 并首次续租成功后、起门禁之前，凭它执行一次 `continuity lease extend-hold --extra-seconds 3600`（幂等键 `RUN-SW008-M3-REL7-001-hold-1`），失败则不开跑。卡 §1 第 11 条同步。

## 2026-11-02 16:50 MST：558 第三轮复核的修改

- 批准凭据：`rel7_1_approve_start.sh` 不再把旧消息 id 写死；起跑时从 `approval_refs.env` 读取用户对**本卡最终 SHA** 的“开跑”（GO_REF/GO_TEXT/GO_SHA，且 GO_SHA 必须等于卡 SHA）和“晚上9:00可以跑”（NIGHT_REF），变更单批准、Decision、DELEG 与回执都引用它们；该文件只在用户亲口说“开跑”之后才写（模板见 `approval_refs.env.template`），所以卡字节不随它变化。回执里“卡字节此后没变”改成“起跑时脚本核对卡字节等于 SHA”。
- 租约延长：`rel7_launch.sh` 在创建 Run 并首次续租成功后、起门禁前自动执行 `lease extend-hold 3600`（凭用户本人在主执行线程的原话 `cmsg_01AfNxhPWkgwWYuL1EVfYC7tJPaJZwt3hvXGtUMyCqBguG`），失败则不开跑，不靠人手动。
- 续租循环：收口脚本开头 `touch STOP_RENEW`；门禁失败时包装脚本也 `touch STOP_RENEW`。
- 启动前：`FAILED` 改名留证（`FAILED.previous.<时间>`），不删；清 `DONE`、`gates_all.exit`、`RESUME`、`PAUSED`、`current_pid`。
- 指纹清单：除 `rel7_launch.sh` 外，又加入 `rel7_2_close_commit.sh`、`rel7_3_chg_close.sh`、`rel7_4_close_worktree.sh`、`m2_lease_renew.sh`、`m2_renew_loop.sh`；启动脚本的清单核对已适配并实测通过（19 项）。`rel7_1_approve_start.sh` 不进清单：它含卡 SHA，而卡里写着清单的 SHA，会循环依赖；它的字节由卡 SHA 检查间接约束。
- 卡 §1 第 12 条：工作树建好后失败不能原地重跑（前置检查会拒绝），以及这种情况怎么处理（保留现场、另出 V1.1）。

## 2026-11-02 16:45 MST：558 第四轮复核的修改

- 卡里所有“17:00 前跑完”的说法（卡头部、§1 实施批准、§1 第 1/7 条、§3 第 3 条、步骤 0）改为“用户 16:11 MST 改为晚上 9:00 起跑，不再受 17:00 限制，预计 2 小时 40 分至 3 小时”，步骤 0 里的时间比较已删。
- `approval_refs.env` 不再 `source`：`load_refs` 逐行解析，GO_SHA 必须 64 位十六进制、GO_REF/NIGHT_REF 必须匹配 `user-confirmation:cmsg_…`，文本字段拒绝引号、反引号、`$`、反斜杠与超长；未知键、缺项一律拒绝。`approval_refs_parser_test.txt` 是 9 个用例的结果。文件由我在读取消息核对作者与正文之后才写。
- `rel7_2_close_commit.sh`：解析同一份文件，回执 DELEG 引用 GO_REF 与 NIGHT_REF。
- 带外锚点：`rel7_launch.sh` 在起跑前取 `origin/claude/rel7-gate-tools-20261102` 上 `rel7_1_approve_start.sh` 的哈希，与笔记本上的副本比对，一致才开跑，比对结果写进 `launch_anchor.log`；本提交里该脚本的 SHA-256 已在线程里单独报出。
- 干跑日志（状态文件、各进程日志、结束标记）放在 `launch_dryrun/`。

## 2026-11-02 16:55 MST：预检逼出的一处卡措辞修改（558 第五轮之后）

- 用户对 fb5ca269 说“开跑”后，起跑前的 `rel7_1_approve_start.sh --check-only` 里，卡预检报“实施批准:审批字段含占位符”：卡 §实施批准那一行写了 `user-confirmation:<该消息 id>`，尖括号被当成占位符。只改这一行的措辞（“凭据取 user-confirmation 加该消息 id 的形式作为 --approval-evidence-ref”），新卡 SHA-256 `1668f66a…44a2`（旧 fb5ca269 作废）；`rel7_1_approve_start.sh` 只有第 13 行 CARD_SHA 变化；指纹清单逐字节不变。
- 本次提交前已全量预检：`--check-only`（precheck passed、清单 19 项匹配、对账 0/0/0）与 `--dry-run` 干跑；干跑日志已更新。
