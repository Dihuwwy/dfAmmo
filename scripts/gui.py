from __future__ import annotations

import ctypes
import ctypes.wintypes

import win32api
import win32con
import win32gui

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from scripts.config import AppConfig
from scripts.gui_actions import ActionsMixin
from scripts.gui_builder import BuilderMixin
from scripts.template_capture import TemplateCaptureOverlay
from scripts.window_binding import BoundWindow
from scripts.workflow import Workflow
from scripts.task_runner import TaskRunner


class MainWindow(ActionsMixin, BuilderMixin, QWidget):
    """Main GUI window combining UI construction, event handling, and workflows."""

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
        self.task_runner = TaskRunner(self.workflow.control, self)
        self.task_runner.busy_changed.connect(self._on_worker_busy_changed)
        self.task_runner.failed.connect(self._on_worker_failed)

        self.game_process_timer = QTimer(self)
        self.game_process_timer.setInterval(self.config.game_process_poll_interval_ms)
        self.game_process_timer.timeout.connect(self.check_game_process)

        self.navigation_timer = QTimer(self)
        self.navigation_timer.setInterval(self.config.navigation_poll_interval_ms)
        self.navigation_timer.timeout.connect(self.advance_game_navigation)

        self._hotkey_down = False
        self._registered_hotkeys = set()
        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [ctypes.wintypes.HWND, ctypes.c_int,
                                         ctypes.wintypes.UINT, ctypes.wintypes.UINT]
        user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
        for hotkey_id, modifiers in ((1001, 0), (1002, win32con.MOD_SHIFT)):
            if user32.RegisterHotKey(int(self.winId()), hotkey_id,
                                    modifiers | 0x4000, win32con.VK_F12):
                self._registered_hotkeys.add(hotkey_id)

        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.setInterval(60)
        self.hotkey_timer.timeout.connect(self._check_hotkey)
        self.hotkey_timer.start()

        self.setWindowTitle(self.config.window_title)
        self.setObjectName("mainWindow")
        self.setMinimumSize(820, 560)
        self._build_ui()
        self._init_window_geometry()
        self.write_log("请先绑定 WeGame 主窗口（如游戏已在运行，可直接点击“开始卡邮件”）。")
        if len(self._registered_hotkeys) < 2:
            self.write_log("部分全局快捷键注册失败（可能被占用），已启用按键检测备用方式。")

    def _on_worker_busy_changed(self, busy: bool) -> None:
        running = self.navigation_timer.isActive() or self.game_process_timer.isActive()
        self.start_card_mail_button.setEnabled(not (busy or running or self.workflow.is_navigation_paused))
        self.stop_button.setEnabled(busy or running or self.workflow.is_navigation_paused)
        if not busy and not running and not self.workflow.is_navigation_paused:
            self.pause_resume_button.setEnabled(False)
            self.resync_button.setEnabled(False)

    def _on_worker_failed(self, message: str) -> None:
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.workflow.cancel_game_navigation()
        self._set_running_controls(False)
        self.write_log(f"后台任务失败：{message}")

    def _init_window_geometry(self) -> None:
        """Restore previous window geometry/splitter if saved, or compute true content size and center.
        Guarantees that the upper controls card is never clipped or truncated by old saved splitter ratios.
        """
        settings = QSettings("dfAmmo", "Assistant")
        saved_geo = settings.value("geometry")
        saved_splitter = settings.value("splitter")

        # Dynamic computation of required upper panel height
        req_top_h = self.left_column.sizeHint().height() + 10
        min_log_h = 160
        overhead_h = self.bind_panel.sizeHint().height() + 48

        if saved_geo and self.restoreGeometry(saved_geo):
            if saved_splitter:
                self.main_splitter.restoreState(saved_splitter)

            # Ensure window is tall enough for full top controls + minimum log panel
            needed_window_h = req_top_h + min_log_h + overhead_h
            if self.height() < needed_window_h:
                self.resize(self.width(), needed_window_h)

            # Activate layout so main_splitter receives updated geometry before adjusting sizes
            if self.layout() is not None:
                self.layout().activate()

            avail_splitter_h = self.main_splitter.height()
            sizes = self.main_splitter.sizes()
            if len(sizes) == 2:
                top_h, bottom_h = sizes[0], sizes[1]
                if top_h < req_top_h or bottom_h < min_log_h:
                    target_top = min(req_top_h, max(280, avail_splitter_h - min_log_h))
                    self.main_splitter.setSizes([target_top, max(min_log_h, avail_splitter_h - target_top)])
            return

        # Optimal initial size derived from actual content cards (avoiding QScrollArea dummy sizeHint)
        content_w = max(
            self.left_column.sizeHint().width() + 32,
            self.bind_panel.sizeHint().width() + 32,
            860,
        )
        content_h = (
            self.bind_panel.sizeHint().height()
            + req_top_h
            + 200
            + 40
        )

        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            w = min(content_w, int(avail.width() * 0.90))
            h = min(content_h, int(avail.height() * 0.90))
        else:
            w, h = content_w, content_h

        self.resize(w, h)
        if self.layout() is not None:
            self.layout().activate()

        avail_splitter_h = self.main_splitter.height()
        self.main_splitter.setSizes([req_top_h, max(min_log_h, avail_splitter_h - req_top_h)])

        if screen is not None:
            geo = self.geometry()
            geo.moveCenter(screen.availableGeometry().center())
            self.setGeometry(geo)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._ensure_controls_expanded)

    def _ensure_controls_expanded(self) -> None:
        """Guarantee that the upper controls card is never clipped or truncated after DPI/font rendering."""
        req_top_h = self.left_column.sizeHint().height() + 8
        min_log_h = 160
        overhead_h = self.bind_panel.height() + 48

        needed_window_h = req_top_h + min_log_h + overhead_h
        if self.height() < needed_window_h:
            self.resize(self.width(), needed_window_h)

        if self.layout() is not None:
            self.layout().activate()

        sizes = self.main_splitter.sizes()
        if len(sizes) == 2 and sizes[0] < req_top_h:
            avail = self.main_splitter.height()
            self.main_splitter.setSizes([req_top_h, max(min_log_h, avail - req_top_h)])

    def _check_hotkey(self) -> None:
        down = bool(win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000)
        if down and not self._hotkey_down:
            shift = bool(win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000)
            hotkey_id = 1002 if shift else 1001
            if hotkey_id not in self._registered_hotkeys:
                self.emergency_stop() if shift else self.toggle_pause_resume()
        self._hotkey_down = down

    def nativeEvent(self, event_type, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == win32con.WM_HOTKEY and msg.wParam in (1001, 1002):
                if msg.wParam == 1002:
                    self.emergency_stop()
                else:
                    self.toggle_pause_resume()
                return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event) -> None:
        settings = QSettings("dfAmmo", "Assistant")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("splitter", self.main_splitter.saveState())

        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.hotkey_timer.stop()
        self.task_runner.shutdown()
        self.workflow.cancel_game_navigation()
        for hotkey_id in self._registered_hotkeys:
            try:
                win32gui.UnregisterHotKey(int(self.winId()), hotkey_id)
            except Exception:
                pass
        super().closeEvent(event)
