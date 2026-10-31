# 驾驶舱补测（部署层 / 新版 1.3.3-163c7a3）findings

- 开始时间：2026-10-31 10:51 MST；结束时间：2026-10-31 11:12 MST
- 被测提交：main `bf22a621`（含 #392 合并提交 `fac06bf6`）
- 发布版本：`main.py --resolve-only` 原文 `launcher: release verified via active_release.json: /workspace/00_Infrastructure/auto_pm/releases/1.3.3-163c7a3`（exit 0）
- 探测方式：全部走部署层 `main.py`（启动器校验发布指针）。continuity 类命令需要已登记项目，而假项目不能登记（登记会改治理 JSON，红线禁止），故在隔离沙箱工作区 `/tmp/probe4-ws`（复制假项目 + 自建最小 registry）里用**同一份发布代码**（`PYTHONPATH=releases/1.3.3-163c7a3 python -m auto_pm -w /tmp/probe4-ws`）执行，宿主仓库 `/workspace` 的治理文件与台账未改；沙箱已删除。
- 操作对象：一次性假项目 `ZZ-2026-903`，未登记到宿主 Workspace Registry，未碰任何真实项目。
- 命令与退出码：`transcript/cmdlines.txt`（38 条）+ `transcript/prep.txt`；复现见 `repro/`。

## 重测结论（8 条）

| 编号 | 上轮问题 | 结论 | 证据（命令 → 退出码/原文） |
|------|----------|------|---------------------------|
| F10 | 相对路径存在却报“不存在” | **已失效** | `main.py context resolve --path 0100_项目/ZZ-2026-903_probe4_fake`（cwd=/workspace）→ exit 1 `项目未登记到 Workspace Registry: ZZ-2026-903`（路径已解析成功，只剩登记问题）；绝对路径同 exit 1 |
| F12 | `pm orient/inbox/plan/...` 在部署版不存在 | **已失效** | `main.py pm --help` → exit 0，列出 `accept approve approver-pin close confirm-start context drafts execute handoff inbox missions`（另含 `orient/plan/park/switch/unpark/verify` 等）；沙箱内 `pm orient ZZ-2026-903 --json` → exit 0，返回四栏与 `next_legal_action` |
| F15 | 同 work-id 换幂等键 → 裸 sqlite 栈 | **仍成立** | 沙箱：`continuity work create --work-id W-P4-1 ... --idempotency-key p4-k1b --read-only`（W-P4-1 已存在、键不同）→ exit 1，`sqlite3.IntegrityError: UNIQUE constraint failed: work_items.work_id`，栈帧直出 |
| F16 | agent 身份可自批 | **仍成立** | `AUTO_PM_AGENT=trae:cn` 下 `change transition CHG-SCPT-2026-001 --to approved --approver probe-bot` → exit 0；`decision create --approver probe-bot` → exit 0（审批结论 approved）。`approver-pin` 只约束 `pm approve/pm accept`，change/decision 面无拦截 |
| F20 | Work scope `dir/**` 不匹配 owned 单文件 | **仍成立** | 沙箱：Work `W-P4-2` scope `0100_项目/ZZ-2026-903_probe4_fake/**`，`run start --owned 0100_项目/ZZ-2026-903_probe4_fake/README.md --declared-dirty 同路径` → exit 1 `Error: owned_paths 超出 Work scope` |
| F21 | 租约过期后永久死锁 | **已失效（reclaim 可用）** | 60s 租约、过期后 `run transition --to SUCCEEDED` → exit 1 `Error: lease 已过期`（仍拒）；`run reclaim --claimant probe-bot-2 --reason ...` → 过期+宽限期内 exit 1 `REFUSE_LIVE_LEASE 租约仍有效（含宽限期）`；再等约 70s 后同命令 → **exit 0 `decision: ALLOW`（process_verdict: PROVEN_DEAD）**；回收后 `run transition --to SUCCEEDED --owner probe-bot-2 --lease-wallet` → exit 0，Run 收口成功 |
| F22 | 同一 Work 可并存两个 Run | **已失效** | 沙箱：W-P4-1 已有非终态 Run R-P4-2，`run start --run-id R-P4-3 ...` → exit 1 `Work 已有非终态 Run：Run R-P4-2 正由 probe-bot 持有，租约到 ...；请等对方交接（pm handoff），或租约过期后再回收（continuity run reclaim）` |
| F24 | 文档“start 后 transition --to RUNNING”必报非法迁移 | **已失效** | `run start --run-id R-P4-2 ...` → exit 0（状态 READY）；随后 `run transition --to RUNNING` → exit 0（version 2）；`--to VERIFYING` → exit 0 |

