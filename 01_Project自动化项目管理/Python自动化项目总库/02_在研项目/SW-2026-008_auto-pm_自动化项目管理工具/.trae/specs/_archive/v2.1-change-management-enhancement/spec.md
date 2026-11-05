# V2.1 变更管理增强迭代 Spec

> 项目：SW-2026-008 auto-pm
> 版本：V0.3.7（pyproject）/ V2.1.0（PRD）
> 创建日期：2026-06-24
> 基线：V0.2.3 已交付（875 测试通过）→ V0.3.7（最近完整签字 1155 passed, 1 skipped；Phase 6 发布收口完成）

## 0. 当前进度基线（强制）

### 0.1 代码规模
- Python 源码：auto_pm/ 包，含 cli/core/change/db/plc/ui/models/config/logging/utils 11 个子包
- 测试套件：1155 个测试全部通过（含 GUI 测试，1 skipped 为可见演示模式）
- 模板：plc-standard-project / plc-shared-library / plc-test-suite / python-tool 4 套 Copier 模板

### 0.2 版本号现状
| 维度 | 当前值 | 目标值 |
|------|--------|--------|
| pyproject.toml | 0.3.7 | 0.3.7（Phase 6 发布收口完成） |
| CHANGELOG 最新 | [0.3.7] | [0.3.7] |
| PRD | V2.1.0 | V2.1.0 |
| PM_SESSION §2/§8 | V0.3.7 Phase 6 发布收口完成 | V0.3.7 Phase 6 发布收口完成 |

### 0.3 路线图完成度
- V2.0（PySide6 UI 基座 + 项目CRUD + 总库管理）：✅ 完成
- V2.0.1-A/C（site 编码 + 042/016 规范对齐）：✅ 完成
- V2.0.1-D/E（PLC 规范矛盾代码修复 + spec_registry 同步）：❌ 遗留
- V2.0.3（规范漂移检测）：✅ 完成
- V2.1（变更管理增强）：✅ 主体完成 + Phase 6 发布收口完成（dogfooding 4 次闭环 CHG-001/062/063/064；发布门禁 G1-G5；试运行报告归档）
- V2.2（规范中心整合）：⏳ 后续
- V2.3（变量表解析整合）：⏳ 后续
- V2.4（模板/插件/报告）：⏳ 后续
- V2.5（系统设置/用户管理/打包）：⏳ 后续

### 0.4 V2.0 历史里程碑核查（已完成，归档参考）
> 以下 M1-M4 为 V2.0 时代里程碑，已于 2026-06-19 前全部完成。**不要与 V0.3.0 的 M0-M3 混淆**（命名碰撞）。

- M1 稳基座（文档/版本对齐）：✅ 6/6 迭代完成
- M2 补能力（CLI/Service 缺口）：✅ 8/8 迭代完成
- M3 重架构（拆上帝类+接口抽象）：✅ 7/7 迭代完成
- M4 扩功能（V2.1~V2.3 路线图）：✅ 5/5 迭代完成

### 0.5 V0.3.0 当前里程碑状态（2026-06-26 更新）

> V0.3.0 里程碑为本次迭代计划，M0 已重定义为"技术债偿还"（非原计划的 V2.0.1 剩余+技术债）。
> 原 M0-1~M0-5 任务（V2.0.1-D/E、list_view mypy、test_project_list flaky、QMessageBox 阻塞）大部分已通过技术债偿还批次完成或并入技术债报告。

