# 测试用 SysLib（仅测试，不得用于生产）

SysLib 的 `FB_TON` / `FB_TONR`（真实毫秒版）内部调用平台原生 `TON`，Siemens 语言服务插件的测试运行时没有原生 TON，
`siemens-lsp test` 一跑到就 `panic: STUB BUILTIN: B_TON`，整个测试进程退出（所以只报出 3 条 FAIL，其余并未真正跑完）。

`run_plugin_test.py` 的做法：在系统临时目录里复制 SysLib 与 005 的 `PLC_ST`，只把**临时副本**里的计时器换成本目录
`timer/` 下按扫描次数计时的替身（文件存成 `.scl.txt`，免得被 `plc check` 当成项目源码扫描），在副本里跑 `siemens-lsp test .`，跑完删掉副本。仓库里的 `.plc.json`、SysLib、005
源码都不改；脚本对比运行前后的文件哈希来证明这一点。

计时行为未验证，以 PLCSIM 或现场为准（用户 10-23 已确认：计时器、计数器不仿真，只测接线与条件）。

运行（在 M3 笔记本任意终端，仓库为控制根或其工位均可）：

```
python 0100_PLC自动化/DJ-2026-005/05_测试与验证/测试用SysLib/run_plugin_test.py --lsp <siemens-lsp 路径>
```
