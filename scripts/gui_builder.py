from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from scripts.bind_button import BindButton
from scripts.game_navigation import NAVIGATION_STEPS
from scripts.styles import MAIN_WINDOW_STYLE


class BuilderMixin:
    """UI construction mixin for MainWindow."""

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ── 1. Connection Toolbar ─────────────────────────────────────────────
        self.bind_panel = QFrame()
        self.bind_panel.setObjectName("connectionBar")
        bind_layout = QHBoxLayout(self.bind_panel)
        bind_layout.setContentsMargins(14, 8, 14, 8)
        bind_layout.setSpacing(10)

        conn_info_box = QVBoxLayout()
        conn_info_box.setSpacing(2)

        conn_title_row = QHBoxLayout()
        conn_title_row.setSpacing(6)

        self.conn_dot = QLabel("●")
        self.conn_dot.setObjectName("connDot")
        self.conn_dot.setProperty("connected", "false")

        conn_title = QLabel("WeGame 客户端")
        conn_title.setObjectName("connStatusLabel")

        self.conn_badge = QLabel("未连接")
        self.conn_badge.setObjectName("connBadge")
        self.conn_badge.setProperty("connected", "false")

        conn_title_row.addWidget(self.conn_dot)
        conn_title_row.addWidget(conn_title)
        conn_title_row.addWidget(self.conn_badge)
        conn_title_row.addStretch(1)

        self.conn_detail_label = QLabel(
            "请按住右侧按钮拖动到 WeGame 主窗口后松开（如游戏已运行可直接卡邮件）"
        )
        self.conn_detail_label.setObjectName("connDetail")

        conn_info_box.addLayout(conn_title_row)
        conn_info_box.addWidget(self.conn_detail_label)

        self.bind_button = BindButton()
        self.bind_button.released_at.connect(self.bind_window_at)

        bind_layout.addLayout(conn_info_box, stretch=1)
        bind_layout.addWidget(self.bind_button)

        root.addWidget(self.bind_panel)

        # Compatibility placeholder for subtitle
        self.subtitle = QLabel("WeGame 辅助就绪")
        self.subtitle.hide()

        # ── 2. QSplitter: Top (Controls & Stepper) + Bottom (Log Panel) ───────
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setObjectName("mainSplitter")

        # Left Scroll Area
        self.left_scroll = QScrollArea()
        self.left_scroll.setObjectName("leftScrollArea")
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.left_column = QWidget()
        # MinimumExpanding: content sets min size; when scroll area viewport is taller,
        # the widget is expanded so stretch factors in left_layout take effect.
        self.left_column.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        left_layout = QVBoxLayout(self.left_column)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(8)

        # ── 2.1 Game Settings Card ───────────────────────────────────────────
        self.feature_panel = QFrame()
        self.feature_panel.setObjectName("settingsCard")
        settings_layout = QVBoxLayout(self.feature_panel)
        settings_layout.setContentsMargins(14, 10, 14, 10)
        settings_layout.setSpacing(8)

        settings_title = QLabel("游戏设置")
        settings_title.setObjectName("sectionTitle")
        self.window_info = QLabel("")
        self.window_info.hide()

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_label = QLabel("安装目录：")
        dir_label.setObjectName("fieldLabel")
        dir_label.setFixedWidth(64)
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

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_label = QLabel("运行模式：")
        mode_label.setObjectName("fieldLabel")
        mode_label.setFixedWidth(64)
        self.semi_auto_radio = QRadioButton("半自动模式 (手动购入穿戴)")
        self.full_auto_radio = QRadioButton("全自动模式 (配装方案一键买齐)")
        current_mode = getattr(self.config, "operation_mode", "semi_auto")
        if current_mode == "full_auto":
            self.full_auto_radio.setChecked(True)
        else:
            self.semi_auto_radio.setChecked(True)
        self.semi_auto_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.semi_auto_radio)
        mode_row.addWidget(self.full_auto_radio)
        mode_row.addStretch(1)

        settings_layout.addWidget(settings_title)
        settings_layout.addWidget(self.window_info)
        settings_layout.addLayout(dir_row)
        settings_layout.addLayout(mode_row)

        # ── 2.2 Primary Actions & Controls Row ───────────────────────────────
        div_settings = QFrame()
        div_settings.setProperty("class", "divider")
        settings_layout.addWidget(div_settings)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        self.start_card_mail_button = QPushButton("开始卡邮件")
        self.start_card_mail_button.setObjectName("startCardMailBtn")
        self.start_card_mail_button.clicked.connect(self.start_card_mail)

        self.pause_resume_button = QPushButton("暂停 (F12)")
        self.pause_resume_button.setObjectName("pauseButton")
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.clicked.connect(self.toggle_pause_resume)

        self.stop_button = QPushButton("停止 (Shift+F12)")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.emergency_stop)

        self.resync_button = QPushButton("重同步")
        self.resync_button.setObjectName("secondaryButton")
        self.resync_button.setEnabled(False)
        self.resync_button.clicked.connect(self.manual_resync)

        self.capture_button = QPushButton("采集模板")
        self.capture_button.setObjectName("secondaryButton")
        self.capture_button.clicked.connect(self.start_template_capture)

        self.rebind_button = QPushButton("重新绑定")
        self.rebind_button.setObjectName("secondaryButton")
        self.rebind_button.clicked.connect(self.reset_binding)

        self.workflow_status_badge = QLabel("待命就绪")
        self.workflow_status_badge.setObjectName("workflowStatusBadge")
        self.workflow_status_badge.setProperty("state", "idle")
        self.workflow_status_badge.setMaximumWidth(200)
        self.workflow_status_badge.setAlignment(Qt.AlignCenter)

        action_bar.addWidget(self.start_card_mail_button)
        action_bar.addWidget(self.pause_resume_button)
        action_bar.addWidget(self.stop_button)
        action_bar.addWidget(self.resync_button)
        action_bar.addWidget(self.capture_button)
        action_bar.addWidget(self.rebind_button)
        action_bar.addStretch(1)
        action_bar.addWidget(self.workflow_status_badge)

        settings_layout.addLayout(action_bar)
        left_layout.addWidget(self.feature_panel)

        # ── 2.3 Stepper Panel (Workflow & Step Triggers) ──────────────────────
        self.debug_panel = QFrame()
        self.debug_panel.setObjectName("stepperCard")
        self.debug_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        debug_outer = QVBoxLayout(self.debug_panel)
        debug_outer.setContentsMargins(14, 12, 14, 12)
        debug_outer.setSpacing(10)

        # Stepper Header
        debug_header = QHBoxLayout()
        debug_title = QLabel("执行流程与单步调试")
        debug_title.setObjectName("sectionTitle")

        self.step_mode_toggle = QPushButton("单步")
        self.step_mode_toggle.setObjectName("stepModeToggle")
        self.step_mode_toggle.setCheckable(True)
        self.step_mode_toggle.setChecked(False)
        self.step_mode_toggle.setFixedWidth(54)
        self.step_mode_toggle.setToolTip("当前：单步模式（点击只执行该步骤）\n点击切换为连续模式（从该步骤继续往后执行）")
        self.step_mode_toggle.clicked.connect(self._on_step_mode_toggled)

        self.reset_status_btn = QPushButton("重置状态")
        self.reset_status_btn.setObjectName("resetStatusBtn")
        self.reset_status_btn.setToolTip("重置所有步骤状态为待命")
        self.reset_status_btn.clicked.connect(self.reset_all_step_states)

        debug_header.addWidget(debug_title)
        debug_header.addStretch(1)
        debug_header.addWidget(self.step_mode_toggle)
        debug_header.addWidget(self.reset_status_btn)
        debug_outer.addLayout(debug_header)

        self.debug_body = QWidget()
        debug_body_layout = QVBoxLayout(self.debug_body)
        debug_body_layout.setContentsMargins(0, 2, 0, 2)
        debug_body_layout.setSpacing(10)

        # ── Step 1: In-game Navigation ────────────────────────
        step1_widget = QWidget()
        step1_vbox = QVBoxLayout(step1_widget)
        step1_vbox.setContentsMargins(0, 0, 0, 0)
        step1_vbox.setSpacing(6)

        step1_header = QHBoxLayout()
        step1_header.setSpacing(8)

        self.step1_dot = QLabel("●")
        self.step1_dot.setProperty("class", "stepDot")
        self.step1_dot.setProperty("state", "idle")

        s1_text_vbox = QVBoxLayout()
        s1_text_vbox.setSpacing(1)
        s1_title = QLabel("阶段 1 · 游戏内自动导航")
        s1_title.setProperty("class", "stepTitle")
        s1_sub = QLabel("识别游戏画面并逐级推进 9 步菜单与模式流程，选人界面触发时自动退出")
        s1_sub.setProperty("class", "stepSubtitle")
        s1_text_vbox.addWidget(s1_title)
        s1_text_vbox.addWidget(s1_sub)

        self.dbg_nav_start_btn = QPushButton("接管导航")
        self.dbg_nav_start_btn.setProperty("class", "stepBtn")
        self.dbg_nav_start_btn.setProperty("stepState", "idle")
        self.dbg_nav_start_btn.setToolTip("检测游戏窗口并自动推进游戏菜单与模式步骤")
        self.dbg_nav_start_btn.clicked.connect(self._dbg_takeover_navigation)

        step1_header.addWidget(self.step1_dot, alignment=Qt.AlignVCenter)
        step1_header.addLayout(s1_text_vbox, stretch=1)
        step1_header.addWidget(self.dbg_nav_start_btn, alignment=Qt.AlignVCenter)
        step1_vbox.addLayout(step1_header)

        # 9 sub-step pills
        sub_steps_row = QHBoxLayout()
        sub_steps_row.setSpacing(4)
        sub_steps_row.setContentsMargins(18, 0, 0, 0)
        self.sub_step_names = [
            "1.模式",
            "2.进大厅",
            "3.选地图",
            "4.选长弓",
            "5.行动",
            "6.配装",
            "7.继续",
            "8.出发",
            "9.选人",
        ]
        self.sub_step_pills: list[QPushButton] = []
        for idx, sname in enumerate(self.sub_step_names):
            pill = QPushButton(sname)
            pill.setProperty("class", "subStepBtn")
            pill.setProperty("pillState", "")
            pill.setCursor(Qt.PointingHandCursor)
            step_desc = (
                NAVIGATION_STEPS[idx].name if idx < len(NAVIGATION_STEPS) else sname
            )
            pill.setToolTip(f"点击直接跳转至第 {idx + 1} 步执行：【{step_desc}】")
            pill.clicked.connect(
                lambda checked=False, i=idx: self._on_step_pill_clicked(i)
            )
            self.sub_step_pills.append(pill)
            sub_steps_row.addWidget(pill)
        sub_steps_row.addStretch(1)
        step1_vbox.addLayout(sub_steps_row)

        debug_body_layout.addWidget(step1_widget)

        div_step1 = QFrame()
        div_step1.setProperty("class", "divider")
        debug_body_layout.addWidget(div_step1)

        # ── Step 2: Pak File Isolation ────────────────────────
        step2_widget = QWidget()
        step2_vbox = QVBoxLayout(step2_widget)
        step2_vbox.setContentsMargins(0, 0, 0, 0)
        step2_vbox.setSpacing(6)

        step2_header = QHBoxLayout()
        step2_header.setSpacing(8)

        self.step2_dot = QLabel("○")
        self.step2_dot.setProperty("class", "stepDot")
        self.step2_dot.setProperty("state", "idle")

        s2_text_vbox = QVBoxLayout()
        s2_text_vbox.setSpacing(1)
        s2_title = QLabel("阶段 2 · 隔离 Pak 补丁文件")
        s2_title.setProperty("class", "stepTitle")
        s2_sub = QLabel(
            "重命名长弓溪谷 Pak 补丁为 .disabled 状态以屏蔽加载（启动前隔离，重启时生效）"
        )
        s2_sub.setProperty("class", "stepSubtitle")
        s2_text_vbox.addWidget(s2_title)
        s2_text_vbox.addWidget(s2_sub)

        self.dbg_rename_pak_btn = QPushButton("屏蔽 Pak")
        self.dbg_rename_pak_btn.setProperty("class", "stepBtn")
        self.dbg_rename_pak_btn.setProperty("stepState", "idle")
        self.dbg_rename_pak_btn.setToolTip("重命名长弓溪谷 Pak 文件为 .disabled 状态以屏蔽加载")
        self.dbg_rename_pak_btn.clicked.connect(self._dbg_rename_pak)

        self.dbg_open_paks_btn = QPushButton("浏览 Paks 目录")
        self.dbg_open_paks_btn.setProperty("class", "stepAuxBtn")
        self.dbg_open_paks_btn.setToolTip("在资源管理器中打开 Paks 补丁文件夹")
        self.dbg_open_paks_btn.clicked.connect(self._dbg_open_paks)

        step2_header.addWidget(self.step2_dot, alignment=Qt.AlignVCenter)
        step2_header.addLayout(s2_text_vbox, stretch=1)
        step2_header.addWidget(self.dbg_rename_pak_btn, alignment=Qt.AlignVCenter)
        step2_header.addWidget(self.dbg_open_paks_btn, alignment=Qt.AlignVCenter)
        step2_vbox.addLayout(step2_header)

        debug_body_layout.addWidget(step2_widget)

        div_step2 = QFrame()
        div_step2.setProperty("class", "divider")
        debug_body_layout.addWidget(div_step2)

        # ── Step 3: WeGame Post-process & Restart ─────────────
        step3_widget = QWidget()
        step3_vbox = QVBoxLayout(step3_widget)
        step3_vbox.setContentsMargins(0, 0, 0, 0)
        step3_vbox.setSpacing(6)

        step3_header = QHBoxLayout()
        step3_header.setSpacing(8)

        self.step3_dot = QLabel("○")
        self.step3_dot.setProperty("class", "stepDot")
        self.step3_dot.setProperty("state", "idle")

        s3_text_vbox = QVBoxLayout()
        s3_text_vbox.setSpacing(1)
        s3_title = QLabel("阶段 3 · WeGame 修复重置与拉起")
        s3_title.setProperty("class", "stepTitle")
        s3_sub = QLabel("等待启动按钮可用，在资源包管理中删除长弓溪谷地图资源，并重新拉起游戏")
        s3_sub.setProperty("class", "stepSubtitle")
        s3_text_vbox.addWidget(s3_title)
        s3_text_vbox.addWidget(s3_sub)

        step3_header.addWidget(self.step3_dot, alignment=Qt.AlignVCenter)
        step3_header.addLayout(s3_text_vbox, stretch=1)
        step3_vbox.addLayout(step3_header)

        # Sub-step action buttons for stage 3
        sec3_row = QHBoxLayout()
        sec3_row.setSpacing(6)
        sec3_row.setContentsMargins(18, 0, 0, 0)

        self.dbg_wait_wegame_btn = QPushButton("等待启动按钮")
        self.dbg_wait_wegame_btn.setProperty("class", "stepBtn")
        self.dbg_wait_wegame_btn.setProperty("stepState", "idle")
        self.dbg_wait_wegame_btn.setToolTip("等待 WeGame 客户端回到启动按钮可用状态")
        self.dbg_wait_wegame_btn.clicked.connect(self._dbg_wait_wegame)

        self.dbg_more_btn = QPushButton("选项菜单 (...)")
        self.dbg_more_btn.setProperty("class", "stepBtn")
        self.dbg_more_btn.setProperty("stepState", "idle")
        self.dbg_more_btn.setToolTip("点击 WeGame 游戏主页右侧的更多操作 (...) 按钮")
        self.dbg_more_btn.clicked.connect(self._dbg_click_more)

        self.dbg_assets_btn = QPushButton("资源包管理")
        self.dbg_assets_btn.setProperty("class", "stepBtn")
        self.dbg_assets_btn.setProperty("stepState", "idle")
        self.dbg_assets_btn.setToolTip("点击弹出菜单中的“游戏资源包管理”项")
        self.dbg_assets_btn.clicked.connect(self._dbg_assets_manage)

        self.dbg_delete_btn = QPushButton("删除长弓溪谷")
        self.dbg_delete_btn.setProperty("class", "stepBtn")
        self.dbg_delete_btn.setProperty("stepState", "idle")
        self.dbg_delete_btn.setToolTip("在资源管理窗口中自动滚动并点击删除长弓溪谷地图资源")
        self.dbg_delete_btn.clicked.connect(self._dbg_delete_changgong)

        self.dbg_restart_btn = QPushButton("重新启动游戏")
        self.dbg_restart_btn.setProperty("class", "stepBtn")
        self.dbg_restart_btn.setProperty("stepState", "idle")
        self.dbg_restart_btn.setToolTip("在 WeGame 中点击启动按钮重新拉起三角洲行动")
        self.dbg_restart_btn.clicked.connect(self._dbg_restart_game)

        sec3_row.addWidget(self.dbg_wait_wegame_btn)
        sec3_row.addWidget(self.dbg_more_btn)
        sec3_row.addWidget(self.dbg_assets_btn)
        sec3_row.addWidget(self.dbg_delete_btn)
        sec3_row.addWidget(self.dbg_restart_btn)
        sec3_row.addStretch(1)

        step3_vbox.addLayout(sec3_row)
        debug_body_layout.addWidget(step3_widget)

        debug_outer.addWidget(self.debug_body)
        left_layout.addWidget(self.debug_panel)
        left_layout.addStretch(1)

        self.left_scroll.setWidget(self.left_column)

        # Mapping for step status updates
        self._step_buttons = {
            "nav_game": {
                "button": self.dbg_nav_start_btn,
                "base_text": "接管导航",
                "title": "接管导航",
            },
            "rename_pak": {
                "button": self.dbg_rename_pak_btn,
                "base_text": "屏蔽 Pak",
                "title": "屏蔽 Pak",
            },
            "open_paks": {
                "button": self.dbg_open_paks_btn,
                "base_text": "浏览 Paks 目录",
                "title": "打开 Paks 目录",
            },
            "wait_wegame": {
                "button": self.dbg_wait_wegame_btn,
                "base_text": "等待启动按钮",
                "title": "等待启动按钮",
            },
            "click_more": {
                "button": self.dbg_more_btn,
                "base_text": "选项菜单 (...)",
                "title": "选项菜单",
            },
            "assets_manage": {
                "button": self.dbg_assets_btn,
                "base_text": "资源包管理",
                "title": "资源包管理",
            },
            "delete_map": {
                "button": self.dbg_delete_btn,
                "base_text": "删除长弓溪谷",
                "title": "删除长弓溪谷",
            },
            "restart_game": {
                "button": self.dbg_restart_btn,
                "base_text": "重新启动游戏",
                "title": "重新启动游戏",
            },
        }

        # ── 3. Right: Log Panel ──────────────────────────────────────────────
        self.log_panel = QFrame()
        self.log_panel.setObjectName("logPanel")
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(12, 10, 12, 10)
        log_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_title = QLabel("运行日志")
        log_title.setObjectName("sectionTitle")

        self.copy_log_btn = QPushButton("复制")
        self.copy_log_btn.setObjectName("copyLogBtn")
        self.copy_log_btn.setToolTip("复制当前所有运行日志")
        self.copy_log_btn.clicked.connect(self.copy_log)

        self.clear_log_btn = QPushButton("清空")
        self.clear_log_btn.setObjectName("clearLogBtn")
        self.clear_log_btn.setToolTip("清空当前显示的日志")
        self.clear_log_btn.clicked.connect(self.clear_log)

        log_header.addWidget(log_title)
        log_header.addStretch(1)
        log_header.addWidget(self.copy_log_btn)
        log_header.addWidget(self.clear_log_btn)

        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_output.setMinimumHeight(120)  # small floor; splitter determines actual size
        self.log_output.document().setMaximumBlockCount(800)
        self.log_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_output)

        # Pending log lines buffered between timer flushes
        self._log_buffer: list[str] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(150)
        self._log_flush_timer.timeout.connect(self._flush_log_buffer)
        self._log_flush_timer.start()

        # ── 4. Assemble QSplitter ─────────────────────────────────────────────
        self.main_splitter.addWidget(self.left_scroll)
        self.main_splitter.addWidget(self.log_panel)
        # Top controls stay content-sized; bottom log expands with window resize
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.left_scroll.setMinimumHeight(280)
        self.log_panel.setMinimumHeight(160)

        root.addWidget(self.main_splitter, stretch=1)
        self.setStyleSheet(MAIN_WINDOW_STYLE)
        self._sync_pak_button_state()
