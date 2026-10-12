from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from scripts.config import APP_ICON_PATH, PROJECT_ROOT
from scripts.update_service import REPO_URL, Release, UpdateCancelled, UpdateService
from scripts.version import current_version
from scripts.styles import COLOR_TEXT_DISABLED, COLOR_SURFACE_SECONDARY, COLOR_BORDER_SUBTLE


class UpdateWorker(QObject):
    finished = Signal(str, object)
    progress = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.busy = False
        self.closed = False
        self.cancelled = threading.Event()

    def start(self, kind, operation):
        if self.busy or self.closed:
            return False
        self.busy = True
        self.cancelled.clear()
        def execute():
            try:
                result = operation()
            except Exception as exc:
                result = exc
            if not self.closed:
                self.finished.emit(kind, result)
        threading.Thread(target=execute, daemon=True, name="dfAmmo-update").start()
        return True

    def report(self, message):
        if not self.closed:
            self.progress.emit(message)


class UpdateMixin:
    def _init_updates(self):
        self.app_version = current_version()
        self.update_worker = UpdateWorker(self)
        self.update_service = UpdateService(self.app_version, report=self.update_worker.report,
                                            cancelled=self.update_worker.cancelled)
        self.update_worker.finished.connect(self._update_finished, Qt.ConnectionType.QueuedConnection)
        self.update_worker.progress.connect(self.write_log, Qt.ConnectionType.QueuedConnection)
        self.available_release: Release | None = None
        self.about_dialog = None
        self._update_plan: Path | None = None
        self._update_installing = False
        self._auto_update_pending = False
        self._apply_update_timer = QTimer(self)
        self._apply_update_timer.setSingleShot(True)
        self._apply_update_timer.timeout.connect(self._handoff_update)
        self._auto_update_timer = QTimer(self)
        self._auto_update_timer.setInterval(3000)
        self._auto_update_timer.timeout.connect(self._try_auto_update)

    def startup_updates(self):
        result_path = PROJECT_ROOT / ".updates" / "result.json"
        if result_path.is_file():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                message = (f"已更新至 v{result['version']}。" if result.get("ok")
                           else f"更新未完成：{result.get('message', '未知错误')}。")
                self.write_log(message)
                result_path.unlink()
            except (OSError, ValueError, KeyError) as exc:
                self.write_log(f"读取更新结果失败：{exc}")
        if self.config.check_updates_on_startup:
            QTimer.singleShot(1200, self.check_updates)

    def show_about(self):
        if self.about_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("关于 dfAmmo")
            dialog.setWindowIcon(QIcon(str(APP_ICON_PATH)))
            dialog.setMinimumWidth(420)
            dialog.setStyleSheet(f"QPushButton#secondaryButton:disabled {{ color: {COLOR_TEXT_DISABLED}; "
                                f"background-color: {COLOR_SURFACE_SECONDARY}; border-color: {COLOR_BORDER_SUBTLE}; }}")
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(22, 20, 22, 20)
            layout.setSpacing(14)
            heading = QHBoxLayout()
            icon = QLabel()
            icon.setPixmap(QIcon(str(APP_ICON_PATH)).pixmap(48, 48))
            icon.setFixedSize(48, 48)
            title = QLabel("dfAmmo")
            title.setStyleSheet("font-size: 24px; font-weight: 600;")
            heading.addWidget(icon)
            heading.addWidget(title)
            heading.addStretch()
            layout.addLayout(heading)
            runtime = "EXE 便携版" if getattr(sys, "frozen", False) else "源码版"
            layout.addWidget(QLabel(f"版本 {self.app_version}  ·  {runtime}"))
            repo = QLabel(f'<a href="{REPO_URL}">GitHub 项目主页</a>')
            repo.setOpenExternalLinks(True)
            layout.addWidget(repo)
            self.startup_check_box = QCheckBox("启动时检查更新")
            self.startup_check_box.setChecked(self.config.check_updates_on_startup)
            self.auto_update_box = QCheckBox("自动安装更新（任务空闲时）")
            self.auto_update_box.setChecked(self.config.auto_update)
            self.startup_check_box.toggled.connect(lambda checked: self._save_update_setting("check_updates_on_startup", checked))
            self.auto_update_box.toggled.connect(lambda checked: self._save_update_setting("auto_update", checked))
            layout.addWidget(self.startup_check_box)
            layout.addWidget(self.auto_update_box)
            buttons = QHBoxLayout()
            self.check_update_button = QPushButton("检查更新")
            self.install_update_button = QPushButton("更新并重启")
            self.cancel_update_button = QPushButton("取消更新")
            self.check_update_button.clicked.connect(self.check_updates)
            self.install_update_button.clicked.connect(self.install_update)
            self.cancel_update_button.clicked.connect(self.cancel_update)
            for button in (self.check_update_button, self.install_update_button, self.cancel_update_button):
                button.setObjectName("secondaryButton")
                buttons.addWidget(button)
            layout.addLayout(buttons)
            self.about_dialog = dialog
        self._sync_update_buttons()
        self.about_dialog.show()
        self.about_dialog.raise_()
        self.about_dialog.activateWindow()

    def _save_update_setting(self, field, checked):
        self.config = replace(self.config, **{field: checked})
        try:
            self.config.save_to_file()
        except OSError as exc:
            self.write_log(f"更新设置保存失败：{exc}")
        if field == "auto_update":
            if checked and self.available_release is not None:
                self._auto_update_pending = True
                self._auto_update_timer.start()
            elif not checked:
                self._auto_update_pending = False
                self._auto_update_timer.stop()

    def _automation_active(self):
        return (self.task_runner.busy or self.navigation_timer.isActive() or self.game_process_timer.isActive()
                or self.workflow.is_navigation_paused
                or (self.capture_overlay is not None and self.capture_overlay.isVisible()))

    def _sync_update_buttons(self):
        if self.about_dialog is None:
            return
        pending = self._update_plan is not None
        self.check_update_button.setEnabled(not self.update_worker.busy and not pending)
        self.install_update_button.setEnabled(self.available_release is not None and not self.update_worker.busy and not pending)
        self.cancel_update_button.setEnabled(self.update_worker.busy or pending or self._auto_update_pending)

    def check_updates(self):
        if self.update_worker.busy or self._update_plan is not None or self.update_worker.closed:
            return
        self.available_release = None
        self.write_log(f"正在检查更新，当前版本 v{self.app_version}。")
        self.update_worker.start("check", self.update_service.check_latest)
        self._sync_update_buttons()

    def install_update(self):
        if self.update_worker.busy or self._update_plan is not None:
            return
        if self.available_release is None:
            self.write_log("请先在“关于”中检查更新。")
            return
        if self._automation_active():
            self.write_log("当前任务尚未结束，请停止任务后再更新。")
            return
        release = self.available_release
        self._auto_update_pending = False
        self._auto_update_timer.stop()
        self.write_log(f"正在准备更新至 v{release.version}。")
        self._lock_update_controls(True)
        self.update_worker.start("prepare", lambda: self.update_service.prepare(release))
        self._sync_update_buttons()

    def _lock_update_controls(self, locked):
        self.feature_panel.setEnabled(not locked)
        self.debug_panel.setEnabled(not locked)
        self.bind_button.setEnabled(not locked)

    def _update_finished(self, kind, result):
        if self.update_worker.closed:
            return
        self.update_worker.busy = False
        if isinstance(result, Exception) or self.update_worker.cancelled.is_set():
            self.write_log(str(result) if isinstance(result, UpdateCancelled) else
                           "已取消更新。" if self.update_worker.cancelled.is_set() else f"更新失败：{result}")
            self._update_plan = None
            self._lock_update_controls(False)
        elif kind == "check":
            self.available_release = result
            if result is None:
                self.write_log("没有可用的新版本。")
            else:
                self.write_log(f"发现新版 v{result.version}，可在“关于”中点击“更新并重启”。")
                if self.config.auto_update:
                    self._auto_update_pending = True
                    self._auto_update_timer.start()
                    self._try_auto_update()
        elif kind == "prepare":
            self._update_plan = result
            self.write_log("更新已就绪，5 秒后退出安装并重启；可在“关于”中取消更新。")
            self._apply_update_timer.start(5000)
        elif kind == "handoff":
            self._update_installing = True
            self.write_log("更新助手已启动，正在退出程序以安装更新。")
            self._flush_log_buffer()
            self.close()
            QApplication.instance().quit()
            return
        self._sync_update_buttons()

    def _try_auto_update(self):
        if not self._auto_update_pending or not self.config.auto_update:
            self._auto_update_timer.stop()
            return
        if not self.update_worker.busy and not self._automation_active() and self._update_plan is None:
            self.install_update()

    def _handoff_update(self):
        if self._update_plan is None:
            return
        if self._automation_active():
            self.write_log("检测到任务仍在运行，已取消安装更新。")
            self.cancel_update()
            return
        path = self._update_plan
        self.update_worker.start("handoff", lambda: self.update_service.launch_helper(path))
        self._sync_update_buttons()

    def cancel_update(self):
        self.update_worker.cancelled.set()
        self._apply_update_timer.stop()
        self._auto_update_timer.stop()
        self._auto_update_pending = False
        if self._update_plan is not None:
            (self._update_plan.parent / "cancel").touch()
            self._update_plan = None
        if not self.update_worker.busy:
            self._lock_update_controls(False)
        self.write_log("已请求取消更新。")
        self._sync_update_buttons()

    def _shutdown_updates(self):
        if not self._update_installing and (self.update_worker.busy or self._update_plan is not None or self._auto_update_pending):
            self.cancel_update()
        self.update_worker.closed = True
        self._apply_update_timer.stop()
        self._auto_update_timer.stop()