| 里程碑 | 状态 | 说明 |
|--------|------|------|
| M0 基座清理（重定义为技术债偿还） | ✅ 完成 | 16/19 项技术债已偿还；1019 测试通过 + ruff 0 + mypy 0 + 元测试 0 violations |
| M0.5 真源收口 + 产品自洽 + dogfood 制度化 | ✅ 完成 | Phase 0 真源收口 + Phase 1 产品自洽（3 项 BUG 修复）+ Phase 2 dogfood 制度化（spec.md §9） |
| M1 变更单章节结构修正 | ✅ 完成 | §6.1 风险等级/缓解措施 + §10 三节结构 + §11 版本详细变更说明 + 040 V2.2.0 |
| M2 影响分析与审批记录持久化 | ✅ 完成 | DB schema 扩展（impact_analysis + approval_history 表）+ Repository + Service 集成 + parser 增强 |
| M3-1 变更单编辑表单 | ✅ 完成 | EditChangeDialog QDialog+QTabWidget 双 Tab + 17 UI 测试 + 5 bug 修复 |
| M3.5 真源收口 Round 2 + 产品自洽 Round 2 | ✅ 完成 | 8 项任务全部完成：M3.5-1 清理 GUI 测试污染 ✅ + M3.5-2 修复 TD-T04 复发 ✅ + M3.5-3 真源收口 R2 ✅ + M3.5-4 CHG-001 内容补全 ✅ + M3.5-5 CHG-062 完整生命周期 ✅ + M3.5-6 change show §6/§8/§9/§10 增强 ✅ + M3.5-7 CLI 表格不截断 ✅ + M3.5-8 change edit CLI 命令 ✅（dict 字段 constraint_impacts/domain_impacts 留给 GUI EditChangeDialog，见 §0.7 CLI/GUI 字段分工） |
| M3-2 传播链可视化 | ✅ 完成 | PropagationView QGraphicsView 水平展示传播链 + _parse_chain 解析 ->/→ 分隔符 + 节点中文名映射 + 箭头连线 + 空链"无跨领域影响" + DEBUG tracing + 8 UI 测试 |
| M3-3 审批时间线 | ✅ 完成 | ApprovalTimeline 自定义 QWidget 垂直展示审批历史 + ChangeService.list_approval_history 读取方法 + change_detail_panel 集成 + 7 UI 测试 |
| M3-4 增强功能 | ✅ 完成 | T76 QWizard 分步向导 ✅；T77 StatusMachineView 状态机可视化 + 一键流转 ✅；T78 ChangeListPanel 4 维度筛选（状态/领域/紧急程度/项目）+ ChangeSummary urgency 字段 ✅；T79 UI 测试 48 项 ✅ |

### 0.6 dogfood 发现的产品缺陷（已修复，保留作历史依据）

| 缺陷 ID | 描述 | 归属阶段 | 严重程度 |
|---------|------|---------|---------|
| BUG-001 | `verification_conclusion` 门禁过硬编码（必须字面量"全部通过"） | M0.5 Phase 1-3 | 🟡 中，已修复 |
| BUG-002 | 台帐更新路径解析错误（中文路径被字符级拆分） | M0.5 Phase 1-2 | 🟡 中，已修复 |

### 0.7 CLI/GUI 变更单编辑字段分工（M3.5-8 确立）

变更单可编辑字段（`ChangeService._UPDATABLE_FIELDS`，共 10 个）按输入复杂度分为 CLI 可编辑和 GUI 专属两类，避免下次迭代遗漏：

| 字段 | 章节 | 类型 | CLI edit | GUI EditChangeDialog | 说明 |
|------|------|------|----------|----------------------|------|
| background | §4 | str | ✅ `--background` | ✅ | 变更背景 |
| necessity | §4 | str | ✅ `--necessity` | ✅ | 变更必要性 |
| references | §4 | str | ✅ `--references` | ✅ | 参考依据 |
| planned_date | §3.4 | str | ✅ `--planned-date` | ✅ | 预计实施日期 |
| urgency | §3.4 | enum | ✅ `--urgency` | ✅ | 紧急程度（normal/urgent/critical） |
| risk_level | §6.1 | enum | ✅ `--risk-level` | ✅ | 风险等级（none/low/medium/high） |
| mitigation | §6.1 | str | ✅ `--mitigation` | ✅ | 缓解措施 |
| propagation_chain | §6.3 | str | ✅ `--propagation-chain` | ✅ | 变更传播链 |
| constraint_impacts | §6.1 | dict | ❌ 留 GUI | ✅ | 项目约束影响（维度→影响程度），CLI 输入 dict 繁琐 |
| domain_impacts | §6.2 | dict | ❌ 留 GUI | ✅ | 技术领域影响（领域→{affected,content,related_chg}），CLI 输入 dict 繁琐 |

**设计原则**：CLI 覆盖 8 个字符串/枚举字段（快速编辑场景），GUI 覆盖全部 10 个字段（含 2 个 dict 复杂字段，完整编辑场景）。下次迭代扩展编辑能力时，需同步检查 CLI/GUI 两端覆盖范围。

