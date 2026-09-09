# Changelog

本文件记录 auto-pm (SW-2026-008) 的所有变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.3.3] - 2026-09-09

### Added

- **CHG-SCPT-2026-030** 新增平台中立 `continuity` CLI，公开 Work、Run、Lease、Checkpoint 与 Handoff v2 的事务操作入口；Git HEAD 与 owned-path dirty 状态由 CLI 独立采集。

### Fixed

- **CHG-SCPT-2026-028** 根启动器向 release 进程传递所属工作空间，使 `pm resume` 与 `context resolve` 无需额外 `-w` 也能读取 Workspace Registry。
- **CHG-SCPT-2026-029** 增加 SPEC 变更领域兼容；Decision Package 按项目编号消歧，跨项目同号且未指定项目时 fail-closed。

## [Unreleased] - 后 1.2.3 批次（CHG-165~186 补录）

> **说明**：本段补录 2026-08-27 起至 2026-09-06 间已执行但未入账的 22 张变更单，
> 分三个子批次：Cockpit OS 功能扩展（CHG-165~177）、稳定发布链路（NG-WP-11~17）、
> 法典治理（CHG-SPEC-001~008）。待下次正式 release 时合并归版本号。

### Added - Cockpit OS 全链路（CHG-SCPT-2026-165~177）

- **CHG-SCPT-2026-165** 落账门禁下沉基线建立
- **CHG-SCPT-2026-166** 落账门禁下沉：StageGateEngine G3 新增落账完整性 BLOCKER，PmSessionCheckService 新增落账新鲜度 WARN（2026-08-27）
- **CHG-SCPT-2026-167** 契约对账器：新增 SHC-017 SkillContractDriftChecker，以代码为唯一真源校验技能文档 C1~C4（2026-08-27）
- **CHG-SCPT-2026-168~169** 驾驶舱架构整合中间批次
- **CHG-SCPT-2026-170** 驾驶舱防空壳实质化体系、结构化决策包契约（W0）与跨领域穿透门禁（W1-1）落地闭环（2026-09-03）
- **CHG-SCPT-2026-171** 证据门禁扩展：Scope Gating 决策包白名单越界拦截、跨资产变更单存在性与真实证据物理硬门禁闭环（2026-09-04）
- **CHG-SCPT-2026-172** W2 批次可恢复 PM Saga 事务日志：8 步 WAL 顺序日志、Checkpoint 故障恢复、补偿回滚与 CLI 扩展（2026-09-04）
- **CHG-SCPT-2026-173** Cockpit OS Phase 0 WBS 0.1 契约层强类型 DTO：TransactionStatus 枚举及 5 个工作流核心 DTO，单测 17 passed 全绿（2026-09-04）
- **CHG-SCPT-2026-174** Cockpit OS Phase 1 WBS 1.1~1.2 事务沙箱 ChangeTransactionManager：快照备份、新建追踪、原子提交与回滚，单测 19 passed（2026-09-04）
- **CHG-SCPT-2026-175** Cockpit OS Phase 2 WBS 2.1 WorkflowOrchestrator.plan：方案规划流水线、项目校验、草稿复用/生成、规范动态绑定，单测 15 passed（2026-09-04）
- **CHG-SCPT-2026-176** Cockpit OS Phase 2 WBS 2.2 WorkflowOrchestrator.execute：执行流水线、事务沙箱原子回滚、verify_only 预检，单测 21 passed（2026-09-04）
- **CHG-SCPT-2026-177** Cockpit OS Phase 3 WBS 3.1 项目全生命周期归档与恢复引擎：ProjectArchiveService、领域就近路由、三道硬门禁、台账自动化（ARC 流水号），单测 45 passed（2026-09-04）

### Added - 稳定发布链路（NG-WP-11~17）

- **NG-WP-11** 冻结候选提交与制品构建：candidate `87183fb`（262 文件）+ wheel SHA-256 `ca47b787…`，886 文件 manifest 全通过（2026-09-05）
- **NG-WP-12** 稳定部署双槽骨架：`00_Infrastructure/auto_pm` 新增 launcher/releases/双指针/manifest（2026-09-05）
- **NG-WP-13** 根入口与环境解耦：main.py/bootstrap/launch 双槽化，全量回归 1946 passed/18 skip（2026-09-05）
- **NG-WP-14** Gate 2 非活动槽 `1.2.3-d41eb38` 部署与净化验证全过（2026-09-05）
- **NG-WP-15** 真实切流：CHG-SCPT-2026-184 原子切流 active=`1.2.3-f950525`，verify_release 465/465（2026-09-06）
- **NG-WP-16** 回退观察验收：7 场景、5/5 短观察和 ledger reconcile 全过（2026-09-06）
- **NG-WP-17** 历史规划归档：CHG-DOCU-2026-005 可逆归档 4 个历史规划文件（2026-09-06）；入口脱钩 CHG-SCPT-2026-185 完成（setup_env 不再 editable 安装 stable flat）

### Changed - 法典治理批次（CHG-SPEC-2026-001~008）

- **CHG-SPEC-2026-001** Obsidian 规范库 P0 治理修补：六门禁全绿、活跃区死链 0、INDEX 67/67（2026-09-06）
  - 副产品：拆单 8 项积压至 CHG-SCPT-2026-186 排期，「台帐」→「台账」错别字全链改名（拆单 #7）
- **CHG-SPEC-2026-002~004** Obsidian 规范库 P1~P4 治理立项（待批准）
- **CHG-SCPT-2026-186** SW 拆单 10 项整合立单（draft 待排期）：SPEC 域枚举、spec index 五域化、PATH 对齐、release 重切台账改名、spec check 9060 豁免、io_points 三安全列解析等

### Fixed

- **CHG-SCPT-2026-178** 前向治理更正：澄清 `1.2.3-d41eb38` 非当前 active，防止历史 §3 条目被错误推断为切流依据

## [1.2.3] - 2026-08-23


### Changed - CHG-SCPT-2026-164 驾驶舱 P2 代码质量收敛与工控现场友好排障增强

- **静态代码检查彻底清零 (0 Ruff Warnings)**：
  - 在 `pyproject.toml` 中为 QML Bridge、ModbusService 与 Logging 模块配置专用白名单（豁免 QML 约定的 `N802/N815` 驼峰规则），`ruff check` 实现 100% Clean Exit (0 告警)。
- **工控异常统一转译器正式上线 (`IndustrialErrorMapper`)**：
  - 新增 `auto_pm/infrastructure/error_handling/error_mapper.py`，将底层 Python 原生异常（`WinError 10061` 连接拒绝、`10060` 通信超时、`10049` 网卡不可用、`10054` 远端重置、`struct.error` 字节序解析失败等）自动转译为带有现场明确排障操作指引的中文诊断信息。
- **Modbus QML 桥接友好排障改造 (`ModbusBridge`)**：
  - 全面接入 `IndustrialErrorMapper`，在保证 IEC 62443 完整堆栈日志可审计性的同时，向 QML 前端提供现场友好诊断信息。
- **自动化测试集补充**：
  - 新增 `tests/infrastructure/test_error_mapper.py`（10 项单测），全量回归测试集增至 1637 项并 100% 通过。

## [1.2.2] - 2026-08-22

### Fixed - CHG-SCPT-2026-163 驾驶舱 P1 级架构安全加固与工控全域测试安全网深化

- **Bridge 层异常可审计性全面加固 (IEC 62443)**：
  - 改造 7 个 QML Bridge 桥接文件（`workbench`, `change`, `delivery`, `file_watcher`, `spec`, `ai_context`, `modbus`），统一接入 `logger.warning(..., exc_info=True)`，消除 120+ 处异常静默吞噬，实现工控现场丢帧与异常的毫秒级追踪。
- **PLC 项目检查器核心矩阵单测建立 (`PlcChecker`)**：
  - 新增 `tests/plc/test_plc_checker_matrix.py`（5 项矩阵单测），覆盖 `.plc.json` 必填项/库路径校验、`PM_SESSION` 行数阈值（150/300行警告与阻断）、`PRD/` 标准四件套识别与 `02_PLC程序` SCL 规范深度集成。
- **Modbus QML 桥接多线程单测建立 (`ModbusBridge`)**：
  - 新增 `tests/modbus/test_modbus_bridge.py`（4 项桥接单测），全面验证 `getNetworkInterfaces()` 本地网卡枚举、`connectDevice/disconnectDevice` 状态机流转、`readRegisters/writeRegister` 信号槽推送及 JSON 配置流转。

## [1.2.1] - 2026-08-22

### Fixed - CHG-SCPT-2026-162 驾驶舱严苛审计缺陷修复与工业级安全加固

- **P0 运行时 NameError 彻底根治**：
  - 修复 `auto_pm/ui/qml/bridges/system_bridge.py` 顶层缺失 `Path` 导入（F821），彻底解决 QML 调用 `syncDocs` 与 `checkDocs` 时触发的隐形 `NameError`。
  - 修复 `auto_pm/application/workbench_facade.py:815` 属性引用错误（修正为 `self._project_service.workspace_root`），保障 5 大过程组 Stage-Gate 门禁评估正常流转。
  - 修复 `auto_pm/application/core/prototype_service.py:357` 降级分支模板变量 `html_code` 未定义缺陷。
- **工控通信与 PLC 门禁测试安全网全面补齐**：
  - 修正 `pyproject.toml` 的 pytest 覆盖率路径与源目录映射（`--cov=auto_pm`，`source = ["auto_pm"]`）。
  - 新增 `tests/modbus/test_modbus_service_unit.py`（13 项全量单测），全面覆盖 CDAB 浮点解码、FC01~FC06 报文编解码及 JSON 配置流转。
  - 新增 `tests/plc/test_checker_lsp905_rules.py`（7 项防御性单测），覆盖 CASE ELSE、TON 定时器三段式、T# 字面量及变量前缀规范。
- **代码质量与类型安全全面收敛**：
  - 通过 Ruff 修复 68 处静态代码问题，清除无效表达式、未用变量及无用导入。
  - 彻底清零 `auto_pm` 生产源码中的 mypy 类型报错（DTO 参数构造、CLI 配置类型转换）。
  - 规范化 Bridge 层异常日志上报，引入 `logger.warning(..., exc_info=True)`，消除静默吞噬。

## [1.2.0] - 2026-08-21

### Added - CHG-SCPT-2026-161 驾驶舱工业逆向摄取 (PlcIngest) 与 HMI 拓扑自适应标准 (STD-909) 落地

- **PLC 逆向摄取服务正式化 (PlcIngestService)**：新增 `auto_pm/application/plc/ingest_service.py`，提供 Python 毫秒级 ETL 逆向流水线，支持批量抽取 3,000+ 变量并自动生成 `io_points.csv`、`communications.yml`、`VAR.md`、`015_IO.md`、`016_PLC.md`、`018_FLOW.md` 等 6 份黄金资产。
- **PLC CLI 命令挂载**：`auto_pm/ui/cli/plc/` 增加 `plc ingest --src <源路径> --pid <ID>` 顶级命令。
- **HMI 原型拓扑自适应 (STD-909 §3.3)**：`PrototypeService.init` 与 CLI 增加 `--topology [infeed|outfeed|both]` 选项，自动根据设备产线位置裁剪 HTML 与 JS 导航。
- **模板底盘彻底去污**：清除 `templates/plc-standard-project` 与 `templates/industrial_hmi` 中的所有写死业务，重塑为纯净可插拔通用底座。
- **双技能协同契约标准化**：重构 `pm-workflow` 与 `plc-electrical-engineer`，建立明确的 Handoff 交接卡点。

## [1.1.0] - 2026-07-19

### Added - CHG-SCPT-2026-132 集成全局公共 Modbus TCP 联调调试模块

- **Modbus 模块及服务新建**：新增 `auto_pm/modbus/modbus_service.py` 核心服务，支持 Ping 链路诊断、连接与仿真管理、所有主流读取/写入功能码测试、并发网格区间扫描探测，并内置模拟物理波形的信号发生器。
- **QML 桥接绑定**：新增 `auto_pm/modbus/modbus_bridge.py`，暴露 Slot 并通过 `QThreadPool` 实现非阻塞并发扫描与实时信号趋势定时推送。
- **QML 页面与组件开发**：
  - 新建 `ModbusDebuggerView.qml`，包含完整的连接卡、读取卡、LED 16位位解析器、实时监测表、折线趋势图、扫描网格、写入槽及物理报文 Hex 控制台。
  - 新建 `ModbusBitExpander.qml` 二进制 LED 点阵可交互操作组件。
  - 新建 `ModbusTrendCanvas.qml` 定时 Canvas 折线绘制曲线。
  - 新建 `ModbusScannerGrid.qml` 10x10 并发区间活跃指示灯网格。
- **导航与上下文集成**：在 `main.qml` 侧边栏轨道 3 公共工具新增入口并将视图挂载在 StackLayout 索引 8 处；在 `qml_main_window.py` 注册 `modbusBridge` 上下文属性。
- **单元测试补充**：在 `tests/modbus/test_modbus_service.py` 补充 25 条功能用例。
- **文档更新**：更新了 `README.md` 功能说明，并在 `02_设计/` 目录下的 PRD、INT 和 UI 说明文档中补齐了 Modbus 联调工坊的全部需求、接口设计与原型定义。

## [1.0.0] - 2026-07-09

### Added - CHG-SCPT-2026-107 V1.0.0 HTML 原型 V7 第 4 阶段收尾落地

- **LoadingOverlay.qml 新建**：异步操作加载指示组件（对齐 V7 .loading-overlay L744-772），深色半透明遮罩 rgba(2,6,23,0.7) + Canvas 绘制环形 spinner（primary 色前景弧 + 淡色背景环）+ RotationAnimation 1s 旋转 + Behavior on opacity 0.2s 平滑过渡 + 可配置 message/spinnerSize/active 属性
- **FutureCapability.qml 新建**：未实现功能灰化占位组件（对齐 V7 .future-capability L774-793 + L1145-1152），Canvas 绘制 dashed 虚线圆角边框 + 旋转 45deg 黄色角标"🚀 M4 迭代解锁" + 锁图标 + 标题 + 描述 + 禁用按钮（opacity:0.5）+ 可配置 title/description/buttonText/badgeText/iconText 属性

### Changed - CHG-SCPT-2026-107 V1.0.0 视图集成 + 版本号三件套升级

