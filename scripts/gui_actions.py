from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import win32gui

from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
    QWidget,
)

from scripts.game_navigation import NAVIGATION_STEPS, NavigationStatus
from scripts.template_capture import TemplateCaptureOverlay
from scripts.workflow import Workflow


class ActionsMixin:
    """Action handlers, business workflows, and debug runner mixin for MainWindow."""

    # ── UI State Helpers ─────────────────────────────────────────────────────

    def _repaint(self, widget: QWidget) -> None:
        """Force Qt style re-evaluation and repaint for dynamic property changes."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _set_badge(self, badge: QLabel, text: str, state: str) -> None:
        """Update badge text and dynamic state property with instant stylesheet polish."""
        badge.setText(text)
        badge.setProperty("state", state)
        self._repaint(badge)

    def _set_running_controls(self, running: bool) -> None:
        """Update action buttons enable/disable states for start/stop cycles."""
        self.start_card_mail_button.setEnabled(not running)
        self.pause_resume_button.setEnabled(running)
        self._set_pause_button_state(is_paused=False)
        self.stop_button.setEnabled(running)
        self.resync_button.setEnabled(running)

    def _run_debug_step(
        self,
        step_id: str,
        start_msg: str,
        action_fn: Callable[[], Any],
        success_msg: Callable[[Any], str] | str,
        fail_label: str,
    ) -> None:
        """Generic runner for WeGame debug steps, unifying state update and logging."""
        if not self._dbg_require_bound():
            return
        self.set_step_state(step_id, "running")
        self.write_log(f"调试：{start_msg}")
        try:
            result = action_fn()
            self.set_step_state(step_id, "success")
            msg = success_msg(result) if callable(success_msg) else success_msg
            self.write_log(f"调试：{msg}")
        except Exception as exc:
            self.set_step_state(step_id, "failed", str(exc))
            self.write_log(f"调试：{fail_label}失败：{exc}")

    # ── Log Management ───────────────────────────────────────────────────────

    def clear_log(self) -> None:
        """Clear current log console output."""
        self.log_output.clear()
        self._log_buffer.clear()

    def copy_log(self) -> None:
        """Copy all log content to clipboard."""
        text = self.log_output.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.write_log("已复制全部运行日志到剪贴板。")

    def write_log(self, message: str) -> None:
        """Append a timestamped message to the log buffer."""
        timestamp = time.strftime("%H:%M:%S")
        self._log_buffer.append(f"[{timestamp}] {message}")

    def _flush_log_buffer(self) -> None:
        """Batch-insert buffered log entries into QPlainTextEdit."""
        if not self._log_buffer:
            return

        lines = self._log_buffer
        self._log_buffer = []

        cursor = self.log_output.textCursor()
        user_has_selection = cursor.hasSelection()

        vbar = self.log_output.verticalScrollBar()
        was_at_bottom = vbar.value() >= vbar.maximum() - 4

        self.log_output.setUpdatesEnabled(False)
        try:
            for line in lines:
                self.log_output.appendPlainText(line)
        finally:
            self.log_output.setUpdatesEnabled(True)
            self.log_output.update()

        if was_at_bottom and not user_has_selection:
            self.log_output.moveCursor(QTextCursor.MoveOperation.End)
            self.log_output.ensureCursorVisible()

    # ── Window Binding ───────────────────────────────────────────────────────

    def bind_window_at(self, x: int, y: int) -> None:
        """Bind to target window at given screen coordinates."""
        try:
            bound_window = self.workflow.window_binder.bind_at_position(x, y)
        except Exception as exc:
            self.write_log(f"绑定失败：{exc}")
            return

        if bound_window.handle == int(self.winId()):
            self.write_log("绑定到了工具窗口本身，请拖到 WeGame 窗口上再松开。")
            return

        self.bound_window = bound_window
        info_text = (
            f"{bound_window.title or '<无标题>'} | "
            f"{bound_window.process_name or '<未知进程>'} | "
            f"pid={bound_window.process_id or '-'} | "
            f"handle={bound_window.handle}"
        )
        self.conn_dot.setProperty("connected", "true")
        self._repaint(self.conn_dot)

        self.conn_badge.setText("已连接")
        self.conn_badge.setProperty("connected", "true")
        self._repaint(self.conn_badge)

        self.conn_detail_label.setText(info_text)
        self.bind_button.default_text = "重新拖拽绑定"
        self.bind_button.setText("重新拖拽绑定")

        self.subtitle.setText("WeGame 窗口已绑定，可以开始执行自动化流程或单步调试。")
        self.write_log(
            "窗口绑定成功："
            f"{bound_window.title or '<无标题>'} | "
            f"{bound_window.process_name or '<未知进程>'} | "
            f"pid={bound_window.process_id or '-'}"
        )

    def reset_binding(self) -> None:
        """Release current bound window and stop running timers."""
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.workflow.cancel_game_navigation()
        self._set_running_controls(False)
        self.bound_window = None

        self.conn_dot.setProperty("connected", "false")
        self._repaint(self.conn_dot)

        self.conn_badge.setText("未连接")
        self.conn_badge.setProperty("connected", "false")
        self._repaint(self.conn_badge)

        self.conn_detail_label.setText("请按住右侧按钮拖动到 WeGame 主窗口后松开（如游戏已运行可直接卡邮件）")
        self.bind_button.default_text = "拖拽至 WeGame 窗口绑定"
        self.bind_button.setText("拖拽至 WeGame 窗口绑定")

        self.subtitle.setText("WeGame 辅助就绪 · 支持窗口智能吸附、实时步骤跟踪与单步调试")
        self.write_log("已解除窗口绑定，请重新选择 WeGame 窗口。")

    # ── Automation Control ───────────────────────────────────────────────────

    def _set_pause_button_state(self, is_paused: bool) -> None:
        if is_paused:
            self.pause_resume_button.setText("继续 (F12)")
            self.pause_resume_button.setProperty("paused", "true")
        else:
            self.pause_resume_button.setText("暂停 (F12)")
            self.pause_resume_button.setProperty("paused", "false")
        self.pause_resume_button.style().unpolish(self.pause_resume_button)
        self.pause_resume_button.style().polish(self.pause_resume_button)
        self.pause_resume_button.update()

    def toggle_pause_resume(self) -> None:
        """Pause or resume the in-game navigation flow."""
        if not (self.navigation_timer.isActive() or self.workflow.is_navigation_paused):
            return

        is_now_paused = self.workflow.toggle_navigation_pause()
        self._set_pause_button_state(is_paused=is_now_paused)

        if is_now_paused:
            self.write_log("[流程暂停] 自动化已暂停，按 F12 继续，或使用单步调试。")
            if hasattr(self, "workflow_status_badge"):
                self._set_badge(self.workflow_status_badge, "流程已暂停 (F12 继续)", "running")
        else:
            self.write_log("[流程继续] 自动化继续推进...")
            if hasattr(self, "workflow_status_badge"):
                self._set_badge(self.workflow_status_badge, "正在执行中...", "running")
            if not self.navigation_timer.isActive():
                self.navigation_timer.start()

    def manual_resync(self) -> None:
        """Manually trigger screen recognition and step advance."""
        if not self.workflow.game_navigator.bound_window:
            self.write_log("[重同步] 当前没有正在导航的游戏窗口。")
            return
        self.write_log("[重同步] 手动重新对齐画面状态...")
        self.advance_game_navigation()

    def emergency_stop(self) -> None:
        """Stop all automation tasks and bring tool window to foreground."""
        was_running = (
            self.navigation_timer.isActive()
            or self.game_process_timer.isActive()
            or self.workflow.is_navigation_paused
        )
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.workflow.cancel_game_navigation()
        self._set_running_controls(False)

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
            self._set_badge(self.workflow_status_badge, "任务已停止", "idle")

        if was_running:
            self.write_log("[任务停止] 已通过快捷键/按钮停止当前自动化任务。")
        else:
            self.write_log("[任务停止] 当前无正在运行的自动化任务。")

    # ── Settings ─────────────────────────────────────────────────────────────

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
        self._sync_pak_button_state()

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

    # ── Template Capture ─────────────────────────────────────────────────────

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

    # ── Core Workflow Actions ────────────────────────────────────────────────

    def start_card_mail(self) -> None:
        self.reset_all_step_states()
        game_process = self.workflow.find_game_process()
        if game_process is not None:
            self.write_log(
                "检测到三角洲行动游戏已在运行中："
                f"{game_process.name} | pid={game_process.process_id}，直接接管导航！"
            )
            self._set_running_controls(True)

            self.set_step_state("nav_game", "running")
            self.update_nav_substep_pills(0)
            event = self.workflow.start_game_navigation(game_process)
            self.write_log(event.message)
            self.navigation_timer.start()
            self.advance_game_navigation()
            return

        if self.bound_window is None:
            self.write_log("[提示] 未检测到运行中的游戏，且尚未绑定 WeGame 窗口。")
            self.write_log("[提示] 请先按住上方「拖拽至 WeGame 窗口绑定」按钮完成绑定，以自动拉起游戏。")
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
        self._set_running_controls(True)
        self.game_process_deadline = time.monotonic() + self.config.game_process_timeout_seconds
        self.write_log(
            "已点击启动元素："
            f"x={position.x}, y={position.y}, "
            f"confidence={position.confidence:.3f}, template={template_path.name}"
        )
        self.write_log("正在等待三角洲行动游戏进程...")
        if hasattr(self, "workflow_status_badge"):
            self._set_badge(self.workflow_status_badge, "等待游戏启动...", "running")
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
            self._set_running_controls(False)
            message = (
                f"在 {self.config.game_process_timeout_seconds} 秒内未检测到三角洲行动进程。"
            )
            self.write_log(message)
            self.set_step_state("nav_game", "failed", "未检测到游戏进程")
            QMessageBox.warning(self, "超时", message)
            if hasattr(self, "workflow_status_badge"):
                self._set_badge(self.workflow_status_badge, "等待启动超时", "failed")

    def advance_game_navigation(self) -> None:
        cur_step_idx = getattr(self.workflow.game_navigator, "step_index", 0)
        self.update_nav_substep_pills(cur_step_idx)

        try:
            event = self.workflow.advance_game_navigation()
        except Exception as exc:
            self.navigation_timer.stop()
            self._set_running_controls(False)
            self.set_step_state("nav_game", "failed", str(exc))
            self.write_log(f"自动导航失败：{exc}")
            return

        if event is None:
            return

        self.write_log(event.message)
        if event.status == NavigationStatus.PAUSED:
            self._set_pause_button_state(is_paused=True)
            if hasattr(self, "workflow_status_badge"):
                self._set_badge(
                    self.workflow_status_badge,
                    f"流程已暂停（步骤 {cur_step_idx + 1}）",
                    "running",
                )
            return

        if event.status in (NavigationStatus.COMPLETE, NavigationStatus.FAILED):
            self.navigation_timer.stop()
            self._set_running_controls(False)

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

                paks_path: Path | None = None
                if self.config.game_install_dir:
                    paks_path = Workflow.get_paks_dir(self.config.game_install_dir)
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
                            self._sync_pak_button_state()
                            self.set_step_state("rename_pak", "success")
                        except OSError as exc:
                            self.set_step_state("rename_pak", "failed", str(exc))
                            self.write_log(f"重命名 pak 文件失败：{exc}")
                        else:
                            for message in results:
                                self.write_log(message)
                else:
                    self.write_log("未配置游戏安装目录，跳过 pak 文件重命名。")

                if self.bound_window is not None:
                    self._run_wegame_post_process()

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
                self._set_badge(self.workflow_status_badge, "全流程自动化已顺利完成", "success")
        except Exception as exc:
            self.set_step_state(current_step, "failed", str(exc))
            self.write_log(f"WeGame 删包或重开失败：{exc}")

    # ── Debug & Step Status Management ───────────────────────────────────────

    def set_step_state(self, step_id: str, state: str, detail: str = "") -> None:
        """Update step button state ('idle' | 'running' | 'success' | 'failed') and global badge."""
        step_info = getattr(self, "_step_buttons", {}).get(step_id)
        title = step_info["title"] if step_info else step_id
        if step_info:
            btn = step_info["button"]
            base_text = step_info["base_text"]

            btn.setProperty("stepState", state)
            if state == "running":
                btn.setText(f"{title}...")
            elif state == "success":
                btn.setText(f"✓ {title}")
            elif state == "failed":
                btn.setText(f"! {title}")
            else:
                btn.setText(base_text)

            self._repaint(btn)

        dot_to_update = None
        if step_id == "nav_game":
            dot_to_update = getattr(self, "step1_dot", None)
        elif step_id in ("rename_pak", "open_paks"):
            dot_to_update = getattr(self, "step2_dot", None)
        elif step_id in ("wait_wegame", "click_more", "assets_manage", "delete_map", "restart_game"):
            dot_to_update = getattr(self, "step3_dot", None)

        if dot_to_update is not None:
            dot_to_update.setProperty("state", state)
            self._repaint(dot_to_update)

        if hasattr(self, "workflow_status_badge"):
            if state == "running":
                badge_text = f"正在执行：{title}"
                badge_state = "running"
            elif state == "success":
                badge_text = f"步骤完成：{title}"
                badge_state = "success"
            elif state == "failed":
                badge_text = f"步骤失败：{title}"
                badge_state = "failed"
            else:
                badge_text = "待命就绪"
                badge_state = "idle"

            self._set_badge(self.workflow_status_badge, badge_text, badge_state)
            if state == "failed" and detail:
                self.workflow_status_badge.setToolTip(f"失败详情：{detail}")
            else:
                self.workflow_status_badge.setToolTip("")

        QApplication.processEvents()

    def update_nav_substep_pills(self, active_index: int) -> None:
        """Update navigation sub-step pills: done, active, or idle."""
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
            self._repaint(pill)
        QApplication.processEvents()

    def reset_all_step_states(self) -> None:
        """Reset all buttons and sub-step pills to idle."""
        if hasattr(self, "_step_buttons"):
            for step_id, info in self._step_buttons.items():
                btn = info["button"]
                btn.setProperty("stepState", "idle")
                btn.setText(info["base_text"])
                self._repaint(btn)

        if hasattr(self, "sub_step_pills"):
            for pill in self.sub_step_pills:
                pill.setProperty("pillState", "")
                self._repaint(pill)

        if hasattr(self, "workflow_status_badge"):
            self._set_badge(self.workflow_status_badge, "● 待命就绪", "idle")

        self._sync_pak_button_state()
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
            self.write_log("调试：需要先绑定 WeGame 窗口才能使用此功能。")
            return False
        return True

    def _dbg_takeover_navigation(self) -> None:
        """Resume game navigation and auto-align with the current game screen."""
        game_process = self.workflow.find_game_process()
        if game_process is None:
            self.write_log("调试：未检测到三角洲行动游戏进程，请先启动游戏再使用此功能。")
            self.set_step_state("nav_game", "failed", "未检测到游戏进程")
            return

        self.set_step_state("nav_game", "running")
        self.write_log(
            f"调试：检测到游戏进程 {game_process.name} | pid={game_process.process_id}，接管导航并自动对齐画面..."
        )
        event = self.workflow.start_game_navigation(game_process)
        self.write_log(event.message)
        self.navigation_timer.start()
        self._set_running_controls(True)
        self.advance_game_navigation()

    def _on_step_pill_clicked(self, step_index: int) -> None:
        """Directly jump to and execute the selected navigation step."""
        game_process = self.workflow.find_game_process()
        if game_process is None:
            self.write_log("未检测到三角洲行动游戏进程，请先启动游戏再点击步骤跳转。")
            return

        target_step = NAVIGATION_STEPS[step_index]
        self.write_log(
            f"【手动跳转】用户指定第 {step_index + 1} 步：【{target_step.name}】"
        )

        self.workflow._game_process = game_process
        if (
            self.workflow.game_navigator.process_id != game_process.process_id
            or self.workflow.game_navigator.bound_window is None
        ):
            event = self.workflow.start_game_navigation(
                game_process, initial_step=step_index
            )
            self.write_log(event.message)
        else:
            event = self.workflow.jump_to_navigation_step(step_index)
            self.write_log(event.message)

        self._set_running_controls(True)
        self.set_step_state("nav_game", "running")
        self.update_nav_substep_pills(step_index)

        if not self.navigation_timer.isActive():
            self.navigation_timer.start()
        self.advance_game_navigation()

    def _dbg_wait_wegame(self) -> None:
        self._run_debug_step(
            step_id="wait_wegame",
            start_msg="等待 WeGame 启动按钮出现...",
            action_fn=lambda: self.workflow.wait_for_wegame_ready(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
                timeout=getattr(self.config, "wegame_ready_timeout_seconds", 60),
            ),
            success_msg="WeGame 启动按钮已出现。",
            fail_label="等待 WeGame 启动按钮",
        )

    def _dbg_click_more(self) -> None:
        self._run_debug_step(
            step_id="click_more",
            start_msg="点击 WeGame 更多按钮（...）...",
            action_fn=lambda: self.workflow.click_wegame_more(
                self.bound_window,
                getattr(self.config, "wegame_more_template", "wegame_more.png"),
                self.config.template_match_threshold,
            ),
            success_msg=lambda pos: f"已点击更多按钮 (x={pos.x}, y={pos.y})。",
            fail_label="点击更多按钮",
        )

    def _dbg_assets_manage(self) -> None:
        self._run_debug_step(
            step_id="assets_manage",
            start_msg="点击游戏资源包管理...",
            action_fn=lambda: self.workflow.click_assets_manage(
                self.bound_window,
                getattr(self.config, "wegame_assets_manage_template", "wegame_assets_manage.png"),
                self.config.template_match_threshold,
            ),
            success_msg=lambda pos: f"已打开资源包管理 (x={pos.x}, y={pos.y})。",
            fail_label="打开资源包管理",
        )

    def _dbg_delete_changgong(self) -> None:
        self._run_debug_step(
            step_id="delete_map",
            start_msg="在资源管理窗口中查找并删除长弓溪谷（会自动向下滚动）...",
            action_fn=lambda: self.workflow.delete_changgong_map(
                getattr(self.config, "wegame_delete_map_template", "wegame_delete_map.png"),
                self.config.template_match_threshold,
                timeout=getattr(self.config, "delete_map_timeout_seconds", 30),
            ),
            success_msg=lambda pos: f"已点击删除长弓溪谷 (x={pos.x}, y={pos.y})。",
            fail_label="删除长弓溪谷",
        )

    def _dbg_restart_game(self) -> None:
        self._run_debug_step(
            step_id="restart_game",
            start_msg="点击 WeGame 启动按钮重新启动游戏...",
            action_fn=lambda: self.workflow.click_start_button(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
            ),
            success_msg=lambda ret: f"已点击启动按钮 {ret[1].name} (x={ret[0].x}, y={ret[0].y})。",
            fail_label="重新启动游戏",
        )

    def _sync_pak_button_state(self) -> None:
        """Inspect actual disk files and sync the pak button label and tooltip."""
        if not hasattr(self, "dbg_rename_pak_btn"):
            return
        status = self.workflow.get_pak_status(
            self.config.game_install_dir,
            self.config.pak_file_names,
        )
        if status == "disabled":
            text = "恢复 Pak (移除 .disabled)"
            tooltip = "当前 Pak 文件已被屏蔽（重命名为 .disabled），点击恢复为正常 .pak 文件"
            self.dbg_rename_pak_btn.setText(text)
            self.dbg_rename_pak_btn.setToolTip(tooltip)
            if hasattr(self, "_step_buttons") and "rename_pak" in self._step_buttons:
                self._step_buttons["rename_pak"]["base_text"] = text
                self._step_buttons["rename_pak"]["title"] = "恢复 Pak"
            self.dbg_rename_pak_btn.setProperty("stepState", "success")
        else:
            text = "屏蔽 Pak (重命名 .disabled)"
            tooltip = "重命名长弓溪谷 Pak 文件为 .disabled 状态以屏蔽加载（再点一次可恢复正常）"
            self.dbg_rename_pak_btn.setText(text)
            self.dbg_rename_pak_btn.setToolTip(tooltip)
            if hasattr(self, "_step_buttons") and "rename_pak" in self._step_buttons:
                self._step_buttons["rename_pak"]["base_text"] = text
                self._step_buttons["rename_pak"]["title"] = "屏蔽 Pak"
            current_state = self.dbg_rename_pak_btn.property("stepState")
            if current_state not in ("running", "failed"):
                self.dbg_rename_pak_btn.setProperty("stepState", "idle")

        self._repaint(self.dbg_rename_pak_btn)

    def _dbg_rename_pak(self) -> None:
        if not self.config.game_install_dir:
            self.write_log("调试：未配置游戏安装目录，请先填写安装目录。")
            self.set_step_state("rename_pak", "failed", "未配置游戏安装目录")
            return

        self.set_step_state("rename_pak", "running")
        try:
            action, results = self.workflow.toggle_pak_files(
                self.config.game_install_dir,
                self.config.pak_file_names,
            )
            if action == "disabled":
                self.set_step_state("rename_pak", "success")
                self.write_log("调试：【已屏蔽 Pak】已重命名为 .disabled 状态（再点一次恢复正常）。")
            else:
                self.set_step_state("rename_pak", "idle")
                if hasattr(self, "workflow_status_badge"):
                    self._set_badge(self.workflow_status_badge, "步骤完成：恢复 Pak", "success")
                self.write_log("调试：【已恢复 Pak】已去除 .disabled 后缀，文件恢复正常（再点一次重新屏蔽）。")

            self._sync_pak_button_state()

            for msg in results:
                self.write_log(f"  └─ {msg}")
        except Exception as exc:
            self.set_step_state("rename_pak", "failed", str(exc))
            self.write_log(f"调试：操作 pak 文件失败：{exc}")
            self._sync_pak_button_state()

    def _dbg_open_paks(self) -> None:
        if not self.config.game_install_dir:
            self.write_log("调试：未配置游戏安装目录，请先填写安装目录。")
            self.set_step_state("open_paks", "failed", "未配置游戏安装目录")
            return
        paks_path = Workflow.get_paks_dir(self.config.game_install_dir)
        self.set_step_state("open_paks", "running")
        try:
            subprocess.Popen(["explorer", str(paks_path)])
            self.set_step_state("open_paks", "success")
            self.write_log(f"调试：已打开 Paks 目录：{paks_path}")
        except OSError as exc:
            self.set_step_state("open_paks", "failed", str(exc))
            self.write_log(f"调试：打开 Paks 目录失败：{exc}")
