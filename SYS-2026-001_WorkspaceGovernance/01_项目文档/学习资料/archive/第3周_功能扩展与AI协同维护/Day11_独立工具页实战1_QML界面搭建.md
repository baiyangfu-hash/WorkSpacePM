# Day 11：独立工具页实战 1：QML 界面搭建

> 🎯 **今日目标**：在驾驶舱中搭建一个自定义小工具的独立 QML 界面（以“PLC 简易计算器”为例）。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成第 2 周全部内容。

---

## 🛠️ 一、创建新界面的标准套路

在 `auto_pm/ui/qml/views/` 目录下创建新视图文件 `MyCustomToolView.qml`：

```qml
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "../theme"
import "../components"

Item {
    id: root

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        // 1. 顶部标题
        Text {
            text: "🛠️ PLC 辅助计算小工具"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeLg
            font.bold: true
        }

        // 2. 状态提示卡片
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            color: Theme.bgSecondary
            radius: 8

            Text {
                anchors.centerIn: parent
                text: "请在下方触发自定义功能计算"
                color: Theme.textSecondary
            }
        }

        // 3. 触发操作按钮
        Button {
            text: "⚡ 立即计算"
            onClicked: {
                console.log("自定义工具按钮被点击！")
            }
        }

        // 占位弹性空间
        Item { Layout.fillHeight: true }
    }
}
```

---

## 🧪 二、5 分钟动手实战实验

用文本编辑器查看 `auto_pm/ui/qml/views/` 下现有的任意一个 View（如 `PlcProjectView.qml`），观察其根元素 `Item`、导入的 `Theme` 与 `ColumnLayout` 结构。

---

## 📝 今日打卡小结

1. 所有独立子页面存放在 `auto_pm/ui/qml/views/`。
2. 页面根节点使用 `Item`，内部用 `ColumnLayout` + `anchors.fill: parent` 撑满窗口。
