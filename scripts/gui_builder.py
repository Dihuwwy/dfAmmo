from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from scripts.bind_button import BindButton
from scripts.game_navigation import NAVIGATION_STEPS
from scripts.flow_layout import FlowLayout
from scripts.styles import MAIN_WINDOW_STYLE
from scripts.md3_widgets import CompactComboBox, Timeline, apply_md_shadow, set_md_icon


class BuilderMixin:
    """UI construction mixin for MainWindow."""

    @staticmethod
    def _make_divider() -> QFrame:
        div = QFrame()
        div.setProperty("class", "divider")
        return div

    @staticmethod
    def _create_step_section(
        dot_char: str,
        title: str,
        subtitle: str,
        btn_text: str = "",
        btn_tooltip: str = "",
        btn_slot: Any = None,
    ) -> tuple[QWidget, QHBoxLayout, QLabel, QPushButton | None]:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        dot = QLabel()
        dot.setFixedSize(12, 12)
        dot.setProperty("class", "stepDot")
        dot.setProperty("state", "idle")

        text_vbox = QVBoxLayout()
        text_vbox.setSpacing(1)
        t_lbl = QLabel(title)
        t_lbl.setProperty("class", "stepTitle")
        sub_lbl = QLabel(subtitle)
        sub_lbl.setProperty("class", "stepSubtitle")
        text_vbox.addWidget(t_lbl)
        text_vbox.addWidget(sub_lbl)

        header.addWidget(dot, alignment=Qt.AlignVCenter)
        header.addLayout(text_vbox, stretch=1)

        btn = None
        if btn_text:
            btn = QPushButton(btn_text)
            btn.setProperty("class", "stepBtn")
            btn.setProperty("stepState", "idle")
            if btn_tooltip:
                btn.setToolTip(btn_tooltip)
            if btn_slot:
                btn.clicked.connect(btn_slot)
            header.addWidget(btn, alignment=Qt.AlignVCenter)

        vbox.addLayout(header)
        return w, header, dot, btn

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ── 1. Connection Toolbar ─────────────────────────────────────────────
        self.bind_panel = self._build_connection_bar()
        self.feature_panel = self._build_settings_card()
        self.header_panel = QWidget()
        self.header_layout = QBoxLayout(QBoxLayout.LeftToRight, self.header_panel)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(8)
        self.header_layout.addWidget(self.bind_panel, 1)
        self.header_layout.addWidget(self.feature_panel, 2)
        root.addWidget(self.header_panel)

        # ── 2. Main Vertical Splitter ─────────────────────────────────────────
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setObjectName("mainSplitter")

        # 2.1 Top Controls (Scrollable)
        self.left_scroll = QScrollArea()
        self.left_scroll.setObjectName("leftScrollArea")
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.left_column = QWidget()
        self.left_column.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        left_layout = QVBoxLayout(self.left_column)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(8)

        self.action_panel = self._build_action_bar()
        self.debug_panel = self._build_stepper_card()
        left_layout.addWidget(self.action_panel)
        left_layout.addWidget(self.debug_panel)
        left_layout.addStretch(1)

        self.left_scroll.setWidget(self.left_column)

        # 2.2 Bottom Log Panel
        self.log_panel = self._build_log_panel()

        # Splitter Assembly
        self.main_splitter.addWidget(self.left_scroll)
        self.main_splitter.addWidget(self.log_panel)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.left_scroll.setMinimumHeight(280)
        self.log_panel.setMinimumHeight(160)

        root.addWidget(self.main_splitter, stretch=1)
        for card in (self.bind_panel, self.feature_panel, self.debug_panel, self.log_panel):
            apply_md_shadow(card)
        icons = (
            (self.start_card_mail_button, "play", "#FFFFFF", QStyle.SP_MediaPlay),
            (self.pause_resume_button, "fast-forward-outline", "#44474E", QStyle.SP_MediaSkipForward),
            (self.stop_button, "stop-circle-outline", "#DC2626", QStyle.SP_MediaStop),
            (self.bind_button, "crosshairs-gps", "#0B57D0", QStyle.SP_TitleBarShadeButton),
            (self.about_button, "information-outline", "#64748B", QStyle.SP_FileDialogInfoView),
            (self.capture_button, "camera-iris", "#44474E", QStyle.SP_DesktopIcon),
            (self.dbg_nav_start_btn, "compass-outline", "#0B57D0", QStyle.SP_ArrowForward),
            (self.reset_status_btn, "refresh", "#44474E", QStyle.SP_BrowserReload),
            (self.copy_log_btn, "content-copy", "#44474E", QStyle.SP_FileIcon),
            (self.clear_log_btn, "trash-can-outline", "#44474E", QStyle.SP_TrashIcon),
        )
        for button, name, color, fallback in icons:
            set_md_icon(button, name, color, fallback)
        self.setStyleSheet(MAIN_WINDOW_STYLE)
        self._sync_pak_button_state()
        self._sync_operation_mode_controls()

    def _build_connection_bar(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("connectionBar")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        self.conn_dot = QLabel("●")
        self.conn_dot.setObjectName("connDot")
        self.conn_dot.setProperty("connected", "false")

        conn_title = QLabel("WeGame 客户端")
        conn_title.setObjectName("connStatusLabel")

        self.conn_badge = QLabel("未连接")
        self.conn_badge.setObjectName("connBadge")
        self.conn_badge.setProperty("connected", "false")
        self.conn_badge.setProperty("status", "disconnected")

        title_row.addWidget(self.conn_dot)
        title_row.addWidget(conn_title)
        title_row.addWidget(self.conn_badge)
        title_row.addStretch(1)

        self.conn_detail_label = QLabel("未绑定窗口")
        self.conn_detail_label.setObjectName("connDetail")
        self.conn_detail_label.setWordWrap(True)
        self.conn_detail_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        info_box.addLayout(title_row)
        info_box.addWidget(self.conn_detail_label)

        self.bind_button = BindButton()
        self.bind_button.setProperty("md3_type", "dashed")
        self.bind_button.released_at.connect(self.bind_window_at)

        layout.addLayout(info_box)
        layout.addStretch(1)
        layout.addWidget(self.bind_button)
        self.about_button = QPushButton()
        self.about_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.about_button.setFixedSize(24, 24)
        self.about_button.setToolTip("关于 / 更新")
        self.about_button.setAccessibleName("关于 / 更新")
        self.about_button.setObjectName("aboutButton")
        self.about_button.setStyleSheet("padding: 0;")
        self.about_button.clicked.connect(self.show_about)
        return panel

    def _build_settings_card(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settingsCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        title = QLabel("设置")
        title.setObjectName("sectionTitle")
        settings_header = QHBoxLayout()
        settings_header.addWidget(title)
        settings_header.addStretch(1)
        settings_header.addWidget(self.about_button)

        # Install dir row
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_label = QLabel("游戏安装目录：")
        dir_label.setObjectName("fieldLabel")
        dir_label.setFixedWidth(92)
        self.game_dir_input = QLineEdit()
        self.game_dir_input.setPlaceholderText("请选择包含 DeltaForce 文件夹的安装目录")
        self.game_dir_input.setText(self.config.game_install_dir)
        self.game_dir_input.editingFinished.connect(self._save_game_dir)
        self.game_dir_button = QPushButton("浏览...")
        self.game_dir_button.setObjectName("secondaryButton")
        self.game_dir_button.setFixedWidth(68)
        self.game_dir_button.clicked.connect(self._choose_game_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self.game_dir_input, stretch=1)
        dir_row.addWidget(self.game_dir_button)

        # Mode row
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_label = QLabel("运行模式：")
        mode_label.setObjectName("fieldLabel")
        mode_label.setFixedWidth(92)
        self.semi_auto_radio = QPushButton("半自动")
        self.full_auto_radio = QPushButton("全自动")
        for button in (self.semi_auto_radio, self.full_auto_radio):
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setProperty("md3_type", "segment")
            button.setFixedSize(88, 32)
        segmented = QFrame()
        segmented.setProperty("md3_type", "segmented_container")
        segments = QHBoxLayout(segmented)
        segments.setContentsMargins(3, 3, 3, 3)
        segments.setSpacing(2)
        segments.addWidget(self.semi_auto_radio)
        segments.addWidget(self.full_auto_radio)
        if self.config.operation_mode == "full_auto":
            self.full_auto_radio.setChecked(True)
        else:
            self.semi_auto_radio.setChecked(True)
        self.semi_auto_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(segmented)
        mode_row.addStretch(1)

        layout.addLayout(settings_header)
        layout.addLayout(dir_row)
        layout.addLayout(mode_row)
        layout.addStretch(1)
        return panel

    def _build_action_bar(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        self.start_card_mail_button = QPushButton("开始卡邮件")
        self.start_card_mail_button.setObjectName("startCardMailBtn")
        self.start_card_mail_button.setProperty("md3_type", "filled")
        self.start_card_mail_button.clicked.connect(self.start_card_mail)

        self.pause_resume_button = QPushButton("继续")
        self.pause_resume_button.setToolTip("继续执行 (Ctrl+F12)")
        self.pause_resume_button.setObjectName("pauseButton")
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.clicked.connect(self.continue_navigation)

        self.stop_button = QPushButton("停止")
        self.stop_button.setToolTip("停止任务 (Shift+F12)")
        self.stop_button.setProperty("md3_type", "danger_outlined")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.emergency_stop)

        self.capture_button = QPushButton("采集模板")
        self.capture_button.setObjectName("secondaryButton")
        self.capture_button.clicked.connect(self.start_template_capture)

        self.workflow_status_badge = QLabel("● 待命就绪")
        self.workflow_status_badge.setProperty("md3_type", "badge")
        self.workflow_status_badge.setWordWrap(True)
        self.workflow_status_badge.setObjectName("workflowStatusBadge")
        self.workflow_status_badge.setProperty("state", "idle")
        self.workflow_status_badge.setFixedWidth(220)
        self.workflow_status_badge.setAlignment(Qt.AlignCenter)

        for btn in (
            self.start_card_mail_button,
            self.pause_resume_button,
            self.stop_button,
        ):
            action_bar.addWidget(btn)
        action_bar.addStretch(1)
        action_bar.addWidget(self.capture_button)
        action_bar.addWidget(self.workflow_status_badge)

        layout.addLayout(action_bar)
        return panel

    def _build_stepper_card(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("stepperCard")
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("执行流程与单步调试")
        title.setObjectName("sectionTitle")

        self.step_mode_toggle = CompactComboBox()
        self.step_mode_toggle.setObjectName("stepModeToggle")
        for label, mode in (("单步", "step"), ("阶段", "stage"), ("连续", "continuous")):
            self.step_mode_toggle.addItem(label, mode)
        self.step_mode_toggle.setCurrentIndex(self.step_mode_toggle.findData("continuous"))
        self.step_mode_toggle.setToolTip("单步：完成一个动作后暂停；阶段：完成当前阶段后停止；连续：衔接后续阶段")
        self.step_mode_toggle.currentIndexChanged.connect(self._on_step_mode_toggled)

        self.reset_status_btn = QPushButton("重置状态")
        self.reset_status_btn.setObjectName("resetStatusBtn")
        self.reset_status_btn.setToolTip("重置所有步骤状态为待命")
        self.reset_status_btn.clicked.connect(self.reset_all_step_states)

        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.step_mode_toggle)
        header.addWidget(self.reset_status_btn)
        outer.addLayout(header)

        self.debug_body = Timeline()
        body_layout = QVBoxLayout(self.debug_body)
        body_layout.setContentsMargins(0, 2, 0, 2)
        body_layout.setSpacing(10)

        # ── Step 1: In-game Navigation ──
        s1_w, _, self.step1_dot, self.dbg_nav_start_btn = self._create_step_section(
            dot_char="●",
            title="阶段一",
            subtitle="游戏内自动导航",
            btn_text="接管导航",
            btn_tooltip="检测游戏窗口并自动推进游戏菜单与模式步骤",
            btn_slot=self._dbg_takeover_navigation,
        )
        s1_vbox = s1_w.layout()

        pills_row = FlowLayout()
        pills_row.setSpacing(6)
        pills_row.setContentsMargins(18, 0, 0, 0)
        self.sub_step_names = [
            "1.模式", "2.进大厅", "3.选地图", "4.选长弓", "5.行动",
            "6.配装", "7.继续", "8.出发", "9.选人",
        ]
        self.sub_step_pills = []
        for idx, sname in enumerate(self.sub_step_names):
            pill = QPushButton(sname)
            pill.setProperty("class", "stepBtn")
            pill.setProperty("pillState", "")
            pill.setCursor(Qt.PointingHandCursor)
            step_desc = NAVIGATION_STEPS[idx].name if idx < len(NAVIGATION_STEPS) else sname
            pill.setToolTip(f"点击直接跳转至第 {idx + 1} 步执行：【{step_desc}】")
            pill.clicked.connect(lambda chk=False, i=idx: self._on_step_pill_clicked(i))
            self.sub_step_pills.append(pill)
            self._add_step_pill(pills_row, pill)
        s1_vbox.addLayout(pills_row)
        body_layout.addWidget(s1_w)
        body_layout.addWidget(self._make_divider())

        # ── Step 2: Pak File Isolation ──
        s2_w, s2_header, self.step2_dot, self.dbg_rename_pak_btn = self._create_step_section(
            dot_char="○",
            title="阶段二",
            subtitle="隔离 Pak 补丁文件",
            btn_text="屏蔽 Pak",
            btn_tooltip="重命名长弓溪谷 Pak 文件为 .disabled 状态以屏蔽加载",
            btn_slot=self._dbg_rename_pak,
        )
        self.dbg_open_paks_btn = QPushButton("浏览 Paks 目录")
        self.dbg_open_paks_btn.setProperty("class", "stepAuxBtn")
        self.dbg_open_paks_btn.setToolTip("在资源管理器中打开 Paks 补丁文件夹")
        self.dbg_open_paks_btn.clicked.connect(self._dbg_open_paks)
        s2_header.addWidget(self.dbg_open_paks_btn, alignment=Qt.AlignVCenter)
        body_layout.addWidget(s2_w)
        body_layout.addWidget(self._make_divider())

        # ── Step 3: WeGame Post-process & Restart ──
        s3_w, _, self.step3_dot, _ = self._create_step_section(
            dot_char="○",
            title="阶段三",
            subtitle="WeGame 修复重置与拉起",
        )
        s3_vbox = s3_w.layout()

        sec3_row = FlowLayout()
        sec3_row.setContentsMargins(18, 0, 0, 0)

        step3_btns_def = [
            ("dbg_wait_wegame_btn", "等待启动按钮", "等待 WeGame 客户端回到启动按钮可用状态", self._dbg_wait_wegame),
            ("dbg_more_btn", "选项菜单 (...)", "点击 WeGame 游戏主页右侧的更多操作 (...) 按钮", self._dbg_click_more),
            ("dbg_assets_btn", "资源包管理", "点击弹出菜单中的“游戏资源包管理”项", self._dbg_assets_manage),
            ("dbg_delete_btn", "删除长弓溪谷", "在资源管理窗口中自动滚动并点击删除长弓溪谷地图资源", self._dbg_delete_changgong),
            ("dbg_restart_btn", "重新启动游戏", "在 WeGame 中点击启动按钮重新拉起三角洲行动", self._dbg_restart_game),
        ]
        for attr_name, text, tip, slot in step3_btns_def:
            btn = QPushButton(text)
            btn.setProperty("class", "stepBtn")
            btn.setProperty("stepState", "idle")
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            setattr(self, attr_name, btn)
            self._add_step_pill(sec3_row, btn)
        s3_vbox.addLayout(sec3_row)
        self.stage_three_actions = sec3_row
        body_layout.addWidget(s3_w)
        body_layout.addWidget(self._make_divider())
        s4_w, _, self.step4_dot, _ = self._create_step_section(
            dot_char="○", title="阶段四",
            subtitle="重返大厅与恢复地图",
        )
        s4_row = FlowLayout()
        s4_row.setContentsMargins(18, 0, 0, 0)
        for attr_name, text, slot in (
            ("dbg_result_btn", "确认并进大厅", self._dbg_stage_four_detect),
            ("dbg_restore_pak_btn", "恢复 Pak", self._dbg_stage_four),
            ("dbg_redownload_btn", "恢复地图下载", self._dbg_stage_four_redownload),
            ("dbg_warehouse_btn", "进入仓库并确认", self._dbg_stage_four_warehouse),
        ):
            btn = QPushButton(text)
            btn.setProperty("class", "stepBtn")
            btn.setProperty("stepState", "idle")
            btn.clicked.connect(slot)
            setattr(self, attr_name, btn)
            self._add_step_pill(s4_row, btn)
        s4_w.layout().addLayout(s4_row)
        self.stage_four_actions = s4_row

        self.full_auto_placeholder_buttons = []
        for number, command in enumerate(("自定义配装", "等待地图恢复", "切换模式重连",
                                          "游戏内自杀并退出", "循环至第一阶段"), start=4):
            button = QPushButton(f"{number}.{command}")
            button.setProperty("class", "stepBtn")
            button.setProperty("placeholder", "true")
            button.setToolTip("全自动模式占位，尚未实现")
            button.setEnabled(False)
            self.full_auto_placeholder_buttons.append(button)
            self._add_step_pill(s4_row, button)
        body_layout.addWidget(s4_w)
        self.debug_body.dots = (self.step1_dot, self.step2_dot, self.step3_dot, self.step4_dot)

        outer.addWidget(self.debug_body)

        # Mapping for step status updates
        self._step_buttons = {
            "nav_game": {"button": self.dbg_nav_start_btn, "base_text": "接管导航", "title": "接管导航"},
            "rename_pak": {"button": self.dbg_rename_pak_btn, "base_text": "屏蔽 Pak", "title": "屏蔽 Pak"},
            "open_paks": {"button": self.dbg_open_paks_btn, "base_text": "浏览 Paks 目录", "title": "打开 Paks 目录"},
            "wait_wegame": {"button": self.dbg_wait_wegame_btn, "base_text": "等待启动按钮", "title": "等待启动按钮"},
            "click_more": {"button": self.dbg_more_btn, "base_text": "选项菜单 (...)", "title": "选项菜单"},
            "assets_manage": {"button": self.dbg_assets_btn, "base_text": "资源包管理", "title": "资源包管理"},
            "delete_map": {"button": self.dbg_delete_btn, "base_text": "删除长弓溪谷", "title": "删除长弓溪谷"},
            "restart_game": {"button": self.dbg_restart_btn, "base_text": "重新启动游戏", "title": "重新启动游戏"},
            "restore_pak": {"button": self.dbg_restore_pak_btn, "base_text": "恢复 Pak", "title": "恢复 Pak"},
            "detect_result": {"button": self.dbg_result_btn, "base_text": "确认并进大厅", "title": "确认并进大厅"},
            "redownload_map": {"button": self.dbg_redownload_btn, "base_text": "恢复地图下载", "title": "恢复地图下载"},
            "warehouse": {"button": self.dbg_warehouse_btn, "base_text": "进入仓库并确认", "title": "进入仓库并确认"},
        }
        for step_ids in (("wait_wegame", "click_more", "assets_manage", "delete_map", "restart_game"),
                         ("detect_result", "restore_pak", "redownload_map", "warehouse")):
            for number, step_id in enumerate(step_ids, start=1):
                info = self._step_buttons[step_id]
                info["number"] = number
                info["base_text"] = f"{number}.{info['base_text']}"
                info["button"].setText(info["base_text"])
        return panel

    def _build_log_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("logPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("运行日志")
        title.setObjectName("sectionTitle")

        self.copy_log_btn = QPushButton("复制")
        self.copy_log_btn.setObjectName("copyLogBtn")
        self.copy_log_btn.setToolTip("复制当前所有运行日志")
        self.copy_log_btn.clicked.connect(self.copy_log)

        self.clear_log_btn = QPushButton("清空")
        self.clear_log_btn.setObjectName("clearLogBtn")
        self.clear_log_btn.setToolTip("清空当前显示的日志")
        self.clear_log_btn.clicked.connect(self.clear_log)

        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.copy_log_btn)
        header.addWidget(self.clear_log_btn)

        self.log_output = QTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_output.setMinimumHeight(120)
        self.log_output.document().setMaximumBlockCount(800)
        self.log_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        layout.addLayout(header)
        layout.addWidget(self.log_output)

        self._log_buffer: list[str] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(150)
        self._log_flush_timer.timeout.connect(self._flush_log_buffer)
        self._log_flush_timer.start()
        return panel

    @staticmethod
    def _add_step_pill(layout, button):
        button.setProperty("md3_type", "step_pill")
        button.setProperty("step_state", "pending")
        group = QWidget()
        row = QHBoxLayout(group)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        if layout.count():
            arrow = QLabel("›")
            arrow.setObjectName("stepArrow")
            row.addWidget(arrow)
        row.addWidget(button)
        button.step_group = group
        layout.addWidget(group)
