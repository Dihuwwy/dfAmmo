import QtQuick
import QtQuick.Controls.Basic

ToolTip {
    id: control

    delay: 500
    topPadding: 7
    bottomPadding: 7
    leftPadding: 10
    rightPadding: 10
    width: Math.min(implicitWidth, 380)

    contentItem: Text {
        text: control.text
        color: "#FFFFFF"
        font.pixelSize: 12
        wrapMode: Text.Wrap
    }
    background: Rectangle {
        radius: 8
        color: "#263043"
    }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120 }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 80 }
    }
}
