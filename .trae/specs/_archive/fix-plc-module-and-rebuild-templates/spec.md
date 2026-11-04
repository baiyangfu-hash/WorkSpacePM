# PLC 专项功能修复与模板重构 Spec

## Why

auto-pm 项目（V0.2.1）整体架构成熟，但 PLC 专项功能存在系统性缺陷：模板与实际项目严重脱节（22 项差距）、规范覆盖度仅 8%、CLI 层绕过 Service 层、SubstanceChecker 实现不规范。当前用 `plc init` 创建的项目无法通过 `plc check`，无法生成符合 LSP-907 规范的真实 PLC 项目结构。需要修复 6 项 Critical + 10 项 Major 问题，并将模板重构为 3 套（公共库/公共库验证/标准单机项目），以支持用户确认的三种项目模式。

## What Changes

### 前置：Git 提交环境修复
- 诊断并解决 pre-commit hook 阻塞问题（specmgr check + 代码风格检查）
- 将当前工作空间变更提交，建立干净基线

### P0: PLC 基础架构合规修复
- **C-1**: 删除模板根级 `.plc.json.jinja`，仅保留 `02_PLC程序/` 子目录下的
- **C-2**: 修正 `_minimal_plc_json` 硬编码 libraries 路径，改为根据项目位置动态计算
- **C-3**: CLI 层改用 PlcService（`plc check`/`plc repair`/`plc standardize` 调用 PlcService 而非直接 PlcChecker/PlcRepairer）
- **H-1**: 修正 `STD_DIRS` 对齐实际项目结构（11 个标准目录）
- **H-2**: 统一 init 入口（`plc init` 内部调用 `project create --stack plc` 或废弃）

### P1: 模板重构为 3 套
- 新建 `plc-shared-library` 模板（参考 SysLib，libraries: []）
- 新建 `plc-test-suite` 模板（参考 DJ-2026-000，扁平结构）
- 重构 `plc-standard` → `plc-standard-project` 模板（参考 DJ-2026-005，11 标准目录）
- 充实 PRD 文档模板内容（字数 800+，减少占位符）
- 添加 DB1/OB1/Test/common 等业务子目录骨架
- 添加 GlobalVars.db、.gitignore、.github/hooks/、项目立项表模板

### P1: SubstanceChecker 修复
- **C-4**: 修正字数统计语义（中文按字数，英文按词数，阈值调整 800/1000）
- **C-5**: 充实模板文档内容避免触发实质化 WARN
- **H-6**: 修正章节正则 `^##\s*` 允许无空格
- **H-7**: 占位符密度 >70% 报 FAIL（符合 PRD P0-002）

### P2: 检查器与修复器增强
- **H-8**: retrofit 增强（PLC 项目补全 .plc.json/PM_SESSION/PRD）
- **H-10**: libraries 路径深度校验（检查 SysLib/timer/FB_TON.scl 等关键文件）
- 添加 `plc check --substance` 和 `plc check --fix` 选项

### P2: 测试补全
- **C-6**: 补全 `plc init`/`plc repair`/`plc standardize` CLI 测试
- **H-9**: 修复 test_service.py 无效断言（`or True`）
- 添加端到端测试（init → check → repair → check）

## Impact

- **Affected specs**: 
  - `.trae/specs/rebuild-auto-pm-v2-unified/`（V2.0 重写依据）
  - `.trae/specs/deep-audit-auto-pm-plc-readiness/`（审查依据）
- **Affected code**:
  - `auto_pm/cli/plc/__init__.py`（CLI 层改用 PlcService）
  - `auto_pm/plc/checker.py`（扩展检查项）
  - `auto_pm/plc/repairer.py`（修正 libraries 路径）
  - `auto_pm/plc/substance_checker.py`（修正字数统计）
  - `auto_pm/plc/models.py`（修正 STD_DIRS）
  - `auto_pm/plc/service.py`（暴露 check_substance）
  - `auto_pm/cli/project.py`（retrofit 增强）
  - `templates/plc-standard/`（重构为 3 套模板）
  - `tests/plc/` + `tests/cli/test_plc.py`（补全测试）
- **Affected docs**:
  - `00_项目基础信息/002_接口文档_INT.md`（同步 CLI 命令变更）
  - `00_项目基础信息/003_详细设计说明书_DSN.md`（同步架构变更）

