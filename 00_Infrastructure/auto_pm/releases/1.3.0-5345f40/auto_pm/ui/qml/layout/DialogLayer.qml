// DialogLayer.qml — 对话框统一宿主 V1.0.0
// 将 main.qml 中 15 个对话框（L946-L1173）统一收口
// 新增 Dialog 只需在此文件追加，main.qml 通过 dialogLayer.openXxx() 调用
// 外部接口：openXxx() 函数 + 结果信号

import QtQuick
import "../dialogs"
import "../theme"

Item {
    id: root
    anchors.fill: parent

    // ── 公开打开函数（main.qml 通过 dialogLayer.openXxx() 调用）
    function openNewProject()                    { newProjectWizard._isOpen = true }
    function openImportProject()                 { importProjectDialog._isOpen = true }
    function openNewChange(projectId)            { newChangeDialog.projectId = projectId; newChangeDialog.open() }
    function openEditChange(changeDetail)        { editChangeDialog.prefill(changeDetail); editChangeDialog._isOpen = true }
    function openReconcileLedger(projectId)      { ledgerReconcileDialog.open(projectId) }
    function openEditProject(pid, pname, detail) { projectEditDialog.open(pid, pname, detail) }
    function openDeleteProject(pid, pname)       { deleteConfirmDialog.projectId = pid; deleteConfirmDialog.projectName = pname; deleteConfirmDialog.open() }
    function openApplyTemplate(pid, pname)       { templateApplyDialog.open(pid, pname) }
    function openPmInitializeConfirm()           { pmInitializeConfirmDialog._isOpen = true }
    function openPmSessionArchive()              { pmSessionArchiveDialog.open() }
    function openSpecIndex()                     { specIndexDialog.open() }
    function openSpecReport()                    { specReportDialog.open() }
    function openSpecFrontmatter()               { specFrontmatterDialog.open() }
    function openAbout()                         { aboutDialog._isOpen = true }
    function openGlobalSettings(wsRoot)          { globalSettingsDialog.workspaceRoot = wsRoot; globalSettingsDialog._isOpen = true }

    // ── 结果信号（汇总所有 Dialog 结果通知 main.qml）
    signal projectCreated(string projectId)
    signal projectImported(string projectId)
    signal changeCreated(string changeNumber)
    signal changeSaved(string changeNumber)
    signal projectSaved(string projectId)
    signal projectDeleted(string projectId)
    signal ledgerReconciled()
    signal pmInitialized(string projectId)
    signal pmSessionArchived()
    signal specIndexGenerated()
    signal specReportGenerated()
    signal specFrontmatterChecked()
    signal globalSettingsSaved(string workspaceRoot)

    // ── 对话框实例
    NewProjectWizard {
        id: newProjectWizard
        anchors.fill: parent; z: 999
        onProjectCreated: root.projectCreated(projectId)
    }
    ImportProjectDialog {
        id: importProjectDialog; objectName: "importProjectDialog"
        anchors.fill: parent; z: 999
        onImported: root.projectImported(projectId)
    }
    NewChangeDialog {
        id: newChangeDialog; objectName: "newChangeDialog"
        anchors.fill: parent; z: 999
        onChangeCreated: root.changeCreated(changeNumber)
    }
    EditChangeDialog {
        id: editChangeDialog; objectName: "editChangeDialog"
        anchors.fill: parent; z: 999
        onChangeSaved: root.changeSaved(changeNumber)
    }
    ProjectEditDialog {
        id: projectEditDialog; objectName: "projectEditDialog"
        anchors.fill: parent; z: 999
        onProjectSaved: root.projectSaved(projectId)
        onCancelled: close()
    }
    DeleteConfirmDialog {
        id: deleteConfirmDialog; objectName: "deleteConfirmDialog"
        anchors.fill: parent; z: 999
        onConfirmed: root.projectDeleted(projectId)
        onCancelled: close()
    }
    TemplateApplyDialog {
        id: templateApplyDialog; objectName: "templateApplyDialog"
        anchors.fill: parent; z: 999
        onCancelled: close()
    }
    PmInitializeConfirmDialog {
        id: pmInitializeConfirmDialog; objectName: "pmInitializeConfirmDialog"
        anchors.fill: parent; z: 999
        onConfirmed: (projectId) => root.pmInitialized(projectId)
        onCancelled: close()
    }
    PmSessionArchiveDialog {
        id: pmSessionArchiveDialog; objectName: "pmSessionArchiveDialog"
        anchors.fill: parent; z: 999
        onArchived: root.pmSessionArchived()
        onCancelled: close()
    }
    LedgerReconcileDialog {
        id: ledgerReconcileDialog; objectName: "ledgerReconcileDialog"
        anchors.fill: parent; z: 999
        onReconciled: root.ledgerReconciled()
        onCancelled: close()
    }
    SpecIndexDialog {
        id: specIndexDialog; objectName: "specIndexDialog"
        anchors.fill: parent; z: 999
        onGenerated: root.specIndexGenerated()
        onCancelled: close()
    }
    SpecReportDialog {
        id: specReportDialog; objectName: "specReportDialog"
        anchors.fill: parent; z: 999
        onGenerated: root.specReportGenerated()
        onCancelled: close()
    }
    SpecFrontmatterDialog {
        id: specFrontmatterDialog; objectName: "specFrontmatterDialog"
        anchors.fill: parent; z: 999
        onChecked: root.specFrontmatterChecked()
        onCancelled: close()
    }
    AboutDialog {
        id: aboutDialog; objectName: "aboutDialog"
        anchors.fill: parent; z: 999
        onClosed: _isOpen = false
    }
    GlobalSettingsDialog {
        id: globalSettingsDialog; objectName: "globalSettingsDialog"
        anchors.fill: parent; z: 999
        onSaved: root.globalSettingsSaved(workspaceRoot)
        onCancelled: _isOpen = false
    }
}
