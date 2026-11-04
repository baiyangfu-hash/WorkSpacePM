# Checklist

## 阶段 1：路线图全量重排

- [x] PRD §6 迭代路线图已重排为 V2.0.1~V2.5 七个版本
- [x] V2.0.1 基座补齐版交付物和验收标准已定义
- [x] V2.1 变更管理增强增加 004 安全问题吸收修复
- [x] 79 条改进建议已重新分类到 V2.0.1~V2.5
- [x] PRD 版本号和变更记录已更新

## 阶段 2：规范全量修订

### PM 规范修订

- [x] 042 V2.3.0 状态机命名已改为 draft/submitted/under_review 等
- [x] 042 V2.3.0 conditionally_approved 状态已补充定义和流转
- [x] 042 V2.3.0 archived 状态已补充定义和流转
- [x] 042 V2.3.0 看板列标识和 STATUS_LABELS 已更新
- [x] 016 V1.1.0 变更管理目录已改为 00_项目管理/04_变更管理/
- [x] 016 V1.1.0 已引用 043 规范
- [x] 016 V1.1.0 PLC/Python 项目目录差异已明确
- [x] 040 §6 三个子表结构在模板中完整定义
- [x] generator.py §6 渲染逻辑已补全三个子表空表格
- [x] parser.py §6 解析逻辑已增加

### PLC 规范修订

- [x] 906 V2.0.0 已覆盖 FB_TONR 累加定时器
- [x] 906 V2.0.0 已覆盖三段式定时器调用模式
- [x] 906 V2.0.0 已覆盖批量调用模式
- [x] 906 V2.0.0 libraryDirectories 已改为 libraries
- [x] 906 V2.0.0 与 903/905 不再矛盾
- [x] 905 §4.3 定时器示例已改用 FC_INT_TO_TIME
- [x] 905 与 903/906 不再矛盾
- [x] 023 V2.1.0 §6.4.2/§6.5.2 定时器示例已改用 FC_INT_TO_TIME
- [x] 023 V2.1.0 §6.5.2 METHOD 已删除 CALL_ 前缀
- [x] 023 V2.1.0 §5.3.2 已删除中文变量名
- [x] PLC 规范间 6 项直接矛盾全部修复

### Python 规范修订/新增

- [x] 210 V1.2.0 行长度阈值已从 79 调整为 120
- [x] 210 V1.2.0 PySide6 GUI 开发模式说明已补充
- [x] 210 V1.2.0 Click CLI 开发模式说明已补充
- [x] 220 V2.3.0 hatchling + pyproject.toml 打包模式已补充
- [x] 216 PySide6 GUI 开发规范已创建
- [x] 217 Click CLI 开发规范已创建

## 阶段 3：spec_registry.json 同步

- [x] SW-2026-008 (auto-pm) 已注册到 registry
- [x] SW-2026-007 (pm-mgr) lifecycle 已改为 deprecated
- [x] 所有修订规范的版本号变更已同步
- [x] 216/217 规范条目已新增
- [x] last_updated 时间戳已更新

## 阶段 4：文档再同步

- [x] PM_SESSION 当前焦点已更新为 V2.0.1 基座补齐
- [x] PM_SESSION 下一步已更新为 V2.0.1 各交付物
- [x] PM_SESSION 状态摘要已反映路线图重排
- [x] TEC V2.0.1 技术决策已补充（编码崩溃修复方案、检查器深度增强方案）
- [x] TEC 变更记录已更新

## 范围边界核查

- [x] V2.0.1-A/C 代码变更已实施（原规划仅规划不实施，但用户要求直接实施）
- [x] 未修改 DJ-2026-000/SysLib 的 REQ 实际内容
- [x] 未修复 SW-2026-004 的安全问题（V2.1 吸收时修复）

## 阶段 5：V2.0.1 代码实施核查（2026-06-22）

### V2.0.1-A: site 编码崩溃修复

- [x] auto_pm/__main__.py 已创建，设置 PYTHONUTF8=1
- [x] auto_pm/cli/__main__.py Windows GBK 终端编码兼容已修复
- [x] python -m auto_pm 在 Windows GBK 环境下正常运行

### V2.0.1-C: 042/016 规范对齐代码实施

- [x] C-01: ChangeStatus Literal 包含 archived
- [x] C-02: STATUS_FLOW 包含 completed→archived + archived 终态
- [x] C-03: STATUS_LABELS 包含 archived: "已归档"
- [x] C-04: APPROVAL_CONCLUSIONS 包含 conditionally_approved（已存在，确认无需修改）
- [x] C-05: _check_transition_guards 包含 archived 门禁
- [x] C-06: transition_status approved/conditionally_approved/rejected 写入逻辑已对齐
- [x] C-07: transition_status 包含 archived 分支
- [x] C-08: rejected→draft 门禁要求附 comment
- [x] C-09: implementing→approved 退回路径已对齐
- [x] C-10: conditionally_approved→implementing 门禁要求附 comment
- [x] C-11: 审批环节名称使用中文语义化标签
- [x] C-12: _CHANGE_SEARCH_PATHS 包含 Python 路径（已存在，确认无需修改）
- [x] C-13: scan_change_files 支持 Python 路径（已对齐，确认无需修改）
- [x] C-14: _PROJ_SEARCH_PATHS 包含 Python 路径（已对齐，确认无需修改）
- [x] C-15: _get_change_file_path 支持 PLC+Python 双路径搜索
- [x] C-16: _find_change_file 支持 PLC+Python 双路径搜索
- [x] C-17: find_ledger_file 支持 PLC+Python 双路径搜索
- [x] C-18: _infer_status_from_approval 包含 conditionally_approved 推断路径
- [x] C-19: archived 状态说明（无法从审批章节推断，需依赖 §3.4 显式读取）
- [x] 19 项冲突全部修复

### 测试验证

- [x] pytest tests/change/ 99 passed
- [x] pytest tests/test_bug2_sync_changes.py 6 passed
- [x] 总计 105 passed, 0 failed

### 文档同步

- [x] CHANGELOG.md 已添加 [0.2.1] 版本条目
- [x] PM_SESSION 已更新 §2/3/5/6/7/8/9
- [x] spec.md 已添加 Implementation Status 章节
- [x] tasks.md 已添加阶段 5 任务
- [x] checklist.md 已添加阶段 5 核查项