- **PlatformDashboardView.qml**：新增 `_loading` 属性 + `loadData()` 控制 + LoadingOverlay 组件实例集成（异步加载驾驶舱数据时显示遮罩）
- **WorkspaceView.qml**：文档 Tab + 变量表 Tab 占位从纯文本升级为 FutureCapability 组件（对齐 V7 L1145-1152 变量表占位设计）
- **版本号三件套升级**：pyproject.toml `0.9.2`→`1.0.0` + CHANGELOG.md 新增 [1.0.0] 章节 + 006_技术债评估报告.md frontmatter `V0.9.2`→`V1.0.0` + main.qml 4 处版本号 `V0.9.3`→`V1.0.0`（title/header 注释/侧边栏版本/状态栏）+ scripts/gui_smoke_test.py `V0.9.3`→`V1.0.0`

### Verified - CHG-SCPT-2026-107 V1.0.0 全量门禁 + GUI 冒烟

- ruff check auto_pm/ 0 errors
- mypy auto_pm/ 0 errors（127 source files，B1/B3 修复后已消除所有错误）
- change/core/application 测试全通过
- QML 测试全通过
- spec 规范测试全通过
- PM_SESSION size 元测试全通过
- LoadingOverlay/FutureCapability 组件加载验证通过
- V1.0.0 发布评估：HTML 原型 V7 四阶段全部落地（CHG-102~107 闭环），版本号三件套一致

### Notes - CHG-SCPT-2026-107 V1.0.0 里程碑说明

- **HTML 原型 V7 四阶段落地完成**：CHG-102（视觉系统升级+导航框架重构）+ CHG-103（变更中心 Split/Ledger）+ CHG-104（TD-A04 跨项目单号过滤修复）+ CHG-105（TD-A04 修复）+ CHG-106（平台驾驶舱 KPI/状态机/时间线）+ CHG-107（Loading Overlay + Future Capability + 收尾门禁 + V1.0.0）
- **V1.0.0 语义化版本**：MAJOR 1.0.0 标志首个稳定发布版本，HTML 原型 V7 全部组件落地，可对外发布
- **后续路线**：M4 迭代解锁变量表编辑器 + 文档浏览器 + 批量操作等 FutureCapability 占位功能

## [0.9.2] - 2026-07-08

### Changed - CHG-SCPT-2026-101 V0.9.2 治理收口迭代闭环（Phase 1-6）

- **Phase 1 PM_SESSION 真源同步**：修正 §2/§8 失真声明（mypy 8→0 + ruff 2→0 + QmlBridge 已拆分为 5 个域 bridge）+ §9"拆薄 QmlBridge"标记 ✅ + ruff --fix 修复 2 个 I001 import 排序
- **Phase 2 Claude P2-P4 项核查**：7 项逐条核查全部无需修改（5 项已修复 P2-S1/S2/S3/S5/S6 + 1 项有测试覆盖不适用 P2-S4 + 1 项合理路线图标记 P2-S7），Claude v3 诊断报告 P2-P4 项严重失真
- **Phase 3 文档收口**：README.md 7 处过时描述修复（QWidget→QML 单入口 + QWizard→分步创建对话框 + dogfooding 3→30+次 + V0.9.0 QML 完整移除 + Facade 接口层落地 + tests/ 111→117 文件 + 试运行报告归档 + 废弃文档列表 + dogfooding 证据表 3→6 条代表性闭环）+ qml_main_window.py 2 处 docstring 更新（模块 docstring + run_qml_gui docstring）+ pyproject.toml 无需修改（Claude #6 pywebview 依赖声明失真，dependencies 中无 pywebview）

### Fixed - CHG-SCPT-2026-101 Phase 4 修复

- **VarTableEditorView.qml L259**：`onFocusLost`→`onEditingFinished`（TextField 标准信号，覆盖失去焦点 + Enter/Return 场景）
- **PM_SESSION 归档**：运行 `auto-pm pm-session archive --section 6 --keep-recent 15`，归档 24 行早期 Implementation Log 条目到 `00_项目管理/05_PM_SESSION归档/PM_SESSION_SW-2026-008_archive_auto.md`，主文件 156.6KB→109.7KB，元测试门禁恢复通过

### Verified - CHG-SCPT-2026-101 三轨门禁 + GUI 冒烟

- ruff check . 实测 All checks passed (0 errors)
- mypy auto_pm/ 实测 Success: no issues found in 125 source files (0 errors)
- tests/spec/ 128 passed 1 skipped in 2.20s
- tests/qml/ 138 passed in 2.21s（可见模式 GUI_VISIBLE=1）
- tests/test_pm_session_size.py 9 passed in 0.18s（PM_SESSION 109.7KB/243 行恢复 ≤150KB）
- 8 个 QML view 全部可加载（QQmlApplicationEngine rootObjects() 非空：ChangeCenterView/ProjectListView/ReportView/SettingsView/SpecCenterView/TemplateView/VarTableEditorView/WorkspaceView）
- auto-pm pm-session check 健康检查通过（0 缺失 0 回归）
- 全量 pytest 207.10s 完成 2 failed + 1258 passed + 2 skipped（2 个失败是 PM_SESSION 大小超阈已归档修复，未复现"卡在 96%"和"7 个 CLI JSON 失败"问题）
- dogfooding：CHG-SCPT-2026-101 第 32 次闭环 closed

### Notes - CHG-SCPT-2026-101 Claude v3 诊断报告失真度核查结论

- **Phase 2 P2-P4 项**：7 项中 5 项已修复 + 1 项有测试覆盖不适用 + 1 项是合理路线图标记，**7/7 严重失真**
- **Phase 3 #6 pywebview 依赖**：pyproject.toml dependencies 中无 pywebview，**Claude #6 失真声明**
- **结论**：Claude v3 在 V0.9.1 代码基线上的静态分析存在大量"已修复项被误报为待修复"问题，后续使用 Claude 诊断报告时须做失真度核查，禁止直接采信
- **预先存在 warnings**（非本次修改引入，留待后续迭代）：VarTableEditorView.qml L177 HorizontalHeaderView anchor + SpecCenterView.qml L203 undefined→QString + WorkspaceView.qml L359 undefined→bool
- **Phase 5 质量加固评估**：Ruff 扩展规则集 RUF/SIM/PLR 发现 3951 错误（规模过大建议后续专门迭代）+ AutoPmConfig 已有基础（app_config.py 2 字段，后续逐步收口硬编码）

## [0.9.1] - 2026-07-08

### Changed - CHG-SCPT-2026-100 阶段 A 闭环收尾（T1-T8 已完成项确认）

- **Claude 诊断报告失真度核查**：19 项问题逐条核查，8 项 P0/P1 已全部修复但报告未更新（严重失真 42%）+ 3 项数字偏差（except Exception 实际 70 处 vs 报告 31 处；parser.py 实际 716 行 vs 报告 837 行；change_service.py 实际 723 行 vs 报告 887 行，部分失真 16%）+ 8 项仍真实存在（P2-P4 建议 42%）
- **阶段 A 闭环收尾**：T1-T8 已完成项全部确认（缓存优先/DB 连接复用/sync 委托/setup_logger 标准化/.gitignore 加固/Optional 统一/Facade Any 替换），Grep 实测 `setup_logger`=0 处、`Optional[X]`=0 处、Facade Any 参数=0 处

### Fixed - CHG-SCPT-2026-100 阶段 B 静默 except 整改

- **delivery_facade.py L82 静默 except 修复**：`auto_pm/application/delivery_facade.py` L10 添加 `import logging` + L30 添加 `log = logging.getLogger(__name__)` + L82-83 静默 `except Exception: pass` 改为 `except Exception as e: log.warning("文件系统扫描失败，返回 None: %s", e, exc_info=True)`
- **6 处静默 except 核查**：仅 1 处真正静默 pass 已修复（delivery_facade.py L82），其余 5 处已有日志记录或合理保留（logging.py L24 兜底/fix_svc.py L170 已 log.warning/file_utils.py L81 raise/frontmatter_svc.py L91+L146 已 log.warning）

### Verified - CHG-SCPT-2026-100 聚焦回归

- 聚焦回归：`pytest tests/application/test_delivery_facade.py -v` 实测 37 passed（0 failed）
- ruff 0 errors（`auto_pm/application/delivery_facade.py`）
- mypy 4 errors（pre-existing unreachable，未新增，`auto_pm/application/delivery_facade.py`）
- dogfooding：CHG-SCPT-2026-100 第 31 次闭环 closed

### Notes - CHG-SCPT-2026-100 Claude 诊断报告失真度核查说明

- **报告失真度高**：Claude 第二版诊断报告（19 项问题）基于修复前状态生成，未反映 T1-T8 已完成的修复，后续使用该报告时必须先核查实际状态
- **阶段 C 长期建议登记**：8 项 P2-P4 建议未在本次修复范围内，登记为长期建议（详见 `.trae/documents/auto-pm_Claude诊断核查与修复计划.md` 阶段 C）
- **版本号 0.9.0→0.9.1**：patch 级别升级，仅含 1 处静默 except 修复 + 文档同步，无 API 变更

## [0.9.0] - 2026-07-05

### Added - CHG-SCPT-2026-094 V0.9.0 旧 QWidget 模块完整移除 + CLI 标志退役

- **Phase 2 main_window.py + 旧 QWidget 模块删除**：删除 `auto_pm/ui/main_window.py`（旧 QWidget 主窗口）+ `auto_pm/ui/styles.py`（QSS）+ `auto_pm/gui/` 兼容包 + `scripts/gui_plc_full_test.py` 旧版全功能测试脚本；删除 7 个旧 QWidget 模块目录：`change_center/`（6 文件）+ `dialogs/`（9 文件）+ `navigation/`（3 文件）+ `project_list/`（6 文件）+ `workspace/`（7 文件）+ `vartable/`（3 文件）+ `widgets/`（3 文件）+ `auto_pm/ui/global_pages/global_view.py`；修改 `auto_pm/ui/__init__.py`（移除 MainWindow 导入，改为空模块 docstring）+ `auto_pm/ui/global_pages/__init__.py`（更新 docstring，说明 spec_center_dto.py 保留原因）
- **CLI 标志退役**：`auto_pm/cli/gui.py` 移除 `--qml` 标志（已变 no-op）+ `--qwidget` 标志（旧版入口）+ `_run_pyside_gui()` 函数；`gui_command` 签名简化为 `(ctx, debug)`，直接调用 `_run_qml_gui()`；模块 docstring 更新；`Taskfile.yml` smoke 任务移除 QWidget 冒烟行 + test-gui 任务改为 `tests/qml/`

### Removed - V0.9.0 Phase 1+2 共计 84 个文件删除

- **43 个测试文件**（Phase 1 CHG-093）：`tests/ui/` 22 文件 + `tests/gui/` 21 文件（含 helpers/ 子目录 + ai_prompt_template.md）；旧 QWidget 端到端验收测试已被 tests/qml/ QML 测试套件等价覆盖
- **41 个生产/脚本文件**（Phase 2 CHG-094）：`main_window.py` + `styles.py` + `auto_pm/gui/__init__.py` + `scripts/gui_plc_full_test.py` + 7 个旧 QWidget 模块目录 37 文件 + `global_view.py`
- **保留**：`auto_pm/ui/qml/`（QML UI）+ `auto_pm/ui/qml_main_window.py`（QML 入口）+ `auto_pm/ui/models/`（模型适配器）+ `auto_pm/ui/global_pages/spec_center_dto.py`（SpecCenterAdapter 仍被 QmlBridge 使用）

### Verified - V0.9.0 回归

- 全量回归：999 passed, 1 skipped in 44.14s（0 failed）
- ruff 0 errors（auto_pm/cli/gui.py + auto_pm/ui/ 修改文件）
- mypy 0 errors（104 source files，从 145 降至 104）
- CLI 冒烟：`auto-pm gui --help` 仅显示 `--debug` 选项
- `import auto_pm.ui` 正常无报错
- dogfooding：CHG-SCPT-2026-093/094 两连闭环（第 24/25 次闭环）

### Notes - V0.9.0 QWidget→QML 完整迁移里程碑说明

- **QML 为唯一 UI 入口**：V0.6.0 QML 作为 PoC 入口引入 → V0.8.0 翻转为默认入口 → V0.9.0 移除全部 QWidget 代码，QML 为唯一入口
- **CLI 标志演进完成**：`--qml`（V0.6.0 PoC 入口）→ V0.8.0 默认入口（标志变 no-op）→ V0.9.0 移除；`--qwidget`（V0.8.0 新增，旧版入口）→ V0.9.0 移除
- **测试套件精简**：739→999 测试（移除 433 QWidget 测试 + 799 后端测试 + 200 QML 测试 + 1 skipped = 999 总计）
- **代码规模缩减**：145→104 source files（移除 41 个旧 QWidget 生产文件）

## [0.8.0] - 2026-07-04

### Added - CHG-SCPT-2026-090/091/092 V0.8.0 QML 完整覆盖 + 旧代码激进清理（Phase 1+2+3 三阶段完整闭环）

- **Phase 1 QmlBridge 扩展 + main.qml 侧边栏补全（CHG-090 第 21 次闭环）**：QmlBridge 新增 SpecCheckService/TemplateService/PmSessionService/DashboardService/AssetSummaryService/DocRefreshService 6 个 Service 注入 + 对应 6 个 hasXxxService bool Property；新增 6 个 Slot（runSpecCheck/refreshProjectDocs/runPmSessionCheck/getDashboard/listAssetSummaries/refreshAssetIndex）+ make_spec_check_service 工厂；main.qml 侧边栏补全 6 入口（规范中心/报告中心/模板管理/设置/工作台/资产）+ StackLayout 7 页占位 Rectangle
- **Phase 2 4 个 QML 页面新增（CHG-091 第 22 次闭环）**：QmlBridge 补齐 6 个 Slot（getTemplateDetail/getSettingsSummary/clearCache/rebuildIndex/getSpecOverview/listSpecEntries）+ specCenterService/hasSpecCenterService 2 个 Property + make_spec_center_service 工厂；4 个 QML 页面（ReportView 378 行 2×2 卡片柱状图 + TemplateView 282 行卡片列表 + SettingsView 476 行 DB 统计 + PM_SESSION 健康 + SpecCenterView 644 行 3 Tab 概览/索引/检查）+ BarRow 组件 59 行；main.qml 4 个占位 Rectangle 替换为真实页面；修复 Dialog 组件冲突（自定义 components/Dialog.qml 阴影 QtQuick.Controls.Dialog，改用 dialogWidth/dialogHeight/showButtons:false 模式）
- **Phase 3 CLI 默认入口切换 + A 类激进清理（CHG-092 第 23 次闭环）**：翻转 `auto-pm gui` 默认入口为 QML（V0.6.0~V0.7.x 为 QWidget PoC 入口）；新增 `--qwidget` 标志启动旧版 QWidget（deprecated，V0.9 移除）；`--qml` 标志改为 deprecated no-op（输出黄色警告）；删除 11 个已迁移 global_pages 文件（4 主页面 + spec_center_tabs/ 7 个文件含 __init__.py）；main_window.py 用 try/except + 4 个占位 QWidget 类（ReportPage/SettingsPage/SpecCenterView/TemplatePage）保证 import 兼容；删除 6 个对应 tests/ui 测试文件

