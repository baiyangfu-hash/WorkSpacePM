# Checklist

## 阶段 1：规范体系审查

### Python 规范审查
- [x] 210_Python编程规范_DEV.md 已读取并核对 auto-pm V2.0 代码遵循度
- [x] 211_Python代码审查规范_DEV.md 已读取并核对 V2.0 代码审查清单
- [x] 215_Python接口文档模板_INT.md 已读取并核对 auto-pm INT 文档符合度
- [x] 220_Python项目打包规范_DEV.md 已读取并核对 pyproject.toml 配置
- [x] Python 规范缺口已识别（PySide6/Click CLI/GUI 测试等专项规范）
- [x] Python 规范修订建议清单已输出

### PLC 规范审查
- [x] LSP-905 SCL 编程规范已读取并核对 DJ-2026-000/SysLib 的 .scl 文件
- [x] LSP-904 注释规范已读取并核对 FB_ValveControl.scl/OB1.scl 注释
- [x] LSP-903 定时器使用规范已读取并核对项目定时器使用
- [x] LSP-906 错误预防规则已读取并核对 V2.0 实践覆盖度
- [x] LSP-907 项目配置规范已读取并核对 .plc.json 配置和目录结构
- [x] 023/815 文档模板已读取并核对 DJ-2026-000/SysLib PRD 文档符合度
- [x] PLC 规范修订建议清单已输出

### PM 规范审查
- [x] 040 变更单模板已读取并核对 auto-pm 变更单生成器输出
- [x] 042 变更管理流程规范已读取并核对 auto-pm 状态机/门禁规则
- [x] 010/016 项目管理/结构规范已读取并核对 auto-pm 项目骨架生成
- [x] PM 规范与 auto-pm 对接缺口已识别
- [x] PM 规范修订建议清单已输出

### spec_registry.json 一致性核查
- [x] spec_registry.json 完整内容已读取
- [x] 每个 spec 条目的 canonical_path 与实际文件存在性已比对
- [x] version/lifecycle/aliases 与实际规范文件 frontmatter 已比对
- [x] 不一致条目已识别并输出同步建议

## 阶段 2：V2.0 文档全量同步

### TEC 文档升级
- [x] 当前 TEC V1.0.0 草稿完整内容已读取
- [x] auto_pm/ 实际代码结构已读取（ui/8 个子模块、core/、change/、db/ 等）
- [x] TEC 已重写为 V2.0.0 已批准状态，对齐 PySide6 实际架构
- [x] V2.0 新增技术决策已补充（PySide6 选型、项目中心式导航、多角色适配、数据真源策略）
- [x] TEC frontmatter 已更新（version: V2.0.0, status: 已批准）

### PRD 文档同步
- [x] PRD V2.0.0 完整内容已读取，§10.2 偏差记录已定位
- [x] §10.2 偏差已整合为正式基线（§3.1 架构图、§3.4 CLI 命令、§2.2 User Stories 等已修改）
- [x] "待补录"状态已消除，文档反映实际实现
- [x] 版本变更记录表已更新

### INT 文档核对
- [x] CLI-07 `project import` 实际实现已核对（CLI 层直接处理 vs Service 方法）
- [x] SVC-06/07/08 声明与实际 Service 层 API 一致性已核对
- [x] INT 中不一致的接口声明已修正
- [x] INT 版本变更记录已更新

### DSN 文档核对
- [x] DSN §4.1 架构图与实际 auto_pm/ui/ 8 个子模块一致性已核对
- [x] navigation/change_center/dialogs 等实际模块的设计说明已补充
- [x] 数据流设计与实际实现一致性已核对
- [x] DSN 版本变更记录已更新

### CHANGELOG/README 同步
- [x] CHANGELOG.md 已更新反映 V2.0 最终交付状态
- [x] README.md 与实际 CLI 命令/功能一致性已核对

## 阶段 3：参考项目双重审查

### DJ-2026-000 审查
- [x] `auto-pm project list` 验证能否识别 DJ-2026-000 已执行
- [x] `auto-pm project show DJ-2026-000` 验证元数据读取已执行
- [x] `auto-pm plc check DJ-2026-000` 验证 LSP-907 检查已执行
- [x] REQ 空模板问题根因已分析
- [x] "需求文档实质化引导"改进建议已提出

### SysLib 审查
- [x] `auto-pm project list` 验证能否识别 SysLib 已执行
- [x] `auto-pm plc check SysLib` 验证 LSP-907 检查已执行
- [x] SysLib 的 REQ 空模板问题已审查
- [x] SysLib 作为"库项目"的管理差异已审查（libraries 字段、FB 接口文档等）

### SW-2026-004 审查
- [x] `auto-pm project list` 验证能否识别 SW-2026-004 已执行
- [x] auto-pm 能否识别 004 技术栈不符（PyQt5 vs PRD 声明 PySide6）已验证
- [x] 004 自身问题清单已审查（UserStore 硬编码/API 路由无 auth/影响分析未持久化）
- [x] auto-pm 规范合规深度检查能力改进建议已提出

## 阶段 4：汇总与输出

### 规范体系审查报告
- [x] Python/PLC/PM 三个域的审查发现已汇总
- [x] spec_registry.json 一致性核查结果已汇总
- [x] 完整审查报告已形成，包含修订建议清单

### 参考项目双重审查报告
- [x] DJ-2026-000/SysLib/SW-2026-004 的审查发现已汇总
- [x] 完整审查报告已形成，包含 auto-pm 改进建议

### auto-pm V2.1+ 改进建议清单
- [x] 所有审查发现的改进建议已汇总
- [x] 按优先级（P0/P1/P2）和建议纳入版本（V2.1/V2.2/V2.3+）已分类
- [x] 完整改进建议清单已形成

## 范围边界核查

- [x] 未修改任何规范文件本身（仅输出修订建议）
- [x] 未修改 auto-pm 代码（仅输出改进建议）
- [x] 未实施 V2.1+ 任何功能（仅记录建议）
- [x] 未修复 SW-2026-004 的实际问题（仅审查并提建议）
- [x] 未填写 DJ-2026-000/SysLib 的 REQ 实际内容（仅审查空模板问题并提改进建议）