计数：**已失效 5 条**（F10、F12、F21、F22、F24），**仍成立 3 条**（F15、F16、F20），**无法判定 0 条**。上一轮“源码层已修”的 F10、F12、F21 在部署层已同样修好，三条全部核实。

## 本轮额外发现（新，非上轮 8 条）

| 编号 | 严重度 | 现象 | 证据 |
|------|--------|------|------|
| N1 | P1 | `project create --dest-dir` 用**相对路径**时，项目被写进发布快照目录 `releases/1.3.3-163c7a3/0100_项目/`，并使启动器判定 active 发布“存在未登记目录”而退回上一版 `1.3.3-8d7d387`（旧版缺少新功能） | `project create --stack python --id ZZ-2026-903 --name probe4_fake --dest-dir 0100_项目` → exit 0，输出路径 `/workspace/00_Infrastructure/auto_pm/releases/1.3.3-163c7a3/0100_项目/ZZ-2026-903_probe4_fake`；下一次命令启动器原文：`警告：当前版本（active）没通过校验，已改用上一版本（previous）启动。原因：[active_release.json] release 存在未登记目录: 0100_项目。`（已删除该目录并用 `--purge-bytecode` 清理后 `--resolve-only` 恢复 1.3.3-163c7a3） |
| N2 | P2 | `reclaim` 在租约已过期但未过宽限期时提示“租约仍有效（含宽限期）”，与实际上已过期的事实表述不符（同一 JSON 里 `lease_expires_at` 早于当前时间） | `run reclaim` 过期后 68s → exit 1 `decision: REFUSE_LIVE_LEASE / reason: 租约仍有效（含宽限期）`，而 `lease_expires_at` 为 `18:06:36Z`，当次执行约 `18:07:2xZ` |
| N3 | P2 | 用 `python -m auto_pm`（不带 -B）跑发布代码会在发布目录生成 `__pycache__`；启动器事后扫描出 30 处并告警（载荷完好、不退回） | `continuity run reclaim --help` → 启动器原文：`发布 1.3.3-163c7a3 里有 30 处 Python 缓存 ... 清除方法：python -B .../launch.py --purge-bytecode`；已按提示清理并复查通过 |

补充观察（不计编号）：
- F7 在新版仍成立：新建假项目目录内仍生成 `PM_SESSION_ZZ-2026-903.md`。
- F9 在新版仍成立：`project create` 后 `grep ZZ-2026-903 workspace_registry.json` → 0 处；`pm resume ZZ-2026-903 --json` → exit 1 `项目未登记到 Workspace Registry`。这也是本轮 continuity 测试必须借沙箱工作区的原因。
- F21 的 `settle-expired`（需回收 Run + Decision）本轮未测，只验证了 `reclaim` 路径。

## 未做

- `pm approve` / `pm accept` 的批准口令拦截（须用户本人操作，红线禁止代做）——未做。
- `continuity run settle-expired` 全链（需先建回收 Run 与 Decision，本轮只测 reclaim）——未做。
- 真实项目上的任何操作——红线禁止，未做。

## 统计

- 重测 8 条：仍成立 3（F15/F16/F20）、已失效 5（F10/F12/F21/F22/F24）、无法判定 0
- 额外新发现 3 条（N1 P1、N2 P2、N3 P2）
- 命令数：约 52 条（cmdlines.txt 38 条，其中 3 条为 shell 变量分词失败的 harness 记录 exit=127；prep.txt 14 条）
- 环境：Ubuntu 24.04 沙箱 / Python 3.12.3 / 依赖按锁定文件安装（Qt 运行库缺失，仅命令行）