### Test - V0.8.0 新增 25 个 QML 测试（Phase 2，1 个测试文件）

- `tests/qml/test_qml_views_v08.py` 25 测试（9 测试类）：覆盖 6 个新 Slot（getTemplateDetail/getSettingsSummary/clearCache/rebuildIndex/getSpecOverview/listSpecEntries 默认+注入场景）+ 2 个新 Property（specCenterService/hasSpecCenterService）+ 5 个 QML 视图加载（ReportView/TemplateView/SettingsView/SpecCenterView/BarRow）+ 4 个向后兼容测试（Phase 1 + V0.6 Slot 仍可用）
- 含修复：MagicMock auto-attribute 返回 truthy 问题（显式 `service.db = None` / `service._repo = None`）；monkeypatch 模式用于 mock 模块级函数 `_read_template_version`/`_read_template_description`

### Verified - V0.8.0 回归

- 聚焦回归：tests/qml/ 200 passed in 5.89s（W1/W2/W3/W4 + Phase 1 + Phase 2 全量通过）
- tests/ui/ 全量回归：433 passed, 59 warnings in 15.40s（warnings 全为预期 DeprecationWarning "QWidget GUI 已弃用"，V0.6.0 起就存在非回归）
- ruff 0 errors（auto_pm/cli/gui.py + auto_pm/ui/main_window.py + auto_pm/ui/global_pages/__init__.py）
- mypy 0 errors（auto_pm/cli/gui.py + auto_pm/ui/main_window.py）
- CLI 冒烟：`auto-pm gui --help` 显示 3 选项 --debug/--qwidget/--qml 正确注册
- dogfooding：CHG-SCPT-2026-090/091/092 三连闭环（第 21/22/23 次闭环）

### Removed - V0.8.0 A 类激进清理（Phase 4+5，17 个文件删除）

- **11 个 global_pages 已迁移文件**（Phase 4）：`auto_pm/ui/global_pages/report_page.py` / `template_page.py` / `settings_page.py` / `spec_center.py` + `spec_center_tabs/` 整个子目录（`overview_tab.py` / `index_tab.py` / `check_tab.py` / `frontmatter_tab.py` / `report_tab.py` / `compare_tab.py` / `__init__.py`）；对应功能已由 QML ReportView/TemplateView/SettingsView/SpecCenterView 完整替代
- **6 个 tests/ui 旧测试文件**（Phase 5）：`test_report_page.py` / `test_settings_page.py` / `test_template_page.py` / `test_spec_center.py`（4 原计划）+ `test_iteration4_interactive.py` / `test_final_acceptance.py`（2 追加，因 import 已删除模块导致 collection error；旧 QWidget 端到端验收测试已被 tests/qml/ QML 测试套件等价覆盖）
- **保留**：`auto_pm/ui/main_window.py`（17 测试文件依赖，V0.9 完全移除）+ `global_view.py` + `spec_center_dto.py`（SpecCenterAdapter 仍被 QML QmlBridge 使用）

### Notes - V0.8.0 QML 完整覆盖里程碑说明

- **QML 默认入口翻转**：V0.6.0 QML 作为 PoC 入口（`--qml` 标志）引入，V0.6.x~V0.7.x 期间与 QWidget 双轨并行，V0.8.0 翻转为默认入口（QML 已通过 200/200 测试，功能等价 QWidget）
- **A 类激进清理策略**：本期删除已迁移到 QML 的 QWidget 代码 + 对应测试，降低维护成本避免双份分叉；保留 main_window.py 框架（用 try/except + 占位 QWidget 兼容旧测试），V0.9 完整移除 main_window.py 时一并清理
- **CLI 标志演进**：`--qml`（V0.6.0 PoC 入口）→ V0.8.0 默认入口（标志变 no-op + 弃用警告）→ V0.9 移除；`--qwidget`（V0.8.0 新增，旧版入口向后兼容）→ V0.9 移除

## [0.7.0] - 2026-07-04

### Added - CHG-SCPT-2026-087/088/089 V0.7.0 PM_SESSION 三层真源架构（Stage 1+2+3 完整闭环）

- **Stage 1 PM_SESSION 拆分归档（CHG-087 第 18 次闭环）**：手动拆分 489KB/1542 行 → 62KB/170 行 active 主文件 + 328KB/1264 行 `archive_V0.6.0.md` 历史归档；§7 Verification Log 整章删除；§3/§5/§6/§8 早期 80+ 条记录折叠为摘要 + 归档索引；建立三层真源架构（Active 主文件 + Historical 归档 + Event 实体 CHG-*.md）
- **Stage 2 auto-pm pm-session 子命令（CHG-088 第 19 次闭环）**：新增 `auto_pm/core/pm_session_service.py`（162 statements, 99% coverage）含 PmSessionParser/PmSessionCheckService/PmSessionArchiveService + `generate_view()` 视图生成器；新增 `auto_pm/cli/session.py`（129 statements, 90% coverage）3 子命令 `pm-session check|archive|view`；`__main__.py` 注册子命令；3 测试文件 56 测试通过；ruff/mypy 0 errors；CLI 端到端验证通过；新增元测试门禁 `tests/test_pm_session_size.py` 检查 PM_SESSION 真实文件大小
- **Stage 3 005/008 影子台账退役（CHG-089 第 20 次闭环）**：`005_变更记录_CHG.md` 归档标记（frontmatter status 已归档 + 标题加【已归档】+ 添加归档通知指向 CHANGELOG/auto-pm change list/CHG-*.md + 历史内容保留）；`008_试运行报告_PILOT.md` 同样归档标记（指向 CHG-*.md §9/§10 作为新真源）；功能完全由 CHANGELOG.md + auto-pm change list + CHG-*.md 覆盖；真源统一到三层架构

### Test - V0.7.0 新增 56 个测试（3 个测试文件）

- `tests/core/test_pm_session_service.py` 36 单元测试覆盖 PmSessionParser（章节级解析正则 `^##\s+(\d+)\.\s+(.+)$`）+ PmSessionCheckService（MAX_FILE_SIZE_KB=150 + MAX_FILE_LINES=300 + REQUIRED_SECTIONS + DEPRECATED_SECTIONS={"7"}）+ PmSessionArchiveService（keep_recent=0 整章归档 vs keep_recent>0 保留 header+末尾 N 行）+ generate_view
- `tests/cli/test_session.py` 16 CLI 集成测试覆盖 check/archive/view/group_registration 4 子命令
- `tests/test_pm_session_size.py` 4 元测试门禁（检查真实 PM_SESSION 文件 ≤150KB/≤300 行）
- 56 测试通过 in 4.91s + ruff 0 errors + mypy 0 errors

### Verified - V0.7.0 回归

- 聚焦回归：56 passed, 0 failed（tests/core/test_pm_session_service.py + tests/cli/test_session.py + tests/test_pm_session_size.py，4.91s）
- mypy 0 errors (auto_pm/core/pm_session_service.py + auto_pm/cli/session.py), ruff 0 errors (4 files)
- dogfooding：CHG-SCPT-2026-087/088/089 三连闭环（第 18/19/20 次闭环）

### Notes - V0.7.0 三层真源架构说明

- **三层真源**：Active 主文件（PM_SESSION.md，最新迭代状态，62KB/170 行）+ Historical 归档（archive_V0.6.0.md，完整历史，328KB/1264 行）+ Event 实体（CHG-*.md，每次变更单详情）
- **影子台账退役**：005/008 在 V0.3.0 前是变更记录单一真源，但 V0.3.0+ 引入 CHG-*.md 后功能完全冗余且长期未维护（005 索引仅到 CHG-079 缺 080-088；008 仅到第 10 次闭环缺 11-19）。归档标记后保留历史内容，新真源为 CHANGELOG.md + auto-pm change list + CHG-*.md
- **PM_SESSION 膨胀根本解决**：通过 `pm-session archive` 子命令自动化拆分流程，避免未来再次手动 PowerShell 操作；元测试门禁确保未来文件大小 ≤150KB/≤300 行

## [0.6.0] - 2026-07-04

### Added - CHG-SCPT-2026-086 V0.6.0 GUI QML 重构（4 周迭代完整闭环）

- **Week 1 QML 基础设施 + PoC**：新增 `auto_pm/ui/qml/` 目录结构（views/components/theme/models/dialogs）+ Theme.qml 设计系统（20+ token）+ `qml_main_window.py` 独立入口 + `cli/gui.py` `--qml` 选项 + `QmlBridge(QObject)` Python↔QML 数据桥（暴露 ProjectService/ChangeService/SpecService）+ `ProjectListModel(QAbstractListModel)` 7 角色 + `ChangeListModel(QAbstractListModel)` 10 角色 + main.qml + ProjectListView.qml PoC 页面 + tests/qml/ 测试基础设施
- **Week 2 核心页面迁移**：ProjectListView.qml 完整功能（卡片/列表双视图 + 搜索 + 业务线/阶段筛选 + 分组折叠 + 分页）+ WorkspaceView.qml 5 Tab（Overview/Change/Check/Doc/VarTable）+ ChangeCenterView.qml 变更列表 + 详情面板 + 5 可复用组件（Card/Badge/TabBar/PrimaryButton/Dialog）+ W1 验证 ③④ 补齐（QmlBridge 暴露 ChangeService/SpecService + 实际运行 GUI 显示 13 项）
- **Week 3 复杂组件 + 对话框**：4 复杂可视化组件（ApprovalTimeline/PropagationView/StatusMachineView/PhaseProgress）+ VarTableModel(QAbstractTableModel) 8 列 + 单元格编辑 + 字段校验 + 批量操作 + TableView 原生虚拟化（万行数据）+ UndoStack 撤销重做（≥20 步）+ VarTableEditorView.qml 完整编辑器视图 + 8 对话框（NewProjectWizard 3 步向导 + NewChangeDialog + ProjectSettingsDialog + SyncCacheDialog + ImportProjectDialog + AboutDialog + ReportDialog + GlobalSettingsDialog）
- **Week 4 测试 + 收尾**：145 个 QML 测试（远超 ≥50 目标）含 9 集成测试 + main_window.py 添加 DeprecationWarning（保守策略：保留旧代码作 fallback，激进删除推迟 V0.7 QML 完整覆盖规范中心/报告/模板后）+ CHG-086 dogfooding 闭环（状态 implementing→closed）+ 版本号三件套升级

### Test - V0.6.0 新增 145 个 QML 测试（10 个测试文件）

- `tests/qml/test_qml_components.py` 11 测试（5 基础组件 Card/Badge/TabBar/PrimaryButton/Dialog 默认属性 + 设置 + 信号）
- `tests/qml/test_qml_components_w3.py` 17 测试（4 复杂组件 ApprovalTimeline/PropagationView/StatusMachineView/PhaseProgress 默认属性 + 设置 + 尺寸 + 映射）
- `tests/qml/test_qml_dialogs_w3.py` 19 测试（8 对话框默认属性 + 字段设置 + loadable 汇总验证）
- `tests/qml/test_var_table_model.py` 36 测试（COLUMNS 常量 + UndoStack push/undo/redo/clear/max_size + 字段校验 + setEntries + clear + data + setCell + batchUpdate + 撤销重做 ≥20 步 + QML Slot 接口）
- `tests/qml/test_qml_integration_w4.py` 9 集成测试（QmlBridge↔ProjectListModel/ChangeListModel 协作 + 项目选择信号 + 变更中心状态流转 + CHG 9 步状态 + 变量表完整工作流 + 校验 + 多组件协作 + 项目新建刷新 + 批量撤销链）
- 其他 5 测试文件 53 测试（W1/W2 PoC + ProjectListModel + ChangeListModel + QmlBridge 接口）

### Verified - V0.6.0 全量回归

- 全量回归：1714 passed, 7 skipped, 0 failed in 217.96s（较 V0.5.4 基线 1569 passed 7 skipped 增加 145 个 QML 测试，0 回归）
- mypy 0 errors (auto_pm/ui/qml 7 source files), ruff 0 errors (auto_pm/ui/qml + tests/qml/)
- dogfooding：CHG-SCPT-2026-086 完整状态流转 implementing→closed（第 17 次闭环）

### Notes - V0.6.0 策略调整说明

- **保守删除策略**：原计划 W4-S6~S9 删除 21,300 行旧 QWidget 代码，实际改为在 main_window.py 添加 DeprecationWarning 保留作 fallback。原因：QML UI 尚未覆盖规范中心/报告/模板/全局设置页（QML main.qml 中为占位），激进删除会导致功能丢失。待 V0.7 QML 完整覆盖后再清理。
- **dogfooding 闭环说明**：CHG-086 状态流转简化为 implementing→closed（无 submitted/reviewing/approved 等中间态，因本变更为 TraeAI 自身迭代，无人工审批环节）

## [0.5.4] - 2026-07-03

### Fixed - CHG-SCPT-2026-085 V0.5.4 深度审查整改（台账字段根源修复+闭环门禁强化+DB 增量同步 P1 修复）

