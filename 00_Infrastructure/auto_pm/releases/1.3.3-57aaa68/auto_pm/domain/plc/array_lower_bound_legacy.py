"""LSP-905-ARRAY-LOWER-BOUND 的存量清单：这些数组声明在“下标从 1 起”规则出台前就已写成 0 起。

存量改写已挂起（归 DJ-2026-005 线程，含安全块 FB_1030），清单里的声明只报 WARNING、不拦；清单之外的（新增、
或清单里的行被改动过的）一律 ERROR。清单只会变短：改成 1 起后对应条目自然不再命中，可以删掉。
2026-10-31（TD-SW008-217）起检查扩到 .db / .udt，``.db`` 里的 12 处存量（DJ-2026-000 的 8 处样例工程、DJ-2026-009 的 4 处）
也记在这里，同样只提示不拦；.db / .udt 里新增的非 1 起声明一律 ERROR。
键 = (相对 0100_PLC自动化 的路径, 去掉 // 注释并压缩空白后的声明文字)。
"""

from __future__ import annotations

LEGACY_ARRAY_LOWER_BOUND: frozenset[tuple[str, str]] = frozenset(
    {
        ('01_SharedLibraries/SysLib/log/FC_LogMsg.scl', 'LogBuffer : ARRAY[0..31] OF STRING[256];'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 'i_arrCurtainOk : ARRAY[0..7] OF BOOL;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 'i_arrDoorClosed : ARRAY[0..7] OF BOOL;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 'i_arrDoorReqBtn : ARRAY[0..7] OF BOOL;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 'i_arrEStopOk : ARRAY[0..7] OF BOOL;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 'i_arrSafetyFault : ARRAY[0..3] OF BOOL;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 'q_arrDoorLamp : ARRAY[0..7] OF BOOL;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 'q_arrDoorUnlock : ARRAY[0..7] OF BOOL;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 's_arrDoorStep : ARRAY[0..7] OF INT;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 's_arrRelockTimer : ARRAY[0..7] OF FB_TON;'),
        ('01_SharedLibraries/SysLib/safety/FB_1030_SafetyManager.scl', 's_arrRtDoorReq : ARRAY[0..7] OF FB_R_TRIG;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/01_外部设备交互/FB_3002_ModbusTcpClient.scl', 'io_arrDownRead : ARRAY[0..31] OF WORD;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/01_外部设备交互/FB_3002_ModbusTcpClient.scl', 'io_arrDownWrite : ARRAY[0..31] OF WORD;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/01_外部设备交互/FB_3002_ModbusTcpClient.scl', 'io_arrUpRead : ARRAY[0..31] OF WORD;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/01_外部设备交互/FB_3002_ModbusTcpClient.scl', 'io_arrUpWrite : ARRAY[0..31] OF WORD;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/05_公共报警/FB_2001_CommonAlarm_AllStation.scl', 's_arrMesAlarmQueue : ARRAY[0..9] OF INT;'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'Hmibutton : ARRAY[0..9] OF BOOL;'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'sm_arrCurtainOk : ARRAY[0..7] OF BOOL := [8(TRUE)];'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'sm_arrDoorClosed : ARRAY[0..7] OF BOOL := [8(TRUE)];'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'sm_arrDoorLamp : ARRAY[0..7] OF BOOL;'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'sm_arrDoorReqBtn : ARRAY[0..7] OF BOOL;'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'sm_arrDoorUnlock : ARRAY[0..7] OF BOOL;'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'sm_arrEStopOk : ARRAY[0..7] OF BOOL := [8(TRUE)];'),
        ('DJ-2026-000/DB1/GlobalVars.db', 'sm_arrSafetyFault : ARRAY[0..3] OF BOOL;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db', 'awModbusDownRead : ARRAY[0..31] OF WORD;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db', 'awModbusDownWrite : ARRAY[0..31] OF WORD;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db', 'awModbusUpRead : ARRAY[0..31] OF WORD;'),
        ('DJ-2026-009_汇川换型改造/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db', 'awModbusUpWrite : ARRAY[0..31] OF WORD;'),
    }
)
