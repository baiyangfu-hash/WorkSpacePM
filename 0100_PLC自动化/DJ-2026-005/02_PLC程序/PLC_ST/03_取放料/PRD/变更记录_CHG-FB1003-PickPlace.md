# 变更记录 FB_1003_PickPlace_BufferFraming

| 版本号 | 变更日期 | 变更类型 | 变更内容 | 变更人 |
|--------|----------|----------|----------|--------|
| V15.0.0 | 2026-10-24 | 重写 | 按新设计整体重写（取代 V7.x）：S20~S25 子相结构、成对取料、夹爪 / 升降缸统一输出、夹紧超时 F106、轴命令占有标志，接口改为 `io_stPP / io_stBridge / io_stMachine / io_stIo / io_stAlarm / io_astAxis` | Claude |
| V7.1.1 | 2026-05-20 | Bug修复 | 修复TC11自动模式Z轴定位测试失效: i_iPickLayer接线从o_iCurrentPickLayer(输出)改为i_iPickLayer_Input(独立输入), 断开FB内部iPickLayer(=0)覆盖导致S20→S21转换条件永远FALSE的反馈回路; GlobalVars.db新增i_iPickLayer_Input: INT字段; OB1.scl第331行接线更新 | Trae |
| V7.0.0 | 2026-05-20 | 重构 | 删除6个间接轴请求输出(q_bZAxisHomeRequest/q_bZAxisMoveAbsReq/q_rZAxisTargetPos/q_bX1AxisHomeRequest/q_bX1AxisMoveAbsReq/q_rX1AxisTargetPos); 新增VAR_IN_OUT io_stZAxis/io_stX1Axis: ST_ServoAxis (PLCopen MC Part 1嵌套结构体); FB内直接操作stPower(使能)/stAbs(绝对定位)/stStop(急停)/stSensor(限位+报警); 接口总数从64降至56(-8); 删除4个伺服点动输入(i_bLx_ZAxis_JogUp/Down, i_bLx_X1Axis_JogFwd/Rev) | Trae |
| V6.0.0 | 2026-05-17 | 重构 | 基于SRC基线重写：状态机从11步改为6步S20~S25；产品检测并入S22步；新增按层选放料点逻辑(L1/L3→D520, L2/L4→D540)；变量名全英文符合801-V1.0.5；轴接口改为q_bXxxRequest+q_rTargetPos模式 | Trae |
| V6.0.0(old) | 2026-04-27 | — | 旧版11步状态机(基于AI不完整理解) | System |

## V7.0.0 详细变更说明

### 接口变更清单

#### VAR_INPUT 删除 (5个)

| 删除变量 | 原用途 | 替代方案 |
|----------|--------|---------|
| i_bReset | 故障复位 | 合并到使能关闭统一处理 (NOT Auto AND NOT Manual → RETURN) |
| i_bLx_ZAxis_JogUp | Z轴点动上升 | 改由ST_ServoAxis.stJog处理(外部轴FB) |
| i_bLx_ZAxis_JogDown | Z轴点动下降 | 同上 |
| i_bLx_X1Axis_JogFwd | X1轴点动前进 | 同上 |
| i_bLx_X1Axis_JogRev | X1轴点动后退 | 同上 |

#### VAR_OUTPUT 删除 (6个)

| 删除变量 | 原用途 | V7.0替代 |
|----------|--------|---------|
| q_bZAxisHomeRequest | Z轴回原点请求 | FB内直接调用io_stZAxis.stHome.Execute |
| q_bZAxisMoveAbsReq | Z轴绝对定位请求 | FB内直接写io_stZAxis.stAbs.Execute |
| q_rZAxisTargetPos | Z轴目标位置 | FB内直接写io_stZAxis.stAbs.Position |
| q_bX1AxisHomeRequest | X1轴回原点请求 | FB内直接调用io_stX1Axis.stHome.Execute |
| q_bX1AxisMoveAbsReq | X1轴绝对定位请求 | FB内直接写io_stX1Axis.stAbs.Execute |
| q_rX1AxisTargetPos | X1轴目标位置 | FB内直接写io_stX1Axis.stAbs.Position |

#### VAR_IN_OUT 新增 (2个)

| 新增变量 | 类型 | 用途 |
|----------|------|------|
| io_stZAxis | ST_ServoAxis | Z轴(升降) - 直读直写，OB1接线=>astServoAxis[1] |
| io_stX1Axis | ST_ServoAxis | X1轴(取放料横移) - 直读直写，OB1接线=>astServoAxis[2] |

### 逻辑变更要点

1. **S20_IDLE新增**: 轴使能检查(stPower.Status→Enable)、伺服报警检查(stSensor.ServoAlarm→Alarm73)
2. **S21/S24新增**: PLCopen MC_MoveAbsolute调用(Position/Velocity/Execute)、超时+Error处理、SV_Stop急停
3. **S23新增**: X1轴绝对定位+限位互锁
4. **使能关闭**: 统一清除所有气缸输出 + 轴命令(Abs.Execute:=FALSE + Stop.Execute:=FALSE)
5. **停止处理**: SV_Stop两轴 + 气缸清零
6. **手动模式**: 清除轴命令(Abs.Execute:=FALSE)

## V7.1.1 详细变更说明

### Bug: TC11自动模式Z轴定位测试失效

**现象**: basic_test.scltest TC11中，设置i_bStart:=TRUE和i_iPickLayer:=1后，o_iCurrentState始终为0(S20)，无法跳转到S21。

**根因**: OB1.scl中i_iPickLayer的接线源是`o_iCurrentPickLayer`(FB_1003的输出)，形成反馈回路：
```
OB1: i_iPickLayer := o_iCurrentPickLayer  ← 输出→输入
FB1003: 内部iPickLayer在S20中=0(未赋值前)
       S20条件: i_iPickLayer > 0 永远FALSE
```

**修复**:
1. GlobalVars.db stPickPlace新增 `i_iPickLayer_Input: INT := 0`
2. OB1.scl 第331行改为: `i_iPickLayer := GlobalVars.stPickPlace.i_iPickLayer_Input`
3. 断开输出→输入反馈回路，层号由HMI/上位机独立指定
