import QtQuick

// One icon from the Segoe icon font that ships with Windows.
Text {
    property string code

    text: code
    font.family: ui.iconFont
    font.pixelSize: 14
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
}