### 0.8 2026-06-27 复核口径（Phase 6 发布收口后更新）

- 当前唯一状态真源：`PM_SESSION_SW-2026-008.md`
- 当前执行总计划：`09_整改项/V0.3.0-项目落地执行总计划_重规划版.md`（Phase 6 发布收口完成，总计划全部完成）
- 当前问题判断依据：`09_整改项/V0.3.0-项目深度诊断与Dogfood专项报告.md`
- 当前主线事实：`Phase 6 发布收口` 已完成，T80-T85 全部交付（README 重写 + CHANGELOG 整理 + 发布门禁规范 G1-G5 + 试运行报告归档 + CHG-SCPT-2026-064 完整生命周期闭环 + 版本号 0.3.6→0.3.7）；dogfooding 4 次闭环（CHG-001/062/063/064）；总计划 §2.3 "可落地使用"8 条标准达成
- 当前运行复核结果：`project show` 的 `version=0.3.7 / phase=developing / description` 全部可信；`mypy auto_pm` 通过；`ruff check .` `All checks passed!`（0 errors）；`pytest` 1155 passed 1 skipped 3 warnings 无回归（复用 V0.3.6 glm5.2 基线）
- 执行限制：两份 `里程碑迭代计划_V2.1.md` 仅可作历史/镜像参考，不得再作为当前推进真源

## 1. Why

### 1.1 遗留问题
V0.2.3 交付后存在三类未解决问题：

1. **V2.0.1 剩余项**：D（906/905/023 PLC 规范矛盾代码修复，41 个代码片段）+ E（spec_registry.json 同步）未完成，阻碍规范体系一致性
2. **技术债**：list_view.py 既有 mypy 错误（Qt 枚举简写）+ tests/ui/test_project_list.py flaky（isVisible 误用）+ 6 个 UI 测试 QMessageBox 阻塞，影响开发效率
3. **V2.1 变更管理能力缺口**：generator.py 章节结构缺陷（§10 缺跨领域联动验证、§11 应为版本详细变更说明）、影响分析与审批记录未持久化到 DB、GUI 变更管理能力薄弱（无编辑表单/传播链可视化/审批时间线）

### 1.2 用户价值
- **PLC 工程师**：V2.0.1-D 修复 41 个规范矛盾代码片段，消除规范体系内部矛盾
- **项目经理**：V2.1 变更管理增强提供传播链可视化、审批时间线、影响分析持久化，变更追溯能力提升
- **开发者**：技术债清理后 mypy/pytest 全绿，开发体验改善

## 2. What Changes

### 2.1 M0：基座清理（已重定义为技术债偿还，✅ 已完成）

> **重定义说明（2026-06-25）**：M0 原计划为"V2.0.1 剩余 + 技术债"，实际执行时重定义为"技术债偿还"。
> 原 M0-1~M0-5 任务中：list_view mypy（M0-3）和 test_project_list flaky（M0-4）已在技术债批次中完成；
> V2.0.1-D（M0-1）和 V2.0.1-E（M0-2）属 PLC 规范域，不在本次 Python 工具迭代范围；
> QMessageBox 阻塞（M0-5）已在技术债批次中处理。
> 详细偿还记录见 `00_项目基础信息/006_技术债评估报告.md`。

#### M0-1：V2.0.1-D PLC 规范矛盾代码修复（不在本次范围）
- 修复 906/905/023 规范中 41 个矛盾代码片段
- 涉及文件：`0100_PLC自动化/00_通用规范/PLC编程/` 下 905/906/023 规范文档
- 验收：41 个片段全部修复，specmgr check 无矛盾告警

#### M0-2：V2.0.1-E spec_registry.json 同步（不在本次范围）
- SW-2026-008 注册到 registry（domain: cross-domain, lifecycle: stable）
- SW-2026-007 标记 deprecated + replaced_by: ["SW-2026-008"]
- last_updated 更新
- 涉及文件：`00_Obsidian_Base全局规范文件仓库/spec_registry.json`
- 验收：spec_registry.json 反映当前工具状态

#### M0-3：list_view.py mypy 修复（✅ 已在技术债批次6完成）
- Qt 枚举简写改为限定形式（Qt.AlignTop → Qt.AlignmentFlag.AlignTop 等）
- ruff-format 合规
- 涉及文件：`auto_pm/ui/project_list/list_view.py`
- 验收：mypy auto_pm/ 全绿

