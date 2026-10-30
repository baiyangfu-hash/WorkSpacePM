# 驾驶舱探测二轮 findings（trae, 20261030）

- 开始时间：2026-10-30 13:10 MST；结束时间：2026-10-30 13:26 MST
- 被测提交：main `17b5faf5`（`git rev-parse --short HEAD`，2026-10-30 拉取）
- 生效发布版：`active_release.json` → **1.3.3-d8f7c8b**（`main.py --resolve-only` 原文：`release verified via active_release.json: .../releases/1.3.3-d8f7c8b`）
- 关键前提：`main.py` 只运行发布快照；本次 main 的发布目录仍只有到 `1.3.3-d8f7c8b`，**任务要求的 `1.3.3-8d7d387` 在仓库里不存在**（`ls 00_Infrastructure/auto_pm/releases/` 无此目录），该版无法复测（记“未找到”）。
- 因此每条结论分两层记录：**部署层**＝`main.py` 实际执行的 1.3.3-d8f7c8b 快照；**源码层**＝main `17b5faf5` 里 SW-2026-008 项目的 `auto_pm`（`__version__ = "1.3.3"`，用 `PYTHONPATH=... -m auto_pm` 运行）。
- 操作对象：一次性假项目 `ZZ-2026-902`（源码层 `project create` 建在 `0100_项目/ZZ-2026-902_probe2_fake`）；未登记 Workspace Registry，未碰任何真实项目。
- 命令与退出码：`transcript/cmdlines.txt`（一行一条；准备阶段见 `transcript/prep.txt`）；复现见 `repro/`。

## 重测结论表（11 条）

| 编号 | 上轮问题 | 结论 | 证据（命令 → 退出码/原文） |
|------|----------|------|---------------------------|
| F7 | 脚手架生成 `PM_SESSION_*.md`，违反治理“已退役” | **仍成立**（源码层已复现） | 源码层 `project create --stack python --id ZZ-2026-902 ...` → exit 0，输出含 `create PM_SESSION_ZZ-2026-902.md`；部署层模板 `releases/1.3.3-d8f7c8b/templates/*/PM_SESSION_{{ project_id }}.md.jinja` 仍在 |
| F9 | `project create` 与 Workspace Registry 两本账 | **仍成立**（两层都复现） | 源码层 `pm resume ZZ-2026-902 --json` → `Error: 项目未登记到 Workspace Registry: ZZ-2026-902` exit 1；部署层同命令同原文 exit 1；`grep ZZ-2026-902 workspace_registry.json` → 0 处 |
| F10 | 相对路径存在却报不存在 | **部署层仍成立 / 源码层已失效** | 部署层 `context resolve --path 0100_项目/ZZ-2026-902_probe2_fake` → `Invalid value for '--path': Directory '...' does not exist.` exit 2；源码层同命令 → exit 1 `项目未登记到 Workspace Registry`（路径已解析成功，只是项目未登记） |
| F12 | 治理文档描述的 `pm orient/inbox/plan/approve/verify/accept/close/park/unpark/switch/missions` 在部署版不存在 | **部署层仍成立 / 源码层已失效** | 部署层 `main.py pm --help` → 只有 `context`、`resume`；源码层 `-m auto_pm pm --help` → 含 `orient inbox plan approve verify accept close park unpark switch missions handoff takeover approver-pin`（exit 0） |
| F15 | 同 work-id 换幂等键 → 裸 sqlite 栈 | **仍成立（部署层）** | `continuity work create --work-id W-P2-R2 ... --idempotency-key p2r-k2b --read-only` → `sqlite3.IntegrityError: UNIQUE constraint failed: work_items.work_id` exit 1；源码层无法测：假项目被注册门禁挡住（见下） |
| F16 | agent 身份可自批（无批准口令拦截） | **部署层仍成立 / 源码层无法判定** | `AUTO_PM_AGENT=trae:cn main.py change transition CHG-SCPT-2026-001 --to approved --approver probe-bot` → exit 0；随后 `decision create --approver probe-bot` → `✅ 决策包已成功创建并固化: DEC-20261030-FB2557E0` exit 0。源码层新增 `pm approve`/`approver-pin`，但 change/decision 面未变，本轮未构造 Mission 链验证 |
| F20 | Work scope `dir/**` 不匹配 owned 单文件 | **仍成立（部署层）** | `continuity run start --owned 0100_项目/ZZ-2026-902_probe2_fake/README.md`（Work scope `.../**`）→ `Error: owned_paths 超出 Work scope` exit 1；源码层无法测：write Work 需通过 `--card-file` 预检，read-only Work 又被注册门禁挡住 |
| F21 | 租约过期后无任何合法下一步（永久死锁） | **部署层仍成立 / 源码层命令面已修** | 60s 租约过期后：`lease renew` → `Error: lease 已过期` exit 1；`run transition --to SUCCEEDED` → `Error: lease 已过期` exit 1；`checkpoint create` → `Error: lease 已过期` exit 1；`continuity run --help` 仅 `start/transition`。源码层 `continuity run --help` 已含 `reclaim settle-expired fence-terminal-lease fence-legacy-terminal reconcile-terminal-lease revoke-unstarted`（未能在假项目完整执行，命令面证据） |
| F22 | 同一 Work 可并存两个 Run | **仍成立（部署层）** | `run start --run-id R-P2-R3 --work-id W-P2-R2 ...`（W-P2-R2 已有 R-P2-R2）→ exit 0，返回 `"state": "RUNNING"` |
| F24 | 文档写“start 后 transition --to RUNNING”，实际 start 已 RUNNING | **部署层仍成立 / 源码层无法判定** | `run start` 返回 `"state": "RUNNING"`（无 READY）；`run transition --to RUNNING` → `Error: 非法 Run 状态迁移: RUNNING -> RUNNING` exit 1；`--to VERIFYING` → exit 0。源码层 run start 新增 `--lease-wallet/--holder-pid`，状态机未验证 |
| F29 | 门禁强制 PM_SESSION ✓ vs 治理禁建 vs 模板生成 | **仍成立** | 源码层 `python check ZZ-2026-902` → 表内 `PM_SESSION 文件 ✓` exit 0；同项目由模板生成（F7）；`AGENTS.md` 与 `.trae/skills/cockpit-entry/SKILL.md` 明确“不改、不新建” |