- **Task A 台账字段空缺根源修复**：`auto_pm/change/ledger_updater.py` `update()` 新增 applicant/apply_date 参数写入"申请人/申请日期"列 + `update_status()` 新增 complete_date 参数写入"完成日期"列；`auto_pm/change/change_service.py` `create_change_request()` / `transition_status()` 调用点自动回填字段；`01_版本变更台帐.md` 7 条历史记录回填申请人/申请日期/完成日期字段
- **Task B CHG 闭环门禁强化**：`auto_pm/change/change_service.py` 新增 `_check_all_verification_items_passed()` 方法解析 §10.1 验证项清单表格检测未通过项 + `transition_status()` completed 分支新增门禁：未通过项存在且未显式标注部分验证时抛 `TransitionGuardError` 阻断流转 + 新增 `allow_partial_verification` 参数支持显式标注部分验证闭环；`auto_pm/cli/change.py` `cmd_transition` 新增 `--allow-partial-verification` 选项；`CHG-SCPT-2026-084.md` §10.1 验收项 4-6 状态标注"➡移至 CHG-085 跟踪"避免重复验收
- **Task C DB 增量同步 P1 缺陷根源修复**：`auto_pm/db/schema.py` DDL_PROJECTS 增加 `scanner_version` 列 + `migrate_schema()` ALTER TABLE 迁移；`auto_pm/models/project.py` `ProjectRecord` 增加 `scanner_version` 字段；`auto_pm/db/sync.py` 新增 `SCANNER_VERSION="v2"` 常量 + `SyncService.__init__()` 增加 `scanner_version` 参数 + `_sync_projects()` 增量模式增加 scanner_version 一致性检查（版本不匹配时强制重扫）；`auto_pm/db/repository.py` `upsert()` + `_row_to_record()` 读写 scanner_version（向后兼容）。原 P1 缺陷：增量同步仅看 marker 文件 mtime，scanner 逻辑变更（如 stack/phase 推断规则修改）不触发已缓存项目重扫，导致 DB 缓存陈旧

### Test - V0.5.4 新增 9 个单元测试（3 个测试类）

- `tests/change/test_ledger_updater.py` 新增 `TestLedgerUpdaterChg085` 类 3 测试（applicant/apply_date/complete_date 回填验证）
- `tests/change/test_change_service.py` 新增 `TestChg085VerificationGate` 类 3 测试（§10.1 门禁：无章节不校验/全通过放行/有未通过项返回编号列表）
- `tests/db/test_sync.py` 新增 `TestScannerVersionChg085` 类 3 测试（全量同步持久化 scanner_version + 版本不匹配强制重扫 + 版本匹配增量跳过）

### Verified - V0.5.4 全量回归

- 全量回归：1569 passed, 7 skipped, 0 failed in 231.52s（较 V0.5.3 基线 1560 passed 7 skipped 增加 9 个测试，0 回归）
- mypy 0 errors (147 文件), ruff CHG-085 相关文件 0 errors（tests/gui/ 40 errors 为 V0.5.2 预存在遗留，非本轮引入）
- dogfooding：CHG-SCPT-2026-085 完整 9 步状态流转 draft→closed（第 16 次闭环）

### Resolved Issues - V0.5.4 已解决问题

- **DB 增量同步 P1 缺陷已修复（CHG-085 Task C）**：scanner_version 机制确保 scanner 逻辑变更时自动触发已缓存项目重扫，DB 缓存不再陈旧，无需删除 `index.db` 强制全量重扫

## [0.5.3] - 2026-07-03

### Fixed - CHG-SCPT-2026-084 V0.5.3 GUI 阻断修复（电气工程师试用反馈）

- **Fix 1 nav_tree.py 导航树项目计数丢失**：`auto_pm/ui/navigation/nav_tree.py` 修复 stack=unknown 的 Python 项目丢失问题 + phase 为空的项目丢失问题；引入 "unset" 哨兵值用于"仅显示未设置阶段的项目"语义（区别于 "all" 不筛选阶段 和 "" 历史兼容别名）
- **Fix 2 project_scanner.py stack 推断缺失**：`auto_pm/core/project_scanner.py` 新增 `_infer_stack_from_path` 方法从项目路径推断 stack（plc/python）；新增 `read_pm_session` phase reader 从 PM_SESSION 读取实际 phase
- **Fix 3 project_scanner.py phase 读取缺陷 + 默认值**：修复 phase 字段读取缺陷，developing 作为默认 phase
- **Fix 4 main_window.py + list_view.py 新建项目入口不可见**：`auto_pm/ui/main_window.py` "新建"按钮强化 + 空状态按钮信号连接；`auto_pm/ui/project_list/list_view.py` phase 语义修复（"unset" 特判）
- **预存缺陷修复**：`tests/ui/test_iteration1_interactive.py` toolTip 检查修复

### Test - V0.5.3 新增 18 个单元测试

- `tests/core/test_project_scanner.py` 新增 11 个测试（_infer_stack_from_path + developing default + read_pm_session phase reader）
- `tests/ui/test_project_list.py` 新增 5 个测试（phase 语义 + "unset" 特判）
- `tests/ui/test_navigation.py` + `tests/ui/test_final_acceptance.py` + `tests/ui/test_iteration2_interactive.py` 测试更新（期望 "unset" + 按钮文本/菜单项更新）

### Verified - V0.5.3 全量回归

- 全量回归：1560 passed, 7 skipped, 0 failed（较 V0.5.2 基线 1542 passed 7 skipped 增加 18 个测试）
- ruff 0 errors, mypy 0 errors
- 扫描验证：13 项目 stack/phase 正确（plc=6, python=6, unknown=1）
- dogfooding：CHG-SCPT-2026-084 完整 9 步状态流转 draft→closed（第 15 次闭环）

### Known Issues - V0.5.3 open_questions

- **DB 增量同步 P1 缺陷**：GUI 启动使用已有 DB 缓存时，已缓存项目的 stack/phase 不会被增量同步更新（显示错误数据）。临时修复：删除 `index.db` 强制全量重扫。待后续修复。

## [0.5.2] - 2026-07-02

### Fixed - CHG-SCPT-2026-082 V0.5.x 稳定期 Week 1 5 格式 Parser 真实样例覆盖

- **W1-S01 format_detector 中文表头识别**：`auto_pm/vartable/parsers/format_detector.py` 新增 `_WORK3_HEADER_CN` 正则（支持 `"类"\t"标签名"\t"数据类型"` 中文表头），§3.4 改为前 2 行任一行匹配 Work3 表头特征（真实样例第 1 行 FB 名称占位、第 2 行才是表头），消除真实 Work3 样例（UTF-16 LE + 中文表头）被误判为 UNKNOWN 的问题
- **W1-S02 _AUTOSHOP_HEADER 正则收紧**：从 `变量名|数据类型|作用域|类别` OR 逻辑过宽（误把 Work3 中文表头识别为 AUTOSHOP）改为 `变量名|(?=.*类别)(?=.*名称)(?=.*数据类型)` 组合逻辑——SW-2026-001 合成样例表头含"变量名"匹配第 1 分支；真实 Autoshop 样例表头 `序号,类别,名称,数据类型` 匹配第 2 分支；Work3 真实样例表头含"类"但不含"类别"/"名称"不匹配
- **W1-S03 work3_parser address 字段 strip 引号**：`auto_pm/vartable/parsers/work3_parser.py` L121 `address = fields[_ADDRESS_IDX].strip().strip('"')` 添加 `.strip('"')` 剥离真实样例空字段值 `""`（两个引号字符）的引号残留；同步对 scope/name/data_type/description 字段统一调用 `.strip('"')`

### Test - W1-S04/W1-S05 真实样例覆盖 26 个新测试

- **W1-S04 SCL 真实样例**：`tests/vartable/test_scl_parser.py` 新增 `TestSclParserRealSamples` 类 10 个测试，覆盖 DJ-2026-005 真实 .scl 文件（OB1/FB_2001/FB_1002/FB_External/FB_1004/FB_1003）FB 名提取、VAR 块识别、复杂类型字段、中文注释处理；含 `skip_if_real_samples_missing` 标记
- **W1-S05 真实样例 fixture + 16 个新测试**：
  - `tests/vartable/samples/Work-FB变量表导出.csv`（UTF-16 LE BOM + 27 列中文表头 + 53 行含 7 空行，9608 字节）
  - `tests/vartable/samples/Autoshop-FB变量表导出.csv`（GBK 编码 + 逗号分隔 + 90 entries）
  - 4 个测试文件新增 16 个真实样例测试：test_format_detector 4（Work3/Autoshop 真实样例格式识别 + 中文表头合成样例 + Work3 不误判为 AUTOSHOP 回归）+ test_work3_parser 6（UTF-16 LE 编码 + 44 entries + address 无引号 + VAR_INPUT/VAR_OUTPUT scope + FB 名 metadata + 真实数据类型）+ test_autoshop_parser 6（GBK 编码 + 90 entries + in scope + i_start + comment 提取 + 真实数据类型）
  - samples/ 目录加入 .gitignore 避免大文件入库

### Verified - V0.5.2 全量回归

- 全量回归：1542 passed, 7 skipped, 0 failed（较 V0.5.1 基线 1477 passed 6 skipped 增加 65 个测试 + 1 skipped）
- ruff 0 errors, mypy 0 errors（145 source files）
- 真实样例端到端：Work3 44 entries 0 errors + Autoshop 90 entries 0 errors + SCL DJ-2026-005 6 文件端到端通过
- dogfooding：CHG-SCPT-2026-082 完整 9 步状态流转 draft→closed（第 13 次闭环）

## [0.5.1] - 2026-07-01

### Fixed - CHG-SCPT-2026-081 GUI 测试三报告整合修复

- **TD-G01 P0 修复**：`auto_pm/core/project_scanner.py` `read_copier_answers` 增加 `or ""` 保底，防止 `.copier-answers.yml` 中 `equipment_type`/`plc_vendor`/`plc_model` 字段为 null 时 Pydantic `ProjectInfo` 校验失败导致新建项目"消失"（a5e8b3cb commit，本版本追溯登记 CHG 流程）
- **V-04~V-12 修复**：`auto_pm/ui/vartable/variable_table_editor.py` `_build_ui` 增加 `verticalHeader().setVisible(False)` + `setCornerButtonEnabled(False)`，消除 QTableView 在 Stretch 模式下 verticalHeader/cornerButton 0 宽度但 visible 导致的 9 个 zero_size 视觉告警
- **V-01~V-03 修复（测试误报）**：`scripts/gui_plc_full_test.py` `_check_widget_bounds` 增加 `_is_inside_scrollarea` 检查，跳过 QScrollArea viewport 内部 widget 的越界检查（QScrollArea 内容设计上可大于 viewport，由滚动条裁剪，属合法溢出）
- **附带防御性修复**：`auto_pm/ui/workspace/workspace_view.py` `ProjectWorkspaceView._build_ui` 设置 `QSizePolicy(Expanding, Expanding)`，改善 QStackedWidget 中的填充行为

### Docs - 三份 GUI 测试报告整合

- `09_整改项/GUI测试整改报告.md`：头部标注"已过时"（2 个 major bug 已在 V0.5.1 修复）
- `test_reports/gui/2026-07-01_完整GUI测试报告.md`：保留为主报告，修正交付物表路径
- `test_screenshots/GUI诊断报告_V0.5.2.md`：补登 TD-G01 P0 bug 详情 + 修正版本号 + 视觉问题补充代码引用

### Test - gui_plc_full_test.py 截图基线

- 重跑 `python scripts/gui_plc_full_test.py`（GUI_VISIBLE=1 可见模式 + 三视口）
- 结果：67 截图 + 0 bugs + 0 visual_issues（V-01~V-12 全部解决）

## [0.5.0] - 2026-07-01

### Added - V2.3 变量表解析整合（Week1-Week3）

- V2.3 Week1（T01-T07）：变量表数据模型 + IoPointsParser + 编码检测 + CLI vartable 命令组 + 38 测试
  - 新增 `auto_pm/vartable/models.py`：VarEntry/VarTable/ParseResult/ParseError 四个 frozen dataclass
  - 新增 `auto_pm/vartable/parsers/io_points_parser.py`：IoPointsParser 深化 AssetSummaryService，处理 io_points.csv 多格式地址
  - 新增 `auto_pm/vartable/utils/encoding.py`：detect_encoding BOM 检测 + fallback（无 chardet 依赖）
  - 新增 `auto_pm/cli/vartable.py`：parse/detect-encoding/list-encodings 三子命令 + Rich Table + Unicode 输出兼容
- V2.3 Week2（T08-T11）：多格式解析器 + 格式自动识别 + CLI 集成 + 35 测试
  - 新增 `auto_pm/vartable/parsers/program_blocks_parser.py`：ProgramBlocksParser 解析 YAML → BlockEntry
  - 新增 `auto_pm/vartable/parsers/communications_parser.py`：CommunicationsParser 解析 YAML → ChannelEntry
  - 新增 `auto_pm/vartable/parsers/base_parser.py` + 5 格式 Parser 骨架（Autoshop/Work3/Codesys/SCL/IntDoc）
  - 新增 `auto_pm/vartable/parsers/format_detector.py`：三级识别（文件名→扩展名→内容特征）+ 工厂模式
  - 扩展 CLI：parse --format/--output-format + list-formats + detect-format 子命令
  - DJ-2026-005 端到端验证 6 项全通过（7 block + 5 channel + 自动识别）
- V2.3 Week3（T12-T14）：5 格式 Parser 深化 + 转换器重建 + 批量解析 + 35 测试
  - 深化 5 格式 Parser（Autoshop/Work3/Codesys/SCL/IntDoc）：添加 detect_format 方法委托 format_detector
  - 新增 `auto_pm/vartable/converter.py`：VariableConverter 统一中间模型导出 CSV/YAML/JSON
  - 新增 `auto_pm/vartable/batch_parser.py`：BatchParser 批量解析目录/文件列表
  - 扩展 CLI：convert + batch-parse 子命令
  - DJ-2026-005 端到端验证 4 项全通过（SCL 解析 + 批量解析 6 文件 278 条变量 + JSON 转换）
- V2.3 Week4（T15-T16）：GUI 变量编辑器 + 项目工作区变量表 Tab + 33 测试
  - 新增 `auto_pm/ui/vartable/variable_table_editor.py`：VariableTableModel（QAbstractTableModel 8 列）+ VariableTableEditor（QTableView + 工具栏 + 右键菜单 + 导入导出 + data_changed 信号）
  - 新增 `auto_pm/ui/vartable/vartable_tab.py`：VartableTab（QSplitter 文件列表 + 编辑器 + 批量解析 + 角色权限 PLCEngineer/SpecEditor 可编辑）
  - 修改 `auto_pm/ui/workspace/workspace_view.py`：Tab 列表接入 VartableTab
  - mypy unreachable 修复（3 处）：用方法调用替代 bool 属性窄化

