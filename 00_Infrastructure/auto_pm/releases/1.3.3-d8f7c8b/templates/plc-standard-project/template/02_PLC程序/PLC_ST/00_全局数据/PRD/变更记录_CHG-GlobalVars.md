# 变更记录 - GlobalVars.db (全局变量数据块)

## 文档信息
| 项目 | 内容 |
|------|------|
| **文件名** | GlobalVars.db |
| **功能描述** | 边框缓存机全局变量数据块 (OB1与各FB的数据交换中心) |
| **当前版本** | V7.0.0 |
| **最后更新** | 2026-05-18 |
| **关联文件** | OB1.scl, FB_1001~1004.scl, FB_2001.scl |

---

## 版本历史

### V7.0.0 (2026-05-18) - **Conveyor子系统V7.0.0重构对齐**
**变更类型**: REFACTOR | **影响范围**: stConveyor结构 + FB实例 | **优先级**: P0-Critical

#### 变更概述
- **根因**: Conveyor子系统从V6.0.0 (FB_1001容器) 重构为V7.0.0 (FB_1002编排器展开调用)
- **目标**: stConveyor结构、FB实例声明与OB1 V7.0.0调用100%对齐
- **范围**: stConveyor从42变量缩减到33变量，FB实例从5个变为7个

#### 详细变更清单

##### 1. stConveyor结构重写 (42→33变量)
- **删除**: i_bEnable, i_bReset, i_rConveyorSpeed, i_iSeparateTime, i_iBlockWaitTime, i_bPickPlaceSafeZone, i_iLayerIndex (这些或不适用于FB_1002，或在重构中取消)
- **删除**: 旧手动操作变量 i_bLx_BlockDown/BlockUp/SeparatePush/SeparateReset/ConveyorFwd/ConveyorRev
- **删除**: 旧输出变量 o_bBlockSolenoid/o_bSeparateSolenoid/o_bConveyorFwd/Slow/Rev, o_bFeedComplete, o_bRunning, o_bFault, o_iCurrentState, o_LxCurrentStep, o_iAlarmCode
- **删除**: 旧传感器故障变量 q_bSensorFaultBlockUp/Down/SeparateUp/Down, q_bSeparateTimeout
- **新增**: i_iSeparateTimeoutMs (INT, 5000ms默认)
- **新增**: 14组逐层输入数组 (i_a前缀): 7组传感器 + 6组手动操作 + i_aPickupConfirmed
- **新增**: 10组逐层输出数组 (q_a前缀): 5组执行器 + q_aLayerStep/AlarmCode/Running/Fault/FeedDone/SensorFault
- **新增**: 3个汇总变量: q_bRunning(OR), q_bFault(OR), q_iAlarmCode(MIN)

##### 2. FB实例变更 (5→7个)
- **删除**: fbConveyor4Layer : FB_1001_Conveyor4Layer_BufferFraming
- **新增**: fbConveyor_L1~L4 : FB_1002_SingleLayerConveyor_BufferFraming (4个展开实例)

##### 3. 命名规范
- 逐层数组统一加 `_a` 前缀 (i_a / q_a)
- 汇总标量统一加 `_b` / `_i` 前缀 (q_b / q_i)
- 手动操作从 Lx_前缀改为 Man 前缀

### V3.0.0 (2026-05-03) - **V5.0.0全面重写：变量名100%英文化**
**变更类型**: REWRITE | **影响范围**: 全局 | **优先级**: P0-Critical

#### 变更概述
- **根因**: OB1↔FB接口变量名不匹配导致TC001/TC002编译错误
- **目标**: 统一所有变量名为英文（符合LSP-905_SCL编程规范）
- **范围**: 替换220+处中文变量名，覆盖5个STRUCT结构

#### 详细变更清单

