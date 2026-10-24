# 使用说明 FB_ExternalDeviceInteraction

## 组框机链路（FB_ExternalDeviceInteraction）

组框机链路（FB_3001）：联机 M501 / 连续送框 M502 / 单套送框许可 M510，本机安全异常输出 R5000.0 与 Y45 / Y46，组框机安全异常 F104（A 类）、通讯异常 F105（提示类）。

要点：

1. 调用位置：OB1 第 4 个。
2. 组框机侧的 R5010.0 / R5011.0 与通讯状态由平台适配写入 `stExt.bPeerSafetyFault / bPeerPermit / bLinkFail`，本 FB 只读。
3. 单套许可 `bSingle`：联机且组框机允许送料上升沿置位；下降沿、小车 Y44 成立、不联机时复位（复位优先）。
4. X160 / X161 暂未并入组框机安全异常（极性待现场确认）。

## 调用

OB1 的调用行见 `00_主程序/OB1.scl`，实例声明见 `00_全局数据/GlobalVars.db`。