### Fixed - TD-C10 治理

- 治理 mypy tests/ 381→0 errors（11 测试文件类型标注修复 + 32/32 技术债全部关闭）
  - 关键技术：bool() 包装打破 mypy 属性 narrowing / str 变量打破 Literal 收窄 / Generator 返回类型 / Callable[[Any],None] 逆变 / PySide6 枚举完整路径

## [0.4.2] - 2026-06-30

### Added - V2.2 Week 1 specmgr 吸收（T02/T03）

- **T02 specmgr 代码迁移**：`auto_pm/spec/` 新增 `core/`（checker_base/config/registry）+ `services/`（IndexService/CheckService/FrontmatterService/ReportService/FixService）+ `models`，吸收 SW-2026-006 specmgr 工具核心能力
- **T03 关键问题修复**：`SpecInfo` 新增 `aliases` 字段（防止 `SpecRegistry.load()` 丢弃 aliases）；10 项健康检查（SHC-001~010）全部迁移；`WorkspaceConfig` 完整迁移
- **dogfooding**：auto-pm 自身可使用 `auto-pm spec check/index/frontmatter/report` 管理自身规范

### Added - V2.2 Week 2 CLI 规范命令（T06-T10）

- **T06 删除死代码**：删除 `auto_pm/spec/commands/index.py`、`frontmatter.py`、`report.py`（cli/spec.py 已有自己的 `_resolve_workspace`）
- **T07 emoji 编码修复**：修复 Windows GBK 终端下 emoji 输出 `UnicodeEncodeError`（`_supports_unicode_output()` 检测 + ASCII fallback icons）
- **T08 新增测试**：tests/spec 从 80 增至 118 passed
- **T09 CLI 选项**：spec 命令新增 `--config`/`--quiet` 选项
- **T10 全量回归**：1246→1364 passed，2 skipped

### Added - V2.2 Week 3 GUI 规范中心页改造（T11-T14）

- **T11 spec_center.py 重构**：从 482 行单文件改为 QTabWidget + DTO 层架构（`spec_center_dto.py` 8 个 frozen dataclass + SpecCenterAdapter），生产代码降至 300 行
- **T12 6 Tab 类**：`spec_center_tabs/` 目录下 6 个 Tab 类（概览/索引/检查/frontmatter/报告/对比）
- **T13 服务集成**：所有 Tab 集成新 IndexService/CheckService/FrontmatterService/ReportService（从旧 SpecIndexService 迁移到 DTO/adapter 模式）
- **T14 LSP-907 集成**：通过 `spec_registry.json` 集成 LSP-907，GUI 规范中心页可查看 14 个规范（PM/PLC/Python 域）

### Fixed - V0.4.2 整改批次 P0 Critical（R-C01~R-C09）

- **R-C01 DSN §9 废弃 API 标注**：标注 `SpecIndexService` 为废弃（被 `IndexService` 替代）
- **R-C02 DSN §11 状态机对齐**：`STATUS_FLOW` 对齐 9 步状态流转
- **R-C03 DSN §10.2 DB 表补全**：补全到 5 表（变更单/审批记录/影响分析/资产摘要/工作空间配置）
- **R-C04 005_CHG 补 CHG-078 索引行**：标准变更单索引表补登 CHG-SCPT-2026-078（第 9 次 dogfooding 闭环）
- **R-C05 ~ R-C09**：其他 Critical 项（已在前一会话完成）

### Changed - V0.4.2 整改批次 P1 Major（R-M01~R-M07）

- **R-M01 文档版本号对齐**：INT/DSN/TEC/REL 4 文档统一升级到 V2.1.0（与 PRD V2.1.2 对齐）
- **R-M02 INT CLI 命令清单补全**：补全 7 行 CLI-21~27（doc refresh/inject + spec check/index/frontmatter/report + change edit）
- **R-M03 INT Service 层补全**：补全 8 行 SVC-22~29（spec 服务族 4 + core 服务族 4）
- **R-M04 005_CHG 补 V2.2 Week1-3 章节**：3 个新章节（Week1 specmgr 吸收 + Week2 CLI 规范命令 + Week3 GUI 改造 + CHG-078 技术债清理）
- **R-M05 008_PILOT 补 CHG-078 第 9 次闭环**：§1.1 试运行周期延伸到 2026-06-30 + 闭环次数 8→9 + 新增 §2.9 闭环证据章节
- **R-M06 006_TD §0.1 总览表更新**：更新到 31 项并补分类（TD-C07/C08/C09/A03）
- **R-M07 007_REL 门禁数据修正**：G3 期望 1 skipped → 2 skipped（L25 + L65）；§4.4 "8 步生命周期" → "9 步状态流转"

### Verified - V0.4.2 全量回归

- 全量回归：1332 passed, 5 skipped, 0 failed（较 V0.4.1 收口基线 1246 passed 1 skipped +86 测试 +4 skipped）
- ruff 0 errors, mypy 0 errors（8 生产文件）
- 33 个新 UI 测试覆盖 6 Tab + DTO 层 + 真实工作空间集成
- dogfooding：CHG-SCPT-2026-078 完整 9 步状态流转 draft→closed（第 9 次闭环）
- 技术债：TD-C07/C08/C09/A03 已清理（17 mypy errors 修复 + 8 文件 docstring + 18 处 type:ignore 清理 + 第 9 次闭环）

## [0.4.1] - 2026-06-29

### Added - V0.4.0 Week 4 文档自动区刷新

- 新增 `auto_pm/core/doc_refresh_service.py`，基于 `io_points.csv`、`program_blocks.yml`、`communications.yml` 生成 PLC 文档自动区内容
- 新增 `auto_pm/cli/doc.py`，提供 `auto-pm doc refresh <project_id> [--dry-run|--json]` 命令
- 新增 `tests/core/test_doc_refresh_service.py`，覆盖自动区 dry-run 与实际刷新

### Changed - Week 4 模板与 CLI 闭环

- `auto_pm/cli/__main__.py` 注册 `doc` 顶层命令组
- `templates/plc-standard-project/template/02_PLC程序/程序文档/016_PLC程序设计总文档_PLC.md.jinja` 新增 `plc-program-components`、`plc-asset-index` 自动区标记
- `templates/plc-standard-project/template/02_PLC程序/程序文档/015_IO分配表_IO.md.jinja` 新增 `plc-io-overview` 自动区标记
- `tests/cli/test_project.py` 新增 `doc refresh` 的 dry-run/json/创建后刷新集成测试
- `00_项目基础信息/008_试运行报告_PILOT.md` 升级到 `V1.1.0`，归档 V0.4.0 Week 2~4 准真实项目闭环证据
- 新增 `09_整改项/V0.4.0-glm5.2执行输入清单.md`，明确后续主线切换为 `V0.4.1 单项目交付闭环深化`

### Added - V0.4.0 Week 3 PLC 工程资产能力

- 新增 `auto_pm/core/asset_summary_service.py`，统一读取 `02_PLC程序/工程资产/` 下 `io_points.csv`、`program_blocks.yml`、`communications.yml` 三类结构化资产
- 新增 `tests/core/test_asset_summary_service.py`，覆盖健康摘要、缺列/缺文件、非 PLC 不适用三类场景

### Changed - Week 3 扫描与 CLI 消费面

- `auto_pm/core/project_scanner.py` 扫描 PLC 项目时自动写入 `extra.asset_summary`
- `auto_pm/cli/project.py` 的 `project show` 新增工程资产摘要输出，展示健康状态、目录状态、IO 点数、程序块数、通讯对象数与问题摘要
- `tests/core/test_project_scanner.py`、`tests/cli/test_project.py` 新增工程资产摘要相关断言

### Verified - Week 3 聚焦回归

- `pytest --no-cov tests/core/test_asset_summary_service.py tests/core/test_project_scanner.py tests/cli/test_project.py tests/plc/test_template_generation.py tests/plc/test_repairer.py tests/plc/test_e2e_plc_workflow.py` → 68 passed
- 真实命令验证：`auto-pm project create --stack plc ...` + `auto-pm project show DJ-2026-333` 可输出“工程资产: 健康 / IO点表: 4 条 / 程序块: 3 个 / 通讯对象: 3 个”

### Verified - V0.4.0 Week 4 文档自动区刷新

- `pytest --no-cov tests/core/test_doc_refresh_service.py tests/core/test_project_scanner.py tests/cli/test_project.py tests/plc/test_template_generation.py tests/plc/test_repairer.py tests/plc/test_e2e_plc_workflow.py` → 70 passed
- 真实命令验证：`auto-pm project create --stack plc ...` + `auto-pm doc refresh DJ-2026-444 --dry-run` + `auto-pm doc refresh DJ-2026-444` 可预览并刷新 2 份 PLC 程序文档中的 3 个自动区

### Added - V0.4.1 Step 1 OverviewTab 工程资产摘要接入

- `auto_pm/ui/overview_tab.py` 接入 `AssetSummaryService`，首页驾驶舱可展示工程资产健康状态、IO 点数、程序块数、通讯对象数与问题摘要
- 历史扫描结果通过 `extra.asset_summary` 字段透传，避免重复扫描
- `tests/ui/test_overview_tab.py` 新增工程资产摘要展示断言

### Added - V0.4.1 Step 2 历史 PLC 项目自动区标记 retrofit

- 新增 `auto_pm/cli/doc.py::cmd_inject`，提供 `auto-pm doc inject <project_id> [--dry-run|--json]` 命令，向历史 PLC 文档注入 `AUTO_PM:BEGIN/END` 自动区标记
- 兼容真实历史文档章节变体（`### 5.1 组件清单与职责`、`## 13. 关联文档索引`、`## 2. 系统硬件配置总览` 等），不再要求 PLC 工程师手工重排章节编号
- `tests/core/test_doc_inject_service.py` 新增锚点匹配 + 章节变体识别 + dry-run/json 集成测试
- `tests/cli/test_doc.py` 新增 `doc inject` 的 dry-run/json/实际注入集成测试

### Changed - V0.4.1 Step 3 PLC 检查不适用口径补齐

- `auto_pm/plc/checker.py` 识别受控历史路径（`00_项目管理/`、`01_需求与设计/`、`02_PLC程序/PLC_ST/PRD/` 等）中的等价 PRD 文档，从"直接误判 fail"改进为"兼容使用 + warn 提示建议后续收口到 PRD/"
- Python 项目 `plc check` 不再因缺少 PLC 工程资产而被驾驶舱误报为失败（明确返回"不适用"语义）
- `tests/plc/test_checker.py` 新增历史路径兼容 + Python 项目不适用两类场景测试

### Verified - V0.4.1 Step 1~3 回归

- `pytest --no-cov tests/ui/test_overview_tab.py tests/core/test_doc_inject_service.py tests/cli/test_doc.py tests/plc/test_checker.py` → 全部通过
- 真实命令验证：`auto-pm doc inject DJ-2026-005 --json` 成功向 2 份真实程序文档注入 3 个自动区；`auto-pm plc check DJ-2026-005 --json` 从 `pass=17 warn=0 fail=4` 变为 `pass=17 warn=4 fail=0`

### Added - V0.4.2 Week 1 DJ-2026-005 真实工程资产首版补齐

- `DJ-2026-005/02_PLC程序/工程资产/io_points.csv` 落地 119 行（CPU DI 21 + CPU DO 18 + DI扩展 36 + DO扩展 24 + 远程IO 20），从 015 IO 分配表 + 016 PLC 程序设计总文档人工提取
- `DJ-2026-005/02_PLC程序/工程资产/program_blocks.yml` 落地 7 块（对齐真实 PLC_ST 目录：OB1/GlobalVars/FB_2001/FB_1002/FB_ExternalDeviceInteraction/FB_1004/FB_1003）
- `DJ-2026-005/02_PLC程序/工程资产/communications.yml` 落地 5 通道（HMI/Upstream/Downstream/RemoteIO/MES）
- `tests/core/test_doc_refresh_service.py` 新增 `test_refresh_with_realistic_assets_emits_real_content_and_idempotent`，覆盖 19 IO/7 blocks/5 channels 真实规模 + 幂等性 + "待补齐"不出现断言

### Verified - V0.4.2 Week 1 真实资产闭环

- `auto-pm project show DJ-2026-005` 工程资产状态 healthy，IO点表 119 条，程序块 7 个，通讯对象 5 个
- `auto-pm doc refresh DJ-2026-005 --dry-run`（首次）→ 2 文档 3 自动区全部标记"有变更"
- `auto-pm doc refresh DJ-2026-005`（实际刷新）→ 2 文档已刷新成功，自动区内容从"待补齐"变为真实数据
- `auto-pm doc refresh DJ-2026-005 --dry-run`（二次，幂等性）→ 2 文档 3 自动区全部标记"无变更"，证明刷新幂等

### Added - V0.4.2 Week 3 第二样本复核

- **DJ-2026-000（SysLib FB 测试套件，扁平结构）边界兼容验证**：`project show` / `change list` / `plc check` / `doc inject --dry-run` / `doc refresh --dry-run` 全链路无崩溃，扁平结构被识别为 syslib_fb 类型并优雅降级为"未找到"提示
- **DJ-2026-099（P1 修复测试标准项目）真实链路验证**：标准模板项目（带历史 `02_PLC程序/02_PLC程序` 旧路径）的 `project show → change list → plc check → doc inject/doc refresh --dry-run` 完整最小链路可走通

### Fixed - V0.4.2 Week 3 rich markup bug

- **症状**：`doc refresh <pid> --dry-run` 输出 issue 时 `[plc-program-components]` 等 block_key 被 rich 当作未知 markup 标签吞噬
- **根因**：`rich.console.print(f"[yellow]{issue}[/yellow]")` 中 issue 文本含 `[block_key]`，被 rich 解析为标签
- **修复**：`auto_pm/cli/doc.py` 中 `cmd_refresh` 和 `cmd_inject` 的 issue 输出改为 `console.print(escape(issue), style="yellow")`
- **回归沉淀**：`tests/cli/test_doc.py::TestDocIssueBracketPreservation` 新增 2 条测试（refresh + inject），先红后绿 TDD

