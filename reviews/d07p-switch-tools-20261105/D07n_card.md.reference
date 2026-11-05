# D07n｜切换到发版 7.1 候选（M3-D07N）

> 卡片编号：`CARD-SW008-M3-D07N V1.0`
> 隔离基线：`d563293171847124e609469b5371c5d8b9688443`（`main` 上 PR #514 的合并提交，发版 7.1 的发版点）
> 路径根：`.`
> 档次：核心档

本卡把 D07 的切换再做一次，让 `1.3.3-d671611` 之后合进 `main` 的 12 个合并提交在本机生效（长任务守卫 `long-run` #514、内存预检 #513、租约口令钱包与 `run start --executor` 修复，及发版 7 切换的证据入库 #506/#507/#517 等）。候选 `1.3.3-d563293` 由合并提交 `d5632931` 用它自己的 `scripts/pmf_build.py` 安装；就是发版点本身（卡 220 门禁提交一栏填冻结提交 `d5632931`，切换基线就是它）。卡 220 的 016 报告提交不存在：门禁 G2 FAIL（V1.0 的 core 组因笔记本两次合盖待机而 git 子进程超时），经用户 2026-11-04T03:35:09Z 例外放行（消息 `cmsg_01AfNxhPWkgwWYuL1EVfYC7t7ArBXS4AXC393MHjk5J7Cu`：两条失败用例单独重跑 2 passed 即放行）；原来引用 016 报告提交的地方改为引用例外证据提交 `c31934b9`（路径 `reviews/rel71b-gate-tools-20261103/`）。切换与回退用 D06 演练过、D07～D07m 用过的同一份 `.auto-pm/reports/m3-d06/pmf_release_ops.sh`（SHA-256 `fe331979d463d4de32209bfb32c7eca8db1e17ee60a39622a92cd8c7be53e8de`）。切换后 `previous` 为现行的 `1.3.3-d671611`。

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `00_Infrastructure/auto_pm/releases/1.3.3-d563293` | 计划新增 | 候选发布的载荷 |
| `00_Infrastructure/auto_pm/deployment_manifest.json` | 存在 | 追加候选的清单条目 |
| `00_Infrastructure/auto_pm/active_release.json` | 存在 | 有效版本改为 `1.3.3-d563293` |
| `00_Infrastructure/auto_pm/previous_release.json` | 存在 | 上一版改为 `1.3.3-d671611` |

授权：用户 2026-11-03 19:33 UTC 在本线程里亲口预授权“今天 #514 合并后，以 main 最新提交打发版 7.1，全量门禁和审计都过就切换；任一不过则不切、保持 1.3.3-d671611。切换后如果驾驶舱启动或冒烟检查失败，自动回切到 1.3.3-d671611。”（消息 cmsg_01AfNxhPWkgwWYuL1EVfYC7tKDxhSnLfp7mWBPVGmAc3TB）；条件：卡 220 的 G1～G9 全 PASS 且独立审计放行本卡与卡 220（唯一例外是 G2：用户 2026-11-04T03:35:09Z 例外放行，消息 `cmsg_01AfNxhPWkgwWYuL1EVfYC7t7ArBXS4AXC393MHjk5J7Cu`，证据提交 `c31934b9`；G2 在 gate_verdict.json 里仍是 FAIL，不改写），任一不过不切换、保持 `1.3.3-d671611`；原话与消息编号记入 `user_switch_confirmation.txt`，没有这份记录脚本不会切换。本卡 SHA 先在线程里报出，并经独立审计放行后才执行（2026-11-03 的流程缺口：D07m 当时没有先送审）。切换前脚本用 SQLite 备份接口把账本原样复制一份留作证据（不用于恢复）。

起点：Run 的工位 `.auto-pm/worktrees/m3-d07n` 从最新 `origin/main` 建；控制根里的 `deployment_manifest.json` 比 `main` 多 16 条本机独有的中间发布条目（已记债），旧运行时要求“控制根里范围内的文件等于 Run 的工位起点”，所以脚本把控制根这份清单的字节在工位里经正常 Hook 提交一次（只此一个文件，不动 `main`），随后再开 Run；这个提交本身可审计，提交说明写明来由。

切换后核验（任一失败立即用同一脚本自动回退指针并停下，回切后写回执）：配置版本 = 实际加载版本 = `1.3.3-d563293`、从发布目录加载、无回落、**冲突列表必须为空（没有例外）**；`pm handoff`、`pm takeover`、`pm orient`、`continuity run reclaim`、`continuity lease record-holder`、`gui` 与新增的 `long-run` 入口能应答（冒烟）；`pm orient SW-2026-008 --json` 的冲突列表为空；本卡在新运行时下通过机器预检；全部注册项目对账 0/0/0；真实 pre-commit 钩子经新运行时退出 0；新版本读真实数据库副本时事件链无断点、Run 活动全部可读；新、现行、上一版三个发布逐文件校验通过。切换后另跑一次 `continuity backup` 与 `verify-backup`（0 条链断裂）。批准、决策、验收三处命令都带用户消息 id 作为 `--approval-evidence-ref`。
禁止：回滚或覆盖数据库（切换前的数据库副本只作证据）、改历史发布/事件/Checkpoint、改源码、合并 main、推送。脚本：`.auto-pm/reports/m3-d07n/d07n_deploy.sh`（`--check-only` 只读预检，可在任何时候运行）。
