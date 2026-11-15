---
spec_id: "COMMANDS"
project_id: "SW-2026-008"
title: "auto-pm 命令总目录（脚本生成）"
---

# 命令总目录

> 本页由 `scripts/command_catalog.py` 生成，不要手改。
> 生成于提交 `68a6402fe4e9`。**本页可能落后**：之后改过命令或代码而没人重跑脚本，页上就是旧的；要最新的，运行 `python scripts/command_catalog.py --print`，以它的输出为准。
> 什么能用、什么不能用，看仓库根 `docs/功能清单.md`；本页只回答“有哪些命令、谁能跑、会不会写文件”。
> “谁能跑”“会不会写”取自 `scripts/cockpit_board/flow/commands_map.json` 的分类；“有没有记录”指 AGENTS.md、36 号操作手册、本项目 README 里有没有写到这条命令，生成时查的，只作参考。

## 驾驶舱命令（222 条）

| 命令 | 干什么 | 谁能跑 | 会不会写文件 | 有没有记录 |
|---|---|---|---|---|
| `change create` | 创建变更单（生成 CHG-*.md 文件并更新台帐） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `change edit` | 编辑变更单字段（支持 §4 基本字段 + §6 影响分析字符串字段） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `change list` | 列出项目变更单 | 任何人 | 不写 | 有 |
| `change show` | 查看变更单详情 | 任何人 | 不写 | 有 |
| `change transition` | 状态流转（更新变更单章节并持久化状态）；批准（approved）和有条件批准（conditionally_approved）在已启用批准口令时须用户本人在终端输入口令。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `change verify` | 变更单验证（CHG-108 缺陷 3：对账门禁） | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `claim add-paths` | 给自己的占位追加路径：领卡后发现还要改别的文件时用，不必放下重领（重领会重置领卡时间，已有提交就排到领卡之前）。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `claim list` | 只读：列出远程所有占位（已放下或租约到期（默认 4 小时，持有者 `claim renew` 续）的视为空闲，不会自动删）。 | 任何人 | 不写 | 没有 |
| `claim number` | 只领号：取下一个不会撞的卡号，不占任何路径（落卡文件时用；开工时再 `claim add-paths` 补路径）。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `claim open` | 领卡。CARD 写卡号，或写 auto 取下一个空号。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `claim reclaim` | 收回别人没动静的占位：推一个“已收回”提交（写明谁、为什么、依据哪句用户的话），不删分支，卡随即空闲。 | 只有用户本人 | 写 | 有 |
| `claim release` | 放下自己的占位：推一个提交把它标成已放下，不删分支（云端也能用）；PR 合并后或用户说放弃时用。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `claim renew` | 续租自己的占位：还在干活就续，把到期时间推到现在 + 4 小时；停了不续，到期自动算空闲。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `clean` | 一键清扫工作区游离日志、散装脚本及临时编译产物 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `constraint check` | 检查约束合规性 | 任何人 | 不写 | 没有 |
| `constraint guard` | 文件操作前登记哈希快照 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `constraint heal` | 自愈修复：剥离多余 BOM 等 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `constraint list` | 列出所有已加载的约束定义 | 任何人 | 不写 | 没有 |
| `constraint verify` | 文件操作后验证哈希一致性 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `context resolve` | 输出当前调用的只读项目上下文卡，不写入全局活动项目。 | 任何人 | 不写 | 没有 |
| `continuity backup` | Take an online, self-verified copy of .auto-pm/continuity.db; the live ledger is only read. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity checkpoint create` | Checkpoint current Git baseline and dirty paths from the Run worktree. | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `continuity dispatch prepare` | Allocate a local Run and emit only a desensitized PREPARED receipt. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity handoff accept` | Atomically transfer the Run lease to the named receiver. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity handoff create` | Create an immutable handoff.v2 from an active lease and checkpoint. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity lease extend-hold` | Raise one Run's total lease-hold cap (default 3 h). Only the user may do this. | 只有用户本人 | 写 | 没有 |
| `continuity lease record-holder` | Record the holder's long-lived process (for example a renewal loop) so that a later reclaim can prove it gone. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity lease renew` | Renew a lease held by the same owner and token. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity lease run-with-renewal` | Run one command (after --) and renew the Run's lease every third of its length until it exits. | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `continuity list-backups` | List the backups taken by ``continuity backup``, newest last. | 任何人 | 不写 | 没有 |
| `continuity mission create` | Create a DRAFT Mission from an explicit, validated authority envelope. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity mission show` | Read one persisted Mission without changing it. | 任何人 | 不写 | 没有 |
| `continuity mission transition` | Apply one legal Mission transition using optimistic locking. | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `continuity orchestration report-finding` | Route a typed internal finding without creating a hidden parallel queue. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity orchestration report-repair` | Record an adapter-observed repair attempt against the explicit A3 budget. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity recovery plan` | Print the exit chain of an abnormal state as a full command list. It only prints: nothing is run, nothing is written. | 任何人 | 不写 | 没有 |
| `continuity restore-backup` | Replace the live ledger with a verified backup; the replaced files are kept, never deleted. | 只有用户本人 | 写 | 没有 |
| `continuity run fence-legacy-terminal` | Invalidate one expired legacy terminal lease token without rewriting Run history. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity run fence-terminal-lease` | Fence one legacy terminal lease through an independently approved recovery Run. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity run legacy-terminal-evidence` | Print the read-only facts a Decision must bind before fencing a legacy terminal lease. | 任何人 | 不写 | 没有 |
| `continuity run reclaim` | Take over a started Run whose holder vanished: only after the lease expired (plus grace) and the holder's process is proven gone. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity run reconcile-terminal-lease` | Release a lease omitted by an exact legacy v2 terminal transition. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity run revoke-unstarted` | Revoke a live Run only when its durable record has no Popen evidence. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity run settle-expired` | Settle one abandoned Run through an explicit live recovery authority. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity run start` | Start a Run after independently observing Git HEAD and owned-path dirtiness. | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `continuity run transition` | Apply one legal Run state transition under an active lease. | 看板不放（钩子调用或规则禁止单独跑） | 写 | 有 |
| `continuity verify-backup` | Verify a backup file (or, without an argument, the live ledger): integrity and the whole event chain. | 任何人 | 不写 | 没有 |
| `continuity work adjudicate` | Forward-cancel one historical BLOCKED Work under an exact adjudication Decision. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity work adjudication-evidence` | Print the read-only facts a Decision must bind before adjudicating one BLOCKED Work. | 任何人 | 不写 | 没有 |
| `continuity work authorize` | Authorize PLANNED Work with a matching Decision package. | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `continuity work create` | Create one logical Work item; write Work remains PLANNED until authorized. | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `continuity work relate` | Create one typed relation between Work items. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `continuity work transition` | Apply one legal Work state transition. | 看板不放（钩子调用或规则禁止单独跑） | 写 | 有 |
| `decision create` | 从已批准的变更单创建结构化决策包（已启用批准口令时须用户本人在终端输入口令）。 | 只有用户本人 | 写 | 有 |
| `decision list` | 列出工作空间内的所有决策包。 | 任何人 | 不写 | 没有 |
| `decision show` | 查看指定决策包详情。 | 任何人 | 不写 | 没有 |
| `delivery archive clean` | 清理旧归档，保留最近 N 个。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `delivery archive list` | 列出归档版本及说明。 | 任何人 | 不写 | 没有 |
| `delivery build` | 构建交付物。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `delivery package` | 打包交付物为 ZIP。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `delivery status` | 查看当前交付物状态。 | 任何人 | 不写 | 没有 |
| `doc check` | 静态审计文档与代码的一致性及版本锁；带 --project 时改查该项目文档的相对链接死链 | 任何人 | 不写 | 有 |
| `doc inject` | 为历史 PLC 项目文档注入 AUTO_PM 自动区标记 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `doc refresh` | 根据工程资产刷新 PLC 文档中的自动区内容 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `doc sync` | 自动自省提取代码元数据并无损注入 Markdown 活文档 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `doctor` | 执行 auto-pm 环境与依赖健康诊断 | 任何人 | 不写 | 没有 |
| `dogfood inspect` | 读取稳定/候选状态和路径白名单，不执行候选代码。 | 任何人 | 不写 | 没有 |
| `dogfood prepare` | 从干净稳定树创建候选 worktree，不覆盖已有目录。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `dogfood review` | 从稳定控制面外部复核候选，候选不能生成自己的放行结论。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `gate judge` | 只读：按日志重新判一遍 OUT_DIR 里的那一轮（不重新生成任何文件）。 | 任何人 | 不写 | 没有 |
| `gate plan` | 只读：列出每组的命令和工作目录。 | 任何人 | 不写 | 没有 |
| `gate precheck` | 只读：推送前一条命令跑 ruff + mypy(win32) + 与改动相关的 pytest；不写账本、不写工作树。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `gate run` | 依次跑各组；测试子进程只拿白名单环境变量，AUTO_PM_* 一律不传。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `git-hook commit-msg` | 执行 commit-msg 生产代码关联单据强校验。 | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `git-hook install` | 安装/激活工作区 Git 物理门禁钩子 (.git/hooks/pre-commit 与 commit-msg)。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `git-hook pre-commit` | 执行 pre-commit 台账一致性校验。 | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `git-hook preflight` | 以同一个不可变暂存快照执行提交前只读预检。 | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `git-hook release-gate` | 执行发布前全局台账一致性校验。 | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `gui` | 启动 GUI 桌面应用；默认入口只读取项目与连续性证据。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `handoff claim` | 领取一个待执行 handoff；manual 只表示可领取，不代表启动 IDE。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff close` | 由 PM 消费一个交接包并原子写入 consumed 状态。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff create` | 创建交接请求，默认状态为 pending。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff fail` | 由租约持有者报告执行失败，保留请求供 PM 处理。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff failures` | 查看 handoff Saga 的失败与重试证据。 | 任何人 | 不写 | 没有 |
| `handoff heartbeat` | 续租执行 handoff，防止工作队列将其判定为失联。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff list` | 列出交接请求；不指定状态时显示全部有效记录。 | 任何人 | 不写 | 没有 |
| `handoff preflight` | 只做 PM 收口预检，不改变 handoff 或项目台账。 | 任何人 | 不写 | 没有 |
| `handoff queue` | 查看 handoff 工作队列快照；此命令只读，不改变交接状态。 | 任何人 | 不写 | 没有 |
| `handoff requeue` | 由 PM 显式将失联或失败请求重新置为待领取。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff result-submit` | 提交执行回执；成功后仅 PM 可调用 close 消费结果。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff saga compensate` | 补偿回滚已失败或需撤销的 Saga 事务，恢复所有修改文件。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff saga resume` | 从断点恢复并继续执行未完成的 Saga 步骤。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff saga status` | 查看 handoff PM 收口 Saga 事务状态与检查点。 | 任何人 | 不写 | 没有 |
| `handoff show` | 查看一个 handoff 请求或已消费回执。 | 任何人 | 不写 | 没有 |
| `handoff start` | 将已领取 handoff 标记为执行中。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `handoff timeout` | 将租约到期的 claimed/in_progress 请求显式标记为 expired。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `implementation-card approve` | Attach external user approval to an already reviewed card (the user's PIN once one is committed, gap 9). | 只有用户本人 | 写 | 没有 |
| `implementation-card by-change` | List the implementation cards hanging under one change order and their states (read-only). | 任何人 | 不写 | 没有 |
| `implementation-card create` | Create JSON and Markdown review artifacts with explicit TODO fields. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `implementation-card dispatch` | Emit the checked execution package; do not launch an executor. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `implementation-card precheck` | Card 027 §5.3: commands, paths and baseline; new-format cards also basis and change order. | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `implementation-card validate` | Validate without changing the card, governance store, or repository. | 任何人 | 不写 | 没有 |
| `implementation-card verify` | Validate current-byte terminal evidence; no merge or deployment. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `ledger reconcile` | 对账：扫描项目 CHG 文件 vs 版本变更台账记录 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `long-run start` | 先内存预检，再脱离终端启动命令和内存守卫。命令写在 -- 后面。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `long-run status` | 只读：看任务进行到哪、退出码、守卫采样数和峰值已提交内存。 | 任何人 | 不写 | 没有 |
| `long-run stop` | 结束一个在跑的任务：恢复暂停、杀掉整棵进程树，状态记为 STOPPED。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `plc check` | 检查项目结构是否符合 LSP-907 规范，并运行 Siemens 语言服务（插件命令行）；有失败项时退出码为 1。 | 任何人 | 不写；带 `--fix` 时写 | 有 |
| `plc docs check` | 核对接口文档/变量定义文档与 SCL 代码（名称、类型、方向、注释），并检查里程碑表的计划日期 | 任何人 | 不写 | 没有 |
| `plc docs confirm` | 去掉已与代码对上的行上的“待确认”标记；仍与代码不一致的行保持标记。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `plc docs plan` | 按项目周期规范推里程碑计划日期。默认只显示；加 --write 才写，且只填空着的计划日期。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `plc docs sync` | 按 SCL 代码补全接口文档与变量定义文档（只写文档，从不写 SCL；补入的行带“待确认”标记）。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `plc ingest` | 工业源工程全量逆向摄取与资产灌入 (AutoShop / TIA Portal) | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `plc init` | 创建 PLC 项目骨架（调用 Copier 模板） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `plc promote` | 将 .ingest_staging 暂存区中审核通过的草案正式投影到工程资产与文档 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `plc repair` | 自动修复项目结构问题 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `plc standardize` | 检测并修正 PRD 文档命名 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `pm accept` | 记录最终用户验收；已启用批准口令时须用户本人在终端输入口令。关闭动作仍受治理门禁约束。 | 只有用户本人 | 写 | 有 |
| `pm acceptance-scan` | 只读：列出这个项目进行中的任务里，``pm verify`` 会拒绝执行的已批准验收命令（发版前在账本所在电脑上跑）。 | 任何人 | 不写 | 没有 |
| `pm approve` | 批准新需求并内部形成授权链，或兼容已有 Mission 调用。 | 只有用户本人 | 写 | 有 |
| `pm approver-pin init` | 只限用户本人：设置或更换批准口令。写入登记文件后要提交（git commit）才生效。 | 只有用户本人 | 写 | 没有 |
| `pm approver-pin status` | 只读：批准口令是否已生效（以 Git 已提交的登记文件为准）。 | 任何人 | 不写 | 没有 |
| `pm close` | 一步收口：与驾驶舱“确认验收/重试同步”同一个 close_accepted；只收用户已验收的 Mission。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `pm confirm-start` | 执行用户的唯一开工确认；内部授权编号不会暴露给用户。 | 只有用户本人 | 写 | 有 |
| `pm context` | 兼容入口；请迁移到 `context resolve`。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm control-root-status` | 只读：控制根在哪个分支、有哪些未提交文件及属主、与 origin/main 差多少（D-44、D-13）。 | 任何人 | 不写 | 没有 |
| `pm drafts` | 列出项目的全部规划草稿（含驾驶舱保存的草稿）及其范围卡阶段。 | 任何人 | 不写 | 没有 |
| `pm execute` | 从完整批准卡冷启动并在前台阻塞执行唯一 local Saga。 | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `pm handoff` | 当前持有者一条命令交接：记检查点并生成发给接手方的 handoff；交接后请停止写入。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm inbox add` | 把一条新事项连同分诊单记入收件箱（状态 PROPOSED，等待用户确认）。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm inbox confirm` | 记录用户对该分诊单的确认（须引用 user-confirmation 证据）。 | 只有用户本人 | 写 | 没有 |
| `pm inbox list` | 列出项目的收件箱条目。 | 任何人 | 不写 | 没有 |
| `pm inbox reject` | 记录用户对该分诊单的驳回（须引用 user-confirmation 证据）。 | 只有用户本人 | 写 | 没有 |
| `pm inbox show` | 显示一条收件箱条目的完整分诊单与 ticket_hash。 | 任何人 | 不写 | 没有 |
| `pm missions` | 只读：这个项目开着哪些卡，按“在干 / 等你 / 搁着 / 已关”四栏列出。 | 任何人 | 不写 | 有 |
| `pm orient` | 只读定位：与 resume 共用同一份版本化查询，并可询问某个动作的能力。 | 任何人 | 不写 | 有 |
| `pm park` | 把手上这张卡记好断点放下：交出钥匙，之后谁也不能写，直到用户让人用 pm unpark 拿回来。 | 只有用户本人 | 写 | 有 |
| `pm pending` | 列出项目中等待批准的最新范围卡。 | 任何人 | 不写 | 没有 |
| `pm plan` | 创建/恢复并持久化新需求范围卡，或兼容已有 Mission 调用。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm recover` | 主控重启后，核对执行进程还在不在，并用大白话写出现在的情况和下一步。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm recover-status` | 只读：对账已启动的执行进程，输出 ALIVE / DEAD / PID_REUSED / UNKNOWN。 | 任何人 | 不写 | 没有 |
| `pm resume` | 编译新会话必须先消费的权威连续性上下文。 | 任何人 | 不写 | 有 |
| `pm retire` | 把陈年残留的 Work（及其根 Mission）、没有 Work 的草稿卡、孤卡正式取消；默认只预演。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm sign-risk` | 只限用户本人：在自己的交互式终端里签署“接受风险”，允许在无法判断原持有者进程时回收 Run。agent 会话一律拒绝。 | 只有用户本人 | 写 | 有 |
| `pm state-backup pull` | Bring a backup home (verified); prints the restore command and never replaces the live ledger. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm state-backup push` | Take a sanitised copy of the ledger and push it to the private repository. | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm state-backup status` | Show when the last off-site backup was pushed from this computer (reads a local file only). | 任何人 | 不写 | 没有 |
| `pm switch` | 插急活一步完成：把在干的卡搁着，再把目标卡拿起来；第二步失败时第一张稳稳停在“搁着”。 | 只有用户本人 | 写 | 有 |
| `pm takeover` | 接手方先只读定位，再接手：自己生成口令存入本机钱包，旧持有者的口令随即失效。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm triage` | 只读：开着的卡 + 收件箱按建议顺序排好，每条写明下一步；不确认、不转计划、不切焦点。 | 任何人 | 不写 | 没有 |
| `pm unpark` | 凭断点把搁着的卡拿回来：先核对工作树没被动过，再发新钥匙（存本机钱包，不显示）。 | 只有用户本人 | 写 | 有 |
| `pm verify` | 质量验证：对最新 VERIFYING 的 Run 生成系统证据检查点，通过后进入“等待用户验收”。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `pm workflow` | 保留历史名称的可发现性，不加载已隔离的旧技能。 | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `pm-session archive` | 归档指定章节的早期内容到归档文件 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pm-session check` | 检查 PM_SESSION 文件健康状态 | 任何人 | 不写 | 没有 |
| `pm-session view` | 从 PM_SESSION 生成只读视图 | 任何人 | 不写；带 `--output`、`-o` 时写 | 没有 |
| `pr open` | 为 AGENT 的工位 <前缀><CARD> 推送分支并开 PR（只开不合） | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `pr ready` | 合并前放行检查（只读）：审计报告、必过检查、safety-zone、安全签字；缺一条退出 1，不合并 | 任何人 | 不写 | 没有 |
| `pr settle-scan` | 合并后的收口清单（只读）：列出工作已并入主线、Run/Mission/变更单还开着的卡和各自合法的下一条命令；不转任何状态 | 任何人 | 不写 | 没有 |
| `project archive` | 把项目归档（CHG-SCPT-2026-652）：只把登记表里的项目状态改成“已归档”，目录不搬，编号和路径不变。 | 只有用户本人 | 写 | 没有 |
| `project create` | 创建新项目（调用 Copier 模板生成骨架） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `project delete` | 删除项目（破坏性操作）：只听用户本人，开着任务或有未提交改动时拒绝，目录先搬进回收区可搬回。 | 只有用户本人 | 写 | 有 |
| `project edit` | 编辑项目元数据（写入 .copier-answers.yml） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `project hooks install` | 为已有项目安装 Git Pre-commit 提交门禁与自愈钩子 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `project hooks status` | 查看项目 Git Pre-commit 提交门禁的安装状态 | 任何人 | 不写 | 没有 |
| `project hooks uninstall` | 为已有项目卸载 Git Pre-commit 提交门禁钩子 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `project import` | 导入外部项目目录：落点和 project create 同一个函数（PLC 进 0100_PLC自动化，其余进 Python 在研目录） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `project list` | 列出工作空间内的项目；性质、状态读登记表（CHG-SCPT-2026-650），没登记的项目两栏显示“未登记” | 任何人 | 不写 | 有 |
| `project reactivate` | 把“已归档”的项目改回“在研”（CHG-SCPT-2026-652）：默认只预演；--confirm 只听用户本人。 | 只有用户本人 | 写 | 没有 |
| `project recycle-list` | 只读：列出回收区里被删掉的项目目录和搬进来多久了；不删、不搬、不改任何文件（TD-208）。 | 任何人 | 不写 | 没有 |
| `project register` | 把已有项目登记到工作区登记表（登记后 pm orient、批准、驾驶舱才认识它） | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `project restore` | 把回收区里的项目目录搬回原处（CHG-SCPT-2026-650）：默认只预演；--apply 只听用户本人，和 project delete 同一口径。 | 只有用户本人 | 写 | 没有 |
| `project retrofit` | 为已有项目补全元数据文件（.copier-answers.yml 及 PLC 标志文件） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `project show` | 查看项目详情 | 任何人 | 不写 | 有 |
| `project snapshot` | 刷新 PM_SESSION 的 Spec Snapshot 版本号（对齐 spec_registry.json） | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `prototype archive` | 快照归档当前原型 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `prototype bundle` | 合并打包 HTML/CSS/JS 原型为单文件离线发布包 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `prototype check` | 校验原型完整性、BOM 及 PLC 变量映射 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `prototype init` | 初始化全新的原型脚手架骨架 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `python check` | 检查 Python 项目规范（210/211/220） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `python init` | 创建 Python 项目骨架（调用 Copier python-tool 模板） | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `python repair` | 修复 Python 项目规范问题 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `release deploy` | 部署前预检；加 --no-check-only 才真部署：预检全绿 → 建账 → 构建 → 切换 → 自检 → 失败自动回退，成功才收口并写回执。 | 只有用户本人 | 写 | 没有 |
| `release rollback` | 用切换前的指针备份把有效版本退回去：先核对备份校验和，只还原指针，不动数据库、不回滚已装发布。 | 只有用户本人 | 写 | 没有 |
| `release status` | 配置的有效版本与上一版、已装发布、发布记录是否互相一致、最近一次部署回执。 | 任何人 | 不写 | 没有 |
| `release trial` | 把生效发布拷一份到工作区外的临时目录，用来复现问题；不动 releases/、不写账本，副本用完请自行删除（D-05）。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `role check` | 检查角色包：文件齐全、角色号合法、规范编号存在、指针不死链、与旧技能逐字一致 | 任何人 | 不写 | 没有 |
| `role list` | 列出驾驶舱里的角色包 | 任何人 | 不写 | 没有 |
| `spec check` | 运行规范健康检查（SHC-001~010）；--fix 会改写规范库文件 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `spec frontmatter` | 检查/同步规范 frontmatter | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `spec index` | 生成规范索引文件（会改写规范库里的索引文件） | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `spec lint` | 规范注册表专项 lint 检查（5条注册表级规则） | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `spec report` | 生成规范元数据汇总报告 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `spec sync` | 一键全量同步与重构 Obsidian 全局规范仓库 (DEV-030 V2.2.0) | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `template list` | 列出可用模板 | 任何人 | 不写 | 没有 |
| `template update` | 对已有项目执行 Copier 模板增量更新 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `vartable batch-parse` | 批量解析目录下多个变量表文件。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `vartable convert` | 解析变量表文件并导出为 CSV/YAML/JSON。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `vartable detect-encoding` | 检测文件编码。 | 任何人 | 不写 | 没有 |
| `vartable detect-format` | 识别文件格式。 | 任何人 | 不写 | 没有 |
| `vartable list-encodings` | 列出支持的编码列表 | 任何人 | 不写 | 没有 |
| `vartable list-formats` | 列出支持的解析格式。 | 任何人 | 不写 | 没有 |
| `vartable parse` | 解析变量表文件，输出条目详情。 | 任何人 | 不写 | 没有 |
| `workflow accept` | 记录最终用户验收；已启用批准口令时须用户本人在终端输入口令。关闭动作仍受治理门禁约束。 | 只有用户本人 | 写 | 没有 |
| `workflow approve` | 批准新需求并内部形成授权链，或兼容已有 Mission 调用。 | 只有用户本人 | 写 | 没有 |
| `workflow confirm-start` | 执行用户的唯一开工确认；内部授权编号不会暴露给用户。 | 只有用户本人 | 写 | 没有 |
| `workflow context` | 兼容入口；请迁移到 `context resolve`。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `workflow execute` | 从完整批准卡冷启动并在前台阻塞执行唯一 local Saga。 | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `workflow history` | 查看工作流执行历史 | 任何人 | 不写 | 没有 |
| `workflow list` | 列出所有可用的工作流定义 | 任何人 | 不写 | 没有 |
| `workflow plan` | 创建/恢复并持久化新需求范围卡，或兼容已有 Mission 调用。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `workflow resume` | 编译新会话必须先消费的权威连续性上下文。 | 任何人 | 不写 | 没有 |
| `workflow run` | 运行指定工作流 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `workflow status` | 查看指定工作流运行详情 | 任何人 | 不写 | 没有 |
| `worktree close` | 收 AGENT 的工位：无未提交改动、提交都已推送才删；已并进 main 的再删本地分支 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `worktree heartbeat` | 刷新本对话工位的心跳（给 Claude Code 的 Stop / PreToolUse 钩子调用；没有本对话的工位就什么都不做） | 看板不放（钩子调用或规则禁止单独跑） | 写 | 没有 |
| `worktree list` | 列出 .auto-pm/worktrees 下每个工位；默认只列名字、分支、路径，加 --deep 才逐个检查 | 任何人 | 不写 | 有 |
| `worktree open` | 为 AGENT 开工位，分支 <前缀><CARD>，从最新 origin/main 起 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `worktree reclaim` | 快捷回收：列出（加 --apply 则回收）持有对话已不在的会话别名工位；回收前一样先存救援引用，分支保留 | agent 可跑（看板经白名单按钮、先预览） | 写 | 有 |
| `worktree release` | 回收一个会话别名工位（对话结束时用）：先把未提交和未跟踪的内容存成救援引用，再收目录；分支保留 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |
| `worktree sweep` | 清理已并进 main 的工位、名册外已并进 main 且干净的目录、远程已删的本地分支、已结束 Run 的 run-plan-* 残留；默认只列 | 任何人 | 不写；带 `--apply` 时写 | 有 |
| `worktree who` | 只读：本机控制根上现在有哪些会话在场（来源、所在位置、多久没动静、疑似孤儿）。 | agent 可跑（看板经白名单按钮、先预览） | 写 | 没有 |

## scripts 下的独立脚本（15 个）

| 脚本 | 干什么 |
|---|---|
| `scripts/build_delivery.py` | 统一交付物构建脚本 (build_delivery.py) |
| `scripts/command_catalog.py` | 生成《命令总目录》和《报警代码表》两页（WBS 8.11）。 |
| `scripts/figure_consistency_check.py` | 图与文档一致性检查（WBS M3-FIG）：Mermaid 图能否解析，图里的信号在接口表、变量表里是否都有。 |
| `scripts/gate_timeout_drill.py` | 质量门超时演练（TD-SW008-188 / 189 在 Windows 上的实测脚本，Linux 上也能跑）。 |
| `scripts/github_collector.py` | 总控屏的 GitHub 采集（只读）——数据层，和 pm_dashboard.py 并列；cockpit_board 包本身不碰网络。 |
| `scripts/gui_smoke_test.py` | GUI 冒烟测试 - 全页面及 DJ-2026-005 深度截图 + 控制台警告收集 |
| `scripts/long_gate.py` | 长门禁主机：把一轮长门禁（九组回归等）交给一个与 AI 会话无关的独立进程 |
| `scripts/long_gate_drill.py` | 长门禁主机的“中途杀会话”演练（Windows 上可复现 10-23 的故障，并证明新做法躲得开） |
| `scripts/memory_gate.py` | 内存总闸看门狗：整机已提交内存到冻结线（默认 = 本机提交上限 x 0.80，31.3 GiB 内存的笔记本约 50 GiB）就冻结涨得最快的一棵进程树（只暂停，绝不杀），回落到解冻线（默认 x 0.75）以下再解冻。 |
| `scripts/pm_dashboard.py` | 多项目安灯板（只读原型）- 从账本和项目文件夹读数据，生成一张 HTML 看板 |
| `scripts/pm_dashboard_gui.py` | 驾驶舱总控屏入口（PySide6）。 |
| `scripts/pmf_build.py` | PMF 可复现构建入口（WBS D02）。 |
| `scripts/release_selfcheck_dryrun.py` | D-146 card 6a: read-only dry run of the release self-check set against a real control root. |
| `scripts/run_tests.py` | 统一测试运行脚本 |
| `scripts/sample_drill.py` | 样件联调：一条命令跑完整条收口线（发版前门槛）。 |
