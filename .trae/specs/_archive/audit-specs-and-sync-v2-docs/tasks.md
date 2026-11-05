# Tasks

## 阶段 1：规范体系审查（核心交付）

- [x] Task 1: 审查 Python 规范体系（210/211/215/220）
  - [x] SubTask 1.1: 读取 210_Python编程规范_DEV.md，核对 auto-pm V2.0 代码遵循度（命名/风格/架构模式/类型注解）
  - [x] SubTask 1.2: 读取 211_Python代码审查规范_DEV.md，核对 V2.0 代码是否通过审查清单
  - [x] SubTask 1.3: 读取 215_Python接口文档模板_INT.md，核对 auto-pm INT 文档是否符合模板
  - [x] SubTask 1.4: 读取 220_Python项目打包规范_DEV.md，核对 auto-pm pyproject.toml/打包配置
  - [x] SubTask 1.5: 识别 Python 规范缺口（如 PySide6/Click CLI/GUI 测试等专项规范是否缺失）
  - [x] SubTask 1.6: 输出 Python 规范修订建议清单

- [x] Task 2: 审查 PLC 规范体系（LSP-905/904/903/906/907/908 + 023/815）
  - [x] SubTask 2.1: 读取 LSP-905 SCL 编程规范，核对 DJ-2026-000/SysLib 的 .scl 文件遵循度
  - [x] SubTask 2.2: 读取 LSP-904 注释规范，核对 FB_ValveControl.scl/OB1.scl 注释格式
  - [x] SubTask 2.3: 读取 LSP-903 定时器使用规范，核对项目定时器使用
  - [x] SubTask 2.4: 读取 LSP-906 错误预防规则，核对是否覆盖 V2.0 实践新问题
  - [x] SubTask 2.5: 读取 LSP-907 项目配置规范，核对 .plc.json 配置和目录结构
  - [x] SubTask 2.6: 读取 023/815 文档模板，核对 DJ-2026-000/SysLib 的 PRD 文档符合度
  - [x] SubTask 2.7: 输出 PLC 规范修订建议清单

- [x] Task 3: 审查 PM 规范体系（040/042 变更管理 + 010/016 项目结构）
  - [x] SubTask 3.1: 读取 040 变更单模板，核对 auto-pm 变更单生成器输出符合度
  - [x] SubTask 3.2: 读取 042 变更管理流程规范，核对 auto-pm 状态机/门禁规则实现
  - [x] SubTask 3.3: 读取 010 项目管理规范/016 项目结构模板，核对 auto-pm 项目骨架生成
  - [x] SubTask 3.4: 识别 PM 规范与 auto-pm 对接缺口
  - [x] SubTask 3.5: 输出 PM 规范修订建议清单

- [x] Task 4: 核查 spec_registry.json 一致性
  - [x] SubTask 4.1: 读取 spec_registry.json 完整内容
  - [x] SubTask 4.2: 比对每个 spec 条目的 canonical_path 与实际文件存在性
  - [x] SubTask 4.3: 比对 version/lifecycle/aliases 与实际规范文件 frontmatter
  - [x] SubTask 4.4: 识别不一致条目并输出同步建议

## 阶段 2：V2.0 文档全量同步

- [x] Task 5: TEC 文档升级到 V2.0.0
  - [x] SubTask 5.1: 读取当前 TEC V1.0.0 草稿完整内容
  - [x] SubTask 5.2: 读取 auto_pm/ 实际代码结构（ui/8 个子模块、core/、change/、db/ 等）
  - [x] SubTask 5.3: 重写 TEC 为 V2.0.0 已批准状态，对齐 PySide6 实际架构
  - [x] SubTask 5.4: 补充 V2.0 新增技术决策（PySide6 选型、项目中心式导航、多角色适配、数据真源策略）

- [x] Task 6: PRD 文档同步到 V2.0.0 实际基线
  - [x] SubTask 6.1: 读取 PRD V2.0.0 完整内容，定位 §10.2 偏差记录
  - [x] SubTask 6.2: 将 §10.2 偏差整合为正式基线（修改 §3.1 架构图、§3.4 CLI 命令、§2.2 User Stories 等）
  - [x] SubTask 6.3: 消除"待补录"状态，使文档反映实际实现
  - [x] SubTask 6.4: 更新版本变更记录表