### Verified - V0.4.2 Week 3 回归

- `pytest --no-cov tests/cli/test_doc.py` → 9 passed
- `pytest --no-cov tests/core/test_doc_refresh_service.py tests/core/test_doc_inject_service.py` → 11 passed
- ruff/mypy 0 errors
- 端到端验证：`auto-pm doc refresh DJ-2026-099 --dry-run` 输出含 `[plc-program-components]`/`[plc-asset-index]`/`[plc-io-overview]` 全部可见

### Added - V0.4.2 Week 4 dogfooding 闭环审查 5 项漏洞批量修复

1. **PILOT 版本号与变更记录漂移**：`008_试运行报告_PILOT.md` §5 缺 V1.4.0 行 / frontmatter `version` 与 §5 最新行不一致 → §5 已补 V1.4.0 行 + frontmatter `version` 升至 V1.5.0（满足 project-rule.md §3 版本号一致性）
2. **`01_版本变更台帐.md` 缺 CHG-SCPT-2026-072 序号 005 + 8 条死链**：新增序号 005（CHG-072，原 005~008 顺延为 006~009）；8 条死链 `./01_变更单/...` → `../01_变更单/...`；现 9 条全部可解析
3. **`005_变更记录_CHG.md` 标准变更单索引表漂移**：从 3 条扩展到 9 条（补 064/072/073/074/075/077）+ CHG-001 性质修正为 DEF+OPT
4. **TD-T14 qapp fixture 多处重复定义**：`tests/conftest.py` 新增 session 级 qapp（TYPE_CHECKING + `from __future__ import annotations` + `assert isinstance(app, QApplication)` 三段式）；`tests/ui/conftest.py` / `tests/gui/conftest.py` / `tests/ui/test_vartable_tab.py` 三处本地 qapp 全部移除
5. **TD-T09 复发**：`tests/gui/test_17_edit_change_dialog.py::_cleanup_test_changes` 的 `except Exception: pass` 静默吞错 → except 范围收窄为 `(OSError, PermissionError, ValueError, KeyError)`，删除 noqa 注释
6. **PM_SESSION §2 代码基线 0.3.8 冻结语义不清晰**：milestone 行补充"pyproject.toml version=0.3.8 不升级；CHANGELOG [Unreleased] 累积 V0.4.0 Week 4 + V0.4.1 Step 1~3 + V0.4.2 Week 1~3 文档迭代证据，待后续版本统一收口"明确语义

### Fixed - V0.4.2 Week 4 TD-TC01 + jinja2 DeprecationWarning 收口

- **TD-TC01 已规避**：Trae Sandbox 中文路径字符级拆分问题，工作方式约定使用 Write/Edit 工具替代 RunCommand 写文件（绕过沙箱对中文路径的字符级拆分），约定已沉淀到 `project_memory.md` "Engineering Conventions" 章节
- **5 个 jinja2 `DeprecationWarning: invalid escape sequence '\d'` 已根除**：根因在 `templates/{plc-standard-project,python-tool,plc-test-suite,plc-standard}/copier.yml` 的 jinja2 字符串字面量 `'^[A-Z]+-\d{4}-\d{3}$'` 含 `\d`，触发 jinja2 lexer `decode("unicode-escape")` Python DeprecationWarning；4 个文件的 `\d` → `\\d`，jinja2 解码后保留 `\d` 字面量给 regex_search

### Changed - V0.4.3 版本号与文档统一

- `pyproject.toml` version 0.3.8 → 0.4.1（commitizen `version_provider = "pep621"` 从此文件读取版本号）
- `CHANGELOG.md` [Unreleased] → [0.4.1]，单条版本条目汇总 V0.4.0 Week 3~4 + V0.4.1 Step 1~3 + V0.4.2 Week 1~4 全部迭代证据
- 新增 `[Unreleased]` 空节占位，供后续版本累积

### Verified - V0.4.3 全量回归基线

- 全量回归：✅ 1246 passed, 1 skipped, 0 warnings in 468s（较 V0.3.8 基线 1163 + 83 新增测试，3 warnings → 0 warnings）
- ruff 0 errors, mypy 0 errors
- jinja2 DeprecationWarning 验证：`pytest tests/cli/test_plc.py::test_plc_init_default_mode -W "error::DeprecationWarning"` → 1 passed（警告转错误仍通过，证明已彻底消除）
- 技术债：26/26 项全部关闭，剩余 0 项

## [0.3.8] - 2026-06-27

### Added - V0.3.8 技术债偿还批次（TD-T10 + TD-T08）

- **T86 TD-T10 台帐脏数据根因修复**：auto_pm/change/ledger_updater.py 新增 `update_status(ledger_path, change_number, status)` 方法（更新台帐状态行）+ `remove(ledger_path, change_number)` 方法（删除台帐行）；auto_pm/change/change_service.py 新增 `_LEDGER_STATUS_MAP`（12 状态→文案映射，含 closed）+ `_find_project_root_from_path` 静态方法（从 CHG 文件路径向上查找项目根目录）+ `transition_status` 方法新增台帐状态回写调用（transition 流转后自动同步台帐状态行）；tests/gui/test_17_edit_change_dialog.py `_cleanup_test_changes` fixture 扩展（删除 CHG 文件后同时调用 `LedgerUpdater.remove` 清理台帐条目）；tests/change/test_ledger_updater.py 新增 8 个单元测试（TestLedgerUpdaterUpdateStatus 4 + TestLedgerUpdaterRemove 4）
- **T87 TD-T08 测试并行化评估**：pyproject.toml dev 依赖新增 `pytest-xdist>=3,<4`；tests/conftest.py `pytest_collection_modifyitems` 改用固定 seed `random.Random(20260627)` 确保 xdist 多 worker 收集一致性
- **T89 CHG-SCPT-2026-072 dogfooding 第五次闭环**：创建 CHG-SCPT-2026-072 + 8 步状态流转 draft→submitted→under_review→approved→implementing→pending_acceptance→accepting→completed→closed 全部成功；transition 自动回写台帐状态验证通过（台帐从🔄实施中→✅已关闭）；填充 §5/§6/§7/§8/§9/§10/§11 真实内容

### Changed - V0.3.8 版本号升级
- pyproject.toml version 0.3.7 → 0.3.8

### Fixed - V0.3.8 根因修复 + 历史脏数据清理

- **TD-T10 台帐脏数据根因修复**：transition 命令流转状态后自动回写台帐状态行（之前需手动更新）；GUI 测试 fixture 清理台帐条目（之前仅删除 CHG 文件不清理台帐）
- **_LEDGER_STATUS_MAP 补充 closed 映射**：T89 dogfooding 流转时发现 `closed` 状态缺少映射（回退为"🔄进行中"），补充 `closed→✅已关闭`
- **台帐历史脏数据清理**：清理 7 条 GUI 测试历史残留脏数据（CHG-065~071 序号 005~011，文件已删除但台帐行残留）；修复 CHG-064 状态为 ✅已关闭

### Verified - V0.3.8 回归测试

- 全量回归：✅ 1163 passed, 1 skipped, 3 warnings in 388.84s（较 V0.3.7 基线 1155 + 8 新增 LedgerUpdater 测试，无回归；3 warnings 为 jinja2 第三方库 DeprecationWarning）
- ruff 0 errors, mypy 0 errors
- T86 单元测试：tests/change/test_ledger_updater.py 19 passed ✅
- T86 GUI 测试：tests/gui/test_17_edit_change_dialog.py 7 passed 1 skipped ✅
- T87 xdist 实测：tests/change/ 串行 158 passed in 39.62s vs 并行 -n 2 158 passed in 492.75s（**xdist 反优化 12 倍**，不采用并行化，改用 --no-cov 加速方案）
- dogfooding: CHG-SCPT-2026-072 完整 8 步生命周期闭环 ✅；change list SW-2026-008 返回 5 条记录（001/062/063/064/072 全 closed）✅；台帐 5 条正确记录全 ✅已关闭/已归档 ✅
- 技术债：20/22 项已偿还，剩余 2 项（TD-A02/TD-TC01）

## [0.3.7] - 2026-06-27

### Added - V0.3.0 Phase 6 发布收口：落地发布 + 证据归档 + 版本切换

- **T80 README 重写**：README.md 8 项更新（功能特性补 M3-2/M3-3/M3-4/M3.5 新能力 + python 命令注释 V1.2.0→V2.5 + change 命令补 edit/--full/show 增强 + GUI 功能补 6 项新功能 + 项目结构 plc-standard→plc-standard-project + 文档导航修正 + 新增 Dogfooding 证据章节 + 工具链关系补充 V2.2/V2.3 吸收计划）
- **T81 CHANGELOG 整理**：CHANGELOG.md [0.3.6] 条目下新增 Fixed 子章节（phase 修复 + ruff 清零 + 台帐重复追加 bug 修复 + 台帐数据清理 185→3 条）；Verified 部分追加 glm5.2 收口后全量回归证据（1155 passed 1 skipped 3 warnings 320s 无回归）
- **T82 发布门禁规范**：新建 `00_项目基础信息/007_发布门禁规范_REL.md` V1.0.0（G1-G5 五项门禁定义：ruff 0 / mypy 0 / pytest 全绿 / 元测试 0 violations / dogfooding CHG 闭环；触发条件 + 标准执行顺序 + 门禁失败处理 + 版本号与门禁关系 + 例外与豁免）
- **T83 试运行证据归档**：新建 `00_项目基础信息/008_试运行报告_PILOT.md` V1.0.0（3 次 Dogfooding 闭环证据 CHG-001/062/063 + 4 项已修复问题 BUG-001/002 + 台帐去重 + CHG-001 内容空白 + 4 项已知限制 + 试运行结论通过 + 后续建议）
- **T84 CHG-SCPT-2026-064 完整生命周期**：创建 CHG-SCPT-2026-064（Phase 6 发布收口）+ 走完整 8 步生命周期（draft→submitted→under_review→approved→implementing→pending_acceptance→accepting→completed→closed）；台帐清理 7 条 GUI 测试残留脏数据（CHG-064~070 序号 004~010）；change list SW-2026-008 返回 4 条 closed 记录；dogfooding 第四次闭环完成

### Changed - V0.3.0 版本号升级
- pyproject.toml version 0.3.6 → 0.3.7

### Fixed - V0.3.7 台帐脏数据复发清理
- 台帐 GUI 测试残留复发：glm5.2 修复后台帐曾清理为 3 条，但全量回归测试时 GUI 测试再次写入 7 条脏数据（CHG-064~070 序号 004~010，无对应文件）；本轮再次清理为 4 条正确记录（001/062/063/064）
- **已知限制记录**：transition 命令不自动更新台帐状态行（仍为"待处理"），需手动更新台帐；GUI 测试 fixture 仅删除 CHG 文件不清理台帐条目，需后续修复（建议新增 TD 项）

### Verified - V0.3.7 Phase 6 回归测试
- 复用 V0.3.6 glm5.2 收口后全量回归基线：✅ 1155 passed, 1 skipped, 3 warnings（无回归，320s；3 warnings 为 jinja2 第三方库 DeprecationWarning）
- ruff 0 errors, mypy 0 errors
- dogfooding: CHG-SCPT-2026-064 完整 8 步生命周期闭环 ✅；change list SW-2026-008 返回 4 条 closed 记录 ✅；台帐 4 条正确记录 ✅

## [0.3.6] - 2026-06-26

### Added - V0.3.0 M3-4 T77-T79: 状态机可视化 + 列表筛选增强 + UI 测试

- **T77 状态机可视化**：auto_pm/ui/dialogs/status_machine_view.py（新增 StatusMachineView QWidget：水平展示 12 状态节点 + 11 箭头；当前状态蓝色边框 + 目标状态绿色填充 + 可达状态可点击 + 不可达状态灰色禁用；节点点击发射 target_selected 信号）；auto_pm/ui/dialogs/transition_dialog.py（集成 StatusMachineView + _on_target_selected 联动更新目标状态/标签/验证结论显隐）
- **T78 列表筛选增强**：auto_pm/models/change.py（ChangeSummary 增加 urgency 字段）；auto_pm/change/parser.py（to_summary 填充 urgency）；auto_pm/change/change_service.py（list_all_changes 增加 urgency 和 project_id 参数，内存筛选）；auto_pm/ui/change_center/change_list_panel.py（新增筛选行：领域下拉 + 紧急程度下拉 + 项目下拉；项目下拉选项从变更单列表动态提取；set_urgency_filter/set_project_filter 方法；blockSignals 防递归）
- **T79 UI 测试**：tests/ui/test_status_machine_view.py（19 测试：渲染 4 + 状态高亮 9 + 信号 3 + 动态更新 3）；tests/ui/test_change_list_panel_filters.py（22 测试：初始加载 4 + 领域 4 + 紧急程度 4 + 项目 4 + 组合 5 + 状态共存 1）；tests/ui/test_change_dialogs.py（新增 TestTransitionDialogStateMachine 7 测试：集成/当前高亮/目标高亮/目标联动/验证结论显隐/可达状态一致性）

### Fixed - V0.3.6-glm5.1/glm5.2 收口（2026-06-26）

- **phase 修复**：auto_pm/core/project_scanner.py（新增 _derive_phase_from_pm_session_content 方法，从 PM_SESSION §2/§8 关键词推导阶段 developing/commissioning/production/archived；`project show` phase 字段从 `-` 恢复为 `developing`）
- **ruff 清零**：scripts/gui_plc_full_test.py（文件级 `# ruff: noqa: E402, T201` + 删除 7 个未使用 import）；scripts/run_tests.py（文件级 `# ruff: noqa: T201`）；tests/gui/test_17_edit_change_dialog.py（2 处 `view = ...` 改为 `_view = ...`）；ruff 34 errors → 0
- **台帐重复追加 bug 修复**：auto_pm/change/ledger_updater.py（update() 添加 `change_number in content` 去重检查，防止重复追加）；auto_pm/change/file_locator.py（generate_change_number() 添加台帐序号 re 扫描，防止文件删除后编号回退）
- **台帐数据清理**：01_版本变更台帐.md 从 185 条脏数据重建为 3 条正确记录（001 archived / 062 closed / 063 closed）