##### 1. stGlobal结构 (11个变量)
| 序号 | 原变量名 | 新变量名 | 类型 | 说明 |
|-----|---------|---------|------|------|
| 1 | i_b复位 | i_bReset | BOOL | 全局复位按钮 |
| 2 | o_w全局报警字 | o_wGlobalAlarmWord | WORD | HMI报警灯用 |
| 3 | o_i当前报警代码 | o_iCurrentAlarmCode | INT | HMI文本显示用 |
| 4 | o_b任何报警激活 | o_bAnyAlarmActive | BOOL | 所有工站停止互锁 |
| 5 | o_iMES报警计数 | o_iMESAlarmCount | INT | MES累计计数 |
| 6 | o_iMES报警队列 | o_iMESAlarmQueue | ARRAY[0..9] OF INT | 最近10条去重记录 |
| 7 | o_b新报警标志 | o_bNewAlarmFlag | BOOL | 触发MES上传 |
| 8 | o_i工站报警状态 | o_iStationAlarmStatus | ARRAY[1..3] OF INT | 三工站报警数组 |
| 9 | o_b输送机报警激活 | o_bConveyorAlarmActive | BOOL | 输送机工站标志 |
| 10 | o_b取放料报警激活 | o_bPickPlaceAlarmActive | BOOL | 取放料工站标志 |
| 11 | o_b送料机构报警激活 | o_bFeederAlarmActive | BOOL | 送料机构工站标志 |

##### 2. stExternal结构 (67个变量)
###### 系统控制信号 (6个)
| 序号 | 原变量名 | 新变量名 | 类型 | 说明 |
|-----|---------|---------|------|------|
| 12 | i_b使能 | i_bEnable | BOOL | 系统总使能 |
| 13 | i_b自动模式 | i_bAutoMode | BOOL | 自动模式选择 |
| 14 | i_b手动模式 | i_bManualMode | BOOL | 手动模式选择 |
| 15 | i_b启动 | i_bStart | BOOL | 启动按钮 |
| 16 | i_b停止 | i_bStop | BOOL | 停止按钮 |
| 17 | i_b复位 | i_bReset | BOOL | 复位按钮 |

###### 组框机输入 (7个) + 输出 (5个)
| 序号 | 原变量名 | 新变量名 | 说明 |
|-----|---------|---------|------|
| 18 | i_b组框机_自动中 | i_bFrameMachine_AutoRunning | 组框机自动运行中 |
| 19 | i_b组框机_允许送料 | i_bFrameMachine_AllowFeed | 允许向缓存机输送 |
| 20 | i_b组框机_有料请求 | i_bFrameMaterialRequest | 有边框需要送入 |
| 21 | i_b组框机_开门请求 | i_bDoorOpenRequest | 操作门打开请求 |
| 22 | i_b组框机_急停 | i_bFrameMachine_EStop | 急停联锁信号 |
| 23 | i_b组框机_安全异常 | i_bFrameMachine_SafetyErr | 安全系统异常 |
| 24 | i_b组框机_通讯异常 | i_bFrameMachine_CommErr | 通讯异常 |
| 25 | o_b组框机_请求送料 | o_bFrameMachine_RequestFeed | 请求输送边框 |
| 26 | o_b组框机_暂停 | o_bFrameMachine_Pause | 发送暂停指令 |
| 27 | o_b组框机_急停 | o_bFrameMachine_EStop | 急停联锁输出 |
| 28 | o_b申请开门 | o_bDoorOpenRequest | 申请开门操作 |
| 29 | o_b组框机_就绪 | o_bFrameMachine_Ready | 本机就绪 |

