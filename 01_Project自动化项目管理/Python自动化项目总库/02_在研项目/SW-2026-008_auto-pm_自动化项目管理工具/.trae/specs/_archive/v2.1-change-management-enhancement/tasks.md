# V2.1 变更管理增强 - 任务拆解

> 关联 spec.md
> 共 4 个里程碑、17 个任务

> **M0 重定义说明（2026-06-25）**：M0 原计划为"V2.0.1 剩余 + 技术债"，实际执行时重定义为"技术债偿还"。
> 原 M0-1/M0-2（V2.0.1-D/E）属 PLC 规范域，不在本次 Python 工具迭代范围；
> M0-3/M0-4/M0-5 已在技术债批次中完成（见 `00_项目基础信息/006_技术债评估报告.md`）。
> M0 实际偿还成果：16/19 项技术债已偿还，1019 测试通过 + ruff 0 + mypy 0 + 元测试 0 violations。

## M0：基座清理（已重定义为技术债偿还，✅ 已完成）

### M0-1：V2.0.1-D PLC 规范矛盾代码修复（不在本次范围，属 PLC 规范域）
- [ ] T1: 查阅 906/905/023 规范，定位 41 个矛盾代码片段
- [ ] T2: 逐片段修复 905 §4.3 TIME→DINT 等矛盾
- [ ] T3: 逐片段修复 023 §6.4.2/§6.5.2 TIME→DINT 等矛盾
- [ ] T4: 逐片段修复 906 §3.1 libraryDirectories→libraries 等
- [ ] T5: specmgr check 验证无矛盾告警
- [ ] T6: 更新 005_变更记录_CHG.md

### M0-2：V2.0.1-E spec_registry.json 同步（不在本次范围，属规范注册表域）
- [ ] T7: SW-2026-008 注册到 registry（domain: cross-domain, lifecycle: stable）
- [ ] T8: SW-2026-007 标记 deprecated + replaced_by: ["SW-2026-008"]
- [ ] T9: last_updated 更新
- [ ] T10: specmgr check 验证

### M0-3：list_view.py mypy 修复（✅ 已在技术债批次6完成）
- [x] T11: Qt 枚举简写改为限定形式（Qt.AlignTop → Qt.AlignmentFlag.AlignTop 等 8 处）
- [x] T12: ruff-format 合规
- [x] T13: mypy auto_pm/ 全绿验证

### M0-4：test_project_list.py flaky 修复（✅ 已在技术债批次中处理）
- [x] T14: isVisible() 改用 isVisibleTo(parent)
- [x] T15: 纳入 git 跟踪
- [x] T16: pytest 连续 3 次无 flaky 验证

### M0-5：6 个 UI 测试 QMessageBox 阻塞修复（✅ 已在技术债批次中处理）
- [x] T17: CreateChangeDialog._load_projects 使用 QTimer.singleShot 自动关闭消息框
- [x] T18: 或注入 mock ProjectService 避免实际加载
- [x] T19: 6 个测试文件独立运行无阻塞验证

## M0.5：真源收口 + 产品自洽 + dogfood 制度化（✅ 已完成 2026-06-25）

> 2026-06-25 新增。基于 GPT5.4 诊断报告 + glm5.2 核查，先收口真源再推进 M1/M2/M3。
> 详细方案见 `09_整改项/V0.3.0-项目落地执行总计划_重规划版.md`。
> 完成成果：Phase 0 真源收口（spec/tasks/PM_SESSION 三份对齐）+ Phase 1 产品自洽（3 项 BUG 修复 + 1019 测试回归通过）+ Phase 2 dogfood 制度化（spec.md §9 固定模板/发布门禁/使用者视角）。

### M0.5-1：真源收口
- [x] T19.1: 修正 spec.md §0.4 状态字段（旧 M1-M4 标注为 V2.0 历史里程碑）
- [x] T19.2: 修正 tasks.md M0 任务状态（标注重定义 + 已完成项打勾）
- [x] T19.3: PM_SESSION §2/§3 同步本次决策
- [x] T19.4: T88 change ledger 引用移除（改为 change create 自动维护）

