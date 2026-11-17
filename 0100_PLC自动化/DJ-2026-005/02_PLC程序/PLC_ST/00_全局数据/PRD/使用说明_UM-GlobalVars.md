# 使用说明 GlobalVars.scl

> **现行（2026-11-15，CHG-PLC-2026-022）**：各功能块经自己的背景数据块调用（如 `"DB_1001_MachineMode_DJ005"(...)`），GlobalVars_DJ005 不再含 FB 实例，源文件改为 `GlobalVars.scl`；现行接口以 `00_程序方案/接口文档_INT.md` 4.1 与 `OB1.scl` 为准，下文旧版本内容只作历史。


## 1. 功能

边框缓存机全局变量数据块，OB1 与各 FB 的数据交换中心。所有功能块通过 VAR_IN_OUT 结构体整块传递，无需逐引脚接线。

## 2. 结构体使用

| 结构体 | 传递给 | 传递方式 |
|--------|--------|----------|
| stConveyor | FB_1002 | VAR_IN_OUT io_stLayer |
| stPickPlace | FB_1003 | VAR_IN_OUT io_stZAxis, io_stX1Axis |
| stGlueFeeder | FB_1004 | VAR_IN_OUT io_stX2Axis |
| stAlarm | FB_2001 | VAR_INPUT |
| stExternal | FB_External | VAR_INPUT |

## 3. OB1 调度示例

```scl
// Step 1: 输送机
FB_1002(io_stLayer := "GlobalVars_DJ005".stConveyor);

// Step 2: 取放料
FB_1003(io_stZAxis := "GlobalVars_DJ005".stPickPlace.stZAxis,
        io_stX1Axis := "GlobalVars_DJ005".stPickPlace.stX1Axis);

// Step 3: 打胶送料
FB_1004(io_stX2Axis := "GlobalVars_DJ005".stGlueFeeder.stX2Axis);

// Step 4: 公共报警
FB_2001(stAlarm := "GlobalVars_DJ005".stAlarm);

// Step 5: 外部设备
FB_External(stExternal := "GlobalVars_DJ005".stExternal);
```

## 4. 调试要点

1. 修改结构体字段后需同步更新对应 FB 的 VAR_IN_OUT 接口定义
2. 结构体字段命名遵循 LSP-905 前缀规范（i_=输入, q_=输出, st=结构体）
3. 新增 FB 时给它建自己的背景数据块（`DB_<编号>_<名>_DJ005.scl`），不要把 FB 实例放进 GlobalVars_DJ005（LSP-905 §4.11）；GlobalVars_DJ005 只放结构体与数组
4. 报警码类型为 WORD（16#0000=无报警）