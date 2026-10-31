# 驾驶舱全流程演练 findings（trae / 2026-10-31）

- 开始：2026-10-31 11:18 MST；结束：2026-10-31 11:40 MST
- 被测提交：main `4c71830e`；发布版 `main.py --resolve-only` 原文 `release verified via active_release.json: /tmp/drill-ws/00_Infrastructure/auto_pm/releases/1.3.3-163c7a3`（沙箱内）
- 隔离方式：整仓复制到 `/tmp/drill-ws`（rsync 排除 `.venv/.git`，4.7s），在沙箱内 `git init` 建基线；所有写账本/登记表操作只在沙箱；宿主 `/workspace` 治理与台账未改。命令与退出码见 `transcript/cmdlines.txt`、`transcript/prep.txt`；复现见 `repro/`。
- 假项目：`SW-2026-991`（Python）、`SW-2026-992`（PLC），各由 `project create` 生成后 `project register` 登记。
- 进度：11:20 沙箱就绪/两项目建成；11:31 需求入箱→批准→开工；11:40 演练收尾（详见下）。

## 剧本完成度

| 步骤 | 状态 | 说明 |
|------|------|------|
| 1 新建 Python + PLC 假项目 | 完成 | 两个 `project create` exit 0（PLC 带 `--mode standard-project --plc-vendor Siemens --plc-model S7-1200`） |
| 2 登记 | 完成（有缺陷） | `project register` 命令存在；`ZZ-2026-904/905` 因业务线 ZZ 触发裸 pydantic 栈，且**一个坏项目会让所有项目登记失败**（D2） |
| 3 需求→计划→批准→开工 | 完成 | inbox add → confirm → plan（plan_hash `8d781a…`）→ approve（AUTHORIZED / work READY）→ confirm-start，全 exit 0 |
| 4 执行 | 完成 | Work `WORK-MSN-8D97B1057D90D45F`、Run `R-DRILL-1`（lease 3600s）、改 README、Checkpoint `CP-DRILL-1` 均 exit 0 |
| 5 租约 | 部分完成 | VERIFYING 下 `lease renew` 成功（需猜 `--expected-version`，D8）；过期 Run `R-DRILL-2` 用 `reclaim` 成功回收（提示时长不准，D9） |
| 6 验证与收口 | **卡住** | `pm verify` 连续三次失败（注册表脏、HEAD 变化、缺少 owned Python path）；Mission 无法进入验收；`pm accept` 报“尚未到达用户验收门”、`pm close` 报“该需求尚未验收”，**文档类需求形成死路**（D1）；`ledger reconcile` 通过 |
| 7 插急活 | 部分完成 | `park` 被拒两次（VERIFYING 不可搁置；Run 终结后 0 个未终结 Run 也不可搁置，D5）；`unpark` 报“没有搁着”；`switch` 只测了非法目标（“Mission 不存在”）；**成功搁置/切换未做** |
| 8 PLC 项目 | 完成 | `plc check SW-2026-992` → Pass=65 Warn=3 Fail=0 `ALL PASS`（WARN 为 Siemens 语言服务未安装） |
| 9 故意犯错 | 部分完成 | 错项目号→“项目未登记到 Workspace Registry”（人话）；工位内跑控制根入口→`managed candidate is execution-only` exit 2；“在工位里跑控制根 main.py”路径未被拦（D10）；重复 work-id 属已知 F15，未重复记 |
| 10 门禁 | 完成 | `doc check` 2/2 PASS；`plc check` 全过；`pm verify` 的质量门三次失败（原因分别记录） |

## 本轮新发现（已知 F7/F9/F15/F16/F20/N1–N3 不复记）