#### M0-4：test_project_list.py flaky 修复（✅ 已在技术债批次中处理）
- isVisible() 改用 isVisibleTo(parent)
- 纳入 git 跟踪
- 涉及文件：`tests/ui/test_project_list.py`
- 验收：pytest -p no:randomly 连续 3 次无 flaky

#### M0-5：6 个 UI 测试 QMessageBox 阻塞修复（✅ 已在技术债批次中处理）
- CreateChangeDialog._load_projects 使用 QTimer.singleShot 自动关闭消息框
- 或注入 mock ProjectService 避免实际加载
- 涉及文件：`tests/ui/test_iteration1~4_interactive.py`、`test_change_dialogs.py`、`test_final_acceptance.py`
- 验收：6 个测试文件可独立运行无阻塞

### 2.2 M1：变更单章节结构修正（generator.py + parser.py + 040 规范）

#### M1-1：§6.1 增加"风险等级"和"缓解措施"字段
- 当前 §6.1 项目约束影响表：约束维度 | 影响程度 | 影响描述 | 应对措施
- 目标结构：约束维度 | 影响程度 | 影响描述 | 风险等级 | 缓解措施
- 涉及文件：`auto_pm/change/generator.py`（渲染）、`auto_pm/change/parser.py`（解析）、`auto_pm/change/models.py`（数据模型）
- 验收：新生成的变更单含 5 列；parser 可解析风险等级和缓解措施

#### M1-2：§10 改为三节结构
- 当前：§10.1 验证项清单 + §10.2 验证结论
- 目标：§10.1 验证项清单 + §10.2 跨领域联动验证 + §10.3 验证结论
- 涉及文件：`auto_pm/change/generator.py`、`auto_pm/change/parser.py`、`auto_pm/change/markdown_editor.py`（append_to_verification_table/update_verification_conclusion 适配）
- 验收：新生成的变更单含三节；markdown_editor 正确插入 §10.3 结论

#### M1-3：§11 版本详细变更说明补全
- 当前 §11 是"附录"
- 目标：§11 版本详细变更说明（含版本号/变更类型/变更内容/影响评估）+ §12 附录
- 涉及文件：`auto_pm/change/generator.py`、`auto_pm/change/parser.py`
- 验收：新生成的变更单 §11 为版本详细变更说明，§12 为附录

#### M1-4：文档版本号对齐 040 模板
- generator.py 渲染的"文档版本"对齐 040 模板当前版本
- 涉及文件：`auto_pm/change/generator.py`
- 验收：生成的变更单文档版本号与 040 模板一致

#### M1-5：040 §3.4 变更状态字段定义（规范文档）
- 040 V2.2.0 在 §3.4 申请信息表中增加"变更状态"字段定义
- 涉及文件：`00_Obsidian_Base全局规范文件仓库/` 下 040 规范文档
- 验收：040 规范 §3.4 含变更状态字段定义

### 2.3 M2：影响分析与审批记录持久化（DB 层）

#### M2-1：DB schema 扩展
- 新增 impact_analysis 表：change_number(PK) | scope | schedule | cost | quality | risk | risk_level | mitigation | propagation_chain | related_changes(JSON)
- 新增 approval_history 表：id(PK) | change_number(FK) | status | approver | comment | approval_date
- 涉及文件：`auto_pm/db/schema.py`、`auto_pm/db/repository.py`
- 验收：schema 迁移脚本可执行；新表可读写

#### M2-2：ChangeRequestRepository 扩展
- 新增 save_impact_analysis(change_number, analysis) 方法
- 新增 get_impact_analysis(change_number) 方法
- 新增 save_approval_record(change_number, status, approver, comment) 方法
- 新增 list_approval_history(change_number) 方法
- 涉及文件：`auto_pm/db/repository.py`
- 验收：4 个方法单元测试通过

#### M2-3：ChangeService 集成
- transition_status 时同步写入 approval_history 表
- create_change_request / update_change_request 时同步写入 impact_analysis 表
- 涉及文件：`auto_pm/change/change_service.py`
- 验收：状态流转后 DB 有审批记录；变更单创建/修改后 DB 有影响分析