### Verified
- 48 passed（test_status_machine_view + test_change_list_panel_filters + test_change_dialogs，2.17s）
- ruff 0 errors, mypy 0 errors
- 全量回归：✅ 1155 passed, 1 skipped（较 0.3.5 基线 1107 + 48 新增测试，无回归，164s）
- glm5.2 收口后全量回归：✅ 1155 passed, 1 skipped, 3 warnings（无回归，320s；3 warnings 为 jinja2 第三方库 DeprecationWarning）

## [0.3.5] - 2026-06-26

### Added - V0.3.0 M3-4: 创建变更单 QWizard 分步向导

- auto_pm/ui/dialogs/create_change_dialog.py（重写为 QWizard 分步向导：BasicInfoPage 基本信息 7 字段 + DescriptionPage 变更描述 2 字段 + ConfirmPage 提交确认汇总展示；isComplete 联动 Next 按钮；validatePage 触发创建；兼容性保留 CreateChangeDialog 别名 + 构造签名 + change_created 信号 + get_change_data + 内部控件 property + 虚拟 _button_box）
- auto_pm/ui/dialogs/__init__.py（导出 CreateChangeWizard）
- tests/ui/test_change_dialogs.py（新增 TestCreateChangeWizard 5 项测试：3 页面结构 + BasicInfoPage isComplete + DescriptionPage isComplete + ConfirmPage 汇总展示 + validatePage 创建信号；修复预存 mypy 错误：qapp/_patch_message_boxes 返回类型 + type: ignore 错误码）

### Verified
- 16 passed（test_change_dialogs.py，无 coverage 3.09s）
- ruff 0 errors, mypy 0 errors
- 全量回归：✅ 1107 passed, 1 skipped（较 0.3.4 基线 1102 + 5 新增 QWizard 测试，无回归，158s）

## [0.3.4] - 2026-06-26

### Added - V0.3.0 M3-2: 传播链可视化

- auto_pm/ui/change_center/propagation_view.py（新增 PropagationView QGraphicsView：水平展示传播链，圆角矩形节点+箭头连线；_parse_chain 解析 `->`/`→` 分隔符为节点+边；节点显示领域中文名 via DOMAINS 映射；空链"无跨领域影响"提示；DEBUG 级别 tracing 覆盖解析/渲染全过程）
- auto_pm/ui/change_center/change_detail_panel.py（集成传播链视图：在"参考依据"与"审批记录"之间插入"传播链"章节）
- tests/ui/test_propagation_view.py（新增 8 UI 测试：空链/None/单节点/多节点/中文名/Unicode箭头/水平方向/无箭头格式）

### Verified
- 1102 passed, 1 skipped, 3 warnings（较 0.3.3 基线 1094 增加 8 个新测试，无回归）
- ruff 0 errors, mypy 0 errors

## [0.3.3] - 2026-06-26

### Added - V0.3.0 M3-3: 审批时间线

- auto_pm/ui/change_center/approval_timeline.py（新增 ApprovalTimeline 自定义 QWidget：垂直展示变更单状态流转历史，圆点+连接线+状态流转+审批人+意见+日期；12 状态颜色映射；空历史"暂无审批记录"提示）
- auto_pm/change/change_service.py（新增 list_approval_history 方法：委托 ChangeRequestRepository.list_approval_history → ApprovalHistoryRepository.list_by_change，按 id 升序返回审批记录；无 DB 时返回空列表）
- auto_pm/ui/change_center/change_detail_panel.py（集成审批时间线：在"参考依据"与"状态流转按钮"之间插入"审批记录"章节）
- tests/ui/test_approval_timeline.py（新增 7 UI 测试：空历史提示 + 单条/多条记录节点数与连接线 + 状态流转文案 + 审批人意见 + 圆点颜色 + 无 DB 不崩溃）

### Verified
- 1094 passed, 1 skipped, 3 warnings（较 0.3.2 基线 1087 增加 7 个新测试，无回归）
- ruff 0 errors, mypy 0 errors

## [0.3.2] - 2026-06-26

### Added - V0.3.0 M3.5: 真源收口 Round 2 + 产品自洽 Round 2

#### M3.5-1~3: GUI 测试污染清理 + TD-T04 复发修复 + 真源收口 R2
- tests/gui/test_17_edit_change_dialog.py（新增 _cleanup_test_changes autouse fixture，模块级跟踪 + os.remove 删除残留变更单）
- 删除 60 个 GUI 测试残留变更单 CHG-SCPT-2026-002~061
- tests/gui/test_17_edit_change_dialog.py（修复 TD-T04 复发：4 处 `if dlg is not None:` → `assert dlg is not None`）
- spec.md/tasks.md/006_技术债评估报告.md/001_PRD.md/PM_SESSION 五端对齐 1087 passed

#### M3.5-4~5: CHG-SCPT-2026-001 内容补全 + CHG-SCPT-2026-062 完整生命周期
- CHG-SCPT-2026-001.md（§5/§6/§7/§8/§9/§10/§11/§12 全部填充真实内容 + 文档版本 V1.0.0→V2.1.0）
- CHG-SCPT-2026-062.md（V2.1.0 模板创建 + 8 次状态流转走完完整生命周期 draft→submitted→under_review→approved→implementing→pending_acceptance→accepting→completed→closed）

#### M3.5-6: change show 命令增强
- auto_pm/models/change.py（ChangeRequest 新增 `sections: dict[str, str]` 字段，存储按章节号拆分的原始 Markdown 文本）
- auto_pm/change/parser.py（解析时保存 `cr.sections = sections`）
- auto_pm/cli/change.py（新增 `_display_section_6/8/9/10` 四个渲染函数 + `_parse_md_table`/`_extract_subsection`/`_truncate` 辅助函数；cmd_show 调用渲染 §6.1/§6.2/§6.3 + §8.1/§8.2 + §9 + §10.1/§10.2/§10.3 共 10 张 rich.Table）

#### M3.5-7: CLI 表格不截断
- auto_pm/cli/change.py（cmd_list 所有短列 min_width+no_wrap=True + 标题列 ratio=1 吸收剩余空间 + 新增 `--full` 选项标题列 overflow="fold" 自动换行；120 宽度下 8 列完整显示）

#### M3.5-8: 新增 change edit CLI 命令
- auto_pm/cli/change.py（新增 cmd_edit 命令，8 个字符串/枚举字段：§4 background/necessity/references/planned_date/urgency + §6 risk_level/mitigation/propagation_chain；复用 ChangeService.update_change_request；dict 字段 constraint_impacts/domain_impacts 留 GUI EditChangeDialog）
- auto_pm/cli/change.py（修复 _display_section_6 中 risk_level/mitigation 误被 has_constraint 门控的显示 bug + click.exceptions.Exit 误捕获）

### Changed - V0.3.0 版本号升级
- pyproject.toml version 0.3.1 → 0.3.2

### Verified - V0.3.0 M3.5 回归测试
- 全量测试：1087 passed, 1 skipped, 3 warnings（与 M3.5-3 一致，M3.5-6/7/8 为 CLI 增强 + bug 修复，未新增测试文件）

## [0.3.1] - 2026-06-25

### Added - V0.3.0 M2: 影响分析与审批记录持久化

#### M2-1: DB schema 扩展（impact_analysis + approval_history 两张表）
- auto_pm/db/schema.py（新增 DDL_IMPACT_ANALYSIS 和 DDL_APPROVAL_HISTORY 两张表定义 + approval_history 索引；TABLE_DDL/INDEX_DDL 列表更新）
- auto_pm/db/connection.py（drop_all 方法新增 DROP TABLE IF EXISTS approval_history/impact_analysis）
- auto_pm/models/change.py（新增 ImpactAnalysis 和 ApprovalRecord 两个 Pydantic v2 持久化模型）
- auto_pm/models/__init__.py（导出 ImpactAnalysis 和 ApprovalRecord）
- auto_pm/db/repository.py（新增 ImpactAnalysisRepository 类：upsert/get_by_change_number/delete；新增 ApprovalHistoryRepository 类：insert/list_by_change/delete_by_change）
- tests/db/test_repository.py（新增：3 个测试类 19 个测试，覆盖 ImpactAnalysisRepository/ApprovalHistoryRepository/ChangeRequestRepositoryExtension）

#### M2-2: ChangeRequestRepository 扩展（4 个委托方法）
- auto_pm/db/repository.py（ChangeRequestRepository.__init__ 组合 ImpactAnalysisRepository + ApprovalHistoryRepository；新增 4 个委托方法：save_impact_analysis/get_impact_analysis/save_approval_record/list_approval_history）

#### M2-3: ChangeService 集成（DB 持久化同步）
- auto_pm/change/change_service.py（__init__ 新增 ProjectRepository 组合，用于满足 change_requests 表外键约束；create_change_request 同步写入 projects + change_requests + impact_analysis；transition_status 同步写入 approval_history；update_change_request 同步更新 impact_analysis）
- tests/change/test_change_service_db.py（新增：5 个集成测试，覆盖 create/transition/update 的 DB 持久化 + 未注入 DB 向后兼容）

#### M2-4: parser.py 解析增强
- auto_pm/change/parser.py（新增 to_impact_analysis(cr) 方法，将 ChangeRequest 的 §6 影响分析字段转换为 ImpactAnalysis 持久化模型）
- tests/change/test_parser.py（新增：test_to_impact_analysis 和 test_to_impact_analysis_empty_fields 2 个测试）

### Changed - V0.3.0 版本号升级
- pyproject.toml version 0.3.0 → 0.3.1

### Verified - V0.3.0 M2 回归测试
- 全量测试：1055 passed, 3 warnings（较 M1 的 1029 增加 26 个测试）
- tests/db/：19 passed（M2-1 + M2-2 新增）
- tests/change/：含 M2-3 5 个集成测试 + M2-4 2 个解析测试

## [0.3.0] - 2026-06-25

### Added - V0.3.0 M1: 变更单章节结构对齐 040 模板 V2.2.0

#### M1-1: §6.1 风险等级+缓解措施字段（PMBOK 风险评估）
- auto_pm/models/change.py（新增 risk_level 和 mitigation 字段，PMBOK 风险评估）
- auto_pm/change/generator.py（新增 _render_risk_level 方法，§6.1 表格下方渲染风险等级和缓解措施）
- auto_pm/change/parser.py（新增 _parse_risk_level 和 _parse_mitigation 方法）
- tests/change/test_generator.py（新增 test_section_6_1_fields 和 test_section_6_1_fields_default）
- tests/change/test_parser.py（新增 test_parse_risk_level_mitigation 和 test_parse_risk_level_none）

#### M1-2: §10 改为三节结构
- auto_pm/change/generator.py（§10 从 2 节改为 3 节：§10.1 验证项清单 | §10.2 跨领域联动验证 | §10.3 验证结论）
- auto_pm/change/markdown_editor.py（update_verification_conclusion 适配 §10.3，兼容旧 §10.2；append_to_verification_table docstring 更新）
- auto_pm/change/parser.py（_extract_verification_conclusion 适配 §10.3；新增 _extract_conclusion_section_text 和 _parse_cross_domain_verification 方法）
- tests/change/test_generator.py（新增 test_section_10_three_subsections）
- tests/change/test_markdown_editor.py（新增：3 个测试覆盖三节结构下追加验证项、更新 §10.3 结论、向后兼容旧 §10.2）

#### M1-3: §11 版本详细变更说明 + §12 附录
- auto_pm/change/generator.py（§11 从"附录"改为"版本详细变更说明"，新增 §12 附录含填写指南和参考资料）

#### M1-4: 文档版本号对齐 040 模板
- auto_pm/change/generator.py（§1 和文档末尾"文档版本"从 V1.0.0 升级为 V2.1.0，表示基于 V2.1.0 模板生成）
- tests/change/test_generator.py（新增 test_document_version_aligned_with_template）

#### M1-5: 040 §3.4 变更状态字段定义
- 040_通用变更单模板_CHG.md（§3.4 新增"变更状态"字段；frontmatter/§1/文档末尾版本号 V2.1.0→V2.2.0；§2 添加 V2.2.0 条目；§11 添加 V2.2.0 详细变更说明）

### Changed - V0.3.0 版本号升级
- pyproject.toml version 0.2.3 → 0.3.0
- 040 规范模板版本 V2.1.0 → V2.2.0（§3.4 新增变更状态字段）

### Verified - V0.3.0 M1 回归测试
- 全量测试：1029 passed, 3 warnings（较 M0.5 的 1019 增加 10 个测试）
- tests/change/：143 passed（含 M1 新增 10 个测试）

## [0.2.3] - 2026-06-24

### Added - V2.0.3: 规范漂移检测能力补齐
- auto_pm/plc/spec_snapshot.py（新增：Spec Snapshot 解析器，提供 `parse_spec_snapshot`/`load_spec_registry`/`compare_versions` 三个函数 + `DriftItem` dataclass，正则解析 PM_SESSION 中的 Spec Snapshot 表格，对比 spec_registry.json，判定 major/minor/patch 漂移级别）
- auto_pm/plc/checker.py（新增第 5 项检查 `Spec Snapshot`：在 PM_SESSION 检查通过后调用 `_check_spec_snapshot`，major 漂移=FAIL，minor/patch 漂移=WARN，无漂移=PASS；边界处理：PM_SESSION 缺失跳过、registry 缺失 WARN、Spec Snapshot 表格缺失 WARN）
- auto_pm/plc/repairer.py（新增 Spec Snapshot 自动修复：在 PM_SESSION 修复后调用 `_repair_spec_snapshot`，从 spec_registry.json 读取最新版本，正则替换 PM_SESSION 中 Spec Snapshot 表格的版本号列；dry_run 模式仅输出预览不修改文件）
- tests/plc/test_spec_snapshot.py（新增：18 个单元测试，覆盖标准表格解析/非标准格式/registry 加载/版本对比）
- tests/plc/test_checker_spec_snapshot.py（新增：5 个单元测试，覆盖无漂移 PASS/主版本 FAIL/次版本 WARN/Spec Snapshot 缺失 WARN/registry 缺失 WARN）
- tests/plc/test_repairer_spec_snapshot.py（新增：4 个单元测试，覆盖自动修复/dry-run 预览/无漂移跳过/Spec Snapshot 缺失跳过）

