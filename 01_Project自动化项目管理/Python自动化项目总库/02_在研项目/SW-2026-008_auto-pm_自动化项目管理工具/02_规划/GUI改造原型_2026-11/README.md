# 驾驶舱 GUI 改造原型（2026-11，云端会话出稿，待本地评估）

> 性质：设计原型与改造建议，**不是已批准的实施卡**。不改任何代码、规则、台账。
> 基线：`main` d5fc81df（PR #522 合并后）。
> 可点的在线版本（仅用户本人可打开，需用户在页面 Share 里分享后他人才能看）：https://claude.ai/artifact/MiNeiaM4ZYRuDXBGWEiqXs

## 本目录文件

| 文件 | 内容 |
|---|---|
| `单个项目.dc.html` | 新方案：单个项目画面（含新目标、范围批准、证据抽屉三个侧滑面板） |
| `项目总览.dc.html` | 新方案：全部项目总览 |

`.dc.html` 是设计画布格式，需要画布运行时才能渲染（直接用浏览器打开显示不全）。看效果用上面的在线链接；评估结构和字段直接读源码即可——布局在 `<x-dc>` 里，示例数据和交互在文件末尾的 `class Component` 里。

## 1. 现状问题

仓库不收 PNG（`.gitignore` 第 49 行），现状截图没有提交。本地重截：在 SW-2026-008 目录下设 `QT_QPA_PLATFORM=offscreen`，用 `auto_pm.ui.boss_qml_window.build_cockpit_bridge(<工作区>)` 加载 `auto_pm/ui/qml/boss_main.qml`，等 8 秒后对根窗口 `grabWindow().save(...)`；或直接 `main.py gui` 打开看。


1. 默认画面 `ui/qml/boss_main.qml` → `views/BossCockpitView.qml` 是一列纵向长表：“提出新目标”表单占首屏，批准、开始、验收要往下翻。
2. `QQuickStyle "Basic"` 的原生浅色 ComboBox、TextField 压在 `Theme.background #020617` 上，占位字是暗灰压暗底，看不清。
3. 同一个需求在待批准卡、看板、项目卡、动态里重复出现，没有主次。

## 2. 方案原则

按 `SYS-2026-001_WorkspaceGovernance/01_项目文档/40_驾驶舱角色与边界_PM.md` 第 6、9 节：汇报分“需要用户决定的 / 正在进行的 / 已完成的 / 出问题的”四块；看板有项目库总览和单个项目两级。

- 首屏只放要用户拍板的事（批准范围、确认开始、确认验收），每件一行，一个主按钮。
- “提出新目标”收成右上角按钮，侧滑面板填写；类型是四个大按钮，不选不能保存。
- 证据、变更单、规范检查、变量与 IO 收进证据抽屉的标签页。
- 配色改浅色：暖灰底 `#F3F4F1`、白色卡片、蓝色主色 `#1F5FBF`；黄、红、绿只用于状态。文字对比度按 4.5:1 选色。

## 3. 专业工作台（`gui --advanced`）建议停止维护 —— 需用户确认

左栏十个页面（平台驾驶舱大盘、平台变更管控、平台架构规范检查、平台迭代与发布、业务项目大厅、工程健康度概览、变量表与 IO 资产、工程变更控制矩阵、工程规范与死区检查、工程交付与试运行报告）。40 号文档的看板只有“项目库总览 + 单个项目”。建议：变更单、规范检查、变量与 IO 三块并进证据抽屉，其余停用。

## 4. 字段来源（不新增后端数据）

| 画面区块 | 来源 |
|---|---|
| 需要你决定 | 快照 `pending_cards`（批准范围）+ `projects[].user_action`（`CONFIRM_START` / `CONFIRM_ACCEPTANCE`） |
| 不能批准的原因 | `pending_cards[].can_approve`、`approve_blocked_reason`、`approver` |
| 草稿结果 | `createPlanningDraft` 返回的 `draft`（`scope_status` 为 PRE_AUTH 时显示“还不能批准”） |
| 正在干卡 | `projects[]` 的 `mission`、`milestone`、`current_owner`、`progress`、`risk`、`verification`、`next_user_action`、`blocked` |
| 任务看板 | 快照 `boards`（`open_count`、`open_limit`、`closed_hidden`） |
| 出问题的 | `completion_state == PENDING_SYNC` + `completion_note`、`notices`、失败横幅 `actionAlert` |
| 最近动态 | 快照 `activities` |
| 证据抽屉 | `requestEvidence`：`verification_evidence`、`work_graph`、`resume`、`read_set`、`evidence_currency`、`change_id`、`decision_id`、`focus` |
| “变量与 IO”标签 | **现在没有**：需要证据里带本卡碰到的点表行，待评估 |
| 项目总览 | 快照 `projects` 按项目汇总；项目状态（执行中/规划中/挂起/归档）需确认现有字段 |

## 5. 建议改动范围（供起草实施卡）

- `auto_pm/ui/qml/views/BossCockpitView.qml`：重排布局
- `auto_pm/ui/qml/components/PmConfirmationCard.qml`、`PendingScopeCard.qml`、`MissionBoard.qml`、`EvidenceDrawer.qml`：换样式；证据抽屉加标签页
- `auto_pm/ui/qml/theme/Theme.qml`：配色
- 新增项目总览视图
- 交互信号与桥接方法不变，不改后端

## 6. 必须守住的现有行为

1. 失败横幅只在用户点“知道了”或同一操作重做成功后消失，5 秒刷新不清它。
2. 批准、开始、重试同步三个按钮的忙碌锁保留，防重复点击。
3. 没跑过的检查不显示“通过”。
4. 不选类型不能保存草稿（TD-SW008-070）。
5. 批准人未配置时批准按钮置灰并写明原因。

## 7. 验收建议

- `tests/qml` 中依赖 `objectName` 的用例全部保留并通过（`planningProject`、`planningKind`、`planningObjective`、`planningAcceptance`、`savePlanningDraft`、`retrySyncButton`、`completedLabel`、`actionAlertBanner`、`actionAlertText`、`actionAlertDismiss`）。
- 用离线截图（`QT_QPA_PLATFORM=offscreen` + `grabWindow`）对比改造前后。

## 8. 待用户裁决

1. 专业工作台是否停止维护（第 3 节）。
2. 浅色还是深色。
3. “变量与 IO”标签是否本轮做（需要证据接口带点表行）。
