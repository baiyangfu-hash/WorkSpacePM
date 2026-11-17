# Day 12：独立工具页实战 2：Python Bridge 编写与注入

> 🎯 **今日目标**：为自定义工具编写专属的 Python Bridge 并将其注入 QML 上下文。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成 Day 11 学习。

---

## 🛠️ 一、编写专属 Bridge 胶水类

在 `auto_pm/ui/bridges/` 目录下创建 `my_custom_bridge.py`：

```python
from PySide6.QtCore import QObject, Signal, Slot

class MyCustomToolBridge(QObject):
    # 状态通知信号
    calcFinished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(result=str)
    def run_calculation(self) -> str:
        # 执行工控计算（如定时器毫秒与周期换算）
        result_str = "计算完成：周期 10ms，标准节拍 60PPM"
        self.calcFinished.emit(result_str)
        return result_str
```

---

## 🔌 二、在主窗口注入 Bridge 上下文

打开 `auto_pm/ui/qml_main_window.py`（主程序装配处）：

```python
# 1. 导入你的 Bridge 类
from auto_pm.ui.bridges.my_custom_bridge import MyCustomToolBridge

# 2. 在 init_bridges 方法中实例化并注册给 QML 引擎
self.my_custom_bridge = MyCustomToolBridge(self)
self.engine.rootContext().setContextProperty("myCustomBridge", self.my_custom_bridge)
```

现在，QML 界面中的任何地方都可以直接通过 `myCustomBridge.run_calculation()` 调用你的 Python 代码！

---

## 📝 今日打卡小结

1. Bridge 类继承自 `QObject`，业务方法添加 `@Slot()`。
2. 通过 `setContextProperty("对象名", 实例)` 注入 QML 全局命名空间。
