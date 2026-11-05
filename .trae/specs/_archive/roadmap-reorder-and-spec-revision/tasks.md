# Tasks

## 阶段 1：路线图全量重排

- [x] Task 1: 重排 PRD §6 迭代路线图
  - [x] SubTask 1.1: 读取当前 PRD §6 完整内容，理解原 V2.0~V2.5 规划
  - [x] SubTask 1.2: 基于 79 条改进建议，将建议重新分类到 V2.0.1~V2.5 七个版本
  - [x] SubTask 1.3: 重写 PRD §6，插入 V2.0.1 基座补齐版，调整 V2.1~V2.5 交付物和验收标准
  - [x] SubTask 1.4: 更新 PRD 版本号和变更记录

## 阶段 2：规范全量修订（8 个现有 + 2 个新增）

### PM 规范修订（对齐 auto-pm）

- [x] Task 2: 修订 042 变更管理流程规范 V2.2.0 → V2.3.0
  - [x] SubTask 2.1: §5.2 状态机命名改为 draft/submitted/under_review/approved/conditionally_approved/rejected/implementing/pending_acceptance/accepting/completed/closed/archived
  - [x] SubTask 2.2: 补充 conditionally_approved 状态定义和流转规则
  - [x] SubTask 2.3: 补充 archived 状态定义和流转规则（completed → archived）
  - [x] SubTask 2.4: 更新看板列标识和 STATUS_LABELS 中文标签
  - [x] SubTask 2.5: 更新 frontmatter 版本号和变更记录

- [x] Task 3: 修订 016 项目结构模板 V1.0.0 → V1.1.0
  - [x] SubTask 3.1: §4.1 变更管理目录从 06_变更管理/ 改为 00_项目管理/04_变更管理/
  - [x] SubTask 3.2: 引用 043 规范作为详细目录结构依据
  - [x] SubTask 3.3: 明确 PLC 项目与 Python 项目的变更管理目录差异
  - [x] SubTask 3.4: 更新 frontmatter 版本号和变更记录

- [x] Task 4: 修订 040 变更单模板（补全 §6）
  - [x] SubTask 4.1: 确认 §6.1/6.2/6.3 三个子表结构在 040 模板中完整定义
  - [x] SubTask 4.2: 修订 auto_pm/change/generator.py §6 渲染逻辑，输出三个子表空表格
  - [x] SubTask 4.3: 修订 auto_pm/change/parser.py 增加 §6 解析逻辑

### PLC 规范修订（矛盾修复 + 过时更新）

- [x] Task 5: 重写 906 错误预防规则 V1.0.0 → V2.0.0
  - [x] SubTask 5.1: 覆盖 FB_TONR 累加定时器使用规则
  - [x] SubTask 5.2: 覆盖三段式定时器调用模式
  - [x] SubTask 5.3: 覆盖批量调用模式
  - [x] SubTask 5.4: 修正 libraryDirectories → libraries
  - [x] SubTask 5.5: 修正与 903/905 的矛盾条目
  - [x] SubTask 5.6: 更新 frontmatter 版本号和变更记录

- [x] Task 6: 修复 905 SCL 编程规范矛盾
  - [x] SubTask 6.1: §4.3 定时器示例改用 FC_INT_TO_TIME，删除 TIME 字面量
  - [x] SubTask 6.2: 确保与 903/906 不再矛盾
  - [x] SubTask 6.3: 更新 frontmatter 变更记录

- [x] Task 7: 修复 023 PLC 程序设计文档模板矛盾 V2.0.0 → V2.1.0
  - [x] SubTask 7.1: §6.4.2/§6.5.2 定时器示例改用 FC_INT_TO_TIME
  - [x] SubTask 7.2: §6.5.2 METHOD 删除 CALL_ 前缀
  - [x] SubTask 7.3: §5.3.2 删除中文变量名，改用英文变量名
  - [x] SubTask 7.4: 更新 frontmatter 版本号和变更记录

### Python 规范修订（过时更新 + 新增）

- [x] Task 8: 修订 210 Python 编程规范 V1.1.0 → V1.2.0
  - [x] SubTask 8.1: §5.2 行长度阈值从 79 调整为 120
  - [x] SubTask 8.2: 补充 PySide6 GUI 开发模式说明（信号槽/布局/QThread）
  - [x] SubTask 8.3: 补充 Click CLI 开发模式说明（命令组/参数/帮助文本）
  - [x] SubTask 8.4: 更新 frontmatter 版本号和变更记录

- [x] Task 9: 修订 220 Python 项目打包规范 V2.2.0 → V2.3.0
  - [x] SubTask 9.1: 补充 hatchling + pyproject.toml 打包模式
  - [x] SubTask 9.2: 保留 PyInstaller 模式作为可选方案
  - [x] SubTask 9.3: 更新 frontmatter 版本号和变更记录

