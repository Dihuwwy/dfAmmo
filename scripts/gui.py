from __future__ import annotations

from pathlib import Path

import win32api
import win32con
import win32gui

from PySide6.QtCore import QObject, QRect, QSettings, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QCursor, QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine, QQmlPropertyMap
from PySide6.QtQuickControls2 import QQuickStyle

from scripts.config import APP_ICON_PATH, AppConfig
from scripts.dpi import physical_coordinates
from scripts.gui_actions import ActionsMixin
from scripts.template_capture import TemplateCaptureOverlay
from scripts.window_binding import BoundWindow
from scripts.workflow import Workflow
from scripts.task_runner import TaskRunner
from scripts.update_ui import UpdateMixin


QML_DIR = Path(__file__).resolve().parent / "qml"


def _first_installed(families: tuple[str, ...]) -> str:
    installed = set(QFontDatabase.families())
    return next((family for family in families if family in installed), families[-1])


class MainController(ActionsMixin, UpdateMixin, QObject):
    """Owns the workflows and publishes view state to the Qt Quick window.

    QML reads the `ui` property map and calls the slots below; it never
    reaches into the workflow, and the workflow never touches QML items.
    """

    logAppended = Signal(str)
    logReset = Signal(str)
    toast = Signal(str, str)

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
        self.workflow.game_navigator.configure_map(self.config)
        self.capture_overlay: TemplateCaptureOverlay | None = None
        self.pending_template_name = ""
        self.game_process_deadline = 0.0
        self._execution_mode = "continuous"
        self._navigation_mode = "continuous"
        self._continue_after_navigation = True
        self._resume_step = None
        self._binding = False
        self._closed = False
        self._log_buffer: list[tuple[str, str]] = []
        self._log_lines: list[tuple[str, str]] = []
        self._ui_state: dict = {}
        self.ui = QQmlPropertyMap(self)

        self.task_runner = TaskRunner(self.workflow.control, self)
        self.task_runner.progress.connect(self.write_log)
        self.workflow.report_progress = self.task_runner.progress.emit
        self.task_runner.busy_changed.connect(self._on_worker_busy_changed)
        self.task_runner.failed.connect(self._on_worker_failed)

        self.game_process_timer = QTimer(self)
        self.game_process_timer.setInterval(self.config.game_process_poll_interval_ms)
        self.game_process_timer.timeout.connect(self.check_game_process)

        self.navigation_timer = QTimer(self)
        self.navigation_timer.setInterval(self.config.navigation_poll_interval_ms)
        self.navigation_timer.timeout.connect(self.advance_game_navigation)

        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(150)
        self._log_flush_timer.timeout.connect(self._flush_log_buffer)
        self._log_flush_timer.start()

        self._hotkey_down = False
        # RegisterHotKey is disabled; polling observes keys without reserving them.
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.setInterval(60)
        self.hotkey_timer.timeout.connect(self._check_hotkey)
        self.hotkey_timer.start()

        self._init_state()
        self._init_updates()
        self._load_window()
        self._restore_geometry()
        self.write_log("请先绑定 WeGame 主窗口（如游戏已在运行，可直接点击“开始卡邮件”）。")

    # ── View Setup ───────────────────────────────────────────────────────────

    def _init_state(self) -> None:
        """Publish every key the view binds to before QML is loaded."""
        ui_font = _first_installed(("HarmonyOS Sans SC", "Microsoft YaHei UI", "Segoe UI"))
        # Latin from a monospace face, Chinese from the interface font rather than a serif fallback.
        log_font = QFont()
        log_font.setFamilies([_first_installed(("JetBrains Mono", "Cascadia Mono", "Cascadia Code", "Consolas")), ui_font])
        log_font.setPixelSize(12)
        self._set_ui(
            windowTitle=self.config.window_title,
            iconUrl=QUrl.fromLocalFile(str(APP_ICON_PATH)).toString(),
            uiFont=ui_font,
            logFont=log_font,
            iconFont=_first_installed(("Segoe Fluent Icons", "Segoe MDL2 Assets")),
            connected=False,
            connTitle="未绑定窗口",
            connSubtitle="",
            connTooltip="",
            gameDir=self.config.game_install_dir,
            operationMode=self.config.operation_mode,
            mapId=self.config.map_id,
            fillTeammates=self.config.check_fill_teammates,
            executionMode=self._execution_mode,
            startEnabled=True,
            continueEnabled=False,
            paused=False,
            stopEnabled=False,
            mapEnabled=True,
            controlsLocked=False,
        )
        self._set_status("待命就绪", "idle")
        self._build_steps()
        self._sync_pak_button_state()

    def _load_window(self) -> None:
        QQuickStyle.setStyle("Basic")
        self.engine = QQmlApplicationEngine(self)
        errors: list[str] = []
        self.engine.warnings.connect(lambda warnings: errors.extend(item.toString() for item in warnings))
        self.engine.addImportPath(str(QML_DIR))
        context = self.engine.rootContext()
        context.setContextProperty("backend", self)
        context.setContextProperty("ui", self.ui)
        self.engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        if not self.engine.rootObjects():
            raise RuntimeError("界面加载失败：\n" + "\n".join(errors or [str(QML_DIR / "Main.qml")]))
        self.window = self.engine.rootObjects()[0]
        self.window.setIcon(QIcon(str(APP_ICON_PATH)))

    def _restore_geometry(self) -> None:
        saved = QSettings("dfAmmo", "Assistant").value("quick/geometry")
        if isinstance(saved, QRect) and any(
                screen.availableGeometry().intersects(saved) for screen in QGuiApplication.screens()):
            self.window.setGeometry(saved)
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = max(self.window.minimumWidth(), min(self.window.width(), int(available.width() * 0.9)))
        height = max(self.window.minimumHeight(), min(self.window.height(), int(available.height() * 0.9)))
        self.window.setGeometry(available.x() + (available.width() - width) // 2,
                                available.y() + (available.height() - height) // 2, width, height)

    # ── Window ───────────────────────────────────────────────────────────────

    def show(self) -> None:
        self.window.show()

    def _show_window(self) -> None:
        self.window.show()

    def _hide_window(self) -> None:
        self.window.hide()

    def _window_handle(self) -> int:
        return int(self.window.winId())

    def _bring_to_front(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.requestActivate()
        try:
            win32gui.SetForegroundWindow(self._window_handle())
        except Exception:
            pass

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._shutdown_updates()
        for timer in (self.game_process_timer, self.navigation_timer, self.hotkey_timer, self._log_flush_timer):
            timer.stop()
        self.task_runner.shutdown()
        self.workflow.cancel_game_navigation()

    @Slot()
    def windowClosing(self) -> None:
        if not self._closed:
            QSettings("dfAmmo", "Assistant").setValue("quick/geometry", self.window.geometry())
        self.shutdown()
        QGuiApplication.quit()

    # ── Worker and Hotkeys ───────────────────────────────────────────────────

    def _on_worker_busy_changed(self, busy: bool) -> None:
        running = self.navigation_timer.isActive() or self.game_process_timer.isActive()
        paused = self.workflow.is_navigation_paused
        self._set_ui(
            mapEnabled=not (busy or running or paused or bool(self._resume_step)),
            startEnabled=not (busy or running or paused),
            stopEnabled=busy or running or paused,
            continueEnabled=not busy and not running and (paused or self._resume_step is not None),
        )

    def _on_worker_failed(self, message: str) -> None:
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.workflow.cancel_game_navigation()
        self._set_running_controls(False)
        self.write_log(f"后台任务失败：{message}")

    def _check_hotkey(self) -> None:
        f12 = bool(win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000)
        shift = bool(win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000)
        ctrl = bool(win32api.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000)
        down = f12 and (shift or ctrl)
        if down and not self._hotkey_down:
            self.emergency_stop() if shift else self.continue_navigation()
        self._hotkey_down = down

    # ── Slots called from QML ────────────────────────────────────────────────

    @Slot()
    def startCardMail(self) -> None:
        self.start_card_mail()

    @Slot()
    def continueNavigation(self) -> None:
        self.continue_navigation()

    @Slot()
    def emergencyStop(self) -> None:
        self.emergency_stop()

    @Slot()
    def takeoverNavigation(self) -> None:
        self._dbg_takeover_navigation()

    @Slot()
    def resetStates(self) -> None:
        self.reset_all_step_states()

    @Slot(int)
    def jumpToStep(self, index: int) -> None:
        self._on_step_pill_clicked(index)

    @Slot(str)
    def runStep(self, step_id: str) -> None:
        self.run_step(step_id)

    @Slot()
    def beginBind(self) -> None:
        self._binding = True
        QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.CrossCursor))

    @Slot()
    def endBind(self) -> None:
        if not self._binding:
            return
        self.cancelBind()
        # Qt reports logical pixels on a scaled desktop; binding needs the
        # same physical coordinates as the later screenshots and clicks.
        with physical_coordinates():
            x, y = win32api.GetCursorPos()
        self.bind_window_at(x, y)

    @Slot()
    def cancelBind(self) -> None:
        if self._binding:
            self._binding = False
            QGuiApplication.restoreOverrideCursor()

    @Slot(str)
    def setGameDir(self, path: str) -> None:
        self.save_game_dir(path)

    @Slot(result=str)
    def chooseGameDir(self) -> str:
        return self.choose_game_dir()

    @Slot(str)
    def setOperationMode(self, mode: str) -> None:
        self.set_operation_mode(mode)

    @Slot(str)
    def setMapId(self, map_id: str) -> None:
        self.set_map(map_id)

    @Slot(bool)
    def setFillTeammates(self, checked: bool) -> None:
        self.set_fill_teammates(checked)

    @Slot(str)
    def setExecutionMode(self, mode: str) -> None:
        self.set_execution_mode(mode)

    @Slot(str)
    def startTemplateCapture(self, name: str) -> None:
        self.start_template_capture(name)

    @Slot()
    def copyLog(self) -> None:
        self.copy_log()

    @Slot()
    def clearLog(self) -> None:
        self.clear_log()

    @Slot()
    def checkUpdates(self) -> None:
        self.check_updates()

    @Slot()
    def installUpdate(self) -> None:
        self.install_update()

    @Slot()
    def cancelUpdate(self) -> None:
        self.cancel_update()

    @Slot(str)
    def setUpdateChannel(self, channel: str) -> None:
        self._save_update_setting("update_channel", channel)

    @Slot(bool)
    def setCheckOnStartup(self, checked: bool) -> None:
        self._save_update_setting("check_updates_on_startup", checked)

    @Slot(bool)
    def setAutoUpdate(self, checked: bool) -> None:
        self._save_update_setting("auto_update", checked)
