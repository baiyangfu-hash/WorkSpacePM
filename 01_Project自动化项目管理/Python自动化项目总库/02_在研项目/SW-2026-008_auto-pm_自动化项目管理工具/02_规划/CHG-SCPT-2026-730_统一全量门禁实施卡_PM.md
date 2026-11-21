# CHG-SCPT-2026-730 驾驶舱统一全量门禁实施卡

- 项目：SW-2026-008
- 基线：`ab83409f697e3c45962980e7a385dfdc5c555e03`
- 开工批准：`user-confirmation:01a1fc00-1d7c-7331-86bf-4afe745dddb0`
- 范围：全量门禁 CLI、持久任务账本、GitHub Actions / Windows 计划任务执行、门禁证据消费及对应验收。GUI 不在本卡范围。
- 根因：原有全量检查由调用它的 agent 线程管理，退出后无法可靠交接。Trae 进程内存持续上涨已观察到，分配源尚未核实。检查入口涉及 `gate run`、扩展到全量的 `gate precheck`、`long-run`、`long_gate.py`、`gate-full` 以及 `pm_merge.py` 的合并检查。
- 验收：不同 agent 用同一任务号查状态和停止。派发不确定时保留原执行。离线切换要求用户确认与本机依赖预检。完整门禁凭证绑定候选、树、基线、清单和规则。正式全量运行前先做跨会话轻量探针。

## 操作入口

1. 在控制根用 `main.py gate start --worktree <工位>` 登记整轮。云端需要候选分支已推送、`gh` 已登录，以及 `main` 上已有支持任务号的工作流。
2. 记录任务号。任一 agent 都可以跑 `main.py gate status <任务号>`，或用 `--worktree <工位>` 按当前候选查。需要停止时跑 `main.py gate stop <任务号>`，重复查询直至执行端确认停止。
3. 云端不可用或已停时，经用户确认后运行 `main.py gate retry <任务号> --worktree <工位> --local --approval-evidence-ref user-confirmation:<消息编号> --siemens-lsp <路径>`。本机需要 Windows 登录会话、锁定版本的 Python/Go/Siemens LSP。派发未知先对账。
4. 本机合并从控制根核对当前候选凭证。基线变化时重新登记；同树合并只有在云端能核对合并第一父提交和原始结果时才复用。
5. 本卡增加 `scripts/cockpit_board/flow/commands_map.json` 的四条登记，已获用户批准。不涉及 GUI 修复。

## 首次上线

730 自身用已生效的收口路线核验，合并前仍需要候选全量结果、独立审计和受保护路径批准。合并后 GitHub 的 `main` 才提供任务号派发，控制根经用户批准启用包含新命令的发布后才接受托管凭证。上线期间的新脚本在缺少凭证时拒绝合并。已落账的任务证据保留在 `.auto-pm/reports/gate-tasks/`，不随工位或 agent 会话清理。

## 首轮云端红项

GitHub 运行 44862271233 的判决为 FAIL。11 组中 cli、infrastructure 和 rest 共 8 个失败，Siemens 插件通过。根因是新增写账查询漏接运行身份守卫，四条 CLI 只登记了看板分类，还缺命令互锁矩阵登记；执行器与 CLI 的组装方向越层，离线 Go 未使用统一的可执行文件解析，插件环境变量未进入 README。计划任务新加了开步前指纹复核，旧测试只覆盖原三个位置；手工入口内存不足时应继续在解析配置前拒绝。

已批准将命令矩阵的四条登记和 README 的离线插件变量纳入 730。修正后先复核这 8 项及相邻测试。
