import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import DfUi

// The view only renders `ui` (state published by the controller) and calls
// `backend` slots; it holds no workflow state of its own.
ApplicationWindow {
    id: window

    readonly property bool semiAuto: ui.operationMode === "semi_auto"

    title: ui.windowTitle
    width: 900
    height: 940
    minimumWidth: 820
    minimumHeight: 560
    color: Theme.window
    font.family: ui.uiFont
    font.pixelSize: 13
    onClosing: backend.windowClosing()

    function scrollLogToEnd() {
        const flickable = logScroll.contentItem
        flickable.contentY = Math.max(0, flickable.contentHeight - flickable.height)
    }

    component SectionTitle: Text {
        color: Theme.text
        font.pixelSize: 14
        font.weight: Font.DemiBold
    }

    component FieldLabel: Text {
        Layout.preferredWidth: 92
        color: Theme.textMuted
    }

    // One stage of the flow: a timeline marker, a heading and its step pills.
    component Stage: Item {
        id: stage

        property string title
        property string subtitle
        property string stageState: "idle"
        property bool first: false
        property bool last: false
        default property alias content: flow.data

        Layout.fillWidth: true
        implicitHeight: body.implicitHeight + (last ? 0 : 16)

        Rectangle {
            x: 5
            y: stage.first ? 10 : 0
            width: 2
            height: (stage.last ? 10 : stage.height) - y
            color: "#E2E8F0"
        }
        Rectangle {
            y: 4
            width: 12
            height: 12
            radius: 6
            color: ({ running: Theme.primary, success: "#10B981", failed: "#EF4444" })[stage.stageState] || "#CBD5E1"
            Behavior on color { ColorAnimation { duration: 200 } }
        }
        Column {
            id: body
            x: 26
            width: stage.width - 26
            spacing: 8

            Row {
                spacing: 8

                Text {
                    id: stageTitle
                    text: stage.title
                    color: Theme.text
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
                Text {
                    text: stage.subtitle
                    color: Theme.textMuted
                    anchors.baseline: stageTitle.baseline
                }
            }
            Flow {
                id: flow
                width: parent.width
                spacing: 6
            }
        }
    }

    component Step: Row {
        id: step

        property bool arrow: true
        property string label
        property string stepState: "idle"
        property string tip
        property bool placeholder: false
        signal activated()

        spacing: 6

        Text {
            visible: step.arrow
            text: "›"
            color: "#94A3B8"
            font.pixelSize: 14
            anchors.verticalCenter: parent.verticalCenter
        }
        StepPill {
            text: step.label
            stepState: step.stepState
            tip: step.tip
            enabled: !step.placeholder
            onClicked: step.activated()
        }
    }

    component Sheet: Popup {
        anchors.centerIn: Overlay.overlay
        modal: true
        focus: true
        padding: 22
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: 20
            color: Theme.card
        }
        Overlay.modal: Rectangle {
            color: "#660F172A"
        }
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 150 }
                NumberAnimation { property: "scale"; from: 0.94; to: 1; duration: 180; easing.type: Easing.OutCubic }
            }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 110 }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // ── Connection and settings ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: false
            spacing: 8

            Card {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                implicitHeight: connection.implicitHeight + 28

                ColumnLayout {
                    id: connection
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    anchors.topMargin: 14
                    anchors.bottomMargin: 14
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: false

                        SectionTitle { text: "WeGame 客户端" }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            implicitWidth: badgeText.implicitWidth + 20
                            implicitHeight: 24
                            radius: 12
                            color: ui.connected ? "#D1FAE5" : Theme.warningSoft
                            Behavior on color { ColorAnimation { duration: 200 } }

                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: ui.connected ? "已连接" : "未连接"
                                color: ui.connected ? "#059669" : Theme.warning
                                font.weight: Font.DemiBold
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 34
                        radius: Theme.radius
                        color: Theme.fill

                        Column {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2

                            Text {
                                width: parent.width
                                text: ui.connTitle
                                color: Theme.textSecondary
                                elide: Text.ElideRight
                            }
                            Text {
                                width: parent.width
                                visible: text !== ""
                                text: ui.connSubtitle
                                color: Theme.textMuted
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                        }
                        HoverHandler { id: detailHover }
                        Tip {
                            visible: ui.connTooltip !== "" && detailHover.hovered
                            text: ui.connTooltip
                        }
                    }

                    // Press here, drag onto the WeGame window and release.
                    Rectangle {
                        id: bind
                        Layout.fillWidth: true
                        implicitHeight: Theme.controlHeight
                        radius: Theme.radius
                        enabled: !ui.controlsLocked
                        color: !enabled ? "#F1F2F5" : bindArea.pressed ? "#BCD3FB"
                             : bindArea.containsMouse ? Theme.primarySoftHover : Theme.primarySoft
                        Behavior on color { ColorAnimation { duration: Theme.fast } }

                        Row {
                            anchors.centerIn: parent
                            spacing: 6

                            Glyph {
                                code: ""
                                color: bindLabel.color
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                id: bindLabel
                                text: bindArea.pressed ? "松开鼠标完成绑定"
                                    : ui.connected ? "重新拖拽绑定" : "拖拽至 WeGame 窗口绑定"
                                color: bind.enabled ? Theme.primary : Theme.textDisabled
                                font.weight: Font.DemiBold
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                        MouseArea {
                            id: bindArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: pressed ? Qt.CrossCursor : Qt.OpenHandCursor
                            onPressed: backend.beginBind()
                            onReleased: backend.endBind()
                            onCanceled: backend.cancelBind()
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                Layout.fillHeight: true
                implicitHeight: settings.implicitHeight + 28

                ColumnLayout {
                    id: settings
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    anchors.topMargin: 14
                    anchors.bottomMargin: 14
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: false

                        SectionTitle { text: "设置" }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            kind: "ghost"
                            glyph: ""
                            tip: "关于 / 更新"
                            implicitWidth: 24
                            implicitHeight: 24
                            onClicked: aboutDialog.open()
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: false
                        enabled: !ui.controlsLocked
                        spacing: 8

                        FieldLabel { text: "游戏安装目录" }
                        Field {
                            id: gameDirField
                            Layout.fillWidth: true
                            text: ui.gameDir
                            placeholderText: "请选择包含 DeltaForce 文件夹的安装目录"
                            onEditingFinished: backend.setGameDir(text)
                        }
                        AppButton {
                            text: "浏览..."
                            onClicked: {
                                const chosen = backend.chooseGameDir()
                                if (chosen !== "")
                                    gameDirField.text = chosen
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: false
                        enabled: !ui.controlsLocked
                        spacing: 8

                        FieldLabel { text: "运行模式" }
                        Segmented {
                            options: [{ label: "半自动", value: "semi_auto" }, { label: "全自动", value: "full_auto" }]
                            value: ui.operationMode
                            onChosen: (value) => backend.setOperationMode(value)
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: false
                        enabled: !ui.controlsLocked
                        spacing: 8

                        FieldLabel { text: "目标地图" }
                        Segmented {
                            enabled: ui.mapEnabled
                            options: [{ label: "长弓溪谷", value: "changgong" }, { label: "AZ3", value: "az3" }]
                            value: ui.mapId
                            tip: ui.mapEnabled ? "" : "任务执行或保留继续进度时不能切换地图"
                            onChosen: (value) => backend.setMapId(value)
                        }
                        Item { Layout.fillWidth: true }
                        Check {
                            text: "检查补齐队友"
                            tip: "行动前检查补齐队友，未勾选时自动开启"
                            checked: ui.fillTeammates
                            onToggled: {
                                backend.setFillTeammates(checked)
                                checked = Qt.binding(() => ui.fillTeammates)
                            }
                        }
                    }
                }
            }
        }

        // ── Actions ──────────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: false
            spacing: 6

            AppButton {
                kind: "primary"
                glyph: ""
                text: "开始卡邮件"
                enabled: ui.startEnabled
                onClicked: backend.startCardMail()
            }
            AppButton {
                kind: ui.paused ? "soft" : "surface"
                glyph: ""
                text: "继续"
                tip: "继续执行 (Ctrl+F12)"
                enabled: ui.continueEnabled
                onClicked: backend.continueNavigation()
            }
            AppButton {
                kind: "danger"
                glyph: ""
                text: "停止"
                tip: "停止任务 (Shift+F12)"
                enabled: ui.stopEnabled
                onClicked: backend.emergencyStop()
            }
            Item { Layout.fillWidth: true }
            AppButton {
                kind: "surface"
                glyph: ""
                text: "采集模板"
                onClicked: captureDialog.open()
            }
            Rectangle {
                id: status

                readonly property var tones: ({
                    running: ["#D3E3FD", "#0B57D0"],
                    success: ["#D1FAE5", "#059669"],
                    failed: ["#FEE2E2", "#DC2626"]
                })
                readonly property var tone: tones[ui.statusState] || ["#E8F0FE", "#1967D2"]

                Layout.preferredWidth: 250
                implicitHeight: Theme.controlHeight
                radius: height / 2
                color: tone[0]
                Behavior on color { ColorAnimation { duration: 200 } }

                Row {
                    anchors.centerIn: parent
                    spacing: 7

                    Rectangle {
                        id: statusDot
                        width: 7
                        height: 7
                        radius: 3.5
                        color: status.tone[1]
                        anchors.verticalCenter: parent.verticalCenter

                        SequentialAnimation on opacity {
                            running: ui.statusState === "running"
                            loops: Animation.Infinite
                            alwaysRunToEnd: true
                            NumberAnimation { to: 0.25; duration: 600; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        width: Math.min(implicitWidth, status.width - 44)
                        text: ui.statusText
                        color: status.tone[1]
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                HoverHandler { id: statusHover }
                Tip {
                    visible: ui.statusTooltip !== "" && statusHover.hovered
                    text: ui.statusTooltip
                }
            }
        }

        // ── Flow and log ─────────────────────────────────────────────────
        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Vertical

            handle: Item {
                id: grip
                implicitHeight: 8

                Rectangle {
                    anchors.centerIn: parent
                    width: 40
                    height: 4
                    radius: 2
                    color: "#B8BECC"
                    opacity: grip.SplitHandle.hovered || grip.SplitHandle.pressed ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                }
            }

            ScrollView {
                id: stepperScroll
                SplitView.preferredHeight: stepperCard.implicitHeight
                SplitView.minimumHeight: 140
                contentWidth: availableWidth
                contentHeight: stepperCard.implicitHeight
                clip: true

                Card {
                    id: stepperCard
                    width: stepperScroll.availableWidth
                    height: implicitHeight
                    implicitHeight: stepper.implicitHeight + 28
                    enabled: !ui.controlsLocked

                    ColumnLayout {
                        id: stepper
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        anchors.topMargin: 14
                        spacing: 0

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: false
                            Layout.bottomMargin: 14
                            spacing: 8

                            SectionTitle { text: "执行流程" }
                            Item { Layout.fillWidth: true }
                            Segmented {
                                segmentWidth: 54
                                options: [{ label: "单步", value: "step" }, { label: "阶段", value: "stage" },
                                          { label: "连续", value: "continuous" }]
                                value: ui.executionMode
                                tip: "单步：完成一个动作后暂停；阶段：完成当前阶段后停止；连续：衔接后续阶段"
                                onChosen: (value) => backend.setExecutionMode(value)
                            }
                            AppButton {
                                kind: "soft"
                                glyph: ""
                                text: "接管导航"
                                tip: "检测游戏窗口并自动推进游戏菜单与模式步骤"
                                onClicked: backend.takeoverNavigation()
                            }
                            AppButton {
                                glyph: ""
                                text: "重置状态"
                                tip: "重置所有步骤状态为待命"
                                onClicked: backend.resetStates()
                            }
                        }

                        Stage {
                            first: true
                            title: "阶段一"
                            subtitle: "游戏内自动导航"
                            stageState: ui.stages[0]

                            Repeater {
                                model: ui.navPills.length

                                Step {
                                    arrow: index > 0
                                    label: ui.navPills[index].text
                                    stepState: ui.navPills[index].state
                                    tip: ui.navPills[index].tooltip
                                    onActivated: backend.jumpToStep(index)
                                }
                            }
                        }

                        Stage {
                            title: "阶段二"
                            subtitle: "隔离 Pak 补丁文件"
                            stageState: ui.stages[1]

                            Repeater {
                                model: ["rename_pak", "open_paks"]

                                Step {
                                    arrow: false
                                    label: ui.steps[modelData].text
                                    stepState: ui.steps[modelData].state
                                    tip: ui.steps[modelData].tooltip
                                    onActivated: backend.runStep(modelData)
                                }
                            }
                        }

                        Stage {
                            title: "阶段三"
                            subtitle: "WeGame 修复重置与拉起"
                            stageState: ui.stages[2]

                            Repeater {
                                model: ["wait_wegame", "click_more", "assets_manage", "delete_map", "restart_game"]

                                Step {
                                    arrow: index > 0
                                    label: ui.steps[modelData].text
                                    stepState: ui.steps[modelData].state
                                    tip: ui.steps[modelData].tooltip
                                    onActivated: backend.runStep(modelData)
                                }
                            }
                        }

                        Stage {
                            last: true
                            title: "阶段四"
                            subtitle: "重返大厅与恢复地图"
                            stageState: ui.stages[3]

                            Repeater {
                                model: ["detect_result", "restore_pak", "redownload_map", "warehouse"]

                                Step {
                                    visible: modelData !== "warehouse" || window.semiAuto
                                    arrow: index > 0
                                    label: ui.steps[modelData].text
                                    stepState: ui.steps[modelData].state
                                    tip: ui.steps[modelData].tooltip
                                    onActivated: backend.runStep(modelData)
                                }
                            }
                            Repeater {
                                model: ["自定义配装", "等待地图恢复", "切换模式重连", "游戏内自杀并退出", "循环至第一阶段"]

                                Step {
                                    visible: !window.semiAuto
                                    placeholder: true
                                    label: (index + 4) + "." + modelData
                                    tip: "全自动模式占位，尚未实现"
                                }
                            }
                        }
                    }
                }
            }

            Card {
                SplitView.fillHeight: true
                SplitView.minimumHeight: 150

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    anchors.topMargin: 12
                    anchors.bottomMargin: 14
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: false
                        spacing: 6

                        SectionTitle { text: "运行日志" }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            glyph: ""
                            text: "复制"
                            tip: "复制当前所有运行日志"
                            implicitHeight: 30
                            onClicked: backend.copyLog()
                        }
                        AppButton {
                            glyph: ""
                            text: "清空"
                            tip: "清空当前显示的日志"
                            implicitHeight: 30
                            onClicked: backend.clearLog()
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Theme.radius
                        color: Theme.logSurface

                        ScrollView {
                            id: logScroll
                            anchors.fill: parent
                            anchors.margins: 4
                            clip: true

                            TextArea {
                                id: logText
                                readOnly: true
                                selectByMouse: true
                                textFormat: TextEdit.RichText
                                wrapMode: TextEdit.Wrap
                                padding: 8
                                color: "#E2E8F0"
                                selectionColor: "#3B5B9A"
                                selectedTextColor: "#FFFFFF"
                                font: ui.logFont
                                ContextMenu.menu: TextMenu { target: logText }
                                background: null
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Toast ────────────────────────────────────────────────────────────
    Rectangle {
        id: toast

        property string kind: "info"

        z: 10
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        width: toastText.width + 32
        height: toastText.implicitHeight + 20
        radius: Theme.radius
        color: kind === "error" ? "#B91C1C" : "#263043"
        opacity: 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 180 } }

        Text {
            id: toastText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, window.width - 112)
            color: "#FFFFFF"
            wrapMode: Text.WrapAnywhere
        }
        Timer {
            id: toastTimer
            interval: 4000
            onTriggered: toast.opacity = 0
        }
    }

    Connections {
        target: backend

        function onLogAppended(html) {
            const flickable = logScroll.contentItem
            const follow = logText.selectedText === ""
                && flickable.contentY >= flickable.contentHeight - flickable.height - 12
            logText.append(html)
            if (follow)
                Qt.callLater(window.scrollLogToEnd)
        }
        function onLogReset(html) {
            logText.text = html
            Qt.callLater(window.scrollLogToEnd)
        }
        function onToast(message, kind) {
            toastText.text = message
            toast.kind = kind
            toast.opacity = 1
            toastTimer.restart()
        }
    }

    // ── About and updates ────────────────────────────────────────────────
    Sheet {
        id: aboutDialog
        objectName: "aboutDialog"
        width: 440

        contentItem: ColumnLayout {
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: false
                spacing: 12

                Image {
                    Layout.preferredWidth: 48
                    Layout.preferredHeight: 48
                    source: ui.iconUrl
                    sourceSize: Qt.size(96, 96)
                }
                ColumnLayout {
                    Layout.fillWidth: false
                    spacing: 2

                    Text {
                        text: "dfAmmo"
                        color: Theme.text
                        font.pixelSize: 22
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: "版本 " + ui.appVersion + "  ·  " + ui.runtime
                        color: Theme.textMuted
                    }
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    Layout.alignment: Qt.AlignTop
                    kind: "ghost"
                    glyph: ""
                    implicitWidth: 28
                    implicitHeight: 28
                    onClicked: aboutDialog.close()
                }
            }

            Text {
                text: '<a href="' + ui.repoUrl + '" style="color:#0B57D0;text-decoration:none;">GitHub 项目主页</a>'
                textFormat: Text.RichText
                onLinkActivated: (link) => Qt.openUrlExternally(link)

                HoverHandler {
                    cursorShape: parent.hoveredLink !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: false
                spacing: 12

                Text {
                    text: "更新渠道"
                    color: Theme.textSecondary
                }
                Segmented {
                    enabled: ui.canCheckUpdate
                    segmentWidth: 72
                    options: [{ label: "正式版", value: "stable" }, { label: "测试版", value: "beta" }]
                    value: ui.updateChannel
                    onChosen: (value) => backend.setUpdateChannel(value)
                }
                Item { Layout.fillWidth: true }
            }

            Check {
                text: "启动时检查更新"
                checked: ui.checkOnStartup
                onToggled: {
                    backend.setCheckOnStartup(checked)
                    checked = Qt.binding(() => ui.checkOnStartup)
                }
            }
            Check {
                text: "自动安装更新（任务空闲时）"
                checked: ui.autoUpdate
                onToggled: {
                    backend.setAutoUpdate(checked)
                    checked = Qt.binding(() => ui.autoUpdate)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: false
                Layout.topMargin: 4
                spacing: 8

                AppButton {
                    Layout.fillWidth: true
                    text: "检查更新"
                    enabled: ui.canCheckUpdate
                    onClicked: backend.checkUpdates()
                }
                AppButton {
                    Layout.fillWidth: true
                    kind: "soft"
                    text: "更新并重启"
                    enabled: ui.canInstallUpdate
                    onClicked: backend.installUpdate()
                }
                AppButton {
                    Layout.fillWidth: true
                    text: "取消更新"
                    enabled: ui.canCancelUpdate
                    onClicked: backend.cancelUpdate()
                }
            }
        }
    }

    // ── Template capture ─────────────────────────────────────────────────
    Sheet {
        id: captureDialog
        width: 420
        onOpened: {
            captureName.text = ""
            captureName.forceActiveFocus()
        }

        function confirm() {
            if (captureName.text.trim() === "")
                return
            close()
            backend.startTemplateCapture(captureName.text)
        }

        contentItem: ColumnLayout {
            spacing: 12

            SectionTitle { text: "采集模板" }
            Text {
                Layout.fillWidth: true
                text: "输入模板名称（不含 .png），然后框选目标区域；框选时按 Esc 取消。同名模板会被覆盖。"
                color: Theme.textMuted
                wrapMode: Text.Wrap
            }
            Field {
                id: captureName
                Layout.fillWidth: true
                placeholderText: "例如 wegame_start_button"
                onAccepted: captureDialog.confirm()
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: false
                Layout.topMargin: 4
                spacing: 8

                Item { Layout.fillWidth: true }
                AppButton {
                    text: "取消"
                    onClicked: captureDialog.close()
                }
                AppButton {
                    kind: "soft"
                    glyph: ""
                    text: "开始框选"
                    enabled: captureName.text.trim() !== ""
                    onClicked: captureDialog.confirm()
                }
            }
        }
    }
}