#### M2-4：parser.py 解析增强
- 解析 §6.1 风险等级和缓解措施字段
- 解析 §10.2 跨领域联动验证章节
- 涉及文件：`auto_pm/change/parser.py`
- 验收：parser 可解析新增字段；单元测试覆盖

### 2.4 M3：GUI 变更管理增强（UI 层，与 M2 并行）

#### M3-1：变更单编辑表单
- 新增 EditChangeDialog（参照 CreateChangeDialog 结构）
- 支持修改 background/necessity/references/planned_date/urgency 字段
- 支持修改 §6 影响分析（风险等级/缓解措施/传播链）
- 涉及文件：新增 `auto_pm/ui/dialogs/edit_change_dialog.py`、`auto_pm/ui/change_center/change_detail_panel.py`（集成）
- 验收：GUI 可编辑变更单字段；保存后文件和 DB 同步更新

#### M3-2：传播链可视化
- §6.3 变更传播链图形化展示（QGraphicsView + 节点连线）
- 节点显示领域名称，连线显示传播方向
- 涉及文件：新增 `auto_pm/ui/change_center/propagation_view.py`、`auto_pm/ui/change_center/change_detail_panel.py`（集成）
- 验收：传播链以图形化方式展示；空传播链显示"无跨领域影响"

#### M3-3：审批时间线
- §8 审批记录以时间线方式展示（QTimeline 或自定义 QWidget）
- 显示审批环节/审批人/审批意见/审批日期
- 涉及文件：新增 `auto_pm/ui/change_center/approval_timeline.py`、`auto_pm/ui/change_center/change_detail_panel.py`（集成）
- 验收：审批记录以时间线展示；DB 缓存的审批历史可读取

#### M3-4：变更管理增强
- T76 创建向导优化 ✅：QWizard 3 步分步向导（BasicInfoPage 基本信息 7 字段 → DescriptionPage 变更描述 2 字段 → ConfirmPage 提交确认汇总展示）；isComplete 联动 Next 按钮；validatePage 触发创建；CreateChangeDialog 别名 + property 兼容层确保调用点零改动
- T77 状态流转 UI ✅：StatusMachineView 可视化状态机（12 节点 + 11 箭头，当前蓝色边框/目标绿色填充/可达可点击/不可达灰色）+ TransitionDialog 集成 + 节点点击一键流转 + _on_target_selected 联动验证结论显隐
- T78 列表筛选增强 ✅：ChangeListPanel 新增领域/紧急程度/项目 3 个筛选下拉；ChangeSummary 增加 urgency 字段；list_all_changes 增加 urgency 和 project_id 参数（内存筛选）；项目下拉选项从变更单列表动态提取
- T79 UI 测试覆盖 ✅：test_status_machine_view.py 19 测试 + test_change_list_panel_filters.py 22 测试 + test_change_dialogs.py 新增 TestTransitionDialogStateMachine 7 测试，共 48 项
- 涉及文件：`auto_pm/ui/dialogs/create_change_dialog.py`、`auto_pm/ui/dialogs/transition_dialog.py`、`auto_pm/ui/change_center/change_list_panel.py`
- 验收：创建向导分步（✅）；状态流转可一键操作（✅）；列表多维度筛选（✅）

## 3. Non-Goals

- 不做 004 安全问题吸收（UserStore 重新设计，推迟 V2.5）
- 不做 specmgr 整合（V2.2 范围）
- 不做变量表解析整合（V2.3 范围）
- 不做模板/插件/报告中心（V2.4 范围）
- 不变更 CLI 接口（保持向后兼容）
- 不变更 STATUS_FLOW 状态机（12 状态已完整）

## 4. 里程碑与验收

### M0 出口标准
- [ ] 41 个 PLC 规范矛盾代码片段全部修复
- [ ] spec_registry.json 同步完成
- [ ] mypy auto_pm/ 全绿
- [ ] pytest 无 flaky（连续 3 次）
- [ ] 6 个 UI 测试无阻塞
- [ ] 全量测试通过

### M1 出口标准
- [ ] generator.py 渲染的变更单含 §6.1 五列（含风险等级/缓解措施）
- [ ] generator.py 渲染的变更单含 §10 三节结构
- [ ] generator.py 渲染的变更单 §11 为版本详细变更说明，§12 为附录
- [ ] parser.py 可解析新增字段
- [ ] 040 规范 §3.4 含变更状态字段定义
- [ ] 新增单元测试覆盖
- [ ] 全量测试通过

