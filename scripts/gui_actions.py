from __future__ import annotations

import subprocess
import time
from dataclasses import replace
from functools import partial
from pathlib import Path

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
from scripts.task_runner import background_action
from scripts.task_control import ControlInterrupted, TaskPaused


class ActionsMixin:
    """Action handlers, business workflows, and debug runner mixin for MainWindow."""

    _wegame_step_ids = ("wait_wegame", "click_more", "assets_manage", "delete_map", "restart_game")

    # ── UI State Helpers ─────────────────────────────────────────────────────

    def _repaint(self, widget: QWidget) -> None:
        """Force Qt style re-evaluation and repaint for dynamic property changes."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _set_property(self, widget, name, value):
        if widget.property(name) != value:
            widget.setProperty(name, value)
            self._repaint(widget)

    def _set_badge(self, badge: QLabel, text: str, state: str) -> None:
        """Update badge text and dynamic state property with instant stylesheet polish."""
        badge.setText(text)
        self._set_property(badge, "state", state)

    def _set_running_controls(self, running: bool) -> None:
        """Update action buttons enable/disable states for start/stop cycles."""
        self.start_card_mail_button.setEnabled(not running and not self.task_runner.busy)
        self._set_pause_button_state(is_paused=False)
        self.stop_button.setEnabled(running or self.task_runner.busy)

    @background_action
    def _run_debug_step(self, step_id, start_msg, action_fn, success_msg, fail_label):
        if not self._dbg_require_bound():
            return False
        self.workflow.control.paused.clear()
        self.set_step_state(step_id, "running")
        self.write_log(f"调试：{start_msg}")
        try:
            result = yield partial(self.workflow.progress.run, "action", action_fn)
        except ControlInterrupted:
            raise
        except Exception as exc:
            self.set_step_state(step_id, "failed", str(exc))
            self.write_log(f"调试：{fail_label}失败：{exc}")
            return False
        self.set_step_state(step_id, "success")
        self.write_log(f"调试：{success_msg(result) if callable(success_msg) else success_msg}")
        return True

    def _wegame_steps(self):
        """Shared actions and messages for single-step and continuous execution."""
        wf, cfg, window = self.workflow, self.config, self.bound_window
        threshold = cfg.template_match_threshold
        return {
            "wait_wegame": ("等待 WeGame 启动按钮出现...",
                partial(wf.wait_for_wegame_ready, window, cfg.start_button_templates,
                        threshold, timeout=cfg.wegame_ready_timeout_seconds),
                "WeGame 启动按钮已出现。", "等待 WeGame 启动按钮", 0),
            "click_more": ("点击 WeGame 更多按钮（...）...",
                partial(wf.click_wegame_more, window, cfg.wegame_more_template, threshold),
                "已点击更多按钮。", "点击更多按钮", 0),
            "assets_manage": ("打开游戏资源包管理...",
                partial(wf.click_assets_manage, window, cfg.wegame_assets_manage_template, threshold),
                "已打开资源包管理。", "打开资源包管理", 0.5),
            "delete_map": ("查找并删除长弓溪谷（会自动向下滚动）...",
                partial(wf.delete_changgong_map, cfg.wegame_delete_map_template,
                        threshold, timeout=cfg.delete_map_timeout_seconds,
                        confirm_template_name=cfg.wegame_confirm_delete_template,
                        confirm_timeout=cfg.confirm_delete_timeout_seconds,
                        game_install_dir=cfg.game_install_dir,
                        pak_names=cfg.pak_file_names,
                        bin_template_name=cfg.wegame_bin_template,
                        manager_header_template=cfg.wegame_manager_header_template),
                lambda pos: f"已发送 WeGame 确定及关闭点击，保留本地重命名文件 (x={pos.x}, y={pos.y})。", "删除长弓溪谷", 1.0),
            "restart_game": ("重新启动游戏...",
                partial(wf.click_start_button, window, cfg.start_button_templates, threshold),
                lambda ret: f"已点击启动按钮 {ret[1].name} (x={ret[0].x}, y={ret[0].y})。",
                "重新启动游戏", 1.2),
        }

    def _dbg_wegame(self, step_id):
        self._run_wegame_post_process(start_step=step_id)


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
            self.log_output.appendPlainText("\n".join(lines))
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

        self.write_log(
            "窗口绑定成功："
            f"{bound_window.title or '<无标题>'} | "
            f"{bound_window.process_name or '<未知进程>'} | "
            f"pid={bound_window.process_id or '-'}"
        )

    def reset_binding(self) -> None:
        """Release current bound window and stop running timers."""
        self._resume_step = None
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.task_runner.cancel()
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

        self.write_log("已解除窗口绑定，请重新选择 WeGame 窗口。")

    # ── Automation Control ───────────────────────────────────────────────────

    def _set_pause_button_state(self, is_paused: bool) -> None:
        self.pause_resume_button.setEnabled(is_paused)
        self._set_property(self.pause_resume_button, "paused", "true" if is_paused else "false")


    def _offer_continue(self, step: str) -> None:
        self._resume_step = step
        self.write_log("已停在步骤边界，点击“继续”或按 Ctrl+F12 执行下一步。")

    def continue_navigation(self) -> None:
        if not (self.workflow.is_navigation_paused or self._resume_step):
            self.write_log("当前没有待继续的步骤，请先启动流程或选择一个步骤。")
            return
        if self.task_runner.busy:
            self.write_log("当前操作正在收尾，请稍候再继续。")
        else:
            self.workflow.control.paused.clear()
            if self._resume_step:
                self._resume_interrupted()
            else:
                self._resume_navigation()

    @background_action
    def _resume_interrupted(self):
        step = self._resume_step
        self._resume_step = None
        self._continue_after_navigation = self.is_continuous_mode
        self.write_log(f"继续执行步骤：{step}；已完成的小操作会跳过。")
        if step == "launch":
            yield from self.start_card_mail.__wrapped__(self, resume=True)
        elif step == "nav_game":
            yield from self._dbg_takeover_navigation.__wrapped__(self)
        elif step == "exit_game":
            yield from self._finish_navigation()
        elif step == "rename_pak":
            yield from self._run_stage_two()
        elif step == "toggle_pak":
            yield from self._dbg_rename_pak.__wrapped__(self)
        elif step in self._wegame_step_ids:
            yield from self._run_wegame_post_process_tasks(start_step=step)
        else:
            yield from self._run_stage_four_tasks(start_step=step)

    @background_action
    def _resume_navigation(self):
        try:
            event = yield self.workflow.resume_game_navigation
        except TaskPaused:
            self.workflow.game_navigator.finished = False
            self.workflow.game_navigator.pause()
            self._set_pause_button_state(True)
            return
        yield from self._advance_game_navigation_result(event)
        self._set_pause_button_state(self.workflow.is_navigation_paused)
        if not self.workflow.is_navigation_paused and not self.workflow.game_navigator.finished:
            self.navigation_timer.start()

    def emergency_stop(self) -> None:
        """Stop all automation tasks and bring tool window to foreground."""
        was_running = (
            self.task_runner.busy
            or self.navigation_timer.isActive()
            or self.game_process_timer.isActive()
            or self.workflow.is_navigation_paused
        )
        if was_running:
            self._resume_step = self.workflow.progress.step or None
        self.game_process_timer.stop()
        self.navigation_timer.stop()
        self.task_runner.cancel()
        self.workflow.cancel_game_navigation()
        self._continue_after_navigation = False
        self._set_running_controls(False)
        self.pause_resume_button.setEnabled(self._resume_step is not None and not self.task_runner.busy)

        self.showNormal()
        self.activateWindow()
        self.raise_()
        try:
            win32gui.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass

        for step_id, info in self._step_buttons.items():
            btn = info["button"]
            if btn.property("stepState") == "running":
                self.set_step_state(step_id, "idle")
        self._set_badge(self.workflow_status_badge, "任务已停止", "idle")

        if was_running:
            self.write_log("[任务停止] 已通过快捷键/按钮停止当前自动化任务。")
            if self._resume_step:
                self.write_log("已保留当前步骤及小操作进度，可点击“继续”接续；点击“开始卡邮件”重新开始。")
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
        if new_mode == self.config.operation_mode:
            return
        self.config = replace(self.config, operation_mode=new_mode)
        self._sync_operation_mode_controls()
        try:
            self.config.save_to_file()
        except OSError as exc:
            self.write_log(f"保存运行模式失败：{exc}")
        else:
            mode_name = "半自动模式" if new_mode == "semi_auto" else "全自动模式"
            self.write_log(f"已切换运行模式为：{mode_name}")

    def _sync_operation_mode_controls(self) -> None:
        semi_auto = self.config.operation_mode == "semi_auto"
        self.dbg_warehouse_btn.setVisible(semi_auto)
        for button in self.full_auto_placeholder_buttons:
            button.setVisible(not semi_auto)
        self.stage_four_actions.invalidate()
        self._controls_fit_timer.start()

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

    @background_action
    def start_card_mail(self, resume=False):
        if not resume:
            self.reset_all_step_states()
        self.workflow.progress.enter("launch")
        self._continue_after_navigation = self.is_continuous_mode
        self.workflow.control.paused.clear()
        game_process = (yield lambda: self.workflow.find_game_process())
        if game_process is not None:
            self.write_log(
                "检测到三角洲行动游戏已在运行中："
                f"{game_process.name} | pid={game_process.process_id}，直接接管导航！"
            )
            yield from self._begin_navigation(game_process)
            return

        if self.bound_window is None:
            self.write_log("[提示] 未检测到运行中的游戏，且尚未绑定 WeGame 窗口。")
            self.write_log("[提示] 请先按住上方「拖拽至 WeGame 窗口绑定」按钮完成绑定，以自动拉起游戏。")
            return

        self.write_log("准备识别并点击启动元素...")
        self.hide()

        try:
            position, template_path = (yield lambda: self.workflow.progress.run("launch", lambda: self.workflow.click_start_button(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
            )))
        except ControlInterrupted:
            raise
        except Exception as exc:
            self.show()
            self.write_log(f"启动按钮匹配/点击失败：{exc}")
            self._set_badge(self.workflow_status_badge, "启动失败，请查看日志", "failed")
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
        self._set_badge(self.workflow_status_badge, "等待游戏启动...", "running")
        self.game_process_timer.start()
        yield from self._check_game_process_tasks()

    @background_action
    def check_game_process(self):
        self.workflow.control.paused.clear()
        game_process = (yield lambda: self.workflow.find_game_process())
        if game_process is not None:
            self.game_process_timer.stop()
            self.write_log(
                "已找到三角洲行动游戏进程："
                f"{game_process.name} | pid={game_process.process_id}"
            )
            yield from self._begin_navigation(game_process)
            return

        if time.monotonic() >= self.game_process_deadline:
            self.game_process_timer.stop()
            self._set_running_controls(False)
            message = (
                f"在 {self.config.game_process_timeout_seconds} 秒内未检测到三角洲行动进程。"
            )
            self.write_log(message)
            self.set_step_state("nav_game", "failed", "未检测到游戏进程")
            self._set_badge(self.workflow_status_badge, "等待启动超时", "failed")

    @background_action
    def advance_game_navigation(self):
        try:
            event = (yield lambda: self.workflow.advance_game_navigation())
        except TaskPaused:
            self.navigation_timer.stop()
            self.workflow.game_navigator.finished = False
            self.workflow.game_navigator.pause()
            self._set_pause_button_state(True)
            return
        except ControlInterrupted:
            raise
        except Exception as exc:
            self.navigation_timer.stop()
            self._set_running_controls(False)
            self.set_step_state("nav_game", "failed", str(exc))
            self.write_log(f"自动导航失败：{exc}")
            return

        yield from self._advance_game_navigation_result(event)

    def _advance_game_navigation_result(self, event):
        cur_step_idx = self.workflow.game_navigator.step_index
        self.update_nav_substep_pills(cur_step_idx)
        if event is None:
            return

        self.write_log(event.message)
        if (event.status == NavigationStatus.RUNNING and event.step_completed
                and self._navigation_mode == "step"):
            self.navigation_timer.stop()
            self.workflow.game_navigator.pause()
            self.workflow.control.paused.set()
            self._set_pause_button_state(True)
            self.write_log("单步完成，已暂停。按 Ctrl+F12 或点击继续执行下一步。")
            return
        if event.status == NavigationStatus.PAUSED:
            self.navigation_timer.stop()
            self.workflow.control.paused.set()
            self._set_pause_button_state(is_paused=True)
            self._set_badge(self.workflow_status_badge, f"流程已暂停（步骤 {cur_step_idx + 1}）", "running")
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
                if self._navigation_mode == "step":
                    self.write_log("单步检测完成，停在选人界面。")
                    self._offer_continue("exit_game")
                    return
                yield from self._finish_navigation()

    def _finish_navigation(self):
        self.workflow.progress.enter("exit_game")
        process_exited, message = yield lambda: self.workflow.progress.run("exit", self.workflow.kill_game_process)
        self.write_log(message)
        if not process_exited:
            self.set_step_state("nav_game", "failed", message)
            return
        if self.bound_window is not None:
            try:
                self.bound_window = yield lambda: self.workflow.window_binder.activate(self.bound_window)
            except ControlInterrupted:
                raise
            except Exception as exc:
                self.write_log(f"返回 WeGame 窗口失败：{exc}")
            else:
                self.write_log("已返回 WeGame 窗口。")
        if self._continue_after_navigation:
            yield from self._run_stage_two()
        else:
            self.write_log("阶段完成：游戏导航及退出已完成，停止后续阶段。")
            self._offer_continue("rename_pak")

    def _run_stage_two(self):
        self.set_step_state("rename_pak", "running")
        try:
            messages = yield lambda: self.workflow.rename_pak_files(
                self.config.game_install_dir, self.config.pak_file_names)
        except ControlInterrupted:
            raise
        except OSError as exc:
            self.set_step_state("rename_pak", "failed", str(exc))
            self.write_log(f"屏蔽 Pak 失败：{exc}")
            return
        for message in messages:
            self.write_log(message)
        self._sync_pak_button_state()
        self.set_step_state("rename_pak", "success")
        if self.is_continuous_mode and self.bound_window is not None:
            yield from self._run_wegame_post_process_tasks()
        else:
            self._offer_continue("wait_wegame")

    @background_action
    def _run_wegame_post_process(self, start_step: str = "wait_wegame"):
        if not self._dbg_require_bound():
            return
        self.workflow.control.paused.clear()
        steps = self._wegame_steps()
        order = list(steps)
        start_index = order.index(start_step) if start_step in steps else 0
        for step_id in order[start_index:]:
            start_msg, action, success_msg, fail_label, delay = steps[step_id]
            if delay:
                yield partial(self.workflow.control.wait, delay)
            succeeded = yield from self._run_debug_step_tasks(
                step_id, start_msg, action, success_msg, fail_label)
            if not succeeded:
                return
            if self.execution_mode == "step":
                next_index = order.index(step_id) + 1
                self._offer_continue(order[next_index] if next_index < len(order) else "detect_result")
                return
        self._set_badge(self.workflow_status_badge, "WeGame 阶段已完成", "success")
        if self.is_continuous_mode:
            yield from self._run_stage_four_tasks()
        else:
            self._offer_continue("detect_result")

    @background_action
    def _run_stage_four(self, start_step: str = "detect_result"):
        self.workflow.control.paused.clear()
        if start_step == "warehouse" and self.config.operation_mode != "semi_auto":
            self.write_log("全自动模式不进入仓库；后续操作尚未实现，未执行或循环。")
            return
        if start_step == "detect_result":
            self.set_step_state("detect_result", "running")
            self.write_log("第四阶段第 1 步：确认提示、选择模式、再次确认并进入大厅...")
            try:
                matched = yield lambda: self.workflow.detect_stage_four_result(
                    self.config.reconnect_notice_template, self.config.game_confirm_template,
                    self.config.reconnect_notice_threshold,
                    self.config.reconnect_notice_timeout_seconds)
            except ControlInterrupted:
                raise
            except Exception as exc:
                self.set_step_state("detect_result", "failed", str(exc))
                self.write_log(f"第四阶段进入大厅失败：{exc}；未执行 Pak 恢复或地图下载。")
                return
            self.set_step_state("detect_result", "success" if matched else "failed", "" if matched else "结果未确认")
            self._set_badge(self.workflow_status_badge, "已返回烽火大厅" if matched else "结果未确认，未恢复 Pak",
                            "success" if matched else "failed")
            if not matched:
                return
            if self.execution_mode == "step":
                self._offer_continue("restore_pak")
                return
        if start_step in ("detect_result", "restore_pak"):
            self.set_step_state("restore_pak", "running")
            try:
                yield lambda: self.workflow.restore_stage_four_paks(
                    self.config.game_install_dir, self.config.pak_file_names)
            except ControlInterrupted:
                raise
            except Exception as exc:
                self.set_step_state("restore_pak", "failed", str(exc))
                self.write_log(f"第四阶段地图恢复失败：{exc}")
                return
            self._sync_pak_button_state()
            self.set_step_state("restore_pak", "success")
            self.write_log("第四阶段：Pak 已恢复，接下来可发送地图恢复请求。")
            if self.execution_mode == "step":
                self._offer_continue("redownload_map")
                return
        if start_step != "warehouse":
            downloaded = yield from self._run_stage_four_redownload_tasks()
            if not downloaded:
                return
            if self.config.operation_mode == "semi_auto" and self.execution_mode == "step":
                self._offer_continue("warehouse")
                return
        if self.config.operation_mode != "semi_auto":
            self.write_log("第四阶段公共步骤完成；全自动后续按钮仅占位，未进仓库，未执行后续操作或循环。")
            self._set_badge(self.workflow_status_badge, "全自动后续待实现", "idle")
            return
        self.set_step_state("warehouse", "running")
        self.write_log("第四阶段第 4 步：进入仓库并确认提示...")
        try:
            yield lambda: self.workflow.enter_stage_four_warehouse(
                self.config.warehouse_notice_template, self.config.game_confirm_template,
                self.config.warehouse_notice_threshold, self.config.navigation_step_timeout_seconds)
        except ControlInterrupted:
            raise
        except Exception as exc:
            self.set_step_state("warehouse", "failed", str(exc))
            self.write_log(f"第四阶段仓库确认失败：{exc}")
            return
        self.set_step_state("warehouse", "success")
        self._set_badge(self.workflow_status_badge, "半自动已完成", "success")
        self.write_log("半自动流程已结束，不再执行后续步骤或循环。请手动穿戴装备，等待地图恢复后切换全面战场并重连。")

    def _run_stage_four_redownload_tasks(self):
        self.set_step_state("redownload_map", "running")
        self.write_log("第四阶段第 3 步：选择长弓、点击下载，再按两次 ESC...")
        try:
            yield lambda: self.workflow.redownload_stage_four_map(
                self.config.redownload_map_choice_template, self.config.redownload_map_panel_template,
                self.config.redownload_map_button_template, self.config.template_match_threshold,
                self.config.navigation_step_timeout_seconds)
        except ControlInterrupted:
            raise
        except Exception as exc:
            self.set_step_state("redownload_map", "failed", str(exc))
            self.write_log(f"第四阶段地图下载请求失败：{exc}；Pak 已经恢复。")
            return False
        self.set_step_state("redownload_map", "success")
        self._set_badge(self.workflow_status_badge, "地图恢复请求已发送", "success")
        return True

    def _dbg_stage_four(self):
        self._run_stage_four(start_step="restore_pak")

    def _dbg_stage_four_detect(self):
        self._run_stage_four(start_step="detect_result")

    def _dbg_stage_four_redownload(self):
        self._run_stage_four(start_step="redownload_map")

    def _dbg_stage_four_warehouse(self):
        self._run_stage_four(start_step="warehouse")


    # ── Debug & Step Status Management ───────────────────────────────────────

    def set_step_state(self, step_id: str, state: str, detail: str = "", *, checkpoint=None) -> None:
        if state == "running" and step_id != "open_paks":
            self.workflow.progress.enter(checkpoint or step_id)
        info = self._step_buttons.get(step_id)
        title = info["title"] if info else step_id
        if info:
            text = {"running": f"{title}...", "success": f"✓ {title}",
                    "failed": f"! {title}"}.get(state, info["base_text"])
            if "number" in info and state in ("running", "success", "failed"):
                text = f"{info['number']}.{text}"
            info["button"].setText(text)
            self._set_property(info["button"], "stepState", state)
        dot = (self.step1_dot if step_id == "nav_game" else self.step2_dot
               if step_id in ("rename_pak", "open_paks") else self.step3_dot
               if step_id in self._wegame_step_ids else self.step4_dot
               if step_id in ("restore_pak", "detect_result", "redownload_map", "warehouse") else None)
        if dot is not None:
            self._set_property(dot, "state", state)
        prefix = {"running": "正在执行", "success": "步骤完成", "failed": "步骤失败"}
        text = f"{prefix[state]}：{title}" if state in prefix else "待命就绪"
        self._set_badge(self.workflow_status_badge, text, state if state in prefix else "idle")
        self.workflow_status_badge.setToolTip(f"失败详情：{detail}" if state == "failed" and detail else "")


    def update_nav_substep_pills(self, active_index: int) -> None:
        """Update navigation sub-step pills: done, active, or idle."""
        for idx, pill in enumerate(self.sub_step_pills):
            if idx < active_index:
                pill_state = "done"
            elif idx == active_index:
                pill_state = "active"
            else:
                pill_state = ""
            self._set_property(pill, "pillState", pill_state)

    def reset_all_step_states(self) -> None:
        """Reset all buttons and sub-step pills to idle."""
        self._resume_step = None
        for info in self._step_buttons.values():
            btn = info["button"]
            btn.setText(info["base_text"])
            self._set_property(btn, "stepState", "idle")
        for pill in self.sub_step_pills:
            self._set_property(pill, "pillState", "")
        self._set_badge(self.workflow_status_badge, "● 待命就绪", "idle")

        self._sync_pak_button_state()

    @property
    def execution_mode(self) -> str:
        return self.step_mode_toggle.currentData()

    @property
    def is_continuous_mode(self) -> bool:
        """Return True if continuous step execution mode is enabled."""
        return self.execution_mode == "continuous"

    def _on_step_mode_toggled(self, index: int) -> None:
        """Handle toggle between single-step mode and continuous mode."""
        self._navigation_mode = self.execution_mode
        self._continue_after_navigation = self.is_continuous_mode
        self.write_log(f"执行模式已切换为：【{self.step_mode_toggle.currentText()}】")

    def _dbg_require_bound(self) -> bool:
        """Return True if WeGame window is bound; log an error otherwise."""
        if self.bound_window is None:
            self.write_log("调试：需要先绑定 WeGame 窗口才能使用此功能。")
            return False
        return True

    @background_action
    def _dbg_takeover_navigation(self):
        """Resume game navigation and auto-align with the current game screen."""
        self.workflow.control.paused.clear()
        game_process = (yield lambda: self.workflow.find_game_process())
        if game_process is None:
            self.write_log("调试：未检测到三角洲行动游戏进程，请先启动游戏再使用此功能。")
            self.set_step_state("nav_game", "failed", "未检测到游戏进程")
            return

        self._continue_after_navigation = self.is_continuous_mode
        self.set_step_state("nav_game", "running")
        self.write_log(
            f"调试：检测到游戏进程 {game_process.name} | pid={game_process.process_id}，接管导航并自动对齐画面..."
        )
        if self.is_continuous_mode:
            self.write_log("调试：已开启【连续模式】，导航完成后将自动衔接后续步骤。")
        elif self.execution_mode == "stage":
            self.write_log("调试：阶段模式，完成游戏导航及退出后停止。")
        else:
            self.write_log("调试：单步模式，完成一个导航动作后暂停。")
        navigator = self.workflow.game_navigator
        initial_step = navigator.step_index if navigator.process_id == game_process.process_id else 0
        yield from self._begin_navigation(game_process, initial_step)

    @background_action
    def _on_step_pill_clicked(self, step_index: int):
        """Directly jump to and execute the selected navigation step."""
        self.workflow.control.paused.clear()
        game_process = (yield lambda: self.workflow.find_game_process())
        if game_process is None:
            self.write_log("未检测到三角洲行动游戏进程，请先启动游戏再点击步骤跳转。")
            return

        target_step = NAVIGATION_STEPS[step_index]
        self.write_log(
            f"【手动跳转】用户指定第 {step_index + 1} 步：【{target_step.name}】"
        )
        self._continue_after_navigation = self.is_continuous_mode

        yield from self._begin_navigation(game_process, step_index, jump=True)

    def _begin_navigation(self, game_process, initial_step=0, jump=False):
        self._navigation_mode = self.execution_mode
        self._continue_after_navigation = self.is_continuous_mode
        wf = self.workflow
        wf._game_process = game_process
        navigator = wf.game_navigator
        if jump and navigator.process_id == game_process.process_id and navigator.bound_window:
            action = partial(wf.jump_to_navigation_step, initial_step)
        else:
            action = partial(wf.start_game_navigation, game_process, initial_step=initial_step, auto_align=not jump)
        self._set_running_controls(True)
        self.set_step_state("nav_game", "running")
        self.update_nav_substep_pills(initial_step)
        event = yield action
        self.write_log(event.message)
        self.navigation_timer.start()
        yield from self._advance_game_navigation_tasks()

    def _dbg_wait_wegame(self) -> None:
        self._dbg_wegame("wait_wegame")


    def _dbg_click_more(self) -> None:
        self._dbg_wegame("click_more")


    def _dbg_assets_manage(self) -> None:
        self._dbg_wegame("assets_manage")


    def _dbg_delete_changgong(self) -> None:
        self._dbg_wegame("delete_map")


    def _dbg_restart_game(self) -> None:
        self._dbg_wegame("restart_game")


    def _sync_pak_button_state(self) -> None:
        disabled = self.workflow.get_pak_status(
            self.config.game_install_dir, self.config.pak_file_names) == "disabled"
        title = "恢复 Pak" if disabled else "屏蔽 Pak"
        text = f"{title} (移除 .disabled)" if disabled else f"{title} (重命名 .disabled)"
        button = self.dbg_rename_pak_btn
        button.setText(text)
        button.setToolTip("点击恢复为正常 .pak 文件" if disabled else "点击重命名为 .disabled，再点一次可恢复")
        self._step_buttons["rename_pak"].update(base_text=text, title=title)
        state = button.property("stepState")
        if disabled or state not in ("running", "failed"):
            self._set_property(button, "stepState", "success" if disabled else "idle")


    @background_action
    def _dbg_rename_pak(self):
        self.workflow.control.paused.clear()
        if not self.config.game_install_dir:
            self.write_log("调试：未配置游戏安装目录，请先填写安装目录。")
            self.set_step_state("rename_pak", "failed", "未配置游戏安装目录")
            return

        self.set_step_state("rename_pak", "running", checkpoint="toggle_pak")
        try:
            progress = self.workflow.progress
            target = progress.run("target", lambda: "restore" if self.workflow.get_pak_status(
                self.config.game_install_dir, self.config.pak_file_names) == "disabled" else "disable")
            action = "restored" if target == "restore" else "disabled"
            operation = self.workflow.restore_pak_files if target == "restore" else self.workflow.rename_pak_files
            results = yield lambda: operation(self.config.game_install_dir, self.config.pak_file_names)
            if action == "disabled":
                self.set_step_state("rename_pak", "success")
                self.write_log("调试：【已屏蔽 Pak】已重命名为 .disabled 状态（再点一次恢复正常）。")
                if self.is_continuous_mode:
                    self.write_log("连续模式：已屏蔽 Pak，继续执行阶段 3 WeGame 流程...")
                    if self.bound_window is not None:
                        yield from self._run_wegame_post_process_tasks()
                    else:
                        self.write_log("调试：未绑定 WeGame 窗口，无法继续执行阶段 3。")
                else:
                    self._offer_continue("wait_wegame")
            else:
                self.set_step_state("rename_pak", "idle")
                self._set_badge(self.workflow_status_badge, "步骤完成：恢复 Pak", "success")
                self.write_log("调试：【已恢复 Pak】已去除 .disabled 后缀，文件恢复正常（再点一次重新屏蔽）。")
                if self.is_continuous_mode:
                    self.write_log("连续模式：已恢复 Pak（未屏蔽），停止后续 WeGame 删包流程。")

            self._sync_pak_button_state()

            for msg in results:
                self.write_log(f"  └─ {msg}")
        except ControlInterrupted:
            raise
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

    _run_debug_step_tasks = _run_debug_step.__wrapped__
    _advance_game_navigation_tasks = advance_game_navigation.__wrapped__
    _check_game_process_tasks = check_game_process.__wrapped__
    _run_wegame_post_process_tasks = _run_wegame_post_process.__wrapped__
    _run_stage_four_tasks = _run_stage_four.__wrapped__