### Changed - V2.0.3: 版本号统一
- pyproject.toml version 0.2.1 → 0.2.3（跳过 0.2.2，因 CHANGELOG 已记录；与 CHANGELOG 最新条目一致）
- PRD 文档版本 V2.0.2 → V2.0.3（新增 V2.0.3 路线图章节）
- PM_SESSION §2 Current Focus 与 §8 Handoff Notes 版本号统一为 V0.2.3（原 §2=V2.0.1、§8=V0.2.2 矛盾）

### Added - V2.0.3: 文档同步
- 00_项目基础信息/005_变更记录_CHG.md（新增：V2.0.3 变更记录文件，记录本次迭代所有变更条目）
- .trae/rules/project-rule.md（新增"迭代文档同步规则（强制）"章节：进度基线强制/迭代后同步/版本号一致性/里程碑核查/变更记录 5 条强制规则）

### Fixed - V2.0.3: 工具能力缺口
- 修复 auto-pm `plc check` 无法检测规范版本漂移的问题（原仅检查项目结构，不对比 PM_SESSION Spec Snapshot 与 spec_registry.json）
- 修复 auto-pm `plc check --fix` 无法自动修复规范版本漂移的问题（原仅修复项目结构问题，不更新 Spec Snapshot 版本号）

## [0.2.2] - 2026-06-23

### Added - V0.2.2 Phase 3: P1 模板重构（3 套 PLC 模板）
- templates/plc-shared-library/（新增：公共库模板，对应 `--mode shared-library`，按功能块类型分目录 actuator/communication/convert/counter/edge/log/pulse/timer/types）
- templates/plc-test-suite/（新增：公共库验证模板，对应 `--mode test-suite`，精简结构 OB1/DB1/FB_/Test）
- templates/plc-standard-project/（重命名自 plc-standard，扩展目录结构，对应 `--mode standard-project`，含 LSP-907 标准目录 + 程序文档）
- auto_pm/core/constants.py（新增：集中定义 STACK_TEMPLATE_MAP/PLC_MODE_TEMPLATE_MAP/get_template_name/get_plc_template_name/业务线选项/技术栈选项/项目阶段选项，消除散落常量）

### Added - V0.2.2 Phase 2: P0 架构合规（PlcService 统一入口）
- auto_pm/plc/service.py（新增：PlcService 类，封装 PlcChecker/PlcRepairer/SubstanceChecker，提供 check/repair/standardize/check_substance/check_workspace 统一入口）
- CLI/UI 层通过 PlcService 操作 PLC 项目，不再直接访问 PlcChecker/PlcRepairer/SubstanceChecker（C-2/C-3 架构合规修复）

### Added - V0.2.2 Phase 5: P2 检查器增强（CLI 选项）
- cli/plc/__init__.py: `plc check` 新增 `--substance` 选项（文档实质化检查，V2.0.1-B）
- cli/plc/__init__.py: `plc check` 新增 `--fix` 选项（检查后自动修复非破坏性问题）
- cli/plc/__init__.py: `plc init` 新增 `--mode` 选项（shared-library/test-suite/standard-project）
- cli/project.py: `project create --stack plc` 新增 `--mode` 选项

### Added - V0.2.2 Phase 6: P2 测试补全
- tests/plc/test_cli.py: CLI 测试从 4 个扩展到 19 个（覆盖 --substance/--fix/--mode 选项 + retrofit PLC 标志文件补全 + 各命令正常/异常路径）（C-6）
- tests/plc/test_e2e.py: 新增端到端测试 3 个（plc init → check → repair 全流程，覆盖三种 mode）（H-9）
- tests/plc/test_templates.py: 新增模板测试 5 个（三套模板 copier copy 渲染验证 + 目录结构断言 + .plc.json 配置验证）

### Changed
- CLI 层 PLC 操作统一通过 PlcService 入口（原直接访问 PlcChecker/PlcRepairer）
- `project retrofit` 命令增强：对 PLC 项目自动补全 .plc.json/PM_SESSION/PRD 标志文件（通过 PlcService.repair 实现）（H-4/H-10）
- 模板映射从散落常量集中到 core/constants.py（STACK_TEMPLATE_MAP + PLC_MODE_TEMPLATE_MAP）
- STACK_TEMPLATE_MAP["plc"] 从 "plc-standard" 改为 "plc-standard-project"（模板重命名）
- PlcChecker.resolve_project_id 从私有方法 `_resolve_project_id` 提升为公共方法（H-1/H-2）
- PlcChecker 新增 syslib_fb 项目类型识别（目录名以 FB_ 开头且路径含 SysLib）

### Fixed - V0.2.2 Phase 1: Git 环境修复
- C-1: .gitignore 未排除 .auto-pm/ 缓存目录，导致 SQLite 缓存文件被误提交

### Fixed - V0.2.2 Phase 4: P1 SubstanceChecker 修复
- C-4: SubstanceChecker 字数统计语义错误（中英文混合统计，阈值不合理）→ 中文按字符数 ≥ 800，英文按词数 ≥ 1000，任一达标即 PASS
- H-6: SubstanceChecker 章节正则 `^##\s*` 误匹配 `###` 三级标题 → 改为 `^##(?!\s*#)\s*`（负向前瞻，排除 ### 及以上）
- H-7: SubstanceChecker 占位符检查仅计数无严重程度分级 → 密度 > 70% FAIL，30-70% WARN，≤ 30% PASS

### Fixed - V0.2.2 Phase 5: P2 检查器增强
- H-8: PlcChecker libraries 路径仅检查目录存在，未校验关键文件 → 新增深度校验（检查 timer/FB_TON.scl、counter/FB_CTD.scl、counter/FB_CTU.scl 等关键文件）
- H-1/H-2: PlcRepairer 访问 PlcChecker 私有方法 `_resolve_project_id` → 改为公共方法 `resolve_project_id`

## [0.2.1] - 2026-06-22

### Added - V2.0.1-A: 修复 site 模块 GBK 编码崩溃
- auto_pm/__main__.py（新增：设置 PYTHONUTF8=1 环境变量，防止子进程 site 模块 GBK 解码崩溃）
- auto_pm/cli/__main__.py（Windows GBK 终端编码兼容：sys.stdout 重新包装为 UTF-8）

### Added - V2.0.1-C: 042/016 规范对齐代码实施（19 项冲突修复）
- enums.py: ChangeStatus Literal 新增 `archived` 状态（C-01）
- models.py: STATUS_FLOW 新增 `completed→archived` 流转 + `archived` 终态；STATUS_LABELS 新增 `archived: "已归档"`（C-02/C-03）
- change_service.py: 5 处修改
  - `_check_transition_guards` 新增 `archived` 门禁（仅 completed 可归档）（C-05）
  - `transition_status` 新增 `archived` 分支（C-07）
  - `rejected→draft` 门禁要求附 comment（C-08）
  - `conditionally_approved→implementing` 门禁要求附 comment（C-10）
  - 审批环节名称从英文大写改为中文语义化标签（对齐 STATUS_LABELS）（C-11）
  - `_get_change_file_path` / `_find_change_file` 支持 PLC + Python 双路径搜索（C-15/C-16）
- parser.py: `_infer_status_from_approval` 新增 `conditionally_approved` 推断路径（☑有条件通过）+ archived 说明注释（C-18/C-19）
- path_resolver.py: `find_ledger_file` 支持 PLC + Python 双路径台帐搜索（C-17）

### Changed
- 状态机从 11 状态扩展为 12 状态（对齐 PM-042 V2.3.0 §5.2）
- 变更管理路径解析从 PLC 单路径改为 PLC/Python 双路径优先匹配
- 审批环节名称从 APPROVED/REJECTED 等英文改为已批准/已驳回等中文

### Fixed
- Windows 下 `python -m auto_pm` 因 .pth 文件 UTF-8 路径触发 GBK 解码崩溃
- `cli/__main__.py` 模块级替换 `sys.stdout` 导致 pytest capture 崩溃（改为 `_fix_windows_encoding()` 函数，仅在 `__main__` 直接执行时调用）
- `archived` 状态无法流转到（缺少状态定义和门禁）
- `rejected→draft` 重新起草无需说明原因
- `conditionally_approved→implementing` 无需确认条件已满足
- Python 项目变更单路径无法识别（仅支持 PLC 路径）
- 台帐文件仅搜索 PLC 项目目录

## [0.2.0] - 2026-06-21

### Added - V2.0: PySide6 项目中心式 UI 基座
- PySide6 主框架（QMainWindow + 侧边栏 + 工具栏 + 状态栏 + QStackedWidget）
- 项目列表首页（卡片网格 + 统计栏 + 筛选栏 + 四态切换）
- 项目工作区（Tab 容器 + 概览/变更/检查/文档 Tab）
- 全局功能页骨架（规范中心/模板管理/报告中心/系统设置）
- 项目 CRUD 对话框（新建/编辑/删除/导入）
- 变更中心（变更列表 + 详情面板 + 创建对话框 + 状态流转）
- 导航树（项目列表/全局功能页切换）
- 多角色适配（PM/PLC/Python/SpecEditor 角色-Tab 映射）
- 总库管理（项目导入 + 多业务线分类 SW/DJ/ZD/XT/WX + 搜索）
- business_line 字段（DB 迁移 + extract_business_line 函数）
- Bug-1~5 修复（路径匹配/扫描路径/枚举对齐/模板推断/扫描深度）
- 接口文档 (INT) - 覆盖 CLI/Service/JS Bridge 三部分接口
- 详细设计说明书 (DSN) - 数据库设计/状态机设计/模板设计/GUI原型设计
- 技术方案文档 (TEC) - 技术选型论证/增量扫描策略/数据真源策略
- GUI 文档 Tab - 项目文档状态查看
- GUI 规范检查 Tab - LSP-907 检查/修复
- GUI 变更单创建功能
- GUI 概览 Tab 增强 - 变更概览统计和最近活动

### Changed
- UI 技术栈从 pywebview 迁移到 PySide6
- 移除 auto_pm/gui/ pywebview 层
- cli/gui.py 启动入口改为 PySide6
- README.md 完全重写，反映实际 CLI 命令和功能
- PRD 补充 frontmatter、文档基础信息表、版本变更记录表
- PM_SESSION 更新 P5 完成状态

### Fixed
- Bug-1: _get_project_path 按 {project_id}_{project_name} 模式匹配
- Bug-2: _sync_changes 在 00_项目管理/04_变更管理/01_变更单/CHG-*/ 路径扫描
- Bug-3: GUI 变更单弹窗枚举对齐 _change_constants.py
- Bug-4: retrofit 命令 _src_path 推断逻辑修正
- Bug-5: 扫描深度统一为 depth=4

## [0.1.0] - 2026-06-19

### Added - P5: SQLite 索引缓存 + Pydantic v2 模型 + pywebview GUI
- SQLite 索引缓存层（3 表：projects / change_requests / scan_log）
- 增量扫描策略（file_mtime 判据，SyncService）
- Pydantic v2 模型层（Project / ProjectRecord / ChangeRequest / ChangeSummary / DTO）
- pywebview 桌面 GUI 应用
- GUI JS Bridge API（GuiApi 类，8 个方法）
- GUI 前端（项目列表/详情/新建/编辑/删除/变更单查看/缓存同步）
- DatabaseManager（WAL 模式，连接池）
- ProjectRepository / ChangeRequestRepository / ScanLogRepository
- ApiResponse[T] 统一返回格式

### Added - P4: python-tool Copier 模板
- templates/python-tool/ Copier 模板
- copier.yml 问题定义（7 个字段 + validator）
- pyproject.toml.jinja（hatchling + 标准化依赖）
- 完整包结构模板（cli/core/config/logging/utils 五层）
- tests/ 模板（conftest + test_import）
- .ruff.toml / .pre-commit-config.yaml / Taskfile.yml 模板
- PM_SESSION / PRD / README Jinja2 模板

### Added - P3: 变更管理迁移
- auto_pm/change/ 包（7 模块）
- change/models.py - 变更单模型 + 规范常量
- change/path_resolver.py - 路径解析 + 安全校验
- change/parser.py - 变更单 Markdown 解析器
- change/generator.py - 变更单 Markdown 生成器
- change/ledger_updater.py - 版本变更台帐更新器
- change/change_service.py - 变更管理 Service
- cli/change.py - change 命令组（list/show/create/transition）
- 完整状态机实现（PM-042 V2.2.0）
- 门禁校验（draft→submitted / under_review→approved / 等）
- 19 个测试用例全部通过

### Added - P2: Click 插件架构 + Service 层迁移
- Click 插件架构（cli/__main__.py 主入口）
- cli/project.py - project 命令组（list/create/show/edit/delete/retrofit）
- cli/plc/ - plc 命令组（init/check/repair/standardize）
- cli/python/ - python 命令组（占位）
- cli/template.py - template 命令组（list/update）
- cli/gui.py - gui 命令
- core/project_service.py - 项目 CRUD Service + 文件系统扫描
- core/template_service.py - Copier 模板调度 Service
- plc/checker.py - LSP-907 检查器
- plc/repairer.py - 自动修复器
- app_context.py - AppContext 全局上下文
- config/app_config.py - pydantic-settings 配置
- logging/logging.py - 幂等 Logger
- utils/file_utils.py - 文件读写工具

### Added - P1: Copier 模板 PoC 验证
- templates/plc-standard/ Copier 模板
- copier.yml 问题定义
- .plc.json.jinja / .copier-answers.yml.jinja
- PM_SESSION / PRD / DSN / TEC / INT 文档模板
- 标准目录结构（02_PLC程序 / 03_HMI设计 / 04_变更管理 / 04_现场调试）
- PoC 验证通过：copier copy 生成符合 LSP-907 的项目骨架

### Technical Decisions
- 技术栈选型: Click + Rich + Pydantic v2 + Copier + pywebview + SQLite(WAL)
- 构建系统: hatchling
- 代码质量: ruff + mypy (strict) + pytest
- 数据真源策略: .copier-answers.yml / PM_SESSION / index.db 三源并存
- 增量扫描: file_mtime 判据，避免全量扫描开销
- CLI 插件架构: Click 子命令组 + 延迟导入避免循环依赖
- GUI 模式: pywebview JS Bridge + ApiResponse[T] 统一格式

### Toolchain
- 取代 pm-mgr (SW-2026-007)
- 取代 plc-check
- 与 specmgr (SW-2026-006) 互补
