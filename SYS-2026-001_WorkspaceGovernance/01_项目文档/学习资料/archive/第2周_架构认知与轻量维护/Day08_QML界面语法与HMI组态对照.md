# Day 08：QML 界面语法与 HMI 组态对照

> 🎯 **今日目标**：看懂 QML 声明式语法，掌握按钮文字、颜色、输入框等界面控件的修改。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成 Day 07 学习。

---

## 💡 一、工控类比：QML 就是“用代码写的触摸屏组态”

在威纶通或西门子 WinCC 中，你画一个按钮：
* 在属性面板设置：宽度 120、高度 40、背景深灰、文字“启动电机”、点击时触发中间继电器 `M0.0`。

在 QML 中，这段组态用清晰的文本表达：

```qml
// 相当于触摸屏里的一个标准按钮控件
Button {
    text: "⚡ 启动电机"
    width: 120
    height: 40
    
    // 点击事件（相当于按下按钮闭合中继）
    onClicked: {
        console.log("启动电机按钮被点击")
    }
}
```

---

## 🎨 二、驾驶舱的全局配色主题 (Theme)

`auto-pm` 采用工业深色磨砂质感，所有颜色严禁在 QML 里写死 `#FFFFFF` 这样的色值，统一引用 `Theme.xxx`：

| 主题常量 | 说明与用途 |
| :--- | :--- |
| `Theme.bgPrimary` | 驾驶舱深黑背景色 |
| `Theme.textPrimary` | 主标题/关键文本亮白色 |
| `Theme.textSecondary` | 注释/次要说明浅灰色 |
| `Theme.accent` | 选中高亮/主动作蓝色 |
| `Theme.success` | 门禁通过/运行正常绿色 |
| `Theme.error` | 故障报警/门禁失败红色 |

---

## 🛠️ 三、常见布局方式：RowLayout 与 ColumnLayout

就像在电气柜里排布断路器一样：
* **`RowLayout`（横排）**：从左往右水平一字排开；
* **`ColumnLayout`（竖排）**：从上往下垂直顺次排列。

```qml
ColumnLayout {
    spacing: 12  // 控件之间的垂直间距

    Text {
        text: "工位 1 状态监视"
        color: Theme.textPrimary
        font.bold: true
    }

    RowLayout {
        spacing: 8
        Button { text: "启动" }
        Button { text: "急停" }
    }
}
```

---

## 🧪 四、5 分钟动手实战实验

### 步骤 1：打开项目列表视图文件
查看 `auto_pm/ui/qml/views/ProjectListView.qml` 的前 30 行，识别其中的 `ColumnLayout` 与 `Theme` 引用。

### 步骤 2：启动应用直观观察
```powershell
python main.py
```
观察界面左上角的标题和按钮布局，对照 QML 代码找到对应元素。

---

## 📝 今日打卡小结

1. QML 是声明式 UI，属性直接决定外观，`onClicked` 响应点击。
2. 颜色统一使用 `Theme.xxx`，保证工业深色风格一致性。
3. 布局使用 `RowLayout`（横排）和 `ColumnLayout`（竖排）。
