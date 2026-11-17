# Day 07：业务计算与算法参数微调

> 🎯 **今日目标**：学会在 Service 层修改底层算法逻辑与参数（以 Modbus 浮点解码与 PLC 规则参数为例）。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成 Day 06 学习。

---

## 💡 一、工控场景：修改算法不需要重画 HMI

在触摸屏工程中，如果只是修改了温度转换公式，你只需要改 PLC 里的计算 FC/FB，触摸屏画面完全不用重新绘制。

在 `auto-pm` 中也是一样：**所有的业务算法都独立封装在 `auto_pm/domain/` 或 `auto_pm/application/core/` 中**。

---

## 🛠️ 二、实战演练：修改 Modbus 32 位浮点解码精度

在 Modbus TCP 通信中，32 位浮点数占用 2 个 16 位连续寄存器（High Word 与 Low Word）。西门子 PLC 通常采用 **CDAB（Word Swap）** 大小端格式。

### 代码位置：
`auto_pm/domain/modbus/modbus_service.py` 中的 `_decode_float_cdab` 函数：

```python
def _decode_float_cdab(high: int, low: int) -> str:
    """CDAB（西门子 Word Swap）32位浮点解码。"""
    import struct
    import math
    try:
        raw = (high << 16) | low
        swapped = ((raw & 0xFFFF) << 16) | ((raw >> 16) & 0xFFFF)
        result = struct.unpack(">f", swapped.to_bytes(4, "big"))[0]
        if math.isnan(result) or math.isinf(result):
            return "N/A"
        # 💡 原版保留 3 位小数：f"{result:.3f}"
        # 💡 如果现场需要更高精度，修改为保留 4 位：f"{result:.4f}"
        return f"{result:.4f}"
    except Exception:
        return "N/A"
```

---

## 🧪 三、5 分钟动手实战实验

我们来写一个独立验证小脚本，亲自测试一下大小端浮点解码：

### 步骤 1：新建一个临时验证脚本
```powershell
python -c "import struct; raw = (0x41A0 << 16) | 0x0000; swapped = ((raw & 0xFFFF) << 16) | ((raw >> 16) & 0xFFFF); print('西门子 20.0 浮点解码结果:', struct.unpack('>f', swapped.to_bytes(4, 'big'))[0])"
```
*预期输出*：`西门子 20.0 浮点解码结果: 20.0`

### 步骤 2：使用 Git 查看确认无多余改动
```powershell
git status
```

---

## 🛡️ 四、业务层修改安全防线

> [!WARNING]
> 1. **严禁在 Service 层导入任何 Qt 或 QML 模块**（如 `from PySide6.QtWidgets import ...`）。Service 必须保持 100% 纯 Python，这样才能在 CLI 和后台独立运行。
> 2. **所有异常必须用 try...except 兜底**，防止因为某一个脏数据导致整个上位机软件闪退。

---

## 📝 今日打卡小结

1. 业务算法集中在 `domain/` 与 `core/` 目录。
2. 修改算法时，界面代码一行都不需要动。
3. 纯 Python 业务逻辑可以通过命令行单行极速测试。