## 本轮新增观察（不计入上轮 11 条）

| 观察 | 证据 | 说明 |
|------|------|------|
| 部署指针与 main 源码脱节，且 main 根源码比发布快照还旧 | `PYTHONPATH=00_Infrastructure/auto_pm -m auto_pm --version` → `1.2.4`，命令面无 `context/continuity`；SW-2026-008 项目源码 → `1.3.3`，`pm` 全命令 | `main.py` 永远跑发布快照；只看 main 源码会误判“已修” |
| 源码层 Work 创建新增项目存在性门禁（F14 在源码层已修） | `continuity work create --pid ZZ-2026-902 --read-only` → `Error: 项目未登记到 Workspace Registry: ZZ-2026-902` exit 1 | 但结合 F9，未登记的新项目仍无法进入 Work/Run，形成“必须先登记、又没有登记命令”的缺口（`context` 只有 `resolve`） |
| 源码层 write Work 需 `--card-file` 通过预检 | `continuity work create --help`：“required for write Work ... pass the pre-start precheck” | 无卡时只能用 `--read-only`，而 read-only 又被注册门禁挡住；探测面在源码层被前置门禁截断 |

## 补交上轮漏交项

- `repro/F23-*.md`、`repro/F26-*.md` 已补（见下）。
- F23 复核（两轮同结论）：部署层 `continuity work --help` → `authorize/create/relate/transition`，无 list/show；源码层增加 `adjudicate`，仍无只读查询 → **仍成立**。
- F26 复核：`ledger reconcile ZZ-2026-902` → `台账缺失 0 / 多余 0 / 状态不一致 0`，`✅ 对账无差异` exit 0；`change verify ZZ-2026-902 --ledger-check` → `✅ 门禁通过` exit 0；此时 continuity 已有 W-P2-R1/R2/R3、R-P2-R1/R2/R3 记录 → 两边互不感知，**仍成立**。

## 本轮统计

- 重测：11 条（F7、F9、F10、F12、F15、F16、F20、F21、F22、F24、F29）
- 结论：**仍成立 11 条**（其中 F10/F12/F21 属“部署层仍成立、源码层已修”；F16 源码层无法判定；其余部署层成立）；**已失效 0 条**；**无法判定**源码层 4 条（F15/F16/F20/F24 的源码行为）
- 漏交补齐：F23、F26 复现文件已补；本轮全部命令落 `transcript/cmdlines.log`
- 命令数：约 82 条（cmdlines.log 68 条 + 准备阶段 14 条）
- 未做：`1.3.3-8d7d387` 版复测（仓库无此发布目录）；源码层 Mission 全链（需登记真实项目，红线禁止）
