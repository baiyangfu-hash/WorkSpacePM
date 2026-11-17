# Day 09：数据表格与报警高亮修改

> 🎯 **今日目标**：掌握 `ListModel` 与 `ListView` 数据绑定，学会调整表格列宽比重与数值超限报警变红。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成 Day 08 学习。

---

## 💡 一、工控类比：HMI 配方表与 ListModel

在工控触摸屏里，报警列表或配方表格通常绑定一个连续的内存数组。
在 QML 中：
* **`ListModel`**：就是内存里的数据表（装有一行行的数据记录）；
* **`ListView`**：就是把这一行行数据按照指定模板（Delegate）渲染出来的表格控件。

```
Python 后台推数据 ──> ListModel (内存数组) ──> ListView (画面网格呈现)
```

---

## 🛠️ 二、实战 1：保证表格列宽严丝合缝（对齐诀窍）

表格列对齐的核心原则：**表头的 `preferredWidth` 必须与数据行 delegate 里的 `preferredWidth` 严格一致！**

```qml
// 表头部分
RowLayout {
    Text { text: "地址"; Layout.preferredWidth: 80 }
    Text { text: "变量名"; Layout.preferredWidth: 150 }
    Text { text: "当前值"; Layout.fillWidth: true }
}

// 数据行 delegate 部分
RowLayout {
    Text { text: model.address; Layout.preferredWidth: 80 }
    Text { text: model.name; Layout.preferredWidth: 150 }
    Text { text: model.value; Layout.fillWidth: true }
}
```

---

## 🚨 三、实战 2：数值超限报警高亮（条件变色）

在电气工程中，压力超过 1000 kPa 时需要变红报警。在 QML 中只需使用三元表达式：

```qml
Text {
    text: model.dec !== undefined ? model.dec.toString() : ""
    
    // 💡 超过 1000 显示报警红色，正常显示主文本亮白
    color: model.dec > 1000 ? Theme.error : Theme.textPrimary
    font.bold: model.dec > 1000
}
```

---

## 🧪 四、5 分钟动手实战实验

查看 `auto_pm/ui/qml/views/ModbusDebuggerView.qml` 中 `registerModel` 的数据填充逻辑，找到 `append` 方法中的字段映射。

---

## 📝 今日打卡小结

1. `ListModel` 存数据，`ListView` 画表格。
2. 表头与数据行的 `preferredWidth` 必须逐一配对保证对齐。
3. 条件变色使用 `condition ? Theme.error : Theme.textPrimary`。
