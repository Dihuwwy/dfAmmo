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

        self.hotkey_registered = False
        try:
            self.hotkey_registered = bool(
                win32gui.RegisterHotKey(int(self.winId()), 1001, 0, win32con.VK_F12)
            )
        except Exception:
            self.hotkey_registered = False

        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.setInterval(80)
        self.hotkey_timer.timeout.connect(self._check_hotkey)
        self.hotkey_timer.start()

        self.setWindowTitle(self.config.window_title)
        self.setObjectName("mainWindow")
        self.resize(760, 600)
        self._build_ui()
        self.write_log("请先绑定 WeGame 主窗口。")

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
        self.capture_button = QPushButton("采集元素模板")
        self.start_card_mail_button = QPushButton("开始卡邮件")
        self.stop_button = QPushButton("强行停止 (F12)")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.emergency_stop)
        self.rebind_button = QPushButton("重新绑定")
        self.rebind_button.setObjectName("secondaryButton")
        self.capture_button.clicked.connect(self.start_template_capture)
        self.start_card_mail_button.clicked.connect(self.start_card_mail)
        self.rebind_button.clicked.connect(self.reset_binding)
        button_row.addWidget(self.start_card_mail_button)
        button_row.addWidget(self.stop_button)
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
        self.log_output.setFixedHeight(130)
        self.log_output.document().setMaximumBlockCount(200)
        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_output)

        root.addWidget(title)
        root.addWidget(self.subtitle)
        root.addWidget(self.bind_panel, stretch=1)
        root.addWidget(self.feature_panel, stretch=1)
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
        self.stop_button.setEnabled(False)
        self.bound_window = None
        self.feature_panel.hide()
        self.bind_panel.show()
        self.subtitle.setText("先绑定 WeGame 主窗口，绑定成功后再显示可用功能。")
        self.write_log("已解除窗口绑定，请重新选择 WeGame 窗口。")

    def emergency_stop(self) -> None:
        was_running = self.navigation_timer.isActive() or self.game_process_timer.isActive()
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.workflow.cancel_game_navigation()
        self.start_card_mail_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        # Re-activate and bring this Assistant window to top
        self.showNormal()
        self.activateWindow()
        self.raise_()
        try:
            win32gui.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass

        if was_running:
            self.write_log("🛑【强行停止】已通过 F12 快捷键强行停止当前所有自动化！")
        else:
            self.write_log("🛑【强行停止】当前无正在运行的自动化任务。")

    def _check_hotkey(self) -> None:
        try:
            if win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000:
                if self.navigation_timer.isActive() or self.game_process_timer.isActive():
                    self.emergency_stop()
        except Exception:
            pass

    def nativeEvent(self, event_type, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == win32con.WM_HOTKEY and msg.wParam == 1001:
                self.emergency_stop()
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
        self.log_output.appendPlainText(f"[{timestamp}] {message}")

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
        self.stop_button.setEnabled(True)
        self.game_process_deadline = time.monotonic() + self.config.game_process_timeout_seconds
        self.write_log(
            "已点击启动元素："
            f"x={position.x}, y={position.y}, "
            f"confidence={position.confidence:.3f}, template={template_path.name}"
        )
        self.write_log("正在等待三角洲行动游戏进程...")
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
            event = self.workflow.start_game_navigation(game_process)
            self.write_log(event.message)
            self.navigation_timer.start()
            self.advance_game_navigation()
            return

        if time.monotonic() >= self.game_process_deadline:
            self.game_process_timer.stop()
            self.start_card_mail_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.write_log(
                f"等待游戏进程超时（{self.config.game_process_timeout_seconds} 秒）。"
            )

    def advance_game_navigation(self) -> None:
        try:
            event = self.workflow.advance_game_navigation()
        except Exception as exc:
            self.navigation_timer.stop()
            self.start_card_mail_button.setEnabled(True)
            self.write_log(f"自动导航失败：{exc}")
            return

        if event is None:
            return

        self.write_log(event.message)
        if event.status in (NavigationStatus.COMPLETE, NavigationStatus.FAILED):
            self.navigation_timer.stop()
            self.start_card_mail_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            if event.status == NavigationStatus.COMPLETE:
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

                if self.config.game_install_dir:
                    paks_path = (
                        Path(self.config.game_install_dir)
                        / "DeltaForce"
                        / "PackContent"
                        / "Paks"
                    )
                    if not paks_path.is_dir():
                        self.write_log(f"Paks 目录不存在，请检查安装目录：{paks_path}")
                        return

                    try:
                        subprocess.Popen(["explorer", str(paks_path)])
                    except OSError as exc:
                        self.write_log(f"打开 Paks 目录失败：{exc}")
                        return
                    self.write_log(f"已打开 Paks 目录：{paks_path}")

                    try:
                        results = self.workflow.rename_pak_files(
                            self.config.game_install_dir,
                            self.config.pak_file_names,
                        )
                    except OSError as exc:
                        self.write_log(f"重命名 pak 文件失败：{exc}")
                    else:
                        for message in results:
                            self.write_log(message)
                else:
                    self.write_log("未配置游戏安装目录，跳过 pak 文件重命名。")

                if self.bound_window is not None:
                    self._run_wegame_post_process()

    def _run_wegame_post_process(self) -> None:
        if self.bound_window is None:
            return

        self.write_log("正在等待 WeGame 启动按钮重新出现...")
        QApplication.processEvents()

        try:
            self.workflow.wait_for_wegame_ready(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
                timeout=getattr(self.config, "wegame_ready_timeout_seconds", 60),
            )
            self.write_log("WeGame 启动按钮已重新出现。")
            QApplication.processEvents()

            self.write_log("正在点击更多选项（...）...")
            self.workflow.click_wegame_more(
                self.bound_window,
                getattr(self.config, "wegame_more_template", "wegame_more.png"),
                self.config.template_match_threshold,
            )
            self.write_log("已点击更多选项。")
            QApplication.processEvents()
            time.sleep(0.5)

            self.write_log("正在打开游戏资源包管理...")
            self.workflow.click_assets_manage(
                self.bound_window,
                getattr(self.config, "wegame_assets_manage_template", "wegame_assets_manage.png"),
                self.config.template_match_threshold,
            )
            self.write_log("已打开游戏资源包管理。")
            QApplication.processEvents()
            time.sleep(1.0)

            self.write_log("正在等待资源管理窗口并删除长弓溪谷资源包...")
            pos = self.workflow.delete_changgong_map(
                getattr(self.config, "wegame_delete_map_template", "wegame_delete_map.png"),
                self.config.template_match_threshold,
                timeout=getattr(self.config, "delete_map_timeout_seconds", 30),
            )
            self.write_log(f"已点击删除长弓溪谷资源包（x={pos.x}, y={pos.y}）。")
            QApplication.processEvents()

            time.sleep(1.2)
            self.write_log("切回 WeGame 窗口，准备重新拉起游戏...")
            position, template_path = self.workflow.click_start_button(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
            )
            self.write_log(
                f"已重新点击启动按钮，游戏正在拉起：{template_path.name} "
                f"(x={position.x}, y={position.y})"
            )
        except Exception as exc:
            self.write_log(f"WeGame 删包或重开失败：{exc}")
