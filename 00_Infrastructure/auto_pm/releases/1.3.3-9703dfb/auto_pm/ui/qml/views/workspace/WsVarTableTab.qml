// WsVarTableTab.qml — 变量表与 IO 资产 Tab V1.0.0
// 从 WorkspaceView.qml 的 varTableTab（原 L1098-L1110）提取
// 内容极简：直接委托 VarTableEditorView

import QtQuick
import ".."
import "../../theme"

Item {
    id: root

    // ── 公开属性
    property string projectId: ""

    VarTableEditorView {
        anchors.fill: parent
        projectId: root.projectId
    }
}