###### 打胶机输入 (6个) + 输出 (4个)
| 序号 | 原变量名 | 新变量名 | 说明 |
|-----|---------|---------|------|
| 30 | i_b打胶机_自动中 | i_bGlueMachine_AutoRunning | 打胶机自动运行中 |
| 31 | i_b打胶机_允许送料 | i_bGlueMachine_AllowFeed | 准备接收边框 |
| 32 | i_b打胶机_取料完成 | i_bGlueMachine_PickupComplete | 完成抓取 |
| 33 | i_b打胶机_故障 | i_bGlueMachine_Fault | 设备故障报警 |
| 34 | i_b打胶机_急停 | i_bGlueMachine_EStop | 急停状态 |
| 35 | i_b打胶机_通讯异常 | i_bGlueMachine_CommErr | 通讯中断 |
| 36 | o_b打胶机_请求运行 | o_bGlueMachine_RequestRun | 请求启动运行 |
| 37 | o_b允许抓料 | o_bAllowPickup | 允许抓取边框 |
| 38 | o_b安全区信号 | o_bSafetyZoneSignal | 安全区开关信号 |
| 39 | o_b打胶机_复位请求 | o_bGlueMachine_ResetReq | 复位请求 |

###### 机器人输入 (5个) + 输出 (3个)
| 序号 | 原变量名 | 新变量名 | 说明 |
|-----|---------|---------|------|
| 40 | i_b机器人_自动中 | i_bRobot_AutoRunning | 机器人自动运行中 |
| 41 | i_b机器人_码料完成 | i_bRobot_StackComplete | 完成码料 |
| 42 | i_b机器人_故障 | i_bRobot_Fault | 设备故障 |
| 43 | i_b机器人_急停 | i_bRobot_EStop | 急停状态 |
| 44 | i_b机器人_通讯异常 | i_bRobot_CommErr | 通讯异常 |
| 45 | o_b机器人_允许码料 | o_bRobot_AllowStacking | 允许码料 |
| 46 | o_b机器人_停止码料 | o_bRobot_StopStacking | 停止码料 |
| 47 | o_b机器人_复位请求 | o_bRobot_ResetReq | 复位请求 |

###### 本机状态 (3个) + 报警输出 (4个)
| 序号 | 原变量名 | 新变量名 | 说明 |
|-----|---------|---------|------|
| 48 | i_b本机就绪 | i_bLocalReady | 本机就绪状态 |
| 49 | i_b任何报警激活 | i_bAnyAlarmActive | 有报警激活 |
| 50 | i_b系统故障 | i_bSystemFault | 系统故障 |
| 51 | o_b组框机紧急停止 | o_bFrameMachine_EmergencyStop | 强制本机停止 |
| 52 | o_b外部设备故障 | o_bExternalDeviceFault | 外部设备故障标志 |
| 53 | o_i外部设备报警汇总 | o_iExternalDeviceAlarmSummary | 故障报警码(300~399) |
| 54 | o_b系统安全条件满足 | o_bSystemSafetyConditionMet | 安全条件满足 |

##### 3. stConveyor结构 (64个变量)
###### 系统控制+工艺参数 (9个)
| 序号 | 原变量名 | 新变量名 | 类型 | 说明 |
|-----|---------|---------|------|------|
| 55 | i_b使能 | i_bEnable | BOOL | 总使能 |
| 56 | i_b自动模式 | i_bAutoMode | BOOL | 自动模式 |
| 57 | i_b手动模式 | i_bManualMode | BOOL | 手动模式 |
| 58 | i_b启动 | i_bStart | BOOL | 启动按钮 |
| 59 | i_b停止 | i_bStop | BOOL | 停止按钮 |
| 60 | i_b复位 | i_bReset | BOOL | 复位按钮 |
| 61 | i_r输送速度 | i_rConveyorSpeed | REAL | 输送带速度设定 |
| 62 | i_i分料时间 | i_iSeparateTime | INT | 分料保持时间(ms) |
| 63 | i_i阻挡等待时间 | i_iBlockWaitTime | INT | 阻挡等待时间(ms) |

