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
        self.setMinimumSize(820, 560)
        self._build_ui()
        self._init_window_geometry()
        self.write_log("请先绑定 WeGame 主窗口（如游戏已在运行，可直接点击“开始卡邮件”）。")

    def _init_window_geometry(self) -> None:
        """Restore previous window geometry/splitter if saved, or compute true content size and center."""
        settings = QSettings("dfAmmo", "Assistant")
        saved_geo = settings.value("geometry")
        saved_splitter = settings.value("splitter")

        if saved_geo and self.restoreGeometry(saved_geo):
            if saved_splitter:
                self.main_splitter.restoreState(saved_splitter)
            return

        # Optimal initial size derived from actual content cards (avoiding QScrollArea dummy sizeHint)
        content_w = max(
            self.left_column.sizeHint().width() + 32,
            self.bind_panel.sizeHint().width() + 32,
            860,
        )
        content_h = (
            self.bind_panel.sizeHint().height()
            + self.left_column.sizeHint().height()
            + 190
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
        top_h = min(self.left_column.sizeHint().height() + 10, int(h * 0.70))
        self.main_splitter.setSizes([top_h, max(100, h - top_h - self.bind_panel.height())])

        if screen is not None:
            geo = self.geometry()
            geo.moveCenter(screen.availableGeometry().center())
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
        settings = QSettings("dfAmmo", "Assistant")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("splitter", self.main_splitter.saveState())

        if getattr(self, "hotkey_registered", False):
            try:
                win32gui.UnregisterHotKey(int(self.winId()), 1001)
            except Exception:
                pass
        super().closeEvent(event)

