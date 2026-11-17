# Day 10：Signal & Slot 前后端通信纽带

> 🎯 **今日目标**：理解 Qt 信号与槽（Signal & Slot）机制，掌握在 Bridge 胶水层添加 `@Slot` 供界面调用。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成 Day 09 学习。

---

## 💡 一、工控类比：信号槽就是“继电器与接触器线圈”

在电气原理图中：
* 按钮按下 $\rightarrow$ 产生触发脉冲（Signal 信号）；
* 导线将脉冲引至接触器线圈 $\rightarrow$ 接触器动作吸合（Slot 槽函数执行动作）。

在 PySide6 与 QML 交互中：
```
QML 按钮点击 (onClicked) ──── 触发 ────> Python Bridge 中的 @Slot 槽函数
Python 数据采集完成 (Signal) ─── 广播 ────> QML 画面监视 (onDataReceived)
```

---

## 🛠️ 二、实战：在 Bridge 中添加一个供 QML 调用的槽函数

打开任意 Bridge 文件（如 `auto_pm/ui/bridges/project_bridge.py`）：

```python
from PySide6.QtCore import QObject, Signal, Slot

class MyToolBridge(QObject):
    # 1. 定义一个信号（用于向 QML 发送通知）
    statusUpdated = Signal(str)

    # 2. 定义一个槽函数（必须加 @Slot 装饰器，否则 QML 无法识别！）
    @Slot(str, result=bool)
    def handle_user_action(self, action_name: str) -> bool:
        print(f"收到 QML 发来的动作指令: {action_name}")
        
        # 处理业务...
        success = True
        
        # 主动通知 QML 状态改变
        self.statusUpdated.emit(f"动作 {action_name} 执行完毕！")
        return success
```

---

## 🧪 三、5 分钟动手实战实验

查看 `auto_pm/ui/bridges/modbus_bridge.py`，观察其中的 `@Slot` 函数与 `Signal` 定义，对照理解其与 `ModbusDebuggerView.qml` 的交互链路。

---

## 🏆 第二周结业里程碑测试

恭喜你完成了第 2 周的学习！你现在已经掌握了：
- [x] 理解 Python Class 与 FB 实例的映射关系
- [x] 在 Service 层修改 Modbus 解码等算法逻辑
- [x] 看懂 QML 声明式语法并使用 `Theme`
- [x] 修改表格列宽对齐与报警颜色
- [x] 掌握 Bridge 中的 `@Slot` 与 `Signal` 交互

**下周起，我们将进入实战攻坚，带你亲手在驾驶舱中新增一个完全属于你自己的小工具子页面！**
