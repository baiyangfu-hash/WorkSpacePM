# “决定”页：按钮 ↔ 命令对照表

> 单一真源是 `decisions.py` 里的 `DECISIONS`。本表给人和 Trae 读；`tests/core/test_cockpit_decisions.py`
> 会核对：每个按钮、每条命令都在本表里出现，且命令真的存在于 `main.py` 的命令树、选项名没写错。

**原则：界面是命令行的另一层皮。** 按钮只拼一条 `main.py pm …` 命令，在控制根后台运行，
命令和退出码原样进页面下方的记录。门禁、租约、受保护路径、批准口令、agent 标记全由命令自己判，
界面不替它放行，也不绕过。所以下表“出现在什么状态”只是方便用户看，不是安全边界。

## 怎么接进主窗口

`app.py` 顶栏有“决定”页签（`goto("decisions")`）；打开页签时 `_refresh_decisions()` 才去读口令状态、待批准范围卡和收件箱
（每个项目 2 条只读命令，最多 `DECISION_PROJECT_LIMIT` 个项目：有开着的卡的项目加今天页最热的几个），
10 分钟定时刷新不去读。命令成功后窗口重读账本。工位里的“批准范围 / 开工”只是带你来这一页。

## 九个按钮

| 按钮 | 作用对象 | 出现在 | 命令（`main.py` 之后） | 要用户填 | 口令生效时 |
|---|---|---|---|---|---|
| 批准范围 | 待批准范围卡（`pm pending` 读出） | 范围卡 | `pm approve --request-id R --plan-hash H --approver A --approval-evidence-ref E` | 撞车放行（可空） | 不传 A、E；命令在终端问口令 |
| 确认开工 | 一张卡 | 草稿、等批准 | `pm confirm-start --mission-id M` | — | 不问口令 |
| 确认验收 | 一张卡 | 等验收 | `pm accept --mission-id M` | — | 命令在终端问口令 |
| 收口 | 一张卡 | 已验收（含“重试同步”） | `pm close --mission-id M` | — | 不问口令 |
| 搁着 | 一张卡 | 在干 | `pm park --mission-id M --reason … --summary … --approval-evidence-ref E` | 原因、断点 | 命令在终端问口令 |
| 拿回 | 一张卡 | 搁着、受阻 | `pm unpark --mission-id M --as 谁 --approval-evidence-ref E` | 谁来接着干 | 命令在终端问口令 |
| 插急活 | 一张卡（要改干的那张） | 搁着、草稿、等批准（同项目有“在干”的卡时） | `pm switch --pid P --to M --reason … --summary … --as 谁 --approval-evidence-ref E` | 原因、断点、谁来干 | 命令在终端问口令 |
| 确认入箱 | 收件箱条目（`pm inbox list` 读出） | 收件箱 | `pm inbox confirm 条目 --ticket-hash T --approver A --approval-evidence-ref E` | 备注（可空） | 同上 |
| 驳回入箱 | 收件箱条目 | 收件箱 | `pm inbox reject 条目 --ticket-hash T --approver A --approval-evidence-ref E --note …` | 驳回理由 | 同上 |

读状态用的只读命令：`pm approver-pin status`（口令是否生效）、`pm pending --project-id P`、`pm inbox list --project-id P`。

## 项目详情页的两个按钮（CHG-SCPT-2026-654）

这两个按钮也登记在 `DECISIONS` 里（`kind` 是 `project`），但**不在“决定”页上**（`build_vm` 只挑 `mission`、`scope_card`、`inbox` 三类），
只在项目详情页概览的“项目状态”一块出现，由同一个控制器（`decision_controller.py`）起命令，回执两边都显示。

| 按钮 | 作用对象 | 出现在 | 命令（`main.py` 之后） | 要用户填 | 口令生效时 |
|---|---|---|---|---|---|
| 确认归档 | 一个项目（在研或暂停） | 项目详情页；先点“归档…”跑过预演，并且预演通过 | `project archive P --confirm --approval-evidence-ref E` | — | 只有“在终端窗口里运行”，命令在终端问口令 |
| 确认重新激活 | 一个项目（已归档） | 项目详情页；先点“重新激活…”跑过预演，并且预演通过 | `project reactivate P --confirm --approval-evidence-ref E` | — | 同上 |

