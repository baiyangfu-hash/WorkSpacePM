# 使用说明 FB_1003_PickPlace_BufferFraming

## 取放料机构（FB_1003_PickPlace_BufferFraming）

取放料机构 S20~S25 状态机：一次 2 根（前位对 = 3+4 层，后位对 = 1+2 层）或一次 4 根（1~4 层）两种取料模式，Z 与 X1 两轴定位，夹爪与升降缸 Y40~Y43 统一由本 FB 写出，产生取料完成、X1 送料完成、安全区信号和取放料报警触发（F30~F33、F66~F75、F106）。

要点：

1. 调用位置：OB1 第 7 个（桥接之后）。
2. 自动模式才执行步序；非自动或 M8 时步序回 S20 外的 0，轴命令撤销，夹爪和升降缸不动（R-PP-09）。
3. `bHoldPP`（报警或暂停）时轴 Halt，步序保持，过程定时器 IN 清零重算，恢复后重发 `Execute`。
4. 回原点 / 准备 / 手动对夹爪、升降缸的要求通过 `stPP.bGripOpenReq / bLiftUpReq / bLiftDownReq` 提出，不直接写 Y40~Y43。
5. 安全区 `bSafeZone`：自动 = 不在 S22 / S23；其他模式 = Z 当前位置不高于待机点 + 容差。
6. 仿真里计时类用例以 PLCSIM / InoProShop 实测为准。

## 调用

OB1 的调用行见 `00_主程序/OB1.scl`，实例声明见 `00_全局数据/GlobalVars.db`。