- [x] Task 10: 新增 216 PySide6 GUI 开发规范
  - [x] SubTask 10.1: 编写规范内容（信号槽机制/布局管理/多角色适配/QThread/GUI 测试）
  - [x] SubTask 10.2: 注册到 spec_registry.json

- [x] Task 11: 新增 217 Click CLI 开发规范
  - [x] SubTask 11.1: 编写规范内容（命令组/参数定义/帮助文本/CLI 测试）
  - [x] SubTask 11.2: 注册到 spec_registry.json

## 阶段 3：spec_registry.json 同步

- [x] Task 12: 更新 spec_registry.json
  - [x] SubTask 12.1: 新增 SW-2026-008 (auto-pm) 条目
  - [x] SubTask 12.2: SW-2026-007 (pm-mgr) lifecycle 改为 deprecated
  - [x] SubTask 12.3: 同步所有修订规范的版本号变更
  - [x] SubTask 12.4: 新增 216/217 规范条目
  - [x] SubTask 12.5: 更新 last_updated 时间戳

## 阶段 4：文档再同步

- [x] Task 13: 同步 PM_SESSION
  - [x] SubTask 13.1: 当前焦点更新为 V2.0.1 基座补齐
  - [x] SubTask 13.2: 下一步更新为 V2.0.1 各交付物
  - [x] SubTask 13.3: 状态摘要反映路线图重排
  - [x] SubTask 13.4: 更新 last_updated 时间戳

- [x] Task 14: 同步 TEC
  - [x] SubTask 14.1: 补充 V2.0.1 技术决策（编码崩溃修复方案、检查器深度增强方案）
  - [x] SubTask 14.2: 更新变更记录

# Task Dependencies

- Task 1（路线图重排）无前置依赖，应最先执行 ✅
- Task 2~4（PM 规范修订）依赖 Task 1 确认的版本规划 ✅
- Task 5~7（PLC 规范修订）可与 Task 2~4 并行 ✅
- Task 8~11（Python 规范修订/新增）可与 Task 2~7 并行 ✅
- Task 12（registry 同步）依赖 Task 2~11 全部完成 ✅
- Task 13~14（文档再同步）依赖 Task 1 和 Task 12 完成 ✅

## 阶段 5：V2.0.1 代码实施（2026-06-22）

### V2.0.1-A: site 编码崩溃修复

- [x] Task 15: 修复 Windows GBK 编码崩溃
  - [x] SubTask 15.1: 创建 auto_pm/__main__.py，设置 PYTHONUTF8=1 环境变量
  - [x] SubTask 15.2: 修改 auto_pm/cli/__main__.py，Windows GBK 终端编码兼容

### V2.0.1-C: 042/016 规范对齐代码实施

- [x] Task 16: P0 — 状态机基础定义
  - [x] SubTask 16.1: enums.py ChangeStatus Literal 新增 archived（C-01）
  - [x] SubTask 16.2: models.py STATUS_FLOW 新增 completed→archived + archived 终态（C-02）
  - [x] SubTask 16.3: models.py STATUS_LABELS 新增 archived: "已归档"（C-03）

- [x] Task 17: P1 — 门禁和流转逻辑
  - [x] SubTask 17.1: change_service.py _check_transition_guards 新增 archived 门禁（C-05）
  - [x] SubTask 17.2: change_service.py transition_status 新增 archived 分支（C-07）
  - [x] SubTask 17.3: change_service.py rejected→draft 门禁要求附 comment（C-08）
  - [x] SubTask 17.4: change_service.py conditionally_approved→implementing 门禁要求附 comment（C-10）

- [x] Task 18: P2 — 解析器状态推断
  - [x] SubTask 18.1: parser.py _infer_status_from_approval 新增 conditionally_approved 推断路径（C-18）
  - [x] SubTask 18.2: parser.py archived 说明注释（C-19）

- [x] Task 19: P3 — Python 项目路径支持
  - [x] SubTask 19.1: change_service.py _get_change_file_path 支持 PLC+Python 双路径（C-15）
  - [x] SubTask 19.2: change_service.py _find_change_file 支持 PLC+Python 双路径（C-16）
  - [x] SubTask 19.3: path_resolver.py find_ledger_file 支持 PLC+Python 双路径（C-17）

- [x] Task 20: P4 — 审批环节名称语义化
  - [x] SubTask 20.1: change_service.py 审批环节名称从英文改为中文标签（C-11）

- [x] Task 21: 测试验证
  - [x] SubTask 21.1: pytest tests/change/ 99 passed
  - [x] SubTask 21.2: pytest tests/test_bug2_sync_changes.py 6 passed
  - [x] SubTask 21.3: 总计 105 passed, 0 failed