## ADDED Requirements

### Requirement: 三种 PLC 项目模板
系统 SHALL 提供 3 套 Copier 模板以支持三种项目模式：
- `plc-shared-library`：公共库模板（参考 SysLib，模块化结构，libraries: []）
- `plc-test-suite`：公共库验证模板（参考 DJ-2026-000，扁平结构）
- `plc-standard-project`：标准单机项目模板（参考 DJ-2026-005，11 标准目录）

#### Scenario: 创建公共库
- **WHEN** 用户执行 `project create --stack plc --mode shared-library --name MyLib`
- **THEN** 生成含 actuator/communication/convert/counter/edge/log/pulse/timer/types 目录骨架的项目
- **AND** `.plc.json` 的 `libraries` 字段为空数组
- **AND** 项目通过 `plc check` 检查

#### Scenario: 创建标准单机项目
- **WHEN** 用户执行 `project create --stack plc --mode standard-project --name DJ-2026-010`
- **THEN** 生成含 11 个标准目录（00_项目管理/01_需求与设计/02_PLC程序/...）的项目
- **AND** `.plc.json` 位于 `02_PLC程序/02_PLC程序/` 下
- **AND** `libraries` 字段智能推断为 `"../../../01_SharedLibraries/SysLib"`
- **AND** 项目通过 `plc check` 检查

### Requirement: PLC CLI 通过 PlcService 层操作
系统 SHALL 强制 CLI 层通过 PlcService 操作 PLC 项目，不直接访问 PlcChecker/PlcRepairer。

#### Scenario: plc check 命令
- **WHEN** 用户执行 `plc check <ID>`
- **THEN** CLI 调用 `PlcService.check()` 而非直接 `PlcChecker`
- **AND** 支持 `--substance` 选项调用 `PlcService.check_substance()`
- **AND** 支持 `--fix` 选项调用 `PlcService.check(fix=True)`

### Requirement: libraries 路径智能推断
系统 SHALL 根据项目位置动态计算 SysLib 相对路径，而非硬编码。

#### Scenario: 根级项目
- **WHEN** `.plc.json` 位于项目根目录（如 DJ-2026-000 模式）
- **THEN** `libraries` 字段为 `"../01_SharedLibraries/SysLib"`

#### Scenario: 嵌套项目
- **WHEN** `.plc.json` 位于 `02_PLC程序/02_PLC程序/`（如 DJ-2026-005 模式）
- **THEN** `libraries` 字段为 `"../../../01_SharedLibraries/SysLib"`

### Requirement: SubstanceChecker 字数统计
系统 SHALL 按语言规则统计字数：中文按字符数，英文按词数。

#### Scenario: 中文文档
- **WHEN** 文档内容为中文且字符数 < 800
- **THEN** 报 WARN（字数不足）

#### Scenario: 占位符密度
- **WHEN** 文档占位符密度 > 70%
- **THEN** 报 FAIL（符合 PRD P0-002）

## MODIFIED Requirements

### Requirement: STD_DIRS 标准目录
`auto_pm/plc/models.py` 的 `STD_DIRS` SHALL 对齐 LSP-907 §3.1 和实际项目结构，包含 11 个标准目录：
```python
STD_DIRS = [
    "00_项目管理", "01_需求与设计", "02_PLC程序", "03_HMI设计",
    "04_现场调试", "04_驱动器与设备", "05_测试与验证", "06_文档与交付",
    "07_技术支持", "08_备件管理", "09_项目总结", "10_知识库"
]
```

### Requirement: plc init 命令
`plc init` SHALL 内部调用 `project create --stack plc`，或废弃并由 `project create --stack plc --mode <MODE>` 替代。

## REMOVED Requirements

### Requirement: 根级 .plc.json 模板
**Reason**: 违反 LSP-907 §3.1，.plc.json 应在 PLC 程序子目录
**Migration**: 删除 `templates/plc-standard/template/.plc.json.jinja`，仅保留 `02_PLC程序/` 子目录下的

### Requirement: 硬编码 libraries 路径
**Reason**: 对根级项目（如 DJ-2026-000）生成错误路径
**Migration**: 改为根据项目位置动态计算