- **预演**：“归档…”“重新激活…”“重新检查”三个按钮不在 `DECISIONS` 里，只跑 `project archive P` / `project reactivate P`（不带 `--confirm`，只查不改），
  命令登记在 `decisions.READ_ONLY_COMMANDS`。输出原样摆出来；“预演通过”只看两样：退出码 0，并且输出里有“预演（没加 --confirm）”这一句（`decisions.DRY_RUN_MARK`）。
- **确认键和预演绑在同一个项目上**：换到另一个项目的详情页，或点“重新读取”，预演作废、确认键消失；确认时命令里的项目号取预演记下的那个。
- **发版切换前的降级**：打开项目详情页或工具页“项目”页签时后台探测一次 `project archive --help`、`project reactivate --help`、`project register --help`
  （也登记在 `READ_ONLY_COMMANDS`），结果在这个窗口里记着，点“重新读取”才重探。命令不存在时两个预演按钮灰着，旁边写“本机发布版太旧：没有这条命令”；探测没读成也灰着并写明原因。
- 凭据 E 同下一节（`click_evidence`，“用户亲手点了这个按钮”）；看板不预填用户原话、不收口令。命令带 agent 标记时自己会拒绝，回执照实显示。
- 项目的“删除”“恢复”不上看板。

## 凭据 E 从哪来

口令**未生效**时，命令要的“用户原话凭据”由本页在点击那一刻生成：
`user-confirmation:gui-click-<年月日T时分秒>-<8 位摘要>`，格式过 `contracts/user_evidence.py` 的检查，不含任何 agent 或模型名。
这只是格式检查，防不了冒名（已知缺口 P1，见《批准口令未生效方案》）；**口令生效后命令用口令代替它**。
批准人 A 取页面顶上“批准人”一栏（默认读环境变量 `AUTO_PM_COCKPIT_APPROVER`）。

## 口令生效时怎么办

命令行故意没有任何非终端的口令通道（`ui/cli/approval_pin.py`）。所以口令生效时，带“口令”的按钮改成
“在终端窗口里运行”：本页在 Windows 上弹出一个新的终端窗口运行**同一条命令**（窗口里命令结束后会等你按回车，好让你看清结果），用户在那个窗口里输入口令；
本程序看不到口令，也看不到退出码，用户看完结果回来点“重新读取”。
“在本程序里弹窗输入口令”需要给命令行加一条非终端通道，那是改批准规则，要用户点头后另开一张卡。

## 进命令行的值怎么把关（预审 510 a）

- 运行命令和“终端窗口里运行”都是按**参数列表**直接起进程，不经过 cmd、PowerShell 或任何 shell；
  终端窗口那条路是起一个固定的 Python 小包装，再把同一条命令当参数传给它（`actions._CONSOLE_WRAPPER`）。
- 来自账本的编号（项目、任务、请求、条目）和哈希走白名单（字母数字和 `. _ : -`，哈希 8～128 位字母数字）。
- 用户自由填的字（原因、断点、备注、批准人、撞车放行）：不许换行和其他控制字符，不许出现 `"` `%` `^` `$` `` ` ``，最长 500 字；
  `&` 和 `|` 只是普通字符，允许，复制出去的命令里会被引号包住。“谁来干”走白名单（如 `claude:cloud`）。
- 测试：`tests/core/test_cockpit_decisions.py` 里带 `"` `&` `|` `^` `%` 换行的用例。

## 永远不会有的按钮

合并、删除、切换发布、代签、绕过提交钩子、启动 agent / Codex、全量门禁。测试里的 `NEVER_WORDS` 清点按钮和对话框文字。

## 没做的（命令行里有，本页没放）

- **入箱（`pm inbox add`）**：它要分诊单（影响、查重、取证、备选方案……），那是 agent 的活，用户只确认或驳回。
- **安全区签字（`pm sign-risk`）**：按规矩只能用户本人在终端或 GitHub PR 上做。
- **交接、接管、重启续做（`handoff`、`takeover`、`recover`）**：agent 之间的线，不是给用户的按钮。

## 给 Trae：怎么加一个按钮

1. 在 `decisions.py` 的 `DECISIONS` 加一行，在 `build_args()` 里接线。
2. 在本表加一行（按钮名和命令前缀要原样出现）。
3. 跑 `python -m pytest tests/core/test_cockpit_decisions.py tests/core/test_cockpit_decisions_widgets.py`。
