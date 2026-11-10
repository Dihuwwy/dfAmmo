pragma Singleton
import QtQuick

// Design tokens. Controls are separated by fill colour, never by hairline
// borders, so edges stay even at fractional display scales.
QtObject {
    readonly property color window: "#F1F4F9"
    readonly property color card: "#FFFFFF"
    readonly property color fill: "#EDF0F6"
    readonly property color fillHover: "#E1E7F3"
    readonly property color fillPressed: "#D3DCEE"
    readonly property color primary: "#0B57D0"
    readonly property color primaryHover: "#1B66C9"
    readonly property color primaryPressed: "#0842A0"
    readonly property color primarySoft: "#E8F0FE"
    readonly property color primarySoftHover: "#D3E3FD"
    readonly property color text: "#191C20"
    readonly property color textSecondary: "#44474E"
    readonly property color textMuted: "#64748B"
    readonly property color textDisabled: "#A9ABB4"
    readonly property color success: "#15803D"
    readonly property color successSoft: "#DCFCE7"
    readonly property color danger: "#DC2626"
    readonly property color dangerSoft: "#FDECEC"
    readonly property color dangerSoftHover: "#FBD5D5"
    readonly property color warning: "#D97706"
    readonly property color warningSoft: "#FEF3C7"
    readonly property color logSurface: "#1E293B"

    readonly property int radius: 12
    readonly property int cardRadius: 18
    readonly property int controlHeight: 34
    readonly property int fast: 120
}
