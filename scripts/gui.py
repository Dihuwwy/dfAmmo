from __future__ import annotations

import ctypes
import ctypes.wintypes

import win32api
import win32con
import win32gui

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from scripts.config import AppConfig
from scripts.gui_actions import ActionsMixin
from scripts.gui_builder import BuilderMixin
from scripts.template_capture import TemplateCaptureOverlay
from scripts.window_binding import BoundWindow
from scripts.workflow import Workflow


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
        self.setMinimumSize(700, 600)
        self._build_ui()
        self._init_window_geometry()
        self.write_log("请先绑定 WeGame 主窗口（如游戏已在运行，可直接点击“开始卡邮件”）。")

    def _init_window_geometry(self) -> None:
        """Let Qt compute natural window size from layout sizeHint, then clamp to 85% screen and center."""
        self.adjustSize()

        screen = QApplication.primaryScreen()
        if screen is None:
            return

        avail = screen.availableGeometry()
        w = min(self.width(), int(avail.width() * 0.85))
        h = min(self.height(), int(avail.height() * 0.85))
        self.resize(w, h)

        geo = self.geometry()
        geo.moveCenter(avail.center())
        self.setGeometry(geo)

    def _check_hotkey(self) -> None:
        now = time_val = win32api.GetTickCount() / 1000.0
        try:
            if win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000:
                if time_val - self._last_hotkey_time >= 0.35:
                    self._last_hotkey_time = time_val
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
                now = win32api.GetTickCount() / 1000.0
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
