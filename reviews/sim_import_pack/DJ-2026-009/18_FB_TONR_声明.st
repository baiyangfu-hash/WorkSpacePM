// ============================================================================
// FB_TONR: 保持型接通延时定时器 (真实毫秒)
// 描述: IN=TRUE 时累积计时, IN=FALSE 时保持已累积的时间不清零;
//       累积到 PT 毫秒后 Q=TRUE 并保持, 只有 R=TRUE 才清零 (R 优先于 IN)
// 实现: 平台没有统一的 TONR (CODESYS 标准库无 TONR), 所以用一个平台标准
//       TON 给"每一段接通"计时, 段结束时把这段的毫秒数加进累计值.
//       PT/ET 引脚仍为 DINT 毫秒 (名字和引脚不变, 用户 2026-10-21 D09 拍板表第 21 行批准)
// 平台:
//   - TIA Portal V18 (S7-1200/1500): TON 即 IEC_TIMER 多重实例. 若导入时报
//     "TON 类型未知", 把 s_fbSeg 的类型改成 TON_TIME, 其余不动.
//   - InoProShop (汇川, CODESYS 内核): TON 来自 Standard 库. 粘贴到 POU 时
//     去掉 BEGIN 一行和变量前的 #, 其余不动.
//   - Siemens LSP 仿真 (.scltest): TON 是否能随仿真时间走以本机实测为准,
//     计时类用例改在 PLCSIM / InoProShop 仿真里验.
// 注意: "保持型"指 IN 断开时不清零, 不是掉电保持; 掉电保持要在实例所在 DB 设置.
// 变更: V3.0.0 (2026-10-21) 由按扫描次数 +1 改为真实毫秒
// ============================================================================

FUNCTION_BLOCK FB_TONR
VAR_INPUT
    IN  : BOOL;
    R   : BOOL;   // 复位输入, 优先于 IN
    PT  : DINT;   // 预设时间(ms), <=0 时 IN 一到 Q 即为 TRUE
END_VAR
VAR_OUTPUT
    Q   : BOOL;
    ET  : DINT;   // 已累积时间(ms), 到达后保持为 PT
END_VAR
VAR
    s_fbSeg     : TON;          // 当前这一段接通的计时 (平台标准 TON)
    s_bSegRun   : BOOL := FALSE; // 当前这一段正在计时
    s_dAccMs    : DINT := 0;    // 已结束各段的累计毫秒
    s_dSegMs    : DINT := 0;    // 当前这一段已走的毫秒
    s_dTotalMs  : DINT := 0;    // 累计 + 当前段
    s_dPtMs     : DINT := 0;    // 本周期生效的预设值(ms), 负数按 0 处理
END_VAR