### M2 出口标准
- [ ] DB schema 扩展（impact_analysis + approval_history 两表）
- [ ] ChangeRequestRepository 4 个新方法可用
- [ ] ChangeService 集成 DB 持久化
- [ ] parser.py 解析增强
- [ ] 新增单元测试覆盖
- [ ] 全量测试通过

### M3 出口标准
- [ ] EditChangeDialog 可用
- [ ] 传播链可视化可用
- [ ] 审批时间线可用
- [ ] 变更管理增强（创建向导/状态流转/列表筛选）
- [ ] 新增 UI 测试覆盖
- [ ] 全量测试通过

### M4 出口标准（Dogfooding）
- [ ] CHG-SW-2026-008.md 变更单文件存在且格式符合 CHG-040 标准
- [ ] 变更单状态走完完整流程（draft → ... → archived）
- [ ] §9 实施记录含 M0/M1/M2/M3 四个里程碑条目
- [ ] §10 验证记录完整
- [ ] 版本变更台帐文件存在且含 V0.3.0 条目
- [ ] `auto-pm change list` 可列出该变更单
- [ ] `auto-pm change show CHG-SW-2026-008` 可正确解析

## 5. 风险管理

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| M0-1 修复 41 个规范片段引入新矛盾 | 中 | 中 | 逐片段修复，每片段 specmgr check 验证 |
| M1 章节结构变更破坏现有变更单解析 | 高 | 高 | parser 兼容旧格式；提供迁移脚本 |
| M2 DB schema 变更导致缓存失效 | 中 | 中 | 提供迁移脚本；保留旧表兼容期 |
| M3 GUI 增强引入 flaky 测试 | 中 | 中 | 使用 isVisibleTo(parent) 替代 isVisible() |
| 范围蔓延（004 安全问题被拉入） | 低 | 高 | 严格按 Non-Goals 执行 |

## 6. 版本号规划

- pyproject.toml: 0.2.3 → 0.3.0
- CHANGELOG.md: 新增 [0.3.0] 条目
- PRD: V2.0.3 → V2.1.0（新增 V2.1.0 路线图章节）
- PM_SESSION §2/§8: V0.2.3 → V0.3.0
- 005_变更记录_CHG.md: 新增 V2.1.0 变更记录

## 7. 测试策略

### 7.1 测试分层
| 层级 | 范围 | 工具 |
|------|------|------|
| L1 单元测试 | generator/parser/repository/service 新方法 | pytest |
| L2 集成测试 | ChangeService + DB 持久化 | pytest + 临时 DB |
| L3 GUI 测试 | EditChangeDialog/传播链/审批时间线 | pytest-qt + QTest |
| L4 端到端测试 | 创建变更单 → 编辑 → 流转 → 归档全流程 | scripts/gui_plc_full_test.py |

### 7.2 质量门禁
每个里程碑必须通过：
- ruff check auto_pm/ tests/
- ruff format --check auto_pm/ tests/
- mypy auto_pm/
- pytest tests/ -x
- 测试覆盖率 >=85%

## 8. 关联文档

- [PM_SESSION_SW-2026-008.md](../../../PM_SESSION_SW-2026-008.md)
- [CHANGELOG.md](../../../CHANGELOG.md)
- [PRD V2.0.3](../../../00_项目基础信息/001_产品需求文档_PRD.md)
- [005_变更记录_CHG.md](../../../00_项目基础信息/005_变更记录_CHG.md)
- [006_技术债评估报告.md](../../../00_项目基础信息/006_技术债评估报告.md)
- [V0.3.0-项目落地执行总计划_重规划版.md](../../../09_整改项/V0.3.0-项目落地执行总计划_重规划版.md)
- [V0.3.0-项目深度诊断与Dogfood专项报告.md](../../../09_整改项/V0.3.0-项目深度诊断与Dogfood专项报告.md)

## 9. Dogfood 制度化（V0.3.0-M0.5-Phase2 新增）

> 基于 GPT5.4 诊断报告 + glm5.2 核查，将 dogfood 从"做过一次"升级为"每次必经"的发布门禁。

