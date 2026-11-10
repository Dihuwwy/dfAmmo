import QtQuick
import QtQuick.Templates as T
import DfUi

T.Button {
    id: control

    // idle | running | current | success | failed
    property string stepState: "idle"
    property string tip: ""

    readonly property bool active: stepState === "running" || stepState === "current"
    readonly property color foreground: !enabled ? "#A9ABB4"
        : stepState === "success" ? Theme.success
        : stepState === "failed" ? Theme.danger
        : active || hovered ? Theme.primary : "#334155"

    implicitHeight: 30
    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    leftPadding: 12
    rightPadding: 12
    hoverEnabled: true
    font.pixelSize: 13
    font.weight: active ? Font.DemiBold : Font.Medium

    background: Rectangle {
        radius: height / 2
        color: !control.enabled ? "#F1F0F4"
             : control.stepState === "success" ? (control.hovered ? "#C9F7D9" : Theme.successSoft)
             : control.stepState === "failed" ? (control.hovered ? "#FDD0D0" : "#FEE2E2")
             : control.active ? "#C8DCFC"
             : control.down ? "#C7D2FE" : control.hovered ? "#E0E7FF" : "#F1F5F9"
        Behavior on color { ColorAnimation { duration: 160 } }
    }

    contentItem: Row {
        spacing: 5

        Glyph {
            visible: control.stepState === "success" || control.stepState === "failed"
            code: control.stepState === "success" ? "" : ""
            font.pixelSize: 11
            color: control.foreground
            anchors.verticalCenter: parent.verticalCenter
        }
        Rectangle {
            id: pulse
            visible: control.stepState === "running"
            width: 6
            height: 6
            radius: 3
            color: Theme.primary
            anchors.verticalCenter: parent.verticalCenter

            SequentialAnimation on opacity {
                running: pulse.visible
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 600; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
            }
        }
        Text {
            text: control.text
            font: control.font
            color: control.foreground
            anchors.verticalCenter: parent.verticalCenter
            Behavior on color { ColorAnimation { duration: 160 } }
        }
    }

    Tip {
        visible: control.tip !== "" && control.hovered
        text: control.tip
    }
}