| 编号 | 严重度 | 现象 | 证据（命令 → 原文/退出码） | 用户会碰到吗 |
|------|--------|------|---------------------------|--------------|
| D1 | **P0** | 文档类改动（scope 只含 `.md`）能批准、开工、改文件、建检查点，但 `pm verify` 永远拒绝“缺少已批准的 owned Python path”，Mission 进不了验收；随后 `accept`/`close` 均拒，且 Run 在 VERIFYING 时 `park` 也被拒 → **整个任务无任何合法收尾路径**（只能手推终态，治理禁止） | `pm verify --mission-id MISSION-437F... --lease-wallet` → exit 1 `自动 Checkpoint generic profile 无法验证: Run 缺少已批准的 owned Python path`（并打印完整 traceback）；`pm accept` → exit 1 `当前 Mission 尚未到达用户验收门`；`pm close` → exit 1 `该需求尚未验收，不能收尾`；`pm park` → exit 1 `只有 RUNNING 或 BLOCKED 的 Run 可以搁着（当前 VERIFYING）` | 是。改 README/文档是最常见需求 |
| D2 | P1 | `project create` 接受 `ZZ` 业务线（并写入项目元数据），`project register` 时抛裸 `pydantic_core.ValidationError: business_line Input should be 'SW','DJ','ZD','XT','WX' or ''`；更糟：工作区里只要存在这一个项目，**登记其他合法项目也失败**；删掉它后立刻成功 | `project create --id ZZ-2026-904` exit 0 → `project register ZZ-2026-904` exit 1 裸栈；`project register SW-2026-991` 同样 exit 1；`rm -rf 0100_项目/ZZ-2026-904*` 后 `project register SW-2026-991` exit 0 | 是。编号前缀不在白名单时整条登记链路塌 |
| D3 | P1 | 立项后按流程登记（`project register` 写 `workspace_registry.json`）但没先提交，`pm verify` 直接失败，并把内部 traceback 打到终端 | `pm verify ...` → exit 1 裸栈 `EvidenceCollectionError: Run unstaged dirty path 超出 owned_paths: SYS-2026-001_WorkspaceGovernance/workspace_registry.json`，JSON `reason` 同文 | 是。“创建→登记→开卡”是标准顺序，登记表天然未提交 |
| D4 | P2 | Run 开始后若用户提交了代码（HEAD 变化），`pm verify` 报“Run git_head 与受管 worktree 当前 HEAD 不一致”（行为合理，但报错带 traceback，且文档未在开卡处提示“验证前不要提交”） | `git commit` 后 `pm verify` → exit 1 同类 traceback | 是。开发者习惯边写边提交 |
| D5 | P1 | `pm park` 前置条件是“恰好 1 个未终结 Run 且状态 RUNNING/BLOCKED”；VERIFYING 卡住不能搁置；把 Run 置 FAILED 后变成 0 个未终结 Run，仍不能搁置 → 卡无法交还钥匙 | `pm park` VERIFYING → exit 1 `只有 RUNNING 或 BLOCKED 的 Run 可以搁着（当前 VERIFYING）`；FAILED 后 → exit 1 `必须恰有 1 个未终结 Run 才能搁着（实际 0 个）` | 是。verify 卡住想临时停手时正好撞上 |
| D6 | P1 | 全新工作区直接入箱：`pm inbox add` 报 `Continuity Store 尚未初始化，拒绝创建收件箱表`；文档未说明要先跑一条 continuity 写命令建库（实测只能先 `continuity work create --read-only` 才初始化） | `pm inbox add ...`（参数齐全）→ exit 1 原文如上；先建只读 Work 后同命令 exit 0 | 是。新克隆第一次提需求就会撞 |
| D7 | P2 | `pm inbox add` 的 `--evidence`、`--alternative` 在 `--help` 里未标 required，缺一个就抛 pydantic 栈，且一次只报一个（要试两轮） | 第 1 次 exit 1 `1 validation error for TriageTicket evidence ... needs at least one unique evidence entry`；补 evidence 后 exit 1 `... needs at least one alternative` | 是 |
| D8 | P2 | `continuity lease renew` 必填 `--expected-version`，但没有任何命令/输出暴露当前版本；只能靠试 1/2/3（本次 1 成功） | `lease renew --expected-version 3` → exit 1 `lease version 冲突`；`2` 同；`1` → exit 0 | 是。LEASE 续租是常用动作 |
| D9 | P2 | `reclaim` 在宽限期内提示“约 68 秒后租约失效再试”，实际要再等约 145 秒才 ALLOW（宽限期比提示长约一倍） | 过期后第一次 `reclaim` → exit 1 `REFUSE_LIVE_LEASE / 请等...约 68 秒后...`；再等 75s 后同命令 → exit 0 `ALLOW` | 是。按提示重试会继续被拒 |
| D10 | P2 | 用控制根入口脚本但从隔离工位目录执行，驾驶舱照常工作（守卫按“入口脚本路径”判断，不看 cwd），用户会误以为自己在工位里操作、实际写的是控制根账本 | 在 `/tmp/drill-ws/.auto-pm/worktrees/drill-w1` 里跑 `/tmp/drill-ws/main.py pm orient ...` → exit 0；跑工位内的 `main.py` → exit 2 `managed candidate is execution-only` | 是（多 agent 工位场景） |
| D11 | P2 | `pm approve` 必须把 plan 的七栏全部重填一遍（否则报缺参），且缺参清单与 `pm plan` 的必填集不同（approve 要 objective…approved-model，却不要求 original-request/safety/check/rollback 的提示） | `pm approve --plan-hash ... --approver ...` → exit 1 `缺少必填参数: --objective, --acceptance, --scope, --risk, --non-goal, --adapter, --approved-model`；整套重填后 exit 0 | 是。批准是最常见动作，重复录入易错 |

## 走通/失败摘要

- 走通：新建（2 项目）→ 登记（合法前缀）→ 入箱 → 确认 → 计划 → 批准 → 开工 → Work/Run/Checkpoint → VERIFYING 续租 → 过期 reclaim → PLC 检查 → doc 门禁 → 台账对账 → 工位守卫（工位内入口）→ 错项目号/错目标卡/未验收收尾的拒绝。
- 卡住：**验收与收口（D1）**——文档类 scope 无法生成可验收检查点，后续 accept/close 全拒；插急活的成功路径（搁置/切换）因 D5 未走通。

## 未做

- 成功的 `park → switch → unpark` 全链（需要第二张卡且 D5 使当前卡无法搁置）——未做。
- 成功的 `accept → close`（被 D1 挡住）——未做。
- `pm handoff` / `pm takeover`、`continuity settle-expired` 全链——未做。
- PLC 项目的 `pm` 全流程（本轮只跑 `plc check`）——未做。

## 统计

- 剧本 10 步：完成 5（1/3/4/8/10）、部分完成 3（2/5/9）、卡住 1（6）、部分完成且成功路径未做 1（7）
- 新发现 11 条：P0 × 1（D1）、P1 × 4（D2/D3/D5/D6）、P2 × 6（D4/D7/D8/D9/D10/D11）
- 命令数：约 80 条（cmdlines.txt 65 条 + 准备/观察 15 条）
- 环境：Ubuntu 24.04 / Python 3.12.3 / Qt 库缺失（仅命令行）