### M0.5-2：产品自洽修复
- [x] T19.5: 修复 ProjectScanner 元数据契约（兼容 project_description + description）— BUG-P0
- [x] T19.6: 修复 path_resolver.py 台帐创建路径跨栈策略 — BUG-002 相关
- [x] T19.7: 放宽 verification_conclusion 门禁（规则校验：包含"通过"即放行）— BUG-001
- [x] T19.8: 自用回归验证（project show/change list/show/transition）

### M0.5-3：dogfood 制度化
- [x] T19.9: 建立 dogfood 固定模板（每个里程碑必经动作清单）
- [x] T19.10: 建立发布门禁清单
- [x] T19.11: 建立使用者视角检查项

## M1：变更单章节结构修正 ✅ 已完成

### M1-1：§6.1 增加"风险等级"和"缓解措施"字段
- [x] T20: generator.py §6.1 表格增加"风险等级"和"缓解措施"两列
- [x] T21: models.py ChangeRequest 增加 risk_level/mitigation 字段
- [x] T22: parser.py _parse_constraint_impact 解析新增字段
- [x] T23: 新增单元测试 tests/change/test_generator.py::test_section_6_1_fields
- [x] T24: 新增单元测试 tests/change/test_parser.py::test_parse_risk_level_mitigation

### M1-2：§10 改为三节结构
- [x] T25: generator.py §10 增加 §10.2 跨领域联动验证子节，§10.2 验证结论改为 §10.3
- [x] T26: markdown_editor.py append_to_verification_table 适配 §10.3
- [x] T27: markdown_editor.py update_verification_conclusion 适配 §10.3
- [x] T28: parser.py 解析 §10.2 跨领域联动验证
- [x] T29: 新增单元测试 tests/change/test_generator.py::test_section_10_three_subsections
- [x] T30: 新增单元测试 tests/change/test_markdown_editor.py::test_append_to_verification_table_v2

### M1-3：§11 版本详细变更说明补全
- [x] T31: generator.py §11 改为"版本详细变更说明"（含版本号/变更类型/变更内容/影响评估表格）
- [x] T32: generator.py 原 §11 附录改为 §12
- [x] T33: parser.py 适配 §11/§12 新结构
- [x] T34: 新增单元测试 tests/change/test_generator.py::test_section_11_version_details

### M1-4：文档版本号对齐 040 模板
- [x] T35: 查阅 040 模板当前版本号
- [x] T36: generator.py 渲染的"文档版本"对齐 040 模板版本
- [x] T37: 新增单元测试验证版本号一致

### M1-5：040 §3.4 变更状态字段定义
- [x] T38: 040 V2.2.0 规范 §3.4 申请信息表增加"变更状态"字段定义
- [x] T39: 更新 040 规范 frontmatter 版本号
- [x] T40: specmgr check 验证（注：specmgr 未安装于 venv，040 模板结构已人工核查）

## M2：影响分析与审批记录持久化 ✅ 已完成

### M2-1：DB schema 扩展
- [x] T41: schema.py 新增 impact_analysis 表定义
- [x] T42: schema.py 新增 approval_history 表定义
- [x] T43: repository.py 新增 ImpactAnalysisRepository 类
- [x] T44: repository.py 新增 ApprovalHistoryRepository 类
- [x] T45: 新增单元测试 tests/db/test_repository.py::test_impact_analysis_repo
- [x] T46: 新增单元测试 tests/db/test_repository.py::test_approval_history_repo

### M2-2：ChangeRequestRepository 扩展
- [x] T47: 新增 save_impact_analysis(change_number, analysis) 方法
- [x] T48: 新增 get_impact_analysis(change_number) 方法
- [x] T49: 新增 save_approval_record(change_number, status, approver, comment) 方法
- [x] T50: 新增 list_approval_history(change_number) 方法
- [x] T51: 新增单元测试覆盖 4 个方法

### M2-3：ChangeService 集成
- [x] T52: transition_status 时同步写入 approval_history 表
- [x] T53: create_change_request 时同步写入 impact_analysis 表
- [x] T54: update_change_request 时同步更新 impact_analysis 表
- [x] T55: 新增集成测试 tests/change/test_change_service_db.py

