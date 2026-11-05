# V2.1 变更管理增强 - 验收检查清单

> 关联 spec.md / tasks.md

## M0：基座清理

### M0-1：V2.0.1-D PLC 规范矛盾代码修复
- [ ] 41 个矛盾代码片段全部修复
- [ ] 905 §4.3 TIME→DINT 修复
- [ ] 023 §6.4.2/§6.5.2 TIME→DINT 修复
- [ ] 023 §6.5.2 METHOD CALL_ 前缀移除
- [ ] 023 §5.3.2 中文变量名改为英文前缀
- [ ] 906 §3.1 libraryDirectories→libraries
- [ ] 907 §2.2 libraryDirectories→libraries
- [ ] specmgr check 无矛盾告警
- [ ] 005_变更记录_CHG.md 已更新

### M0-2：V2.0.1-E spec_registry.json 同步
- [ ] SW-2026-008 已注册（domain: cross-domain, lifecycle: stable）
- [ ] SW-2026-007 已标记 deprecated + replaced_by: ["SW-2026-008"]
- [ ] last_updated 已更新
- [ ] specmgr check 通过

### M0-3：list_view.py mypy 修复
- [ ] Qt.AlignTop → Qt.AlignmentFlag.AlignTop 等 8 处已改
- [ ] ruff format --check 通过
- [ ] mypy auto_pm/ 全绿

### M0-4：test_project_list.py flaky 修复
- [ ] isVisible() 已改用 isVisibleTo(parent)
- [ ] 文件已纳入 git 跟踪
- [ ] pytest 连续 3 次无 flaky

### M0-5：6 个 UI 测试 QMessageBox 阻塞修复
- [ ] CreateChangeDialog._load_projects 已优化
- [ ] test_iteration1_interactive.py 无阻塞
- [ ] test_iteration2_interactive.py 无阻塞
- [ ] test_iteration3_interactive.py 无阻塞
- [ ] test_iteration4_interactive.py 无阻塞
- [ ] test_change_dialogs.py 无阻塞
- [ ] test_final_acceptance.py 无阻塞

### M0 出口
- [ ] 全量测试通过（875+ 测试无回归）
- [ ] mypy auto_pm/ 全绿
- [ ] ruff check + format 通过

## M1：变更单章节结构修正

### M1-1：§6.1 增加"风险等级"和"缓解措施"字段
- [ ] generator.py §6.1 表格含 5 列（约束维度/影响程度/影响描述/风险等级/缓解措施）
- [ ] models.py ChangeRequest 含 risk_level/mitigation 字段
- [ ] parser.py 可解析新增字段
- [ ] tests/change/test_generator.py::test_section_6_1_fields 通过
- [ ] tests/change/test_parser.py::test_parse_risk_level_mitigation 通过

### M1-2：§10 改为三节结构
- [ ] generator.py §10 含三节（10.1验证项/10.2跨领域联动/10.3结论）
- [ ] markdown_editor.py append_to_verification_table 适配 §10.3
- [ ] markdown_editor.py update_verification_conclusion 适配 §10.3
- [ ] parser.py 可解析 §10.2 跨领域联动验证
- [ ] tests/change/test_generator.py::test_section_10_three_subsections 通过
- [ ] tests/change/test_markdown_editor.py::test_append_to_verification_table_v2 通过

### M1-3：§11 版本详细变更说明补全
- [ ] generator.py §11 为"版本详细变更说明"
- [ ] generator.py §12 为附录
- [ ] parser.py 适配 §11/§12 新结构
- [ ] tests/change/test_generator.py::test_section_11_version_details 通过

### M1-4：文档版本号对齐 040 模板
- [ ] generator.py 渲染的"文档版本"与 040 模板一致
- [ ] 单元测试验证版本号一致

### M1-5：040 §3.4 变更状态字段定义
- [ ] 040 V2.2.0 §3.4 含"变更状态"字段定义
- [ ] 040 规范 frontmatter 版本号已更新
- [ ] specmgr check 通过

### M1 出口
- [ ] 新增单元测试全部通过
- [ ] 全量测试无回归
- [ ] 旧格式变更单可被 parser 兼容解析

## M2：影响分析与审批记录持久化

