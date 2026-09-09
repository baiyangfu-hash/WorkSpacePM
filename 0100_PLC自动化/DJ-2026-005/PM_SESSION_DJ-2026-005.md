# PM_SESSION_DJ-2026-005

## 0. Meta
- project_id: DJ-2026-005
- project_name: 边框缓存机
- project_root: c:\Users\fubai\Documents\My_Workspace\0100_PLC自动化\DJ-2026-005
- last_updated: 2026-09-09
- owners: fubai / PM & PLC协作团队
- cockpit_status: 已登记到 Workspace Registry；由 PM-056、Continuity Store 与稳定驾驶舱运行时治理

## 1. Positioning（项目定位）
- one_liner: 边框缓存机 PLC/HMI 软件工程交付与维护
- users: 设备调试/维护工程师；产线操作人员
- non_goals: 上位机SCADA系统开发

## 2. Current Focus（当前焦点）
- current_focus: 原始源程序 PDF 工艺 100% 还原与 STD-840 对象化 SCL 重构闭环
- milestone: 门禁 100% 绿门禁 (51 PASS, 0 WARN)；全量源程序梯形图工艺时序与 10 组配方示教系统对齐 ✅
- acceptance:
  - ✅ 召回原版三菱梯形图/FBD/注释/HMI全部 12 份 PDF 并归档为单一真源
  - ✅ 重构 FB_1002：10s反转排空初始化、安全区干涉互锁、单阀双气缸双端全检、5s满料防侧翻自动减速
  - ✅ 重构 FB_1003：小车 4 槽位光电防重叠调度算法、小车接料安全位互锁、10组配方与示教点位 UDT
  - ✅ 重构 FB_1004：X2 台车三点位移动、STD-820 打胶机安全区与抓料可交握

## 3. Status Summary（当前状态摘要）
- in_progress: 当前无活动 Work/Run；G3 工艺对齐验收作为历史项目状态保留
- next_up: `pm resume DJ-2026-005 --json` 后建立独立 Work/Run；现场侧仍为 TIA Portal 编译验证与 GP-Pro EX 点表同步
- open_questions: 无
- risks_dependencies: 需现场 TIA Portal 环境进行实机编译下装

## 4. Work Definition（工作定义与模块索引）

### 4.1 规范与程序级方案层 (00_程序方案/ 单一真源)
- naming-spec:  ..\..\00_Obsidian_Base全局规范文件仓库\03_PLC自动化域\905_SCL编程规范_LSP.md
- req:          02_PLC程序\PLC_ST\00_程序方案\需求分析文档_REQ.md
- int:          02_PLC程序\PLC_ST\00_程序方案\接口文档_INT.md
- tec:          02_PLC程序\PLC_ST\00_程序方案\技术方案文档_TEC.md
- dsn:          02_PLC程序\PLC_ST\00_程序方案\详细设计说明书_DSN.md
- io:           02_PLC程序\PLC_ST\00_程序方案\015_IO分配表_IO.md
- flow:         02_PLC程序\PLC_ST\00_程序方案\018_自动工艺流程图_FLOW.md

### 4.2 源代码与FB模块层 (全部 VAR_IN_OUT 结构体整块传递)
- ob1:          02_PLC程序\PLC_ST\00_主程序\OB1.scl (5行顶级调度)
- db1:          02_PLC程序\PLC_ST\00_全局数据\GlobalVars.db (集中数据中心)
- fb1002:       02_PLC程序\PLC_ST\02_输送机\FB_1002_SingleLayerConveyor_BufferFraming.scl
- fb1003:       02_PLC程序\PLC_ST\03_取放料\FB_1003_PickPlace_BufferFraming.scl
- fb1004:       02_PLC程序\PLC_ST\04_打胶机送料\FB_1004_GlueMachineFeeder_BufferFraming.scl
- fb2001:       02_PLC程序\PLC_ST\05_公共报警\FB_2001_CommonAlarm_AllStation.scl
- external:     02_PLC程序\PLC_ST\01_外部设备交互\FB_ExternalDeviceInteraction.scl (DJ005基准实现；模板归一命名映射 FB_3001_ExternalInteraction)

