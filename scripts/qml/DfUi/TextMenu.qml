import QtQuick
import QtQuick.Controls.Basic
import DfUi

// Right-click menu for text controls, replacing the unstyled English default.
Menu {
    id: menu

    property Item target
    property bool editable: false

    padding: 6
    background: Rectangle {
        implicitWidth: 132
        radius: Theme.radius
        color: "#3B4A63"
    }

    component Entry: MenuItem {
        id: entry

        height: visible ? implicitHeight : 0
        implicitHeight: 32
        leftPadding: 12
        rightPadding: 12

        contentItem: Text {
            text: entry.text
            color: entry.enabled ? "#FFFFFF" : "#94A0B4"
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 8
            color: entry.highlighted && entry.enabled ? "#52637F" : "transparent"
        }
    }

    Entry {
        visible: menu.editable
        text: "剪切"
        enabled: menu.target && menu.target.selectedText !== ""
        onTriggered: menu.target.cut()
    }
    Entry {
        text: "复制"
        enabled: menu.target && menu.target.selectedText !== ""
        onTriggered: menu.target.copy()
    }
    Entry {
        visible: menu.editable
        text: "粘贴"
        enabled: menu.target && menu.target.canPaste
        onTriggered: menu.target.paste()
    }
    Entry {
        text: "全选"
        enabled: menu.target && menu.target.length > 0
        onTriggered: menu.target.selectAll()
    }
}