### M2-4：parser.py 解析增强
- [x] T56: parser.py 解析 §6.1 风险等级和缓解措施字段（与 M1-1 T22 协同，已在 M1 完成）
- [x] T57: parser.py 解析 §10.2 跨领域联动验证章节（与 M1-2 T28 协同，已在 M1 完成）
- [x] T58: parser.py 增加 to_impact_analysis(cr) 方法输出持久化结构
- [x] T59: 新增单元测试 tests/change/test_parser.py::test_to_impact_analysis

## M3：GUI 变更管理增强

### M3-1：变更单编辑表单
- [x] T60: 新增 auto_pm/ui/dialogs/edit_change_dialog.py
- [x] T61: EditChangeDialog 支持修改 background/necessity/references/planned_date/urgency
- [x] T62: EditChangeDialog 支持修改 §6 影响分析（风险等级/缓解措施/传播链）
- [x] T63: change_detail_panel.py 集成 EditChangeDialog
- [x] T64: 新增 UI 测试 tests/ui/test_edit_change_dialog.py

### M3.5：真源收口 Round 2 + 产品自洽 Round 2（⏳ 进行中）

> 2026-06-25 深度审查后插入。基于三角色视角（架构师/PLC工程师/项目经理）真实运行 auto-pm 发现 6 项阻断问题。
> 详细方案见 `09_整改项/V0.3.0-项目深度诊断与Dogfood专项报告.md`。

- [x] M3.5-1: 清理 GUI 测试污染（删除 60 个残留变更单 CHG-SCPT-2026-002~061 + 添加 _cleanup_test_changes autouse fixture）
- [x] M3.5-2: 修复 TD-T04 条件断言跳过复发（test_17 中 4 处 `if dlg is not None:` 改为 assert + 反转模式）
- [x] M3.5-3: 真源收口 Round 2（spec/tasks/技术债报告/PRD 测试数与版本号对齐 1087 passed + 新增 TD-T09）
- [x] M3.5-4: 填充 CHG-SCPT-2026-001 内容（§5/§6/§7/§8/§9 真实内容 + 文档版本 V1.0.0→V2.1.0 + §10 三节结构 + §11 版本变更说明 + §12 附录）
- [x] M3.5-5: 创建 CHG-SCPT-2026-062 并走完完整生命周期（draft→submitted→under_review→approved→implementing→pending_acceptance→accepting→completed→closed，8 次流转全部成功）
- [x] M3.5-6: `change show` 命令增强（ChangeRequest 新增 `sections: dict[str, str]` 字段 + parser 保存原始章节文本 + cmd_show 调用 `_display_section_6/8/9/10` 渲染 §6.1/§6.2/§6.3 + §8.1/§8.2 + §9 + §10.1/§10.2/§10.3 共 10 张 rich.Table；CHG-001/CHG-062 验证通过；396 passed 1 skipped 无回归）
- [x] M3.5-7: CLI 表格不截断（cmd_list 所有短列 min_width+no_wrap + 标题列 ratio=1 吸收剩余空间 + 新增 --full 选项标题列 fold 换行；120 宽度下 8 列全部完整显示 CHG-SCPT-2026-001 不再截断为 CHG-SCP…）
- [x] M3.5-8: 新增 `change edit` CLI 命令（8 个字符串字段：§4 background/necessity/references/planned_date/urgency + §6 risk_level/mitigation/propagation_chain；复用 ChangeService.update_change_request；dict 字段 constraint_impacts/domain_impacts 留给 GUI EditChangeDialog；修复 _display_section_6 中 risk_level/mitigation 误判 has_constraint 的显示 bug + click.exceptions.Exit 误捕获）

### M3-2：传播链可视化
- [x] T65: 新增 auto_pm/ui/change_center/propagation_view.py
- [x] T66: QGraphicsView + 节点连线展示传播链
- [x] T67: 节点显示领域名称，连线显示传播方向
- [x] T68: 空传播链显示"无跨领域影响"
- [x] T69: change_detail_panel.py 集成传播链视图
- [x] T70: 新增 UI 测试 tests/ui/test_propagation_view.py

