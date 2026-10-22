# FB_1001_Station1 变更记录

> **项目编号**: DJ-2026-009  
> **功能块**: `FB_1001_Station1`  
> **模块名称**: 工位1 动作机构控制  
> **当前版本**: V1.0.0  
> **编制人**:   
> **规范依据**: DEV-001 / PM-042 / LSP-907  

---

## 版本变更履历

| 版本号 | 变更单号 | 变更类型 | 变更描述 | 申请人 | 实施日期 |
| :---: | :---: | :---: | :--- | :---: | :---: |
| V1.0.0 | CHG-PLC-2026-001 | REQ | 初始版本创建：标准 5 步工步状态机与结构体整块传递架构 |  | 2026-08-23 |
| V1.1.0 | 无（CARD-DJ-2026-009-003 草稿，预做分支 `claude/dj009-card003`） | BUG | 删除本块对握手信号 `bMachine_ReadyIn` / `bMachine_ReadyOut` 的直接写入（OB1 接上 FB_3001 后，这几行会绕过 FB_3001 的通讯故障联锁，在断线时照样向对方发“准备好”）；新增状态位 `stStatus.bReadyOut`、`stStatus.bProductPresent`（本块内部判断有无产品）和产品传感器预留数组 `stSensors.arrProductSens[0..7]`，供 FB_3001 使用。属安全区，须仿真和用户签字 | 云端 Claude | 2026-10-21 |
| V1.2.0 | 无（CARD-DJ-2026-009-004 草稿，预做分支 `claude/safety-manager-card004`） | SAFETY | 运动只在 FB_1030 运行许可（`stControl.bSafeToRun`）下进行：许可一丢同一扫描电机清零、步序冻结（3Sun 断点续跑），两次复位 + 按启动后从断点接着走；原来报警/离开自动时两个气缸一刀切强制缩回，改按常量 `CYL1/CYL2_RETRACT_ON_STOP` 逐阀定（阀型未定前按保持）；新增 `stStatus.bFrozen`、`stStatus.bMotionStopped`（开门条件）。接口文档按代码重写引脚表（原来把结构体字段当引脚，plc check 一直报不一致）。属安全区，须仿真和用户签字 | 云端 Claude | 2026-10-22 |
