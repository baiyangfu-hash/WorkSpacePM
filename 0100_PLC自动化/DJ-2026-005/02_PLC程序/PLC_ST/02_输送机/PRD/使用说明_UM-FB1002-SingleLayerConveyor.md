# 使用说明 FB_1002_SingleLayerConveyor_BufferFraming

## 1. 功能

单层边框输送机 10 步状态机（步 0/1/2/10/20/30/50/60/70/80），每层调用一次。电机正转 / 反转 / 慢速和阻挡、分料气缸命令都写在 `io_stLayer` 里，由 FB_1007 映射到物理输出。

## 2. 调用

`fbL1(i_dInitRevMs := 10000, i_dPreBlockMs := 3000, i_dSlowFeedMs := 2000, i_dReleaseOkMs := 1000, i_dReleaseNgMs := 8000, i_dStarveMs := 10000, i_dCylTimeoutMs := 5000, io_stLayer := GlobalVars.stConv.astLayer[1]);`

## 3. 调试要点

1. 上电后须先“初始化”：回原点预处理期间 `bInitReq` 置位，层走步 1 → 2，反转 10 s 后 `bReady` = 1。
2. 取料机构不在安全区（`bSafeZone` = 0）时，正转 / 反转 / 慢速立即切断，回安全区后继续。
3. `bHold`（暂停或本层报警）时，电机切断、步序保持、气缸命令保持、各过程定时器清零重算。
4. `bReset`（急停类或进手动）或退料上升沿：步回 0，阻挡 / 分料升起，电机停，准备完成与请求取料清零。
5. 满料检测 1、2 同亮且正转时立即转慢速。
6. 8 个气缸位置各一个 5 s 报警触发，缺料另有一个触发，见接口文档第 5 节。
7. 定时器用 SysLib `FB_TON`（毫秒）。仿真里计时类用例以 PLCSIM / InoProShop 实测为准。
