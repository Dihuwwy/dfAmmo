import QtQuick
import QtQuick.Controls.Basic
import DfUi

TextField {
    id: control

    implicitHeight: Theme.controlHeight
    leftPadding: 12
    rightPadding: 12
    topPadding: 0
    bottomPadding: 0
    verticalAlignment: TextInput.AlignVCenter
    color: enabled ? Theme.text : Theme.textDisabled
    placeholderTextColor: "#8A93A6"
    selectionColor: "#BCD3FB"
    selectedTextColor: Theme.text
    selectByMouse: true
    ContextMenu.menu: TextMenu {
        target: control
        editable: true
    }

    background: Rectangle {
        radius: Theme.radius
        color: control.activeFocus ? "#E1E9F8" : Theme.fill
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
}
