import QtQuick
import DfUi

// Single-choice selector with a sliding indicator.
Rectangle {
    id: root

    property var options: []      // [{ label, value }]
    property var value
    property int segmentWidth: 88
    property string tip: ""
    signal chosen(var value)

    readonly property int currentIndex: {
        for (let i = 0; i < options.length; i++)
            if (options[i].value === value)
                return i
        return -1
    }

    implicitHeight: Theme.controlHeight
    implicitWidth: options.length * segmentWidth + 6
    radius: Theme.radius
    color: Theme.fill
    opacity: enabled ? 1 : 0.55

    Rectangle {
        visible: root.currentIndex >= 0
        x: 3 + root.currentIndex * root.segmentWidth
        y: 3
        width: root.segmentWidth
        height: root.height - 6
        radius: Theme.radius - 3
        color: Theme.primary
        Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }

    Row {
        x: 3
        y: 3

        Repeater {
            model: root.options

            Item {
                width: root.segmentWidth
                height: root.height - 6

                Text {
                    anchors.centerIn: parent
                    text: modelData.label
                    font.weight: Font.Medium
                    color: index === root.currentIndex ? "#FFFFFF" : hover.hovered ? Theme.primary : "#475569"
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                }
                HoverHandler { id: hover }
                TapHandler {
                    onTapped: if (modelData.value !== root.value) root.chosen(modelData.value)
                }
            }
        }
    }

    HoverHandler { id: rootHover }
    Tip {
        visible: root.tip !== "" && rootHover.hovered
        text: root.tip
    }
}
