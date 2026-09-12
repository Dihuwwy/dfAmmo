from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import win32api
import win32con
import win32gui

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

from scripts.bind_button import BindButton
from scripts.config import AppConfig
from scripts.game_navigation import NavigationStatus
from scripts.styles import MAIN_WINDOW_STYLE
from scripts.template_capture import TemplateCaptureOverlay
from scripts.workflow import Workflow
from scripts.window_binding import BoundWindow


class MainWindow(QWidget):
    """Main GUI shell."""

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or AppConfig.load_from_file()
        self.workflow = Workflow(
            game_process_names=self.config.game_process_names,
            template_threshold=self.config.template_match_threshold,
            navigation_step_timeout_seconds=self.config.navigation_step_timeout_seconds,
            game_window_timeout_seconds=self.config.game_window_timeout_seconds,
        )
        self.bound_window: BoundWindow | None = None
        self.capture_overlay: TemplateCaptureOverlay | None = None
        self.pending_template_name = ""
        self.game_process_deadline = 0.0
        self.game_process_timer = QTimer(self)
        self.game_process_timer.setInterval(self.config.game_process_poll_interval_ms)
        self.game_process_timer.timeout.connect(self.check_game_process)
        self.navigation_timer = QTimer(self)
        self.navigation_timer.setInterval(self.config.navigation_poll_interval_ms)
        self.navigation_timer.timeout.connect(self.advance_game_navigation)

        self._last_hotkey_time = 0.0
        self.hotkey_registered = False
        try:
            self.hotkey_registered = bool(
                win32gui.RegisterHotKey(int(self.winId()), 1001, 0, win32con.VK_F12)
            )
        except Exception:
            self.hotkey_registered = False

        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.setInterval(60)
        self.hotkey_timer.timeout.connect(self._check_hotkey)
        self.hotkey_timer.start()

        self.setWindowTitle(self.config.window_title)
        self.setObjectName("mainWindow")
        self.resize(800, 600)
        self._build_ui()
        self.write_log("请先绑定 WeGame 主窗口（如游戏已在运行，可直接点击“开始卡邮件”）。")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        title = QLabel(self.config.window_title)
        title.setObjectName("title")

        self.subtitle = QLabel("先绑定 WeGame 主窗口，绑定成功后再显示可用功能。")
        self.subtitle.setObjectName("subtitle")

        self.bind_panel = QFrame()
        self.bind_panel.setObjectName("bindPanel")
        bind_layout = QVBoxLayout(self.bind_panel)
        bind_layout.setContentsMargins(28, 28, 28, 28)
        bind_layout.setSpacing(14)
        bind_layout.setAlignment(Qt.AlignCenter)

        bind_content = QWidget()
        bind_content.setObjectName("bindContent")
        bind_content.setFixedWidth(480)
        bind_content_layout = QVBoxLayout(bind_content)
        bind_content_layout.setContentsMargins(0, 0, 0, 0)
        bind_content_layout.setSpacing(18)
        bind_content_layout.setAlignment(Qt.AlignCenter)

        bind_title = QLabel("绑定 WeGame 窗口")
        bind_title.setObjectName("sectionTitle")
        bind_title.setAlignment(Qt.AlignCenter)

        self.bind_button = BindButton()
        self.bind_button.released_at.connect(self.bind_window_at)

        bind_content_layout.addWidget(bind_title)
        bind_content_layout.addWidget(self.bind_button)
        bind_layout.addWidget(bind_content)

        self.feature_panel = QFrame()
        self.feature_panel.setObjectName("featurePanel")
        feature_layout = QVBoxLayout(self.feature_panel)
        feature_layout.setContentsMargins(20, 18, 20, 18)
        feature_layout.setSpacing(10)

        feature_title = QLabel("后续功能")
        feature_title.setObjectName("sectionTitle")
        self.window_info = QLabel("")
        self.window_info.setWordWrap(True)

        dir_row = QHBoxLayout()
        dir_label = QLabel("游戏安装目录：")
        self.game_dir_input = QLineEdit()
        self.game_dir_input.setPlaceholderText("请选择包含 DeltaForce 文件夹的安装目录")
        self.game_dir_input.setText(self.config.game_install_dir)
        self.game_dir_input.editingFinished.connect(self._save_game_dir)
        self.game_dir_button = QPushButton("浏览")
        self.game_dir_button.setObjectName("secondaryButton")
        self.game_dir_button.clicked.connect(self._choose_game_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self.game_dir_input, stretch=1)
        dir_row.addWidget(self.game_dir_button)

        button_row = QHBoxLayout()
        self.start_card_mail_button = QPushButton("开始卡邮件")
        self.start_card_mail_button.clicked.connect(self.start_card_mail)

        self.pause_resume_button = QPushButton("暂停 (F12)")
        self.pause_resume_button.setObjectName("pauseButton")
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.clicked.connect(self.toggle_pause_resume)

        self.stop_button = QPushButton("停止 (Shift+F12)")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.emergency_stop)

        self.resync_button = QPushButton("界面重同步")
        self.resync_button.setObjectName("secondaryButton")
        self.resync_button.setEnabled(False)
        self.resync_button.clicked.connect(self.manual_resync)

        self.capture_button = QPushButton("采集元素模板")
        self.capture_button.clicked.connect(self.start_template_capture)

        self.rebind_button = QPushButton("重新绑定")
        self.rebind_button.setObjectName("secondaryButton")
        self.rebind_button.clicked.connect(self.reset_binding)

        button_row.addWidget(self.start_card_mail_button)
        button_row.addWidget(self.pause_resume_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.resync_button)
        button_row.addWidget(self.capture_button)
        button_row.addStretch(1)
        button_row.addWidget(self.rebind_button)

        mode_row = QHBoxLayout()
        mode_label = QLabel("运行模式：")
        self.semi_auto_radio = QRadioButton("半自动模式（手动购入穿戴）")
        self.full_auto_radio = QRadioButton("全自动模式（配装方案一键买齐）")
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

        feature_layout.addWidget(feature_title)
        feature_layout.addWidget(self.window_info)
        feature_layout.addLayout(dir_row)
        feature_layout.addLayout(mode_row)
        feature_layout.addLayout(button_row)
        self.feature_panel.hide()

        # ── Debug panel ──────────────────────────────────────────────────────
        # ── Debug & Execution Tracker Panel ──────────────────────────────────
        self.debug_panel = QFrame()
        self.debug_panel.setObjectName("debugPanel")
        debug_outer = QVBoxLayout(self.debug_panel)
        debug_outer.setContentsMargins(18, 14, 18, 14)
        debug_outer.setSpacing(10)

        # Header: Title, Global Status Badge, Reset Button, Toggle Button
        debug_header = QHBoxLayout()
        debug_title = QLabel("🛠 工作流实时跟踪 & 单步调试")
        debug_title.setObjectName("sectionTitle")

        self.workflow_status_badge = QLabel("● 待命就绪")
        self.workflow_status_badge.setObjectName("workflowStatusBadge")
        self.workflow_status_badge.setProperty("state", "idle")

        self.reset_status_btn = QPushButton("重置状态")
        self.reset_status_btn.setObjectName("resetStatusBtn")
        self.reset_status_btn.setToolTip("清空所有步骤高亮状态，恢复为待命")
        self.reset_status_btn.clicked.connect(self.reset_all_step_states)

        self.debug_toggle_button = QPushButton("收起")
        self.debug_toggle_button.setObjectName("debugToggleBtn")
        self.debug_toggle_button.setFixedWidth(64)
        self.debug_toggle_button.clicked.connect(self._toggle_debug_panel)

        debug_header.addWidget(debug_title)
        debug_header.addSpacing(10)
        debug_header.addWidget(self.workflow_status_badge)
        debug_header.addStretch(1)
        debug_header.addWidget(self.reset_status_btn)
        debug_header.addWidget(self.debug_toggle_button)
        debug_outer.addLayout(debug_header)

        self.debug_body = QWidget()
        debug_body_layout = QVBoxLayout(self.debug_body)
        debug_body_layout.setContentsMargins(0, 4, 0, 0)
        debug_body_layout.setSpacing(8)

        # ── Section 1: In-game Navigation ────────────────────────────────────
        sec1_card = QFrame()
        sec1_card.setProperty("class", "debugSectionCard")
        sec1_layout = QVBoxLayout(sec1_card)
        sec1_layout.setContentsMargins(12, 8, 12, 10)
        sec1_layout.setSpacing(6)

        sec1_title = QLabel("阶段 1 · 游戏内自动化导航 (In-Game Automation)")
        sec1_title.setProperty("class", "debugSectionTitle")

        sec1_main_row = QHBoxLayout()
        self.dbg_nav_start_btn = QPushButton("▶ 1. 接管游戏导航")
        self.dbg_nav_start_btn.setProperty("class", "stepBtn")
        self.dbg_nav_start_btn.setProperty("stepState", "idle")
        self.dbg_nav_start_btn.setToolTip("检测游戏窗口并自动推进 10 个菜单与模式步骤")
        self.dbg_nav_start_btn.clicked.connect(self._dbg_takeover_navigation)

        sec1_hint = QLabel("自动识别游戏画面并逐级推进 10 步流程，选人界面触发时自动退出游戏：")
        sec1_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")

        sec1_main_row.addWidget(self.dbg_nav_start_btn)
        sec1_main_row.addSpacing(8)
        sec1_main_row.addWidget(sec1_hint)
        sec1_main_row.addStretch(1)

        # 10 sub-step pills
        sub_steps_row = QHBoxLayout()
        sub_steps_row.setSpacing(4)
        self.sub_step_names = [
            "1.模式",
            "2.关弹窗",
            "3.进大厅",
            "4.选地图",
            "5.选长弓",
            "6.行动",
            "7.配装",
            "8.继续",
            "9.出发",
            "10.选人",
        ]
        self.sub_step_pills: list[QLabel] = []
        for sname in self.sub_step_names:
            pill = QLabel(sname)
            pill.setProperty("class", "subStepPill")
            pill.setProperty("pillState", "")
            self.sub_step_pills.append(pill)
            sub_steps_row.addWidget(pill)
        sub_steps_row.addStretch(1)

        sec1_layout.addWidget(sec1_title)
        sec1_layout.addLayout(sec1_main_row)
        sec1_layout.addLayout(sub_steps_row)
        debug_body_layout.addWidget(sec1_card)

        # ── Section 2: Pak File Isolation ────────────────────────────────────
        sec2_card = QFrame()
        sec2_card.setProperty("class", "debugSectionCard")
        sec2_layout = QVBoxLayout(sec2_card)
        sec2_layout.setContentsMargins(12, 8, 12, 10)
        sec2_layout.setSpacing(6)

        sec2_title = QLabel("阶段 2 · Pak 补丁隔离 (Pak File Isolation)")
        sec2_title.setProperty("class", "debugSectionTitle")

        sec2_btn_row = QHBoxLayout()
        sec2_btn_row.setSpacing(8)
        self.dbg_rename_pak_btn = QPushButton("📦 2. 屏蔽 Pak (重命名 .disabled)")
        self.dbg_rename_pak_btn.setProperty("class", "stepBtn")
        self.dbg_rename_pak_btn.setProperty("stepState", "idle")
        self.dbg_rename_pak_btn.setToolTip("重命名长弓溪谷 Pak 文件为 .disabled 状态以屏蔽加载")
        self.dbg_rename_pak_btn.clicked.connect(self._dbg_rename_pak)

        self.dbg_open_paks_btn = QPushButton("📂 浏览 Paks 目录")
        self.dbg_open_paks_btn.setProperty("class", "stepAuxBtn")
        self.dbg_open_paks_btn.setToolTip("在资源管理器中打开 Paks 补丁文件夹（测试辅助）")
        self.dbg_open_paks_btn.clicked.connect(self._dbg_open_paks)

        sec2_btn_row.addWidget(self.dbg_rename_pak_btn)
        sec2_btn_row.addWidget(self.dbg_open_paks_btn)
        sec2_btn_row.addStretch(1)

        sec2_layout.addWidget(sec2_title)
        sec2_layout.addLayout(sec2_btn_row)
        debug_body_layout.addWidget(sec2_card)

        # ── Section 3: WeGame Post-process & Restart ────────────────────────
        sec3_card = QFrame()
        sec3_card.setProperty("class", "debugSectionCard")
        sec3_layout = QVBoxLayout(sec3_card)
        sec3_layout.setContentsMargins(12, 8, 12, 10)
        sec3_layout.setSpacing(6)

        sec3_title = QLabel("阶段 3 · WeGame 修复重置与拉起 (Post-Process & Launch)")
        sec3_title.setProperty("class", "debugSectionTitle")

        sec3_btn_row = QHBoxLayout()
        sec3_btn_row.setSpacing(8)

        self.dbg_wait_wegame_btn = QPushButton("⏳ 3. 等待启动按钮")
        self.dbg_wait_wegame_btn.setProperty("class", "stepBtn")
        self.dbg_wait_wegame_btn.setProperty("stepState", "idle")
        self.dbg_wait_wegame_btn.setToolTip("等待 WeGame 客户端回到启动按钮可用状态")
        self.dbg_wait_wegame_btn.clicked.connect(self._dbg_wait_wegame)

        self.dbg_more_btn = QPushButton("⋯ 4. 点击选项菜单")
        self.dbg_more_btn.setProperty("class", "stepBtn")
        self.dbg_more_btn.setProperty("stepState", "idle")
        self.dbg_more_btn.setToolTip("点击 WeGame 游戏主页右侧的更多操作 (...) 按钮")
        self.dbg_more_btn.clicked.connect(self._dbg_click_more)

        self.dbg_assets_btn = QPushButton("📁 5. 资源包管理")
        self.dbg_assets_btn.setProperty("class", "stepBtn")
        self.dbg_assets_btn.setProperty("stepState", "idle")
        self.dbg_assets_btn.setToolTip("点击弹出菜单中的“游戏资源包管理”项")
        self.dbg_assets_btn.clicked.connect(self._dbg_assets_manage)

        self.dbg_delete_btn = QPushButton("🗑️ 6. 删除长弓溪谷")
        self.dbg_delete_btn.setProperty("class", "stepBtn")
        self.dbg_delete_btn.setProperty("stepState", "idle")
        self.dbg_delete_btn.setToolTip("在资源管理窗口中自动滚动并点击删除长弓溪谷地图资源")
        self.dbg_delete_btn.clicked.connect(self._dbg_delete_changgong)

        self.dbg_restart_btn = QPushButton("🚀 7. 重新启动游戏")
        self.dbg_restart_btn.setProperty("class", "stepBtn")
        self.dbg_restart_btn.setProperty("stepState", "idle")
        self.dbg_restart_btn.setToolTip("在 WeGame 中点击启动按钮重新拉起三角洲行动")
        self.dbg_restart_btn.clicked.connect(self._dbg_restart_game)

        sec3_btn_row.addWidget(self.dbg_wait_wegame_btn)
        sec3_btn_row.addWidget(self.dbg_more_btn)
        sec3_btn_row.addWidget(self.dbg_assets_btn)
        sec3_btn_row.addWidget(self.dbg_delete_btn)
        sec3_btn_row.addWidget(self.dbg_restart_btn)
        sec3_btn_row.addStretch(1)

        sec3_layout.addWidget(sec3_title)
        sec3_layout.addLayout(sec3_btn_row)
        debug_body_layout.addWidget(sec3_card)

        # Mapping for step status updates
        self._step_buttons = {
            "nav_game": {
                "button": self.dbg_nav_start_btn,
                "base_text": "▶ 1. 接管游戏导航",
                "title": "接管游戏导航",
            },
            "rename_pak": {
                "button": self.dbg_rename_pak_btn,
                "base_text": "📦 2. 屏蔽 Pak (重命名 .disabled)",
                "title": "屏蔽 Pak",
            },
            "open_paks": {
                "button": self.dbg_open_paks_btn,
                "base_text": "📂 浏览 Paks 目录",
                "title": "打开 Paks 目录",
            },
            "wait_wegame": {
                "button": self.dbg_wait_wegame_btn,
                "base_text": "⏳ 3. 等待启动按钮",
                "title": "等待启动按钮",
            },
            "click_more": {
                "button": self.dbg_more_btn,
                "base_text": "⋯ 4. 点击选项菜单",
                "title": "点击选项菜单",
            },
            "assets_manage": {
                "button": self.dbg_assets_btn,
                "base_text": "📁 5. 资源包管理",
                "title": "资源包管理",
            },
            "delete_map": {
                "button": self.dbg_delete_btn,
                "base_text": "🗑️ 6. 删除长弓溪谷",
                "title": "删除长弓溪谷",
            },
            "restart_game": {
                "button": self.dbg_restart_btn,
                "base_text": "🚀 7. 重新启动游戏",
                "title": "重新启动游戏",
            },
        }

        debug_outer.addWidget(self.debug_body)
        self.debug_panel.hide()  # only shown after window binding


        self.log_panel = QFrame()
        self.log_panel.setObjectName("logPanel")
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(16, 14, 16, 16)
        log_layout.setSpacing(8)

        log_title = QLabel("运行日志")
        log_title.setObjectName("sectionTitle")
        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(180)
        self.log_output.document().setMaximumBlockCount(500)
        # Performance: use NoWrap so long lines don't force complex layout
        self.log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_output)

        # Pending log lines buffered between timer flushes
        self._log_buffer: list[str] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(150)
        self._log_flush_timer.timeout.connect(self._flush_log_buffer)
        self._log_flush_timer.start()

        root.addWidget(title)
        root.addWidget(self.subtitle)
        root.addWidget(self.bind_panel, stretch=1)
        root.addWidget(self.feature_panel)
        root.addWidget(self.debug_panel)
        root.addWidget(self.log_panel)

        self.setStyleSheet(MAIN_WINDOW_STYLE)

    def bind_window_at(self, x: int, y: int) -> None:
        try:
            bound_window = self.workflow.window_binder.bind_at_position(x, y)
        except Exception as exc:
            self.write_log(f"绑定失败：{exc}")
            return

        if bound_window.handle == int(self.winId()):
            self.write_log("绑定到了工具窗口本身，请拖到 WeGame 窗口上再松开。")
            return

        self.bound_window = bound_window
        self.window_info.setText(
            "已绑定窗口："
            f"{bound_window.title or '<无标题>'} | "
            f"{bound_window.process_name or '<未知进程>'} | "
            f"pid={bound_window.process_id or '-'} | "
            f"handle={bound_window.handle}"
        )
        self.bind_panel.hide()
        self.feature_panel.show()
        self.debug_panel.show()
        self.subtitle.setText("WeGame 窗口已绑定，可以开始执行任务。")
        self.write_log(
            "窗口绑定成功："
            f"{bound_window.title or '<无标题>'} | "
            f"{bound_window.process_name or '<未知进程>'} | "
            f"pid={bound_window.process_id or '-'}"
        )

    def reset_binding(self) -> None:
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.workflow.cancel_game_navigation()
        self.start_card_mail_button.setEnabled(True)
        self.pause_resume_button.setEnabled(False)
        self._set_pause_button_state(is_paused=False)
        self.stop_button.setEnabled(False)
        self.resync_button.setEnabled(False)
        self.bound_window = None
        self.feature_panel.hide()
        self.debug_panel.hide()
        self.bind_panel.show()
        self.subtitle.setText("先绑定 WeGame 主窗口，绑定成功后再显示可用功能。")
        self.write_log("已解除窗口绑定，请重新选择 WeGame 窗口。")

    def _set_pause_button_state(self, is_paused: bool) -> None:
        if is_paused:
            self.pause_resume_button.setText("▶ 继续 (F12)")
            self.pause_resume_button.setObjectName("resumeButton")
        else:
            self.pause_resume_button.setText("⏸ 暂停 (F12)")
            self.pause_resume_button.setObjectName("pauseButton")
        self.pause_resume_button.setStyle(self.pause_resume_button.style())

    def toggle_pause_resume(self) -> None:
        is_nav_running = self.navigation_timer.isActive()
        is_proc_running = self.game_process_timer.isActive()
        is_paused = self.workflow.is_navigation_paused

        if not (is_nav_running or is_proc_running or is_paused):
            self.write_log("ℹ️ 当前没有正在运行的自动化任务。")
            return

        if is_paused:
            event = self.workflow.resume_game_navigation()
            self._set_pause_button_state(is_paused=False)
            if not self.navigation_timer.isActive():
                self.navigation_timer.start()
            self.write_log(event.message)
            self.advance_game_navigation()
        else:
            event = self.workflow.pause_game_navigation()
            self._set_pause_button_state(is_paused=True)
            self.write_log(event.message)

    def manual_resync(self) -> None:
        if not (self.navigation_timer.isActive() or self.workflow.is_navigation_paused):
            self.write_log("当前不在游戏导航流程中，无法重同步。")
            return

        event = self.workflow.resync_game_navigation()
        if event is not None:
            self.write_log(event.message)
        else:
            self.write_log("未匹配到任何已知流程步骤画面，请确认游戏窗口是否在前台或画面是否正常。")

    def emergency_stop(self) -> None:
        was_running = (
            self.navigation_timer.isActive()
            or self.game_process_timer.isActive()
            or self.workflow.is_navigation_paused
        )
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.workflow.cancel_game_navigation()
        self.start_card_mail_button.setEnabled(True)
        self.pause_resume_button.setEnabled(False)
        self._set_pause_button_state(is_paused=False)
        self.stop_button.setEnabled(False)
        self.resync_button.setEnabled(False)

        # Re-activate and bring this Assistant window to top
        self.showNormal()
        self.activateWindow()
        self.raise_()
        try:
            win32gui.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass

        for step_id, info in getattr(self, "_step_buttons", {}).items():
            btn = info["button"]
            if btn.property("stepState") == "running":
                self.set_step_state(step_id, "idle")
        if hasattr(self, "workflow_status_badge"):
            self.workflow_status_badge.setText("🛑 任务已停止")
            self.workflow_status_badge.setProperty("state", "idle")
            self.workflow_status_badge.style().unpolish(self.workflow_status_badge)
            self.workflow_status_badge.style().polish(self.workflow_status_badge)
            self.workflow_status_badge.update()

        if was_running:
            self.write_log("🛑【任务停止】已通过快捷键/按钮停止当前自动化任务！")
        else:
            self.write_log("🛑【任务停止】当前无正在运行的自动化任务。")

    def _check_hotkey(self) -> None:
        now = time.monotonic()
        try:
            if win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000:
                if now - self._last_hotkey_time >= 0.35:
                    self._last_hotkey_time = now
                    shift_down = bool(win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000)
                    if shift_down:
                        self.emergency_stop()
                    else:
                        self.toggle_pause_resume()
        except Exception:
            pass

    def nativeEvent(self, event_type, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == win32con.WM_HOTKEY and msg.wParam == 1001:
                now = time.monotonic()
                if now - self._last_hotkey_time >= 0.35:
                    self._last_hotkey_time = now
                    self.toggle_pause_resume()
                return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event) -> None:
        if getattr(self, "hotkey_registered", False):
            try:
                win32gui.UnregisterHotKey(int(self.winId()), 1001)
            except Exception:
                pass
        super().closeEvent(event)

    def _save_game_dir(self) -> None:
        game_install_dir = self.game_dir_input.text().strip()
        if game_install_dir == self.config.game_install_dir:
            return

        updated_config = replace(self.config, game_install_dir=game_install_dir)
        try:
            updated_config.save_to_file()
        except OSError as exc:
            self.write_log(f"保存游戏安装目录失败：{exc}")
            return

        self.config = updated_config
        self.write_log("游戏安装目录已保存。")

    def _on_mode_changed(self) -> None:
        new_mode = "semi_auto" if self.semi_auto_radio.isChecked() else "full_auto"
        if new_mode == getattr(self.config, "operation_mode", "semi_auto"):
            return
        self.config = replace(self.config, operation_mode=new_mode)
        try:
            self.config.save_to_file()
        except OSError as exc:
            self.write_log(f"保存运行模式失败：{exc}")
        else:
            mode_name = "半自动模式" if new_mode == "semi_auto" else "全自动模式"
            self.write_log(f"已切换运行模式为：{mode_name}")

    def _choose_game_dir(self) -> None:
        initial_dir = self.game_dir_input.text().strip() or str(Path.home())
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "选择包含 DeltaForce 文件夹的安装目录",
            initial_dir,
        )
        if not selected_dir:
            return
        self.game_dir_input.setText(selected_dir)
        self._save_game_dir()

    def write_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self._log_buffer.append(f"[{timestamp}] {message}")

    def _flush_log_buffer(self) -> None:
        if not self._log_buffer:
            return

        lines = self._log_buffer
        self._log_buffer = []

        # Check if user is currently selecting text – don't disturb cursor
        cursor = self.log_output.textCursor()
        user_has_selection = cursor.hasSelection()

        # Check if user has scrolled up manually
        vbar = self.log_output.verticalScrollBar()
        was_at_bottom = vbar.value() >= vbar.maximum() - 4

        # Block signals during batch insert to avoid per-line repaints
        self.log_output.setUpdatesEnabled(False)
        try:
            for line in lines:
                self.log_output.appendPlainText(line)
        finally:
            self.log_output.setUpdatesEnabled(True)
            self.log_output.update()

        # Only auto-scroll if user hasn't scrolled up and isn't selecting
        if was_at_bottom and not user_has_selection:
            self.log_output.moveCursor(QTextCursor.MoveOperation.End)
            self.log_output.ensureCursorVisible()

    def start_template_capture(self) -> None:
        name, ok = QInputDialog.getText(self, "保存模板", "模板名称，例如 wegame_start_button：")
        if not ok:
            self.write_log("已取消模板采集。")
            return

        self.pending_template_name = name.strip()
        if not self.pending_template_name:
            self.write_log("模板名称不能为空。")
            return

        self.write_log("开始采集模板，请框选目标元素区域。")
        self.hide()

        self.capture_overlay = TemplateCaptureOverlay()
        self.capture_overlay.selected.connect(self.save_template_from_rect)
        self.capture_overlay.canceled.connect(self.cancel_template_capture)

        QTimer.singleShot(200, self.capture_overlay.begin)

    def cancel_template_capture(self) -> None:
        self.show()
        self.write_log("已取消模板采集。")

    def save_template_from_rect(self, rect: QRect) -> None:
        physical_rect = self._to_physical_rect(rect)
        global_top_left = physical_rect.topLeft()
        global_bottom_right = physical_rect.bottomRight()

        try:
            output_path = self.workflow.screenshot.capture_region_to_template(
                name=self.pending_template_name,
                left=global_top_left.x(),
                top=global_top_left.y(),
                right=global_bottom_right.x() + 1,
                bottom=global_bottom_right.y() + 1,
            )
        except Exception as exc:
            self.show()
            self.write_log(f"模板保存失败：{exc}")
            QMessageBox.warning(self, "保存失败", str(exc))
            return

        self.show()
        self.write_log(f"模板已保存：{output_path}")
        QMessageBox.information(self, "保存成功", f"模板已保存：\n{output_path}")

    def _to_physical_rect(self, rect: QRect) -> QRect:
        screen = QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
        if screen is None:
            return rect

        ratio = screen.devicePixelRatio()
        geometry = screen.geometry()
        left = geometry.x() + round((rect.left() - geometry.x()) * ratio)
        top = geometry.y() + round((rect.top() - geometry.y()) * ratio)
        right = geometry.x() + round((rect.right() - geometry.x()) * ratio)
        bottom = geometry.y() + round((rect.bottom() - geometry.y()) * ratio)
        return QRect(QPoint(left, top), QPoint(right, bottom)).normalized()

    def start_card_mail(self) -> None:
        self.reset_all_step_states()
        # Check if Delta Force is already running; if so, directly take over navigation
        game_process = self.workflow.find_game_process()
        if game_process is not None:
            self.write_log(
                "检测到三角洲行动游戏已在运行中："
                f"{game_process.name} | pid={game_process.process_id}，直接接管导航！"
            )
            self.start_card_mail_button.setEnabled(False)
            self.pause_resume_button.setEnabled(True)
            self._set_pause_button_state(is_paused=False)
            self.stop_button.setEnabled(True)
            self.resync_button.setEnabled(True)

            self.set_step_state("nav_game", "running")
            self.update_nav_substep_pills(0)
            event = self.workflow.start_game_navigation(game_process)
            self.write_log(event.message)
            self.navigation_timer.start()
            self.advance_game_navigation()
            return

        if self.bound_window is None:
            self.write_log("请先绑定 WeGame 窗口。")
            return

        self.write_log("准备识别并点击启动元素...")
        self.hide()
        QApplication.processEvents()

        try:
            position, template_path = self.workflow.click_start_button(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
            )
        except Exception as exc:
            self.show()
            self.write_log(f"启动按钮匹配/点击失败：{exc}")
            QMessageBox.warning(self, "执行失败", str(exc))
            return

        self.show()
        self.start_card_mail_button.setEnabled(False)
        self.pause_resume_button.setEnabled(True)
        self._set_pause_button_state(is_paused=False)
        self.stop_button.setEnabled(True)
        self.resync_button.setEnabled(True)
        self.game_process_deadline = time.monotonic() + self.config.game_process_timeout_seconds
        self.write_log(
            "已点击启动元素："
            f"x={position.x}, y={position.y}, "
            f"confidence={position.confidence:.3f}, template={template_path.name}"
        )
        self.write_log("正在等待三角洲行动游戏进程...")
        if hasattr(self, "workflow_status_badge"):
            self.workflow_status_badge.setText("⏳ 等待三角洲行动启动...")
            self.workflow_status_badge.setProperty("state", "running")
            self.workflow_status_badge.style().unpolish(self.workflow_status_badge)
            self.workflow_status_badge.style().polish(self.workflow_status_badge)
            self.workflow_status_badge.update()
        self.game_process_timer.start()
        self.check_game_process()

    def check_game_process(self) -> None:
        game_process = self.workflow.find_game_process()
        if game_process is not None:
            self.game_process_timer.stop()
            self.write_log(
                "已找到三角洲行动游戏进程："
                f"{game_process.name} | pid={game_process.process_id}"
            )
            self.set_step_state("nav_game", "running")
            self.update_nav_substep_pills(0)
            event = self.workflow.start_game_navigation(game_process)
            self.write_log(event.message)
            self.navigation_timer.start()
            self.advance_game_navigation()
            return

        if time.monotonic() >= self.game_process_deadline:
            self.game_process_timer.stop()
            self.start_card_mail_button.setEnabled(True)
            self.pause_resume_button.setEnabled(False)
            self._set_pause_button_state(is_paused=False)
            self.stop_button.setEnabled(False)
            self.resync_button.setEnabled(False)
            self.write_log(
                f"等待游戏进程超时（{self.config.game_process_timeout_seconds} 秒）。"
            )
            if hasattr(self, "workflow_status_badge"):
                self.workflow_status_badge.setText("✕ 等待游戏启动超时")
                self.workflow_status_badge.setProperty("state", "failed")
                self.workflow_status_badge.style().unpolish(self.workflow_status_badge)
                self.workflow_status_badge.style().polish(self.workflow_status_badge)
                self.workflow_status_badge.update()

    def advance_game_navigation(self) -> None:
        # Reflect sub-step pills with current index
        cur_step_idx = getattr(self.workflow.game_navigator, "step_index", 0)
        self.update_nav_substep_pills(cur_step_idx)

        try:
            event = self.workflow.advance_game_navigation()
        except Exception as exc:
            self.navigation_timer.stop()
            self.start_card_mail_button.setEnabled(True)
            self.pause_resume_button.setEnabled(False)
            self._set_pause_button_state(is_paused=False)
            self.stop_button.setEnabled(False)
            self.resync_button.setEnabled(False)
            self.set_step_state("nav_game", "failed", str(exc))
            self.write_log(f"自动导航失败：{exc}")
            return

        if event is None:
            return

        self.write_log(event.message)
        if event.status == NavigationStatus.PAUSED:
            self._set_pause_button_state(is_paused=True)
            if hasattr(self, "workflow_status_badge"):
                self.workflow_status_badge.setText(f"⏸️ 流程已暂停（当前处于步骤 {cur_step_idx + 1}）")
                self.workflow_status_badge.setProperty("state", "running")
                self.workflow_status_badge.style().unpolish(self.workflow_status_badge)
                self.workflow_status_badge.style().polish(self.workflow_status_badge)
                self.workflow_status_badge.update()
            return

        if event.status in (NavigationStatus.COMPLETE, NavigationStatus.FAILED):
            self.navigation_timer.stop()
            self.start_card_mail_button.setEnabled(True)
            self.pause_resume_button.setEnabled(False)
            self._set_pause_button_state(is_paused=False)
            self.stop_button.setEnabled(False)
            self.resync_button.setEnabled(False)

            if event.status == NavigationStatus.FAILED:
                self.set_step_state("nav_game", "failed", event.message)
                return

            if event.status == NavigationStatus.COMPLETE:
                self.set_step_state("nav_game", "success")
                self.update_nav_substep_pills(len(self.sub_step_pills))
                process_exited, process_message = self.workflow.kill_game_process()
                self.write_log(process_message)

                if self.bound_window is not None:
                    try:
                        self.workflow.window_binder.activate(self.bound_window)
                    except Exception as exc:
                        self.write_log(f"返回 WeGame 窗口失败：{exc}")
                    else:
                        self.write_log("已返回 WeGame 窗口。")

                if not process_exited:
                    return

                # Rename pak files BEFORE opening explorer, so explorer doesn't steal
                # focus and break the WeGame window handle
                paks_path: Path | None = None
                if self.config.game_install_dir:
                    paks_path = (
                        Path(self.config.game_install_dir)
                        / "DeltaForce"
                        / "PackContent"
                        / "Paks"
                    )
                    if not paks_path.is_dir():
                        self.write_log(f"Paks 目录不存在，请检查安装目录：{paks_path}")
                        paks_path = None

                    if paks_path is not None:
                        self.set_step_state("rename_pak", "running")
                        try:
                            results = self.workflow.rename_pak_files(
                                self.config.game_install_dir,
                                self.config.pak_file_names,
                            )
                            self.set_step_state("rename_pak", "success")
                        except OSError as exc:
                            self.set_step_state("rename_pak", "failed", str(exc))
                            self.write_log(f"重命名 pak 文件失败：{exc}")
                        else:
                            for message in results:
                                self.write_log(message)
                else:
                    self.write_log("未配置游戏安装目录，跳过 pak 文件重命名。")

                # Run WeGame post-process (delete map pkg, restart) BEFORE opening explorer
                if self.bound_window is not None:
                    self._run_wegame_post_process()

                # Open explorer LAST so it doesn't steal focus from WeGame
                if paks_path is not None:
                    try:
                        subprocess.Popen(["explorer", str(paks_path)])
                    except OSError as exc:
                        self.write_log(f"打开 Paks 目录失败：{exc}")
                    else:
                        self.write_log(f"已打开 Paks 目录：{paks_path}")

    def _run_wegame_post_process(self) -> None:
        if self.bound_window is None:
            return

        current_step = "wait_wegame"
        try:
            self.set_step_state("wait_wegame", "running")
            self.write_log("正在等待 WeGame 启动按钮重新出现...")
            QApplication.processEvents()

            self.workflow.wait_for_wegame_ready(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
                timeout=getattr(self.config, "wegame_ready_timeout_seconds", 60),
            )
            self.set_step_state("wait_wegame", "success")
            self.write_log("WeGame 启动按钮已重新出现。")
            QApplication.processEvents()

            current_step = "click_more"
            self.set_step_state("click_more", "running")
            self.write_log("正在点击更多选项（...）...")
            self.workflow.click_wegame_more(
                self.bound_window,
                getattr(self.config, "wegame_more_template", "wegame_more.png"),
                self.config.template_match_threshold,
            )
            self.set_step_state("click_more", "success")
            self.write_log("已点击更多选项。")
            QApplication.processEvents()
            time.sleep(0.5)

            current_step = "assets_manage"
            self.set_step_state("assets_manage", "running")
            self.write_log("正在打开游戏资源包管理...")
            self.workflow.click_assets_manage(
                self.bound_window,
                getattr(self.config, "wegame_assets_manage_template", "wegame_assets_manage.png"),
                self.config.template_match_threshold,
            )
            self.set_step_state("assets_manage", "success")
            self.write_log("已打开游戏资源包管理。")
            QApplication.processEvents()
            time.sleep(1.0)

            current_step = "delete_map"
            self.set_step_state("delete_map", "running")
            self.write_log("正在等待资源管理窗口并删除长弓溪谷资源包...")
            pos = self.workflow.delete_changgong_map(
                getattr(self.config, "wegame_delete_map_template", "wegame_delete_map.png"),
                self.config.template_match_threshold,
                timeout=getattr(self.config, "delete_map_timeout_seconds", 30),
            )
            self.set_step_state("delete_map", "success")
            self.write_log(f"已点击删除长弓溪谷资源包（x={pos.x}, y={pos.y}）。")
            QApplication.processEvents()

            time.sleep(1.2)
            current_step = "restart_game"
            self.set_step_state("restart_game", "running")
            self.write_log("切回 WeGame 窗口，准备重新拉起游戏...")
            position, template_path = self.workflow.click_start_button(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
            )
            self.set_step_state("restart_game", "success")
            self.write_log(
                f"已重新点击启动按钮，游戏正在拉起：{template_path.name} "
                f"(x={position.x}, y={position.y})"
            )
            if hasattr(self, "workflow_status_badge"):
                self.workflow_status_badge.setText("✓ 全流程自动化已顺利完成")
                self.workflow_status_badge.setProperty("state", "success")
                self.workflow_status_badge.style().unpolish(self.workflow_status_badge)
                self.workflow_status_badge.style().polish(self.workflow_status_badge)
                self.workflow_status_badge.update()
        except Exception as exc:
            self.set_step_state(current_step, "failed", str(exc))
            self.write_log(f"WeGame 删包或重开失败：{exc}")


    # ── Debug & Step Status Management ──────────────────────────────────────

    def set_step_state(self, step_id: str, state: str, detail: str = "") -> None:
        """Update step button state ('idle' | 'running' | 'success' | 'failed') and global badge."""
        step_info = getattr(self, "_step_buttons", {}).get(step_id)
        title = step_info["title"] if step_info else step_id
        if step_info:
            btn = step_info["button"]
            base_text = step_info["base_text"]

            btn.setProperty("stepState", state)
            if state == "running":
                btn.setText(f"⏳ {title}...")
            elif state == "success":
                btn.setText(f"✓ {title}")
            elif state == "failed":
                btn.setText(f"✕ {title}")
            else:
                btn.setText(base_text)

            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

        # Update global workflow status badge
        if hasattr(self, "workflow_status_badge"):
            if state == "running":
                badge_text = f"⏳ 正在执行：{title}" + (f" ({detail})" if detail else "")
                self.workflow_status_badge.setText(badge_text)
                self.workflow_status_badge.setProperty("state", "running")
            elif state == "success":
                badge_text = f"✓ 步骤完成：{title}"
                self.workflow_status_badge.setText(badge_text)
                self.workflow_status_badge.setProperty("state", "success")
            elif state == "failed":
                badge_text = f"✕ 步骤失败：{title}" + (f" ({detail})" if detail else "")
                self.workflow_status_badge.setText(badge_text)
                self.workflow_status_badge.setProperty("state", "failed")

            self.workflow_status_badge.style().unpolish(self.workflow_status_badge)
            self.workflow_status_badge.style().polish(self.workflow_status_badge)
            self.workflow_status_badge.update()

        QApplication.processEvents()

    def update_nav_substep_pills(self, active_index: int) -> None:
        """Update 10 navigation sub-step pills: done, active, or idle."""
        if not hasattr(self, "sub_step_pills"):
            return
        for idx, pill in enumerate(self.sub_step_pills):
            if idx < active_index:
                pill_state = "done"
            elif idx == active_index:
                pill_state = "active"
            else:
                pill_state = ""
            pill.setProperty("pillState", pill_state)
            pill.style().unpolish(pill)
            pill.style().polish(pill)
            pill.update()
        QApplication.processEvents()

    def reset_all_step_states(self) -> None:
        """Reset all buttons and sub-step pills to idle."""
        if hasattr(self, "_step_buttons"):
            for step_id, info in self._step_buttons.items():
                btn = info["button"]
                btn.setProperty("stepState", "idle")
                btn.setText(info["base_text"])
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()

        if hasattr(self, "sub_step_pills"):
            for pill in self.sub_step_pills:
                pill.setProperty("pillState", "")
                pill.style().unpolish(pill)
                pill.style().polish(pill)
                pill.update()

        if hasattr(self, "workflow_status_badge"):
            self.workflow_status_badge.setText("● 待命就绪")
            self.workflow_status_badge.setProperty("state", "idle")
            self.workflow_status_badge.style().unpolish(self.workflow_status_badge)
            self.workflow_status_badge.style().polish(self.workflow_status_badge)
            self.workflow_status_badge.update()

        QApplication.processEvents()

    def _toggle_debug_panel(self) -> None:
        if self.debug_body.isVisible():
            self.debug_body.hide()
            self.debug_toggle_button.setText("展开")
        else:
            self.debug_body.show()
            self.debug_toggle_button.setText("收起")
        self.adjustSize()

    def _dbg_require_bound(self) -> bool:
        """Return True if WeGame window is bound; log an error otherwise."""
        if self.bound_window is None:
            self.write_log("⚠️ 调试：需要先绑定 WeGame 窗口才能使用此功能。")
            return False
        return True

    def _dbg_takeover_navigation(self) -> None:
        """Resume game navigation from the current step (skips WeGame launch)."""
        if not self._dbg_require_bound():
            return
        game_process = self.workflow.find_game_process()
        if game_process is None:
            self.write_log("调试：未检测到游戏进程，请先启动三角洲行动再使用此功能。")
            self.set_step_state("nav_game", "failed", "未检测到游戏进程")
            return

        self.set_step_state("nav_game", "running")
        self.update_nav_substep_pills(0)
        self.write_log(
            f"调试：检测到游戏进程 {game_process.name} | pid={game_process.process_id}，接管导航..."
        )
        event = self.workflow.start_game_navigation(game_process)
        self.write_log(event.message)
        self.navigation_timer.start()
        self.start_card_mail_button.setEnabled(False)
        self.pause_resume_button.setEnabled(True)
        self._set_pause_button_state(is_paused=False)
        self.stop_button.setEnabled(True)
        self.resync_button.setEnabled(True)
        self.advance_game_navigation()

    def _dbg_wait_wegame(self) -> None:
        if not self._dbg_require_bound():
            return
        self.set_step_state("wait_wegame", "running")
        self.write_log("调试：等待 WeGame 启动按钮出现...")
        try:
            self.workflow.wait_for_wegame_ready(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
                timeout=getattr(self.config, "wegame_ready_timeout_seconds", 60),
            )
            self.set_step_state("wait_wegame", "success")
            self.write_log("调试：WeGame 启动按钮已出现 ✓")
        except Exception as exc:
            self.set_step_state("wait_wegame", "failed", str(exc))
            self.write_log(f"调试：等待 WeGame 启动按钮失败：{exc}")

    def _dbg_click_more(self) -> None:
        if not self._dbg_require_bound():
            return
        self.set_step_state("click_more", "running")
        self.write_log("调试：点击 WeGame 更多按钮（...）...")
        try:
            pos = self.workflow.click_wegame_more(
                self.bound_window,
                getattr(self.config, "wegame_more_template", "wegame_more.png"),
                self.config.template_match_threshold,
            )
            self.set_step_state("click_more", "success")
            self.write_log(f"调试：已点击更多按钮 (x={pos.x}, y={pos.y}) ✓")
        except Exception as exc:
            self.set_step_state("click_more", "failed", str(exc))
            self.write_log(f"调试：点击更多按钮失败：{exc}")

    def _dbg_assets_manage(self) -> None:
        if not self._dbg_require_bound():
            return
        self.set_step_state("assets_manage", "running")
        self.write_log("调试：点击游戏资源包管理...")
        try:
            pos = self.workflow.click_assets_manage(
                self.bound_window,
                getattr(self.config, "wegame_assets_manage_template", "wegame_assets_manage.png"),
                self.config.template_match_threshold,
            )
            self.set_step_state("assets_manage", "success")
            self.write_log(f"调试：已打开资源包管理 (x={pos.x}, y={pos.y}) ✓")
        except Exception as exc:
            self.set_step_state("assets_manage", "failed", str(exc))
            self.write_log(f"调试：打开资源包管理失败：{exc}")

    def _dbg_delete_changgong(self) -> None:
        if not self._dbg_require_bound():
            return
        self.set_step_state("delete_map", "running")
        self.write_log("调试：在资源管理窗口中查找并删除长弓溪谷（会自动向下滚动）...")
        try:
            pos = self.workflow.delete_changgong_map(
                getattr(self.config, "wegame_delete_map_template", "wegame_delete_map.png"),
                self.config.template_match_threshold,
                timeout=getattr(self.config, "delete_map_timeout_seconds", 30),
            )
            self.set_step_state("delete_map", "success")
            self.write_log(f"调试：已点击删除长弓溪谷 (x={pos.x}, y={pos.y}) ✓")
        except Exception as exc:
            self.set_step_state("delete_map", "failed", str(exc))
            self.write_log(f"调试：删除长弓溪谷失败：{exc}")

    def _dbg_restart_game(self) -> None:
        if not self._dbg_require_bound():
            return
        self.set_step_state("restart_game", "running")
        self.write_log("调试：点击 WeGame 启动按钮重新启动游戏...")
        try:
            position, template_path = self.workflow.click_start_button(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
            )
            self.set_step_state("restart_game", "success")
            self.write_log(
                f"调试：已点击启动按钮 {template_path.name} (x={position.x}, y={position.y}) ✓"
            )
        except Exception as exc:
            self.set_step_state("restart_game", "failed", str(exc))
            self.write_log(f"调试：重新启动游戏失败：{exc}")

    def _dbg_rename_pak(self) -> None:
        if not self.config.game_install_dir:
            self.write_log("调试：未配置游戏安装目录，请先填写安装目录。")
            self.set_step_state("rename_pak", "failed", "未配置游戏安装目录")
            return
        self.set_step_state("rename_pak", "running")
        self.write_log("调试：重命名 pak 文件...")
        try:
            results = self.workflow.rename_pak_files(
                self.config.game_install_dir,
                self.config.pak_file_names,
            )
            self.set_step_state("rename_pak", "success")
            for msg in results:
                self.write_log(f"调试：{msg}")
        except OSError as exc:
            self.set_step_state("rename_pak", "failed", str(exc))
            self.write_log(f"调试：重命名 pak 文件失败：{exc}")

    def _dbg_open_paks(self) -> None:
        if not self.config.game_install_dir:
            self.write_log("调试：未配置游戏安装目录，请先填写安装目录。")
            self.set_step_state("open_paks", "failed", "未配置游戏安装目录")
            return
        paks_path = (
            Path(self.config.game_install_dir)
            / "DeltaForce"
            / "PackContent"
            / "Paks"
        )
        self.set_step_state("open_paks", "running")
        try:
            subprocess.Popen(["explorer", str(paks_path)])
            self.set_step_state("open_paks", "success")
            self.write_log(f"调试：已打开 Paks 目录：{paks_path}")
        except OSError as exc:
            self.set_step_state("open_paks", "failed", str(exc))
            self.write_log(f"调试：打开 Paks 目录失败：{exc}")