### 4.3 监控与HMI资产
- change_mgmt:  11_监控\01_变更管理\02_变更记录\01_版本变更台账.md
- hmi-pro:      03_HMI设计\原型\files\HMI原型设计.html (11页面工业级高保真交互原型 V2.0.0)
- hmi-archive:  03_HMI设计\原型\archive_v1.6\ (历史原型归档)
- hmi-tag:      03_HMI设计\hmi_tag_mapping.json (120+ 变量与全量 71 DI / 48 DO 点表映射字典)

## 5. Changelog（变更日志）
- 2026-09-04 | CHG-PLC-2026-013: 在 FB_2001 补充外部通信心跳丢失报警代码(2010)与报警字映射(16#0010)，同步更新 接口文档_INT.md，plc check Pass=51 Warn=0 Fail=0 全绿完成闭环。
- 2026-09-03 | CHG-PLC-2026-012: 在 FB_2001_CommonAlarm_AllStation.scl 补充安全回看看门狗超时常量 (2009) 与全局报警字映射 (16#0008)，同步更新 接口文档_INT.md，plc check Pass=51 Warn=0 Fail=0 全绿完成闭环。
- 2026-09-01 | CHG-PLC-2026-011: 4层输送机切换为持续慢速运行机制，机器人安全区无交互时慢速输送，取料交互时停机防干涉，取料结束后自动恢复。
- 2026-08-26 | 基准真源净化: 同步 Spec Snapshot 至当前规范版本，并统一 DJ005 对外部交互模块的模板归一命名说明，避免基准项目继续输出旧口径。
- 2026-08-25 | STD-820 跨机动态安全防御闭环: 落实打胶机全套安全状态(急停/故障/心跳/允许)持续监视、小车运行途中突发异常紧急制动拦截、以及取料后 4 卡槽物理光电脱离闭环，彻底杜绝撞机风险。
- 2026-08-25 | 源程序真源对齐与对象化重构: 依据原版梯形图 PDF 深度对齐输送机(10s退料/满料防侧翻)、取放料(4槽位光电调度/10组配方)、打胶送料(STD-820交握)，全量 12 个 SCL 达成 0-Warn (Pass=51, Warn=0, Fail=0)。
- 2026-08-25 | 标杆代码强迫症级纯净化: 全量 .scl 模块变量命名与作用域全面对齐 LSP-905，消除所有 238 个 Warning。
- 2026-08-24 | 工艺定义与全真命名整改: 彻底清除“码垛”历史污染，统一更正为“贮存分料/供料 (Infeed)”。
- 2026-08-24 | HMI 原型工业级高保真重构 V2.0.0: 补全 71 DI/48 DO 全真端子排与 11 画面全结构化重塑。

## 6. Implementation Log
- 2026-09-04 | CHG-PLC-2026-013 落账完成: FB_2001 挂接心跳丢失报警代码与报警字映射，更新接口文档；子代理 AI-20260904-022144-A110233A 门禁全绿，PM 已消费闭环，变更单已关闭，台账一致 [已验证]
- 2026-09-03 | CHG-PLC-2026-012 落账完成: FB_2001 挂接看门狗超时报警逻辑 (2009 / 16#0008)，更新接口文档；子代理 AI-20260903-193532-D803F4AA completed 并由 PM consumed；plc check 51 PASS, 0 WARN, 0 FAIL [已验证]
- 2026-09-01 | CHG-PLC-2026-011 落账完成: 修改 FB_1002 STEP_10_AUTO_START，收敛原 STEP 20/30/50/60/70/80 分段送料为单步持续慢速策略；plc check Pass=51 Warn=0 Fail=0 -> ALL PASS [已验证]
- 2026-08-26 | 基准项目真源净化完成: Spec Snapshot 漂移归零，REQ/DSN/INT 旧前缀与外部交互模块命名说明完成收口 | plc check 51 PASS, 0 WARN, 0 FAIL [已验证]
- 2026-08-25 | 源程序梯形图工艺还原闭环: FB_1002 / FB_1003 / FB_1004 全量重构对齐，通过全量门禁与单测 | plc check 51 PASS, 0 WARN, 0 FAIL [已验证]
- 2026-08-25 | LSP-905 0-Warn 纯净化达成: 全量 SCL 静态扫描 Warning 彻底清零 | plc check 51 PASS, 0 WARN, 0 FAIL [已验证]
- 2026-08-24 | 澄清与整改完成: ST_ExternalDevice / FB_ExternalDeviceInteraction（现模板归一命名：FB_3001_ExternalInteraction）/ REQ / HMI 文档全面修正为 Infeed 供料 [已验证]
- 2026-08-24 | HMI 原型 V2.0.0 全真重构与全物理点表补完完成，11 页面全功能通过 [已验证]

## 8. Handoff Notes
- 2026-09-04 | from=pm-workflow | to=plc-electrical-engineer | mode=execution | request_id=AI-20260904-022144-A110233A | status=consumed
  - task_dispatched: FB_2001 外部通信心跳丢失报警(STD-860/STD-820)扩展与接口文档更新
  - result: 子代理完成 SCL 编码与 INT.md 同步；plc check 51 PASS, 0 WARN, 0 FAIL 全绿；CHG-PLC-2026-013 closed 归档，PM 已消费闭环。
- 2026-09-03 | from=pm-workflow | to=plc-electrical-engineer | mode=execution | request_id=AI-20260903-193532-D803F4AA | status=consumed
  - task_dispatched: FB_2001 安全传感器超时报警与接口文档更新
  - result: 子代理已提交结构化回执，FB_2001 常量与位逻辑已对齐 LSP-905，INT.md 已同步；CHG-PLC-2026-012 已流转至 completed，台账对账全绿，PM 已消费闭环。
- 2026-09-01 | from=pm-workflow | to=plc-electrical-engineer | reason=CHG-PLC-2026-011 收尾治理
  - task_dispatched: 复核 4层输送机持续慢速运行改动，剔除未实现 CHG-PLC-2026-012 与旧版 USAGE 草稿，避免混入迁移前工作树。
  - execution_result: FB_1002 静态门禁通过；PM_SESSION 乱码污染已移除；版本台账仅保留已实现并关闭的 CHG-PLC-2026-011。
  - pm_acceptance: 准许作为独立 PLC 变更提交；TIA Portal 实机编译仍由现场环境后续闭环。
- 2026-08-25 | from=pm-workflow | to=plc-electrical-engineer | reason=源程序梯形图工艺真源对齐
  - task_dispatched: 派发基于 01_梯形图.pdf / 04_FB_FUN.pdf 的输送机 9 步状态机、取放料 4 槽位供需调度与 10 组配方、打胶送料 X2 轴 STD-820 交握重构。
  - execution_result: plc-electrical-engineer 完成全量 SCL 编码与门禁验证，达成 Pass=51, Warn=0, Fail=0 全绿。 [已验证]
  - pm_acceptance: PM 确认工艺时序、安全互锁与 10 组配方 UDT 契约 100% 吻合，准予结项落账。 [已验证]

## 9. Next Actions
- [P0] TIA Portal 编译验证 | done_when=无编译错误
- [P1] 现场上机信号联调 | done_when=完成实机IO及工装握手测试

## Spec Snapshot（基线，供版本漂移检测）
| spec_id | 版本 | 记录日期 | 说明 |
|---------|------|---------|------|
| PROJ-016 | V1.2.0 | 2026-08-01 | 通用项目结构模板 (已漂移 V1.1.0→V1.2.0，已确认) |
| REQ-020 | V1.1.0 | 2026-06-06 | 通用需求分析文档模板 |
| LSP-905 | V1.2.1 | 2026-06-06 | SCL编程规范 |
| LSP-904 | V1.2.0 | 2026-06-06 | SCL注释规范 |
| LSP-903 | V2.1.0 | 2026-06-06 | 定时器使用规范 |
| LSP-906 | V2.1.0 | 2026-06-06 | PLC编程错误预防规则 |
| LSP-907 | V1.3.0 | 2026-06-06 | PLC项目配置规范 |
| INT-815 | V1.1.0 | 2026-06-06 | PLC接口文档模板 |
| PLC-023 | V2.1.0 | 2026-06-06 | PLC程序设计文档模板 |
| DEV-004 | V1.1.1 | 2026-06-06 | 通用项目文档版本管理与变更核心规范 |
| CHG-040 | V2.2.0 | 2026-08-01 | 通用变更单模板 (已漂移 V2.1.0→V2.2.0，已确认) |
| CHG-041 | V2.1.0 | 2026-06-06 | 通用版本变更台帐模板 |
| PM-042 | V2.4.0 | 2026-06-06 | 通用变更管理流程规范 |