- [x] Task 7: INT 文档核对与同步
  - [x] SubTask 7.1: 核对 CLI-07 `project import` 实际实现（CLI 层直接处理 vs Service 方法）
  - [x] SubTask 7.2: 核对 SVC-06/07/08 声明与实际 Service 层 API 一致性
  - [x] SubTask 7.3: 修正 INT 中不一致的接口声明
  - [x] SubTask 7.4: 更新 INT 版本变更记录

- [x] Task 8: DSN 文档核对与同步
  - [x] SubTask 8.1: 核对 DSN §4.1 架构图与实际 auto_pm/ui/ 8 个子模块一致性
  - [x] SubTask 8.2: 补充 navigation/change_center/dialogs 等实际模块的设计说明
  - [x] SubTask 8.3: 核对数据流设计与实际实现一致性
  - [x] SubTask 8.4: 更新 DSN 版本变更记录

- [x] Task 9: CHANGELOG/README 同步
  - [x] SubTask 9.1: 更新 CHANGELOG.md 反映 V2.0 最终交付状态
  - [x] SubTask 9.2: 核对 README.md 与实际 CLI 命令/功能一致性

## 阶段 3：参考项目双重审查

- [x] Task 10: DJ-2026-000 双重审查
  - [x] SubTask 10.1: 运行 `auto-pm project list` 验证能否识别 DJ-2026-000
  - [x] SubTask 10.2: 运行 `auto-pm project show DJ-2026-000` 验证元数据读取
  - [x] SubTask 10.3: 运行 `auto-pm plc check DJ-2026-000` 验证 LSP-907 检查
  - [x] SubTask 10.4: 审查 REQ 空模板问题，分析根因
  - [x] SubTask 10.5: 提出"需求文档实质化引导"改进建议

- [x] Task 11: SysLib 双重审查
  - [x] SubTask 11.1: 运行 `auto-pm project list` 验证能否识别 SysLib
  - [x] SubTask 11.2: 运行 `auto-pm plc check SysLib` 验证 LSP-907 检查（库项目特殊处理）
  - [x] SubTask 11.3: 审查 SysLib 的 REQ 空模板问题
  - [x] SubTask 11.4: 审查 SysLib 作为"库项目"的管理差异（libraries 字段、FB 接口文档等）

- [x] Task 12: SW-2026-004 双重审查
  - [x] SubTask 12.1: 运行 `auto-pm project list` 验证能否识别 SW-2026-004
  - [x] SubTask 12.2: 验证 auto-pm 能否识别 004 的技术栈不符（PyQt5 vs PRD 声明 PySide6）
  - [x] SubTask 12.3: 审查 004 自身问题清单（UserStore 硬编码/API 路由无 auth/影响分析未持久化）
  - [x] SubTask 12.4: 提出 auto-pm 规范合规深度检查能力改进建议

## 阶段 4：汇总与输出

- [x] Task 13: 输出《规范体系审查报告》
  - [x] SubTask 13.1: 汇总 Python/PLC/PM 三个域的审查发现
  - [x] SubTask 13.2: 汇总 spec_registry.json 一致性核查结果
  - [x] SubTask 13.3: 形成完整审查报告，包含修订建议清单

- [x] Task 14: 输出《参考项目双重审查报告》
  - [x] SubTask 14.1: 汇总 DJ-2026-000/SysLib/SW-2026-004 的审查发现
  - [x] SubTask 14.2: 形成完整审查报告，包含 auto-pm 改进建议

- [x] Task 15: 输出《auto-pm V2.1+ 改进建议清单》
  - [x] SubTask 15.1: 汇总所有审查发现的改进建议
  - [x] SubTask 15.2: 按优先级（P0/P1/P2）和建议纳入版本（V2.1/V2.2/V2.3+）分类
  - [x] SubTask 15.3: 形成完整改进建议清单

# Task Dependencies

- Task 5~9（文档同步）依赖 Task 1~4（规范审查）的发现 ✅
- Task 10~12（参考项目审查）可与 Task 1~4（规范审查）并行 ✅
- Task 13~15（汇总输出）依赖 Task 1~12 全部完成 ✅
- Task 5/6/7/8/9 之间可并行（不同文档独立）✅
- Task 10/11/12 之间可并行（不同项目独立）✅
