// ============================================================================
// FB_TON: 接通延时定时器 (真实毫秒)
// 描述: 当IN为TRUE时, 经过PT毫秒后Q变为TRUE; IN为FALSE时Q/ET复位
// 实现: 内部调用平台标准 IEC 定时器 TON, PT/ET 引脚仍为 DINT 毫秒
//       (名字和引脚不变, 用户 2026-10-21 D09 拍板表第 21 行批准)
// 平台:
//   - TIA Portal V18 (S7-1200/1500): TON 即 IEC_TIMER 多重实例. 若导入时报
//     "TON 类型未知", 把 s_fbTon 的类型改成 TON_TIME, 其余不动.
//   - InoProShop (汇川, CODESYS 内核): TON 来自 Standard 库. 粘贴到 POU 时
//     去掉 BEGIN 一行和变量前的 #, 其余不动.
//   - Siemens LSP 仿真 (.scltest): TON 是否能随仿真时间走以本机实测为准,
//     计时类用例改在 PLCSIM / InoProShop 仿真里验.
// 变更: V3.0.0 (2026-10-21) 由按扫描次数 +1 改为真实毫秒
// ============================================================================

FUNCTION_BLOCK FB_TON
VAR_INPUT
    IN  : BOOL;
    PT  : DINT;   // 预设时间(ms), <=0 时 Q 跟随 IN
END_VAR
VAR_OUTPUT
    Q   : BOOL;
    ET  : DINT;   // 已用时间(ms), 到达后保持为 PT
END_VAR
VAR
    s_fbTon   : TON;          // 平台标准接通延时定时器
    s_dPtMs   : DINT := 0;    // 本周期生效的预设值(ms), 负数按 0 处理
END_VAR
