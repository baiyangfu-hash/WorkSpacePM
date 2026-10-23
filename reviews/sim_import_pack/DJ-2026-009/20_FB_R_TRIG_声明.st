// FB_R_TRIG: 上升沿检测
// 描述: 检测FALSE到TRUE的跳变

FUNCTION_BLOCK FB_R_TRIG
VAR_INPUT
    IN  : BOOL;   // 待检测的布尔输入信号
END_VAR
VAR_OUTPUT
    Q   : BOOL;   // 上升沿检测输出 (一个周期内为TRUE)
END_VAR
VAR
    LastIN : BOOL := FALSE;
END_VAR