### M2-1：DB schema 扩展
- [ ] impact_analysis 表已创建
- [ ] approval_history 表已创建
- [ ] ImpactAnalysisRepository 类已实现
- [ ] ApprovalHistoryRepository 类已实现
- [ ] tests/db/test_repository.py::test_impact_analysis_repo 通过
- [ ] tests/db/test_repository.py::test_approval_history_repo 通过

### M2-2：ChangeRequestRepository 扩展
- [ ] save_impact_analysis 方法可用
- [ ] get_impact_analysis 方法可用
- [ ] save_approval_record 方法可用
- [ ] list_approval_history 方法可用
- [ ] 4 个方法单元测试通过

### M2-3：ChangeService 集成
- [ ] transition_status 同步写入 approval_history
- [ ] create_change_request 同步写入 impact_analysis
- [ ] update_change_request 同步更新 impact_analysis
- [ ] tests/change/test_change_service_db.py 集成测试通过

### M2-4：parser.py 解析增强
- [ ] parser.py 解析 §6.1 风险等级和缓解措施
- [ ] parser.py 解析 §10.2 跨领域联动验证
- [ ] parser.py to_impact_analysis(cr) 方法可用
- [ ] tests/change/test_parser.py::test_to_impact_analysis 通过

### M2 出口
- [ ] 新增单元/集成测试全部通过
- [ ] 全量测试无回归
- [ ] DB schema 迁移脚本可执行

## M3：GUI 变更管理增强

### M3-1：变更单编辑表单
- [ ] EditChangeDialog 类已实现
- [ ] 支持修改 background/necessity/references/planned_date/urgency
- [ ] 支持修改 §6 影响分析
- [ ] change_detail_panel.py 已集成
- [ ] tests/ui/test_edit_change_dialog.py 通过

### M3-2：传播链可视化
- [ ] propagation_view.py 已实现
- [ ] QGraphicsView 节点连线展示
- [ ] 空传播链显示"无跨领域影响"
- [ ] change_detail_panel.py 已集成
- [ ] tests/ui/test_propagation_view.py 通过

### M3-3：审批时间线
- [ ] approval_timeline.py 已实现
- [ ] 从 DB approval_history 读取
- [ ] change_detail_panel.py 已集成
- [ ] tests/ui/test_approval_timeline.py 通过

### M3-4：变更管理增强
- [x] 创建向导分步表单（基本信息 → 变更描述 → 提交确认，QWizard 实现）
- [ ] 状态流转可视化状态机 + 一键流转
- [ ] 列表筛选增强（状态/领域/紧急程度/项目）
- [ ] UI 测试覆盖

### M3 出口
- [ ] 新增 UI 测试全部通过
- [ ] 全量测试无回归
- [ ] GUI 冒烟测试通过

## 最终出口

### 版本号统一
- [ ] pyproject.toml version = "0.3.0"
- [ ] CHANGELOG.md 新增 [0.3.0] 条目
- [ ] PRD 版本 V2.0.3 → V2.1.0
- [ ] PM_SESSION §2 Current Focus = V0.3.0
- [ ] PM_SESSION §8 Handoff Notes = V0.3.0
- [ ] 005_变更记录_CHG.md 新增 V2.1.0 变更记录
- [ ] CHG-SW-2026-008.md 变更单状态为 archived（dogfooding）
- [ ] 版本变更台帐含 V0.3.0 条目（dogfooding）

### 质量门禁
- [ ] ruff check auto_pm/ tests/ 通过
- [ ] ruff format --check auto_pm/ tests/ 通过
- [ ] mypy auto_pm/ 全绿
- [ ] pytest tests/ -x 全部通过
- [ ] 测试覆盖率 >=85%

### 文档同步
- [ ] PM_SESSION §4 Artifacts Index 已更新
- [ ] PM_SESSION §5 Logs 新增迭代记录
- [ ] PM_SESSION §6 Implementation Log 已回写
- [ ] PM_SESSION §7 Verification Log 已回写
- [ ] PM_SESSION §8 Handoff Notes 已更新
- [ ] PM_SESSION §9 Next Actions 已更新
- [ ] PRD §6 路线图新增 V2.1.0 章节