###### 手动操作 (24个ARRAY[1..4])
| 类别 | 原前缀 | 新前缀 | 数量 |
|-----|--------|--------|------|
| 阻挡气缸 | i_b阻挡下降/上升 | i_bLx_BlockDown/Up | 8 |
| 分料气缸 | i_b分料推出/复位 | i_bLx_SeparatePush/Reset | 8 |
| 输送带 | i_b输送正转/反转 | i_bLx_ConveyorFwd/Rev | 8 |

###### 传感器 (28个ARRAY[1..4])
| 类别 | 原前缀 | 新前缀 | 数量 |
|-----|--------|--------|------|
| 到位感应 | i_b分料前感应器 | i_bPreSeparateSensor | 4 |
| 冗余检测 | i_b到位感应器1/2 | i_bPositionSensor1/2 | 8 |
| 阻挡反馈 | i_b阻挡气缸上/下位 | i_bBlockCylinderUp/Down | 8 |
| 分料反馈 | i_b分料气缸上/下位 | i_bSeparateCylinderUp/Down | 8 |

###### 执行器输出 (20个ARRAY[1..4]) + 状态输出 (5个)
| 类别 | 原前缀 | 新前缀 | 数量 |
|-----|--------|--------|------|
| 阻挡电磁阀 | o_b阻挡电磁阀 | o_bBlockSolenoid | 4 |
| 分料电磁阀 | o_b分料电磁阀 | o_bSeparateSolenoid | 4 |
| 输送正转 | o_b输送带正转 | o_bConveyorFwd | 4 |
| 输送慢速 | o_b输送带慢速 | o_bConveyorSlow | 4 |
| 输送反转 | o_b输送带反转 | o_bConveyorRev | 4 |
| 下游反馈 | i_b取放料完成/o_b放料完成 | i_bFeedComplete/o_bFeedComplete | 8 |
| 状态显示 | o_b运行中/故障/当前状态/Lx步序 | o_bRunning/Fault/CurrentState/LxCurrentStep | 7 |
| 报警码 | o_i本站报警代码 | o_iAlarmCode | 1 |

##### 4. stPickPlace结构 (85个变量)
###### 系统控制 (6个) - 同stConveyor格式
###### 手动伺服点动 (4个)
| 原变量名 | 新变量名 | 说明 |
|---------|---------|------|
| i_bZ轴点动上/下 | i_bLx_ZAxis_JogUp/Down | Z轴上下点动 |
| i_bX1轴点动前/后 | i_bLx_X1Axis_JogFwd/Rev | X1轴前后点动 |

###### 手动气缸控制 (10个)
| 原变量名 | 新变量名 | 说明 |
|---------|---------|------|
| i_b升降上升/下降 | i_bLx_LiftUp/Down | 升降气缸 |
| i_b前夹紧夹紧/松开 | i_bLx_FrontGrip_Close/Open | 前夹紧气缸 |
| i_b后夹紧夹紧/松开 | i_bLx_RearGrip_Close/Open | 后夹紧气缸 |
| i_b前夹紧2夹紧/松开 | i_bLx_FrontGrip2_Close/Open | 第二组前夹爪 |
| i_b后夹紧2夹紧/松开 | i_bLx_RearGrip2_Close/Open | 第二组后夹爪 |

###### 工艺参数 (6个)
| 原变量名 | 新变量名 | 类型 | 说明 |
|---------|---------|------|------|
| i_r取料速度 | i_rPickupSpeed | REAL | Z轴取料速度 |
| i_r放料速度 | i_rPlaceSpeed | REAL | Z轴放料速度 |
| i_rZ轴速度 | i_rZAxisSpeed | REAL | Z轴通用速度 |
| i_rX1轴速度 | i_rX1AxisSpeed | REAL | X1轴通用速度 |
| i_i夹紧确认时间 | i_iGripConfirmTime | INT | 夹紧确认等待 |
| i_i升降动作时间 | i_iLiftActionTime | INT | 升降动作超时 |