### M3-3：审批时间线
- [x] T71: 新增 auto_pm/ui/change_center/approval_timeline.py
- [x] T72: 自定义 QWidget 时间线展示（审批环节/审批人/审批意见/审批日期）
- [x] T73: 从 DB approval_history 表读取审批历史
- [x] T74: change_detail_panel.py 集成审批时间线
- [x] T75: 新增 UI 测试 tests/ui/test_approval_timeline.py

### M3-4：变更管理增强
- [x] T76: create_change_dialog.py 改为 QWizard 分步向导（基本信息 → 变更描述 → 提交确认）
- [x] T77: transition_dialog.py 可视化状态机 + 一键流转按钮
- [x] T78: change_list_panel.py 列表筛选增强（按状态/领域/紧急程度/项目）
- [x] T79: 新增 UI 测试覆盖向导/流转/筛选

## M4：Dogfooding — auto-pm 自身使用 CHG-*.md 变更单流程

### M4-1：迭代启动 — 创建正式变更单
- [ ] T80: 使用 `auto-pm change create` 创建 CHG-SW-2026-008.md 变更单（domain=SW, project_id=SW-2026-008）
- [ ] T81: 变更单走审批流程 draft → submitted → under_review → approved → implementing
- [ ] T82: 验证 parser 可正确解析新生成的变更单

### M4-2：迭代实施 — 同步实施记录
- [ ] T83: M0 完成后在变更单 §9 追加实施记录条目
- [ ] T84: M1/M2/M3 完成后分别追加实施记录条目
- [ ] T85: 使用 `auto-pm change transition` 流转 implementing → pending_acceptance

### M4-3：迭代验收 — 验证+归档
- [ ] T86: 在变更单 §10 追加验证记录（单元测试/集成测试/端到端/版本号一致性）
- [ ] T87: 走 pending_acceptance → accepting → completed → archived 流程

### M4-4：版本变更台帐
> **T88 决策（2026-06-25）**：原 T88 引用 `auto-pm change ledger` 命令，该命令实际不存在。
> 决策：从计划移除，由 `change create` 自动维护台帐（现有逻辑已够用，单独 CLI 命令属过度设计）。
- [x] T88: ~~使用 `auto-pm change ledger` 创建版本变更台帐~~（已移除，改为 change create 自动维护）
- [ ] T89: 台帐记录 V0.3.0 迭代全部变更条目
- [ ] T90: 验证 `auto-pm change list` 和 `auto-pm change show` 可正确操作

## 执行顺序

```
M0（基座清理）→ M1（章节结构修正）→ M2（持久化）+ M3（GUI 增强）并行 → M4（Dogfooding）
```

- M0 必须先完成（消除基座问题）
- M1 必须在 M2 之前（章节结构变更影响 parser 输出）
- M2 和 M3 可并行（数据层与 UI 层独立）
- M3-1 依赖 M2-1（EditChangeDialog 需要读取 DB 影响分析）
- M3-3 依赖 M2-2（审批时间线需要读取 DB 审批历史）
- **M4 与 M0-M3 并行推进**：M4-1 在迭代启动时执行；M4-2 随每个里程碑完成同步更新；M4-3/M4-4 在迭代收尾时执行

## 依赖关系图

```
M0-1 ─┐
M0-2 ─┤
M0-3 ─┼─→ M0 出口 → M1-1 ──→ M1-2 ──→ M1-3 ──→ M1-4 ──→ M1-5 ──→ M1 出口
M0-4 ─┤                                                              │
M0-5 ─┘                                                              ↓
                                              ┌─→ M2-1 ──→ M2-2 ──→ M2-3 ──→ M2-4 ──→ M2 出口
                                              │                    │
                                              │                    ↓
                                              └─→ M3-1 ←───────────┘
                                                  M3-2
                                                  M3-3 ←─── M2-2
                                                  M3-4
                                                    │
                                                    ↓
                                                  M3 出口
                                                    │
                                                    ↓
                              M4-1（迭代启动）→ M4-2（随 M0-M3 同步）→ M4-3 + M4-4（迭代收尾）
```
