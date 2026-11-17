// WsDocTab.qml — 项目文档浏览 Tab V1.0.0
// 从 WorkspaceView.qml 的 docTab（原 L1084-L1096）提取
// 内容极简：直接委托 DocBrowserView

import QtQuick
import ".."
import "../../theme"

Item {
    id: root

    // ── 公开属性
    property string projectId: ""

    DocBrowserView {
        anchors.fill: parent
        projectId: root.projectId
    }
}