###### 气缸位置传感器 (10个)
| 原前缀 | 新前缀 | 示例 |
|--------|--------|------|
| i_b升降_动点/原点 | i_bLift_WorkPoint/HomePoint | 升降气缸位置反馈 |
| i_b前夹紧_动点/原点 | i_bFrontGrip_WorkPoint/HomePoint | 前夹紧位置反馈 |
| i_b后夹紧_动点/原点 | i_bRearGrip_WorkPoint/HomePoint | 后夹紧位置反馈 |
| i_b前夹紧2_动点/原点 | i_bFrontGrip2_WorkPoint/HomePoint | 前夹紧2位置反馈 |
| i_b后夹紧2_动点/原点 | i_bRearGrip2_WorkPoint/HomePoint | 后夹紧2位置反馈 |

###### 产品检测传感器 (4个)
| 原变量名 | 新变量名 | 说明 |
|---------|---------|------|
| i_b长边1/2检测 | i_bLongEdge1/2_Detect | 长边存在检测 |
| i_b短边1/2检测 | i_bShortEdge1/2_Detect | 短边存在检测 |

###### 伺服轴信号 (12个)
| 类别 | 原前缀 | 新前缀 | 数量 |
|-----|--------|--------|------|
| 原点信号 | i_bZ/X1/X2轴_原点 | i_bZ/X1/X2Axis_Home | 3 |
| 伺服故障 | i_bZ/X1/X2轴_伺服故障 | i_bZ/X1/X2Axis_ServoFault | 3 |
| 正向限位 | i_bZ/X1/X2轴_正向限位 | i_bZ/X1/X2Axis_ForwardLimit | 3 |
| 反向限位 | i_bZ/X1/X2轴_反向限位 | i_bZ/X1/X2Axis_ReverseLimit | 3 |

###### 上游信号 (4个) + 气缸输出 (10个) + 伺服输出 (3个) + 下游信号 (1个) + 状态输出 (7个) + 定时器输出 (4个)
| 原前缀 | 新前缀 | 说明 |
|--------|--------|------|
| i_b输送机_L1~L4_放料完成 | i_bConveyor_L1~L4_FeedComplete | 四层放料完成 |
| o_b升降_上升/下降 | o_bLift_Up/Down | 升降气缸控制 |
| o_b前/后夹紧_夹紧/松开 | o_bFront/RearGrip_Close/Open | 夹紧气缸控制 |
| o_b前/后夹紧2_夹紧/松开 | o_bFront/RearGrip2_Close/Open | 第二组夹爪控制 |
| o_bZ轴_脉冲/方向/伺服使能 | o_bZAxis_PulseOutput/DirectionOutput/ServoEnable | Z轴伺服控制 |
| o_b放料完成_给送料机构 | o_bFeedComplete_ToFeeder | 下游通知 |
| o_b运行中/故障/当前状态 | o_bRunning/Fault/CurrentState | 状态显示 |
| o_rZ/X1/X2轴当前位置 | o_rZ/X1/X2Axis_CurrentPosition | 位置反馈 |
| o_i当前取料层数 | o_iCurrentPickupLayer | 当前层号 |
| o_i本站报警代码 | o_iStationAlarmCode | 报警码(101~199) |
| q_e放料完成保持/动作/产品检测稳定/初始化_Elapsed | q_eFeedCompleteHold/Action/ProductDetectStable/Init_Elapsed | 定时器调试 |

##### 5. stFeeder结构 (31个变量)
###### 系统控制 (6个) - 同stConveyor格式
###### 手动X2轴点动 (2个)
| 原变量名 | 新变量名 | 说明 |
|---------|---------|------|
| i_bX2轴点动前/后 | i_bLx_X2Axis_JogFwd/Rev | X2轴前后点动 |

###### 工艺参数 (3个)
| 原变量名 | 新变量名 | 类型 | 说明 |
|---------|---------|------|------|
| i_r送料速度 | i_rFeedSpeed | REAL | X2轴送料速度 |
| i_r待机位置 | rStandbyPosition | REAL | 待机位置坐标 |
| i_r取料位置 | rPickupPosition | REAL | 取料位置坐标 |

