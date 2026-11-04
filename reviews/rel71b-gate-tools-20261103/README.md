# 发版 7.1 G2 例外证据（只含证据与 V1.1 卡/工具，不含载荷；不开 PR）

- 用户原话（用户本人在线程里打字）：`cmsg_01AfNxhPWkgwWYuL1EVfYC7t7ArBXS4AXC393MHjk5J7Cu`，2026-11-04T03:35:09Z：“同意 7.1 G2 按两条单测重跑结果判定：两条通过即放行，不再整组重跑 core”。
- 两次冻结（Kernel-Power 506/507，Reason 15，LidOpenState=false，AcOnline=true）：2026-11-04T00:57:15Z→01:10:18Z（17:57:15→18:10:18 MST）与 01:19:24Z→01:30:23Z（18:19:24→18:30:23 MST）；佐证 commit_watch.log 的 909 秒与 786 秒空档（00:56:24→01:11:33Z、01:17:45→01:30:51Z）。core 组 17:24:51～20:16:44 MST（`evidence/V10_status.log`）。
- V1.0 原始报错：`evidence/V10_core_error_3018-3080.txt`（ERROR，setup 里 git rev-parse 超时 785.3 s，限 60 s）、`evidence/V10_core_failure_3484-3627.txt`（FAILED，git check-ref-format 等了约 662 s，限 300 s；末行汇总 1 failed, 3047 passed, 15 skipped, 1 error in 10310.95s）。
- 重跑：`evidence/rerun.txt`（2 passed in 25.80s）、`rerun.exit`（0）、命令与环境 `rerun_two.sh`、前后核对 `pin_before.txt` / `pin_after.txt`（HEAD 都是冻结提交 d5632931…，origin/main 同）、`status_before.txt` / `status_after.txt`（相同）、`heartbeat.log`（只有 1 个采样，因为重跑只 26 秒）、电源：`power_*.txt`（脚本内抓取因 Git Bash 把 /a 当路径而失败，`power_after_fixed.txt` 是补抓，/requests 需管理员，合盖动作未查到值）。文件字节核对：对 `bytes_after_gates.txt` 做 `sha256sum -c` 无差异（在笔记本上执行，结果为空输出）。
- 判卷记录原样：`evidence/gate_verdict.json`（G2 仍是 FAIL）、`G2_report.txt`、`judge_output.txt`、`FAILED`。
- 例外记录：`evidence/EXCEPTION.md`。判卷脚本与 D07n 逻辑都没改。
- V1.1 整组重跑卡与工具（备用，按用户方案不跑）：`220_…V1.1_PM.md`、`v11_tools/`，单元演练输出 `evidence/v11_checks.txt`。
