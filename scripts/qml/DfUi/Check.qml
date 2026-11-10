import QtQuick
import QtQuick.Templates as T
import DfUi

T.CheckBox {
    id: control

    property string tip: ""

    implicitHeight: 24
    implicitWidth: implicitContentWidth
    spacing: 8
    hoverEnabled: true

    indicator: Rectangle {
        y: (control.height - height) / 2
        width: 18
        height: 18
        radius: 6
        color: !control.enabled ? "#E9ECF2"
             : control.checked ? (control.hovered ? Theme.primaryHover : Theme.primary)
             : control.hovered ? "#D0D7E5" : "#DDE2EC"
        Behavior on color { ColorAnimation { duration: Theme.fast } }

        Glyph {
            anchors.centerIn: parent
            code: ""
            font.pixelSize: 11
            color: "#FFFFFF"
            scale: control.checked ? 1 : 0
            Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutBack } }
        }
    }

    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        font: control.font
        color: control.enabled ? Theme.textSecondary : Theme.textDisabled
        verticalAlignment: Text.AlignVCenter
    }

    Tip {
        visible: control.tip !== "" && control.hovered
        text: control.tip
    }
}
