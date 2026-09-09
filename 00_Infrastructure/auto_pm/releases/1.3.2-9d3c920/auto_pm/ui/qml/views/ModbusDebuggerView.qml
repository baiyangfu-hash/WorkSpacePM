// ModbusDebuggerView.qml — PLC Modbus 联调测试工坊主视图（V13 原型落地）
//
// 功能对齐 018_UI架构原型_V13.html：
//   - 📡 Ping 链路诊断（建立 Modbus 连接前的网络层探路）
//   - Modbus TCP 连接参数配置（IP/Port/UnitID/仿真模式开关）
//   - 读取功能码选择：FC01/02/03/04/07/17/20/22/23/24/43（共 11 个）
//   - 写入功能码选择：FC05/06/15/16/21/22（共 6 个）
//   - 16位寄存器位解析器（LED 矩阵，双击表格行自动填入）
//   - 双标签子视图：实时监测表 / 寄存器扫描探测器（趋势曲线标签已移除）
//   - 物理报文 Hex 终端（实时 TX/RX/SYS 日志）
//   - 导入/导出 JSON 配置
//
// 数据流：
//   QML → modbusBridge.Slot → Python ModbusService
//   Python → modbusBridge.Signal → QML 更新 UI
//
// PLC-HMI 概念映射：
//   本视图 ≈ HMI 调试画面（PLC 操作员界面的 Modbus 诊断页）

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../theme"
import "../components"