### 9.1 Dogfood 固定模板（每个里程碑必经动作清单）

每个里程碑（M0/M1/M2/M3）完成后，必须执行以下固定动作：

| 序号 | 动作 | 命令/操作 | 产出 |
|------|------|----------|------|
| 1 | 创建变更单 | `python -m auto_pm -w "<workspace>" change create --pid SW-2026-008 --domain SCPT --nature OPT --scope SYSTEM --scope MODULE --applicant fubai --background "..." --necessity "..." --references "..." --urgency normal` | CHG-SCPT-2026-XXX.md |
| 2 | 流转到审批 | `change transition CHG-SCPT-2026-XXX --to submitted` | 状态更新 |
| 3 | 流转到实施 | `change transition CHG-SCPT-2026-XXX --to approved` → `--to implementing` | 状态更新 |
| 4 | 补实施记录 | 手动编辑变更单 §9 | §9 填充 |
| 5 | 流转到验收 | `change transition CHG-SCPT-2026-XXX --to pending_acceptance` → `--to accepting` | 状态更新 |
| 6 | 补验证记录 | 手动编辑变更单 §10 | §10 填充 |
| 7 | 完成验收 | `change transition CHG-SCPT-2026-XXX --to completed --verification-conclusion "全部通过（附说明）"` | 状态更新 |
| 8 | 归档关闭 | `change transition CHG-SCPT-2026-XXX --to closed` 或 `--to archived` | 终态 |
| 9 | 验证可读 | `change list SW-2026-008` + `change show CHG-SCPT-2026-XXX` | 列表+解析验证 |
| 10 | 回写文档 | PM_SESSION §5/§6/§8/§9 + 005_变更记录_CHG.md + CHANGELOG.md | 文档同步 |

### 9.2 发布门禁清单（强制，未通过不得发布）

| 序号 | 门禁项 | 验证方法 | 通过标准 |
|------|--------|---------|---------|
| 1 | 版本号四端一致 | 检查 pyproject.toml / CHANGELOG.md / PRD / PM_SESSION §2=§8 | 四端版本号一致 |
| 2 | 全量测试通过 | `pytest -q --no-cov` | 0 failed |
| 3 | ruff 检查通过 | `ruff check auto_pm tests` | 0 errors |
| 4 | mypy 检查通过 | `mypy auto_pm` | 0 errors |
| 5 | 元测试无 violations | `pytest tests/test_fixture_health.py -q` | 0 violations |
| 6 | 核心 CLI 回归 | `project show SW-2026-008` + `change list SW-2026-008` | 命令成功且输出可信 |
| 7 | dogfood 闭环证据 | 检查 CHG-SCPT-2026-XXX.md 状态 | 走完完整生命周期（draft→...→closed/archived） |
| 8 | 文档同步 | 检查 PM_SESSION/CHANGELOG/005_变更记录 | 全部已更新 |
| 9 | 关键缺陷有状态 | 检查 BUG-XXX 在 tasks.md 中的归属 | 每个缺陷有归属阶段和状态 |
| 10 | 使用者视角检查 | 见 §9.3 | 全部通过 |

### 9.3 使用者视角检查项（电气工程师/项目经理视角）

| 序号 | 检查项 | 视角 | 通过标准 |
|------|--------|------|---------|
| 1 | 项目列表信息可信 | 电气工程师 | `project list` 输出的名称/版本/阶段/描述非空且正确 |
| 2 | 项目详情信息可信 | 电气工程师 | `project show <pid>` 输出完整且正确 |
| 3 | 新建变更单顺手 | 项目经理 | `change create` 命令参数自然，不需要"迎合工具的话" |
| 4 | 验收结论表达自然 | 项目经理 | `verification_conclusion` 可写"全部通过（附说明）"等自然表达 |
| 5 | 路径与台帐跨栈顺手 | 电气工程师 | PLC 和 Python 项目都能在正确位置创建/更新台帐 |
| 6 | 审批与验收表达自然 | 项目经理 | 状态流转命令参数自然，错误提示清晰 |
| 7 | GUI/CLI 减少管理成本 | 电气工程师 | CLI 命令简洁，GUI 操作直观（如已有 GUI） |
| 8 | 变更单可读性 | 项目经理 | `change show` 输出格式清晰，关键信息一目了然 |
