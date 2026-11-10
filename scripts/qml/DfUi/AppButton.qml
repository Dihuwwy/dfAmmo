import QtQuick
import QtQuick.Templates as T
import DfUi

T.Button {
    id: control

    // tonal | surface | soft | primary | danger | ghost
    property string kind: "tonal"
    property string glyph: ""
    property string tip: ""

    readonly property var tones: ({
        "tonal": { bg: Theme.fill, hover: Theme.fillHover, down: Theme.fillPressed,
                   fg: Theme.textSecondary, fgHover: Theme.primary, off: "#F1F2F5", offFg: "#A9ABB4" },
        "surface": { bg: "#FFFFFF", hover: "#E1E9F8", down: Theme.fillPressed,
                     fg: Theme.textSecondary, fgHover: Theme.primary, off: "#E2E7F0", offFg: "#868B98" },
        "soft": { bg: Theme.primarySoft, hover: Theme.primarySoftHover, down: "#BCD3FB",
                  fg: Theme.primary, fgHover: Theme.primary, off: "#F1F2F5", offFg: "#A9ABB4" },
        "primary": { bg: Theme.primary, hover: Theme.primaryHover, down: Theme.primaryPressed,
                     fg: "#FFFFFF", fgHover: "#FFFFFF", off: "#DCE2F9", offFg: "#777B85" },
        "danger": { bg: Theme.dangerSoft, hover: Theme.dangerSoftHover, down: "#F8BFBF",
                    fg: Theme.danger, fgHover: Theme.danger, off: "#E2E7F0", offFg: "#868B98" },
        "ghost": { bg: "#00EDF0F6", hover: Theme.fill, down: Theme.fillHover,
                   fg: Theme.textMuted, fgHover: Theme.primary, off: "#00EDF0F6", offFg: "#A9ABB4" }
    })
    readonly property var tone: tones[kind] || tones.tonal
    readonly property color foreground: !enabled ? tone.offFg : hovered ? tone.fgHover : tone.fg

    implicitHeight: kind === "primary" ? 38 : Theme.controlHeight
    implicitWidth: Math.max(implicitHeight, implicitContentWidth + leftPadding + rightPadding)
    leftPadding: text === "" ? 0 : kind === "primary" ? 22 : 14
    rightPadding: leftPadding
    hoverEnabled: true
    font.pixelSize: kind === "primary" ? 14 : 13
    font.weight: kind === "primary" || kind === "soft" ? Font.DemiBold : Font.Medium

    background: Rectangle {
        radius: control.kind === "primary" ? height / 2 : Theme.radius
        color: !control.enabled ? control.tone.off : control.down ? control.tone.down
             : control.hovered ? control.tone.hover : control.tone.bg
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight

        Row {
            id: row
            anchors.centerIn: parent
            spacing: 6

            Glyph {
                visible: control.glyph !== ""
                code: control.glyph
                color: control.foreground
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                visible: control.text !== ""
                text: control.text
                font: control.font
                color: control.foreground
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
    }

    Tip {
        visible: control.tip !== "" && control.hovered
        text: control.tip
    }
}