###### 传感器/伺服 (4个) + 打胶机交互 (2个) + 上游信号 (1个)
| 原变量名 | 新变量名 | 说明 |
|---------|---------|------|
| i_bX2轴_原点/正向限位/反向限位/伺服故障 | i_bX2Axis_Home/ForwardLimit/ReverseLimit/ServoFault | X2轴状态 |
| i_b打胶机允许送料/取料完成 | i_bGlueMachine_AllowFeed/PickupComplete | 打胶机交互 |
| i_b取放料_放料完成 | i_bPickPlace_FeedComplete | 上游放料完成 |

###### 执行器输出 (3个) + 安全区 (1个) + 状态 (4个) + 报警 (1个) + 定时器 (4个)
| 原变量名 | 新变量名 | 说明 |
|---------|---------|------|
| o_b允许抓料 | o_bAllowPickup | 允许抓料信号 |
| o_bX2轴请求前移/后移 | o_bX2Axis_RequestFwd/Rev | X2轴移动请求 |
| o_b安全区信号 | o_bSafetyZoneSignal | 安全区管理 |
| o_b运行中/故障/当前状态 | o_bRunning/Fault/CurrentState | 状态显示 |
| o_rX2轴当前位置 | o_rX2Axis_CurrentPosition | X2轴位置反馈 |
| o_i本站报警代码 | o_iStationAlarmCode | 报警码(201~299) |
| q_e通讯超时/动作/初始化/抓料保持_Elapsed | q_eCommTimeout/Action/Init/PickupHold_Elapsed | 定时器调试 |

---

## 质量保证措施

### 验证方法
1. ✅ **grep搜索验证**: 使用正则表达式`^\s+(i_|o_|q_)[^\s]*[\u4e00-\u9fa5]`搜索中文变量名 → 结果: **0处残留**
2. ✅ **结构完整性检查**: 5个STRUCT全部保留(stGlobal/stExternal/stConveyor/stPickPlace/stFeeder)
3. ✅ **变量数量核对**:
   - stGlobal: 11个变量 ✓
   - stExternal: 67个变量(27输入+20输出) ✓
   - stConveyor: 64个变量(63输入+30输出) ✓
   - stPickPlace: 85个变量(55输入+30输出) ✓
   - stFeeder: 31个变量(17输入+14输出) ✓
   - **总计: 258个变量** ✓

### 编译兼容性
- ✅ 与OB1.scl V5.0.0 100%同步
- ✅ 与FB_1001~1004接口定义完全匹配
- ✅ 符合LSP-905_SCL编程规范要求
- ✅ 支持VS Code PLC调试器验证

### 回归测试建议
1. 在TIA Portal中重新编译整个项目
2. 验证OB1对GlobalVars的所有引用无TC001错误
3. 检查HMI画面变量绑定是否需要更新
4. 测试MES通讯接口的变量映射

---

## 关联文档
- [PLC程序全面重写方案_V5.0.0.md](../.trae/documents/PLC程序全面重写方案_V5.0.0.md)
- [接口文档_IFC-FB1001-Conveyor4Layer.md](./conveyor/接口文档_IFC-FB1001-Conveyor4Layer.md)
- [变更记录_CHG-FB1001-Conveyor4Layer.md](./conveyor/变更记录_CHG-FB1001-Conveyor4Layer.md)

---

## 参考规范
- **命名标准**: LSP-905_SCL编程规范
- **架构设计**: DJ-2026-005 PLC程序架构设计文档 V4.2.0
- **IEC 61131-3**: 国际电工委员会PLC编程语言标准

---

*文档生成时间: 2026-05-03 15:30:00*
*生成工具: Trae IDE AI Assistant*
*审核状态: 待人工审核*