Item {
    id: root

    signal backToProjectList()

    // ── 连接状态 ──────────────────────────────────────────
    property bool _isConnected: false
    property int _subTabIndex: 0   // 0=监测 1=扫描
    // ── 网卡数据源 ─────────────────────────────────────────
    ListModel { id: nicModel }

    Component.onCompleted: {
        if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
            var nics = modbusBridge.getNetworkInterfaces()
            nicModel.clear()
            for (var i = 0; i < nics.length; i++) {
                nicModel.append(nics[i])
            }
            nicCombo.currentIndex = 0
        }
    }


    // ── Bridge 信号连接 ────────────────────────────────────
    Connections {
        target: (typeof modbusBridge !== "undefined" && modbusBridge !== null) ? modbusBridge : null

        function onConnectionStateChanged(ok) {
            root._isConnected = ok
            if (ok) {
                connectBtn.text = "🔌 断开连接"
                connectBtn.palette.button = Theme.error
                _log("SYS", "连接已建立。")
                // 自动执行一次扫描
                _doRead()
            } else {
                connectBtn.text = "连接设备"
                connectBtn.palette.button = Theme.primary
            }
        }

        function onPingResultReceived(success, msg) {
            pingTimeoutTimer.stop()
            pingBtn.enabled = true
            pingBtn.text = "📡 Ping"
            pingDot.color = success ? Theme.success : Theme.error
            pingText.text = msg
            pingText.color = success ? Theme.success : Theme.error
        }

        function onRegisterDataReceived(data) {
            // 清空并重建监测表
            registerModel.clear()
            for (var i = 0; i < data.length; i++) {
                registerModel.append(data[i])
            }
        }

        function onConsoleLogAppended(logType, hexStr) {
            var prefix = {
                "TX":   "<font color='#6366f1'>[TX]</font>",
                "RX":   "<font color='#10b981'>[RX]</font>",
                "SYS":  "<font color='#94a3b8'>[SYS]</font>",
                "ERR":  "<font color='#ef4444'>[ERR]</font>",
                "PING": "<font color='#f59e0b'>[PING]</font>",
            }[logType] || "[?]"
            consoleText.text += prefix + " " + hexStr + "\n"
            // 自动滚到底
            consoleFlickable.contentY = Math.max(0, consoleText.height - consoleFlickable.height)
        }

        function onScanCellUpdated(offset, isActive) {
            scannerGrid.updateCell(offset, isActive)
        }

        function onScanFinished() {
            startScanBtn.enabled = true
            startScanBtn.text = "⚡ 重新探测"
        }

        function onTrendDataUpdated(v1, v2) {
            trendCanvas.appendData(v1, v2)
        }
    }

    // ── 私有工具函数 ──────────────────────────────────────
    function _log(logType, msg) {
        if (typeof modbusBridge !== "undefined" && modbusBridge !== null) return  // Bridge 会推送
        // 无 Bridge 时直接写控制台（测试用）
        consoleText.text += "[" + logType + "] " + msg + "\n"
    }

    function _doRead() {
        if (!root._isConnected) return
        if (typeof modbusBridge === "undefined" || modbusBridge === null) return
        modbusBridge.readRegisters(
            fcCombo._comboValue,
            parseInt(startAddrField.text) || 0,
            parseInt(countField.text) || 10,
            endianCombo._comboValue,
            presetCombo._comboValue
        )
    }
    function _onParamsChanged() {
        if (pollChk.checked) {
            _updatePolling()
        }
    }

    function _updatePolling() {
        if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
            modbusBridge.setPolling(
                pollChk.checked,
                fcCombo._comboValue,
                parseInt(startAddrField.text) || 0,
                parseInt(countField.text) || 10,
                endianCombo._comboValue,
                presetCombo._comboValue
            )
        }
    }


    function _fillWriteSlot(addr, val, physicalAddr) {
        writeAddrField.text = addr.toString()
        writeValField.text = val.toString()
        // 同步到 16位解析器
        bitExpander.displayAddr = physicalAddr
        bitExpander.loadValue(val)
    }

    // ─────────────────────────────────────────────────────
    // 主布局 (重构为 V15 工业级 Ribbon + Main Stage + Bottom Console 架构)
    // ─────────────────────────────────────────────────────

     ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingMd

        // ── 1. 页眉 Header ─────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Column {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: "PLC Modbus 联调测试工坊 V15"
                    font.pixelSize: Theme.fontSizeXxl
                    font.bold: true
                    color: Theme.textPrimary
                }
                Text {
                    text: "参考 GitHub 开源 (QModMaster / ModbusPoll) 工业级设计 | 平铺 Ribbon、16位解析器、实时数据表、物理报文链路"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textMuted
                }
            }

            Button {
                text: "⬆ 导入配置"
                font.pixelSize: Theme.fontSizeSm
                onClicked: importDialog.open()
            }

            Button {
                text: "⬇ 导出配置"
                font.pixelSize: Theme.fontSizeSm
                onClicked: exportDialog.open()
            }

            Button {
                id: connectBtn
                text: root._isConnected ? "🔌 断开连接" : "🔌 连接 PLC 设备"
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
                palette.button: root._isConnected ? Theme.error : Theme.primary
                onClicked: {
                    if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
                        if (root._isConnected) {
                            modbusBridge.disconnectDevice()
                        } else {
                            modbusBridge.connectDevice(
                                ipField.text,
                                parseInt(portField.text) || 502,
                                parseInt(slaveField.text) || 1,
                                simChk.checked,
                                nicCombo.currentIp
                            )
                        }
                    } else {
                        root._isConnected = !root._isConnected
                        if (root._isConnected) _doReadSim()
                    }
                }
            }
            CheckBox { id: simChk; checked: false; visible: false }
        }

        // ── 2. 顶部 Ribbon 参数区 ───────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            // 面板 A: 连接参数配置
            GlassPanel {
                Layout.preferredWidth: 380
                implicitHeight: ribbonConnCol.implicitHeight + Theme.spacingMd * 2

                ColumnLayout {
                    id: ribbonConnCol
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Text {
                        text: "🔌 连接参数配置"
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeSm
                        font.bold: true
                    }

                    // 网卡选择
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 2
                        Text { text: "物理网卡绑定选择"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                        ComboBox {
                            id: nicCombo
                            Layout.fillWidth: true
                            font.pixelSize: Theme.fontSizeSm
                            textRole: "name"
                            model: nicModel
                            property string currentIp: model.count > 0 && currentIndex >= 0 ? model.get(currentIndex).ip : ""
                        }
                    }

                    // IP + Ping
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.spacingSm
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: "目标 PLC IP 地址"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 4
                                TextField {
                                    id: ipField
                                    Layout.fillWidth: true; text: "192.168.1.88"
                                    placeholderText: "192.168.x.x"
                                    font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary
                                    background: Rectangle {
                                        color: Qt.rgba(0,0,0,0.2); radius: Theme.radiusSm
                                        border.color: ipField.activeFocus ? Theme.primary : Theme.border; border.width: 1
                                    }
                                }
                                Button {
                                    id: pingBtn
                                    text: "📡 Ping"
                                    font.pixelSize: Theme.fontSizeXs
                                    implicitHeight: 32; implicitWidth: 64
                                    onClicked: {
                                        pingBtn.enabled = false
                                        pingBtn.text = "..."
                                        pingDot.color = Theme.textMuted
                                        pingText.text = "ICMP 探测中..."
                                        pingText.color = Theme.textMuted
                                        pingTimeoutTimer.start()
                                        if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
                                            modbusBridge.pingHost(ipField.text, nicCombo.currentIp)
                                        } else {
                                            pingTimeoutTimer.stop()
                                            pingBtn.enabled = true
                                            pingBtn.text = "📡 Ping"
                                            pingDot.color = Theme.success
                                            pingText.text = "来自 " + ipField.text + " 的回复: TTL=64"
                                            pingText.color = Theme.success
                                        }
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.preferredWidth: 70; spacing: 2
                            Text { text: "端口"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            TextField {
                                id: portField
                                Layout.fillWidth: true; text: "502"
                                validator: IntValidator { bottom: 1; top: 65535 }
                                font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary
                                background: Rectangle { color: Qt.rgba(0,0,0,0.2); radius: Theme.radiusSm; border.color: portField.activeFocus ? Theme.primary : Theme.border; border.width: 1 }
                            }
                        }

                        ColumnLayout {
                            Layout.preferredWidth: 70; spacing: 2
                            Text { text: "站号"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            TextField {
                                id: slaveField
                                Layout.fillWidth: true; text: "1"
                                validator: IntValidator { bottom: 1; top: 255 }
                                font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary
                                background: Rectangle { color: Qt.rgba(0,0,0,0.2); radius: Theme.radiusSm; border.color: slaveField.activeFocus ? Theme.primary : Theme.border; border.width: 1 }
                            }
                        }
                    }

                    // Ping 状态小工具行 (始终占位，绝对固定高度避免面板上下拉长抖动)
                    RowLayout {
                        id: pingStatusRow
                        Layout.fillWidth: true; spacing: 6
                        Rectangle { id: pingDot; width: 6; height: 6; radius: 3; color: Theme.textMuted }
                        Text { id: pingText; text: "ICMP 链路就绪 (等待探测)"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs; Layout.fillWidth: true; elide: Text.ElideRight }
                    }

                    // 5 秒 Ping 超时防护定时器
                    Timer {
                        id: pingTimeoutTimer
                        interval: 5000
                        repeat: false
                        onTriggered: {
                            pingBtn.enabled = true
                            pingBtn.text = "📡 Ping"
                            pingDot.color = Theme.error
                            pingText.text = "ICMP 探测响应超时 (5s)"
                            pingText.color = Theme.error
                        }
                    }
                }
            }

            // 面板 B: Modbus Polling 指令与解码配置
            GlassPanel {
                Layout.fillWidth: true
                implicitHeight: ribbonPollCol.implicitHeight + Theme.spacingMd * 2

                ColumnLayout {
                    id: ribbonPollCol
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Text {
                        text: "⚙️ Modbus Polling 指令与解码配置"
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeSm
                        font.bold: true
                    }

                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.spacingSm

                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: "配置模板预设 (Presets)"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            ComboBox {
                                id: presetCombo
                                onCurrentIndexChanged: root._onParamsChanged()
                                Layout.fillWidth: true
                                font.pixelSize: Theme.fontSizeSm
                                model: ListModel {
                                    ListElement { text: "-- 自定义物理调试 --"; value: "custom" }
                                    ListElement { text: "西门子 S7-1200 风机控制 (03 Holding)"; value: "siemens_fan" }
                                    ListElement { text: "多路 PT100 温度传感器 (04 Input)"; value: "temp_monitor" }
                                }
                                textRole: "text"
                                property string _comboValue: model.get(currentIndex).value
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: "寄存器区段 / 功能码"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            ComboBox {
                                id: fcCombo
                                onCurrentIndexChanged: root._onParamsChanged()
                                Layout.fillWidth: true
                                font.pixelSize: Theme.fontSizeSm
                                model: ListModel {
                                    ListElement { text: "03 读保持寄存器 (Holding)";  value: "03" }
                                    ListElement { text: "04 读输入寄存器 (Input)";     value: "04" }
                                    ListElement { text: "01 读线圈状态 (Coils)";       value: "01" }
                                    ListElement { text: "02 读离散输入 (Discrete)";    value: "02" }
                                    ListElement { text: "23 读/写多寄存器 (RW)";       value: "23" }
                                    ListElement { text: "07 读异常状态 (Exception)";    value: "07" }
                                    ListElement { text: "17 报告从站ID (Report ID)";   value: "17" }
                                    ListElement { text: "20 读文件记录 (File Read)";    value: "20" }
                                    ListElement { text: "22 掩码写寄存器 (Mask)";       value: "22" }
                                    ListElement { text: "24 读FIFO队列 (FIFO)";        value: "24" }
                                    ListElement { text: "43 读设备标识 (Device ID)";    value: "43" }
                                }
                                textRole: "text"
                                property string _comboValue: model.get(currentIndex).value
                            }
                        }

                        ColumnLayout {
                            Layout.preferredWidth: 90; spacing: 2
                            Text { text: "起始地址"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            TextField {
                                id: startAddrField
                                onTextChanged: root._onParamsChanged()
                                Layout.fillWidth: true; text: "0"
                                validator: IntValidator { bottom: 0; top: 65535 }
                                font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary
                                background: Rectangle { color: Qt.rgba(0,0,0,0.2); radius: Theme.radiusSm; border.color: startAddrField.activeFocus ? Theme.primary : Theme.border; border.width: 1 }
                            }
                        }

                        ColumnLayout {
                            Layout.preferredWidth: 80; spacing: 2
                            Text { text: "长度"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            TextField {
                                id: countField
                                onTextChanged: root._onParamsChanged()
                                Layout.fillWidth: true; text: "10"
                                validator: IntValidator { bottom: 1; top: 125 }
                                font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary
                                background: Rectangle { color: Qt.rgba(0,0,0,0.2); radius: Theme.radiusSm; border.color: countField.activeFocus ? Theme.primary : Theme.border; border.width: 1 }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.spacingSm

                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: "Float 32 字节序 (Byte Swap)"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            ComboBox {
                                id: endianCombo
                                onCurrentIndexChanged: root._onParamsChanged()
                                Layout.fillWidth: true
                                font.pixelSize: Theme.fontSizeSm
                                model: ListModel {
                                    ListElement { text: "CDAB (Little-Endian / 西门子)"; value: "CDAB" }
                                    ListElement { text: "ABCD (Big-Endian / 标准)";     value: "ABCD" }
                                    ListElement { text: "BADC (Mid-Little-Endian)";    value: "BADC" }
                                    ListElement { text: "DCBA (Little-Endian Swap)";   value: "DCBA" }
                                }
                                textRole: "text"
                                property string _comboValue: model.get(currentIndex).value
                            }
                        }

                        CheckBox {
                            id: pollChk
                            text: "周期轮询 (1000ms)"
                            checked: true
                            font.pixelSize: Theme.fontSizeXs
                            onCheckedChanged: _updatePolling()
                        }

                        Button {
                            id: readBtn
                            text: "⚡ 单次扫描 / 读取"
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                            palette.button: Theme.success
                            onClicked: _doRead()
                        }
                    }
                }
            }
        }

        // ── 3. 中部 Main Stage (数据表 Grid + 16位 Bit Expander) ─────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 340
            spacing: Theme.spacingMd

            // 寄存器数据主表
            GlassPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "📊 实时数据监视表 (Live Registers Monitor Grid)"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                            Layout.fillWidth: true
                        }
                        Text {
                            text: "💡 双击数据行或点击「填入」加载写缓存区"
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSizeXs
                        }
                    }

                    // 表头 Header Row
                    Rectangle {
                        Layout.fillWidth: true
                        height: 32
                        color: Qt.rgba(0, 0, 0, 0.25)
                        radius: Theme.radiusSm

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.spacingSm
                            anchors.rightMargin: Theme.spacingSm
                            spacing: 8

                            Text { text: "物理地址"; Layout.preferredWidth: 90; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs; font.bold: true }
                            Text { text: "绑定 Tag 符号"; Layout.fillWidth: true; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs; font.bold: true }
                            Text { text: "十进制 (Dec)"; Layout.preferredWidth: 90; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs; font.bold: true }
                            Text { text: "十六进制 (Hex)"; Layout.preferredWidth: 90; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs; font.bold: true }
                            Text { text: "32位浮点解码"; Layout.preferredWidth: 110; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs; font.bold: true }
                            Text { text: "快捷操作"; Layout.preferredWidth: 60; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs; font.bold: true; horizontalAlignment: Text.AlignRight }
                        }
                    }

                    // 表格 ListView
                    ListView {
                        id: registerTableView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: ListModel { id: registerModel }

                        delegate: Rectangle {
                            width: registerTableView.width
                            height: 36
                            color: index % 2 === 0 ? Qt.rgba(1,1,1,0.01) : "transparent"
                            border.color: Theme.borderSubtle
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: Theme.spacingSm
                                anchors.rightMargin: Theme.spacingSm
                                spacing: 8

                                Text {
                                    Layout.preferredWidth: 90
                                    text: model.physical || ""
                                    color: Theme.secondary
                                    font.pixelSize: Theme.fontSizeXs
                                    font.family: "Consolas, Courier New, monospace"
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: model.tag || ""
                                    color: Theme.textSecondary
                                    font.pixelSize: Theme.fontSizeXs
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.preferredWidth: 90
                                    text: model.dec !== undefined ? model.dec.toString() : ""
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontSizeXs
                                    font.family: "Consolas, Courier New, monospace"
                                }
                                Text {
                                    Layout.preferredWidth: 90
                                    text: model.hex || ""
                                    color: Theme.warning
                                    font.pixelSize: Theme.fontSizeXs
                                    font.family: "Consolas, Courier New, monospace"
                                }
                                Text {
                                    Layout.preferredWidth: 110
                                    text: model.float_decoded || ""
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontSizeXs
                                }
                                Button {
                                    Layout.preferredWidth: 60
                                    text: "✍ 填入"
                                    font.pixelSize: 10
                                    implicitHeight: 22
                                    onClicked: root._fillWriteSlot(model.address, model.dec, model.physical)
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.NoButton
                                onDoubleClicked: root._fillWriteSlot(model.address, model.dec, model.physical)
                            }
                        }

                        Text {
                            visible: registerModel.count === 0
                            anchors.centerIn: parent
                            text: "暂无数据，请在顶部配置参数后点击连接或扫描"
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSizeSm
                        }
                    }
                }
            }

            // 右侧 16位 Bit Expander & 写入控制面板 (用 ScrollView 严格限制卡片边界，彻底封印溢出)
            GlassPanel {
                Layout.preferredWidth: 340
                Layout.fillHeight: true
                clip: true

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ColumnLayout {
                        width: parent.width - 12
                        spacing: Theme.spacingSm

                        ModbusBitExpander {
                            id: bitExpander
                            Layout.fillWidth: true
                            Layout.preferredHeight: 180
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

                        Text {
                            text: "✍️ 物理参数下发写入"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                        }

                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: "写入功能码"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                            ComboBox {
                                id: writeFcCombo
                                Layout.fillWidth: true
                                font.pixelSize: Theme.fontSizeSm
                                model: ListModel {
                                    ListElement { text: "06 写单保持寄存器"; value: "06" }
                                    ListElement { text: "05 写单线圈";       value: "05" }
                                    ListElement { text: "16 写多保持寄存器"; value: "16" }
                                    ListElement { text: "15 写多线圈";       value: "15" }
                                    ListElement { text: "21 写多寄存器 (RW)";value: "21" }
                                    ListElement { text: "22 掩码写寄存器";   value: "22" }
                                }
                                textRole: "text"
                                property string _comboValue: model.get(currentIndex).value
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true; spacing: 4
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 2
                                Text { text: "地址"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                                TextField {
                                    id: writeAddrField
                                    Layout.fillWidth: true; text: "0"
                                    validator: IntValidator { bottom: 0; top: 65535 }
                                    font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary
                                    background: Rectangle { color: Qt.rgba(0,0,0,0.2); radius: Theme.radiusSm; border.color: writeAddrField.activeFocus ? Theme.primary : Theme.border; border.width: 1 }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 2
                                Text { text: "数值"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
                                TextField {
                                    id: writeValField
                                    Layout.fillWidth: true; text: "0"
                                    font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary
                                    background: Rectangle { color: Qt.rgba(0,0,0,0.2); radius: Theme.radiusSm; border.color: writeValField.activeFocus ? Theme.primary : Theme.border; border.width: 1 }
                                }
                            }
                        }

                        Button {
                            id: writeBtn
                            Layout.fillWidth: true
                            text: "✍ 下发写入指令到 PLC"
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                            enabled: root._isConnected
                            onClicked: {
                                if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
                                    modbusBridge.writeRegister(
                                        writeFcCombo._comboValue,
                                        parseInt(writeAddrField.text) || 0,
                                        writeValField.text
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── 4. 底部 Live Traffic Trace 沉底控制台 ─────────────
        GlassPanel {
            Layout.fillWidth: true
            implicitHeight: 180
            clip: true

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingSm

                TabBar {
                    id: subTabBar
                    Layout.fillWidth: true

                    TabButton { text: "📟 Modbus TCP 网口物理报文链路 (Live Traffic Trace)" }
                    TabButton { text: "🧭 0-99 寄存器区段扫描探测器 (Interrogator Scanner)" }
                }

                StackLayout {
                    id: subStack
                    currentIndex: subTabBar.currentIndex >= 0 ? subTabBar.currentIndex : 0
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    // Tab 0: 物理报文 Trace (独立 Container)
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Flickable {
                            id: consoleFlickable
                            anchors.fill: parent
                            contentHeight: consoleText.implicitHeight
                            clip: true

                            Text {
                                id: consoleText
                                width: consoleFlickable.width
                                text: "[SYS] Modbus TCP 网口物理链路已就绪...\n"
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontSizeXs
                                font.family: "Consolas, Courier New, monospace"
                                textFormat: Text.RichText
                                wrapMode: Text.WrapAnywhere
                            }
                        }
                    }

                    // Tab 1: 扫描探测器 (独立 Container)
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: Theme.spacingSm

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "🧭 寄存器区段扫描探测器 (Interrogator Scanner 0-99)"
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontSizeSm
                                    font.bold: true
                                    Layout.fillWidth: true
                                }
                                Button {
                                    id: startScanBtn
                                    text: "⚡ 立即探测 (0-99)"
                                    font.pixelSize: Theme.fontSizeSm
                                    onClicked: {
                                        scannerGrid.resetAll()
                                        startScanBtn.enabled = false
                                        startScanBtn.text = "扫描中..."
                                        if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
                                            modbusBridge.scanRegisters(0, 99)
                                        } else {
                                            _simulateScan()
                                        }
                                    }
                                }
                            }

                            Flickable {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                contentHeight: scannerGrid.implicitHeight
                                clip: true

                                ModbusScannerGrid {
                                    id: scannerGrid
                                    width: parent.width
                                    startOffset: 0
                                    onCellClicked: {
                                        startAddrField.text = offset.toString()
                                        subTabBar.currentIndex = 0
                                        _doRead()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    } // ColumnLayout 主布局结束
    // ── 文件对话框（导入/导出） ─────────────────────────
    FileDialog {
        id: importDialog
        title: "导入 Modbus 配置文件"
        nameFilters: ["JSON 配置文件 (*.json)"]
        onAccepted: {
            if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
                var config = modbusBridge.importConfig(selectedFile.toString().replace("file:///", ""))
                if (config && config.ip) {
                    ipField.text = config.ip
                    portField.text = (config.port || 502).toString()
                    slaveField.text = (config.slave_id || 1).toString()
                    simChk.checked = config.sim_mode !== false
                }
            }
        }
    }

    FileDialog {
        id: exportDialog
        title: "导出 Modbus 配置文件"
        fileMode: FileDialog.SaveFile
        nameFilters: ["JSON 配置文件 (*.json)"]
        defaultSuffix: "json"
        onAccepted: {
            if (typeof modbusBridge !== "undefined" && modbusBridge !== null) {
                modbusBridge.exportConfig(selectedFile.toString().replace("file:///", ""))
            }
        }
    }

    // ── 无 Bridge 时的仿真扫描函数 ───────────────────────
    function _doReadSim() {
        // 本地仿真数据（无 Bridge 时使用）
        registerModel.clear()
        var tags = ["Fan_Speed_SP", "Fan_Status", "Fan_Current", "Fan_Temp_H", "Fan_Temp_L", "Fan_Warn"]
        for (var i = 0; i < 8; i++) {
            registerModel.append({
                address: i,
                physical: (40001 + i).toString(),
                tag: i < tags.length ? tags[i] : "DB10.DBW" + (i * 2),
                dec: Math.floor(Math.random() * 4000),
                hex: "0x" + Math.floor(Math.random() * 65535).toString(16).toUpperCase().padStart(4, "0"),
                float_decoded: (Math.random() * 200).toFixed(3),
                is_coil: false
            })
        }
    }

    property var _scanTimer: null

    function _simulateScan() {
        var step = 0
        var activeSet = [0,1,2,3,4,5,6,7,10,11,12,13,14,15,42,43]
        var timer = Qt.createQmlObject("import QtQuick; Timer { interval: 60; repeat: true }", root)
        timer.triggered.connect(function() {
            for (var j = 0; j < 5; j++) {
                var cellId = step * 5 + j
                if (cellId >= 100) break
                scannerGrid.updateCell(cellId, activeSet.indexOf(cellId) >= 0)
            }
            step++
            if (step >= 20) {
                timer.stop()
                timer.destroy()
                startScanBtn.enabled = true
                startScanBtn.text = "⚡ 重新探测"
            }
        })
        timer.start()
    }
}