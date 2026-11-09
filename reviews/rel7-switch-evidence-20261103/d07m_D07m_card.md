# D07m｜切换到第七次发版候选（M3-D07M）

> 卡片编号：`CARD-SW008-M3-D07M V1.0`
> 隔离基线：`d671611a13bc15536047769fdb0498666c414044`（`main` 上 PR #496 的合并提交，第七次发版点）
> 路径根：`.`
> 档次：核心档

本卡把 D07 的切换再做一次，让 `1.3.3-6a9f127` 之后合进 `main` 的 69 个合并提交（其中进入 `main` 的 PR 53 个，#441～#496 之间）在本机生效；其中最要紧的是 #496：控制根里结算过期 Run 的命令（`continuity run settle-expired`）现在能用，B2 和 V1.0 两个过期 Run 要靠它收拾。候选 `1.3.3-d671611` 由合并提交 `d671611a` 用它自己的 `scripts/pmf_build.py` 安装；它的 `auto_pm`、`templates`、`scripts` 三棵子树与卡 219 V1.1（M3-REL7）门禁全过的提交 `45900806` 逐字节相同（卡 219 的提交就是在这个合并提交上只加了一份报告）。#496 以后合并的不在本次候选里。切换与回退用 D06 演练过、D07～D07l 用过的同一份 `.auto-pm/reports/m3-d06/pmf_release_ops.sh`（SHA-256 `fe331979d463d4de32209bfb32c7eca8db1e17ee60a39622a92cd8c7be53e8de`）。切换后 `previous` 为现行的 `1.3.3-6a9f127`。

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `00_Infrastructure/auto_pm/releases/1.3.3-d671611` | 计划新增 | 候选发布的载荷 |
| `00_Infrastructure/auto_pm/deployment_manifest.json` | 存在 | 追加候选的清单条目 |
| `00_Infrastructure/auto_pm/active_release.json` | 存在 | 有效版本改为 `1.3.3-d671611` |
| `00_Infrastructure/auto_pm/previous_release.json` | 存在 | 上一版改为 `1.3.3-6a9f127` |

授权：用户 2026-11-03 13:05 UTC 在本线程里亲口预授权“同意审计核过的发版 7 重判卡（V1.1）直接开跑；G1~G9 全 PASS 后切换发版 7；有任何一项不通过就不切换。”（消息 cmsg_01AfNxhPWkgwWYuL1EVfYC7t5zPFVx9hSbijaekjfXg5kz），另见同线程 2026-11-03T04:52:49Z 的同类预授权；V1.1 门禁已 G1～G9 全 PASS（`.auto-pm/reports/m3-rel7b/gates/gate_verdict.json`）；原话与消息编号记入 `user_switch_confirmation.txt`；没有这份记录脚本不会切换。本卡 SHA 先在线程里报出。切换前脚本用 SQLite 备份接口把账本原样复制一份留作证据（不用于恢复）。

切换后核验（任一失败立即用同一脚本回退指针并停下）：配置版本 = 实际加载版本 = `1.3.3-d671611`、从发布目录加载、无回落、无冲突（唯一例外：身份报告里的冲突列表恰好是 `["LEASE_EXPIRED"]`——那是 B2 的旧 Run 和卡 219 V1.0 的 Run 两个已过期租约，卡 219 §1 第 9 条已审定为已知项，等切换后用 #496 修好的命令结算；列表里多出任何别的冲突都算失败）；`pm handoff`、`pm takeover`、`pm orient`、`continuity run reclaim`、`continuity lease record-holder` 与 `gui` 入口能应答；本卡在新运行时下通过机器预检；全部注册项目对账 0/0/0；真实 pre-commit 钩子经新运行时退出 0；新版本读真实数据库副本时事件链无断点、Run 活动全部可读；新、现行、上一版三个发布逐文件校验通过。切换后另跑一次 `continuity backup` 与 `verify-backup`（0 条链断裂）。
禁止：回滚或覆盖数据库（切换前的数据库副本只作证据）、改历史发布/事件/Checkpoint、改源码、合并 main、推送。脚本：`.auto-pm/reports/m3-d07m/d07m_deploy.sh`（`--check-only` 只读预检，可在任何时候运行）。
