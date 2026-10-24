# PLC 现场调试与上机复核 Checklist (DJ-2026-005 边框缓存机)

## 1. ✅ 本地 LSP 验证承诺区 (100% 自动通过)

- [x] **SCL 语法合规**：0 Error / 0 Warning（已通过 Siemens LSP 诊断，遵循 LSP-905/904/903 规范）
- [x] **作用域与依赖**：`.plc.json` 解析通过，指向 `../../../01_SharedLibraries/SysLib` 库依赖映射 5/5 健全
- [x] **变量前缀标准**：`FB_2001` 等所有 FB 的 `VAR_OUTPUT` 统一采用 `q_` 小驼峰前缀
- [ ] **单元测试集**：`mode_alarm_test.scltest`、`conveyor_test.scltest`、`manual_home_external_test.scltest`（新设计，2026-10-24 已写、待本机 `plc test` 跑通；旧 basic_test / interlock_test 已随旧设计删除）
- [x] **台账与 PM 闭环**：`auto-pm ledger reconcile DJ-2026-005` 自动对账一致，CHG 变更单完工闭环

---

## 2. ⚠️ 现场物理复核重点区 (需调试工程师在设备旁打勾确认)

- [ ] **硬限位与伺服原点 (SV 轴系统)**
  - Z 轴（升降轴）、X1 轴（取放料横移轴）、X2 轴（打胶送料轴）物理正负限位开关接线与 ORG 原点传感器极性核对。
- [ ] **打胶机交互物理 IO 地址 (X76 / X102 / Y44 / Y47)**
  - 打胶机允许送料输入信号（物理地址 X76）电平逻辑确认。
  - 打胶机取料完成输入信号（物理地址 X102）脉冲宽度确认。
  - 允许取料输出（Y44）与安全区控制信号（Y47）硬件继电器开闭复核。
- [ ] **双电磁阀控制逻辑 (Clamp Action vs Release)**
  - 夹爪动作电磁阀 `o_b*Clamp_Action` 与松开电磁阀 `o_b*Clamp_Release := NOT Action` 的气路常开/常闭极性测试。
- [ ] **急停与安全回路物理切断**
  - 现场按下急停按钮后，PROFINET 驱动器 Enable 信号切断与变频器硬安全门锁闭合测试。

---

## 3. 📝 现场调试参数实测记录表

| 参数项 | SCL 代码默认值 | 现场实测最佳设定值 | 调试工程师 | 调试日期 |
|---|---|---|---|---|
| 送料超时时间 (`i_iSeparateTimeoutMs`) | 5000 ms | ______ ms | | |
| 传感器消抖时间 (`i_dDebounceMs`) | 0 ms | ______ ms | | |
| Z 轴待机位坐标 (`rStandbyPosition`) | 0.0 mm | ______ mm | | |
| X2 轴打胶机取料位坐标 (`rPickupPosition`) | 300.0 mm | ______ mm | | |
