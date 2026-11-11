from __future__ import annotations

import subprocess
import time
from html import escape
from dataclasses import replace
from functools import partial
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from scripts.game_navigation import NavigationStatus
from scripts.template_capture import TemplateCaptureOverlay
from scripts.workflow import Workflow
from scripts.task_runner import background_action
from scripts.task_control import ControlInterrupted, TaskPaused


class ActionsMixin:
    """Action handlers and workflows; view state is published through `_set_ui`."""

    _wegame_step_ids = ("wait_wegame", "click_more", "assets_manage", "delete_map", "restart_game")
    _stage_four_step_ids = ("detect_result", "restore_pak", "redownload_map", "warehouse")
    _stage_step_ids = (("nav_game",), ("rename_pak", "open_paks"), _wegame_step_ids, _stage_four_step_ids)
    _nav_step_labels = ("模式", "进大厅", "选地图", "", "行动", "配装", "继续", "出发", "选人")

    # ── View State ───────────────────────────────────────────────────────────

    def _set_ui(self, **values) -> None:
        """Publish changed values to QML; unchanged ones trigger no rebinding."""
        for key, value in values.items():
            if key not in self._ui_state or self._ui_state[key] != value:
                self._ui_state[key] = value
                self.ui.insert(key, value)

    def _set_status(self, text: str, state: str, tooltip: str = "") -> None:
        self._set_ui(statusText=text, statusState=state, statusTooltip=tooltip)

    def _build_steps(self) -> None:
        """Create idle step, navigation pill and stage state for the configured map."""
        map_name = self.config.map_name
        steps = {
            "nav_game": ("接管导航", ""),
            "rename_pak": ("屏蔽 Pak", ""),
            "open_paks": ("浏览 Paks 目录", "在资源管理器中打开 Paks 补丁文件夹"),
            "wait_wegame": ("等待启动按钮", "等待 WeGame 客户端回到启动按钮可用状态"),
            "click_more": ("选项菜单 (...)", "点击 WeGame 游戏主页右侧的更多操作 (...) 按钮"),
            "assets_manage": ("资源包管理", "点击弹出菜单中的“游戏资源包管理”项"),
            "delete_map": (f"删除{map_name}", "在资源管理窗口中删除目标地图资源"),
            "restart_game": ("重新启动游戏", "在 WeGame 中点击启动按钮重新拉起三角洲行动"),
            "detect_result": ("确认并进大厅", ""),
            "restore_pak": ("恢复 Pak", ""),
            "redownload_map": ("恢复地图下载", ""),
            "warehouse": ("进入仓库并确认", ""),
        }
        self._steps = {step_id: {"title": title, "text": title, "state": "idle", "tooltip": tooltip}
                       for step_id, (title, tooltip) in steps.items()}
        for step_ids in (self._wegame_step_ids, self._stage_four_step_ids):
            for number, step_id in enumerate(step_ids, start=1):
                self._steps[step_id]["text"] = f"{number}.{self._steps[step_id]['title']}"
        self._nav_states = ["idle"] * len(self._nav_step_labels)
        self._stages = ["idle"] * len(self._stage_step_ids)
        self._publish_steps()

    def _publish_steps(self) -> None:
        navigator_steps = self.workflow.game_navigator.steps
        self._set_ui(
            steps={step_id: {"text": info["text"], "state": info["state"], "tooltip": info["tooltip"]}
                   for step_id, info in self._steps.items()},
            navPills=[{"text": f"{index + 1}.{label or '选' + self.config.map_name}", "state": state,
                       "tooltip": f"跳转至第 {index + 1} 步执行：【{navigator_steps[index].name}】"}
                      for index, (label, state) in enumerate(zip(self._nav_step_labels, self._nav_states))],
            stages=list(self._stages),
        )

    def _set_running_controls(self, running: bool) -> None:
        """Update action button availability for start/stop cycles."""
        active = running or self.task_runner.busy
        self._set_ui(startEnabled=not active, stopEnabled=active,
                     mapEnabled=not (active or bool(self._resume_step)))
        self._set_pause_button_state(is_paused=False)

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
            "delete_map": (f"查找并删除{cfg.map_name}（会自动向下滚动）...",
                partial(wf.delete_changgong_map, cfg.map_template(cfg.wegame_delete_map_template),
                        threshold, timeout=cfg.delete_map_timeout_seconds,
                        confirm_template_name=cfg.wegame_confirm_delete_template,
                        confirm_timeout=cfg.confirm_delete_timeout_seconds,
                        game_install_dir=cfg.game_install_dir,
                        pak_names=cfg.active_pak_names,
                        bin_template_name=cfg.wegame_bin_template,
                        manager_header_template=cfg.wegame_manager_header_template),
                lambda pos: f"已发送 WeGame 确定及关闭点击，保留本地重命名文件 (x={pos.x}, y={pos.y})。", f"删除{cfg.map_name}", 1.0),
            "restart_game": ("重新启动游戏...",
                partial(wf.click_start_button, window, cfg.start_button_templates, threshold),
                lambda ret: f"已点击启动按钮 {ret[1].name} (x={ret[0].x}, y={ret[0].y})。",
                "重新启动游戏", 1.2),
        }

    def run_step(self, step_id: str) -> None:
        """Run a single step from its pill."""
        if step_id == "rename_pak":
            self._dbg_rename_pak()
        elif step_id == "open_paks":
            self._dbg_open_paks()
        elif step_id in self._wegame_step_ids:
            self._run_wegame_post_process(start_step=step_id)
        elif step_id in self._stage_four_step_ids:
            self._run_stage_four(start_step=step_id)

    # ── Log Management ───────────────────────────────────────────────────────

    def clear_log(self) -> None:
        """Clear current log console output."""
        self._log_buffer.clear()
        self._log_lines.clear()
        self.logReset.emit("")

    def copy_log(self) -> None:
        """Copy all log content to clipboard."""
        self._flush_log_buffer()
        if self._log_lines:
            QApplication.clipboard().setText("\n".join(plain for plain, _ in self._log_lines))
            self.write_log("已复制全部运行日志到剪贴板。")

    def write_log(self, message: str) -> None:
        """Append a timestamped message to the log buffer."""
        timestamp = time.strftime("%H:%M:%S")
        color = "#E2E8F0"
        if any(word in message for word in ("失败", "错误", "异常")):
            color = "#EF4444"
        elif any(word in message for word in ("请先", "警告", "提示", "未检测", "未绑定", "超时")):
            color = "#F59E0B"
        elif any(word in message for word in ("成功", "完成", "已恢复", "已连接")):
            color = "#10B981"
        self._log_buffer.append((
            f"[{timestamp}] {message}",
            f'<span style="color:#64748B;">[{timestamp}]</span> '
            f'<span style="color:{color};">{escape(message).replace(chr(10), "<br>")}</span>'))

    def _flush_log_buffer(self) -> None:
        """Send buffered entries to the view in one batch, keeping the last 800."""
        if not self._log_buffer:
            return
        lines, self._log_buffer = self._log_buffer, []
        self._log_lines.extend(lines)
        if len(self._log_lines) > 1000:
            del self._log_lines[:-800]
            self.logReset.emit("<br>".join(html for _, html in self._log_lines))
        else:
            self.logAppended.emit("<br>".join(html for _, html in lines))

    # ── Window Binding ───────────────────────────────────────────────────────

    def bind_window_at(self, x: int, y: int) -> None:
        """Bind to target window at given screen coordinates."""
        try:
            bound_window = self.workflow.window_binder.bind_at_position(x, y)
        except Exception as exc:
            self.write_log(f"绑定失败：{exc}")
            return

        if bound_window.handle == self._window_handle():
            self.write_log("绑定到了工具窗口本身，请拖到 WeGame 窗口上再松开。")
            return

        self.bound_window = bound_window
        self._set_ui(
            connected=True,
            connTitle=bound_window.title or "<无标题>",
            connSubtitle=f"{bound_window.process_name or '<未知进程>'} · PID {bound_window.process_id or '-'}",
            connTooltip=f"窗口句柄：{bound_window.handle}",
        )
        self.write_log(
            "窗口绑定成功："
            f"{bound_window.title or '<无标题>'} | "
            f"{bound_window.process_name or '<未知进程>'} | "
            f"pid={bound_window.process_id or '-'}"
        )

    # ── Automation Control ───────────────────────────────────────────────────

    def _set_pause_button_state(self, is_paused: bool) -> None:
        self._set_ui(continueEnabled=is_paused, paused=is_paused)


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
            yield from self._run_wegame_post_process_tasks(start_step=step, realign=True)
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
        self._set_ui(continueEnabled=self._resume_step is not None and not self.task_runner.busy)

        self._bring_to_front()

        for step_id, info in self._steps.items():
            if info["state"] == "running":
                self.set_step_state(step_id, "idle")
        # Keep the cursor visible on the stopped navigation step, without the running pulse.
        self._nav_states = ["current" if state == "running" else state for state in self._nav_states]
        self._publish_steps()
        self._set_status("任务已停止", "idle")

        if was_running:
            self.write_log("[任务停止] 已通过快捷键/按钮停止当前自动化任务。")
            if self._resume_step:
                self.write_log("已保留当前步骤及小操作进度，可点击“继续”接续；点击“开始卡邮件”重新开始。")
        else:
            self.write_log("[任务停止] 当前无正在运行的自动化任务。")

    # ── Settings ─────────────────────────────────────────────────────────────

    def save_game_dir(self, game_install_dir: str) -> None:
        game_install_dir = game_install_dir.strip()
        if game_install_dir == self.config.game_install_dir:
            return

        updated_config = replace(self.config, game_install_dir=game_install_dir)
        try:
            updated_config.save_to_file()
        except OSError as exc:
            self.write_log(f"保存游戏安装目录失败：{exc}")
            return

        self.config = updated_config
        self._set_ui(gameDir=game_install_dir)
        self.write_log("游戏安装目录已保存。")
        self._sync_pak_button_state()

    def choose_game_dir(self) -> str:
        """Pick the install directory; an empty result means the dialog was cancelled."""
        selected_dir = QFileDialog.getExistingDirectory(
            None,
            "选择包含 DeltaForce 文件夹的安装目录",
            self.config.game_install_dir or str(Path.home()),
        )
        if selected_dir:
            self.save_game_dir(selected_dir)
        return selected_dir

    def set_operation_mode(self, new_mode: str) -> None:
        if new_mode == self.config.operation_mode:
            return
        self.config = replace(self.config, operation_mode=new_mode)
        self._set_ui(operationMode=new_mode)
        try:
            self.config.save_to_file()
        except OSError as exc:
            self.write_log(f"保存运行模式失败：{exc}")
        else:
            mode_name = "半自动模式" if new_mode == "semi_auto" else "全自动模式"
            self.write_log(f"已切换运行模式为：{mode_name}")

    def set_map(self, map_id: str) -> None:
        if map_id == self.config.map_id or not self._ui_state["mapEnabled"]:
            return
        self.config = replace(self.config, map_id=map_id)
        self._set_ui(mapId=map_id)
        self.workflow.game_navigator.configure_map(self.config)
        self.workflow.progress.reset()
        self.workflow.game_navigator.step_index = 0
        self.reset_all_step_states()
        try:
            self.config.save_to_file()
        except OSError as exc:
            self.write_log(f"保存目标地图失败：{exc}")
        self.write_log(f"目标地图：{self.config.map_name}。请确认对应模板已采集、Pak 文件名正确。")

    def set_fill_teammates(self, checked: bool) -> None:
        self.config = replace(self.config, check_fill_teammates=checked)
        self._set_ui(fillTeammates=checked)
        self.workflow.game_navigator.check_fill_teammates = checked
        self.workflow.game_navigator._fill_teammates_verified = self.workflow.game_navigator._fill_teammates_clicked = False
        try:
            self.config.save_to_file()
        except OSError as exc:
            self.write_log(f"保存补齐队友设置失败：{exc}")

    # ── Template Capture ─────────────────────────────────────────────────────

    def start_template_capture(self, name: str) -> None:
        if self._automation_active():
            self.write_log("请先停止当前任务，再采集模板。")
            return
        self.pending_template_name = name.strip()
        if not self.pending_template_name:
            self.write_log("模板名称不能为空。")
            return

        self.write_log("开始采集模板，请框选目标元素区域。")
        self._hide_window()

        self.capture_overlay = TemplateCaptureOverlay()
        self.capture_overlay.selected.connect(self.save_template_from_rect)
        self.capture_overlay.canceled.connect(self.cancel_template_capture)

        QTimer.singleShot(200, self.capture_overlay.begin)

    def cancel_template_capture(self) -> None:
        self._show_window()
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
            self._show_window()
            self.write_log(f"模板保存失败：{exc}")
            self.toast.emit(f"模板保存失败：{exc}", "error")
            return

        self._show_window()
        self.write_log(f"模板已保存：{output_path}")
        self.toast.emit(f"模板已保存：{output_path.name}", "info")

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
        if not (yield from self._require_pak_targets()):
            return
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
        self._hide_window()

        try:
            position, template_path = (yield lambda: self.workflow.progress.run("launch", lambda: self.workflow.click_start_button(
                self.bound_window,
                self.config.start_button_templates,
                self.config.template_match_threshold,
            )))
        except ControlInterrupted:
            raise
        except Exception as exc:
            self._show_window()
            self.write_log(f"启动按钮匹配/点击失败：{exc}")
            self._set_status("启动失败，请查看日志", "failed")
            return

        self._show_window()
        self._set_running_controls(True)
        self.game_process_deadline = time.monotonic() + self.config.game_process_timeout_seconds
        self.write_log(
            "已点击启动元素："
            f"x={position.x}, y={position.y}, "
            f"confidence={position.confidence:.3f}, template={template_path.name}"
        )
        self.write_log("正在等待三角洲行动游戏进程...")
        self._set_status("等待游戏启动...", "running")
        self.game_process_timer.start()
        yield from self._check_game_process_tasks()

    def _require_pak_targets(self):
        """Check Pak targets up front: navigation ends by terminating the game."""
        try:
            yield lambda: self.workflow.require_pak_targets(
                self.config.game_install_dir, self.config.active_pak_names)
        except ControlInterrupted:
            raise
        except (OSError, RuntimeError) as exc:
            self.set_step_state("nav_game", "failed", str(exc))
            self.write_log(str(exc))
            return False
        return True

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
            self._set_status("等待启动超时", "failed")

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
            self._set_status(f"流程已暂停（步骤 {cur_step_idx + 1}）", "running")
            return

        if event.status in (NavigationStatus.COMPLETE, NavigationStatus.FAILED):
            self.navigation_timer.stop()
            self._set_running_controls(False)

            if event.status == NavigationStatus.FAILED:
                self.set_step_state("nav_game", "failed", event.message)
                return

            if event.status == NavigationStatus.COMPLETE:
                self.set_step_state("nav_game", "success")
                self.update_nav_substep_pills(len(self._nav_states))
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
                self.config.game_install_dir, self.config.active_pak_names, self.config.active_extra_files)
            for message in messages:
                self.write_log(message)
            yield lambda: self.workflow.require_paks_disabled(
                self.config.game_install_dir, self.config.active_pak_names, blocked_action="后续流程")
        except ControlInterrupted:
            raise
        except (OSError, RuntimeError) as exc:
            self.set_step_state("rename_pak", "failed", str(exc))
            self.write_log(f"屏蔽 Pak 失败：{exc}")
            self._sync_pak_button_state()
            return
        self._sync_pak_button_state()
        self.set_step_state("rename_pak", "success")
        if self.is_continuous_mode and self.bound_window is not None:
            yield from self._run_wegame_post_process_tasks()
        else:
            self._offer_continue("wait_wegame")

    @background_action
    def _run_wegame_post_process(self, start_step: str = "wait_wegame", realign: bool = False):
        if not self._dbg_require_bound():
            return
        self.workflow.control.paused.clear()
        steps = self._wegame_steps()
        order = list(steps)
        requested_index = order.index(start_step) if start_step in steps else 0
        if realign and start_step in ("click_more", "assets_manage", "delete_map"):
            start_step = yield from self._realign_wegame_step(start_step)
        start_index = order.index(start_step) if start_step in steps else 0
        for step_id in order[start_index:]:
            start_msg, action, success_msg, fail_label, delay = steps[step_id]
            if delay:
                yield partial(self.workflow.control.wait, delay)
            succeeded = yield from self._run_debug_step_tasks(
                step_id, start_msg, action, success_msg, fail_label)
            if not succeeded:
                return
            # Steps redone after stepping back do not count as the single step.
            if self.execution_mode == "step" and order.index(step_id) >= requested_index:
                next_index = order.index(step_id) + 1
                self._offer_continue(order[next_index] if next_index < len(order) else "detect_result")
                return
        self._set_status("WeGame 阶段已完成", "success")
        if self.is_continuous_mode:
            yield from self._run_stage_four_tasks()
        else:
            self._offer_continue("detect_result")

    def _realign_wegame_step(self, step: str):
        """After a stop, continue from the step the WeGame screen is actually at."""
        progress = self.workflow.progress
        if step == "delete_map" and "bin" in progress.completed:
            # The delete click was sent; the deletion logic verifies the rest itself.
            return step
        try:
            located = yield partial(self.workflow.locate_wegame_step, self.bound_window,
                                    self.config.wegame_assets_manage_template, self.config.template_match_threshold)
        except ControlInterrupted:
            raise
        except Exception as exc:
            self.write_log(f"未能识别 WeGame 当前画面，按原步骤继续：{exc}")
            return step
        if located != step:
            self.write_log(f"[对齐] WeGame 画面处于【{self._steps[located]['title']}】，从该步骤继续。")
        elif step != "delete_map":
            # The click may have been sent without taking effect; the screen says it is still due.
            progress.completed.pop("action", None)
        return located

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
            self._set_status("已返回烽火大厅" if matched else "结果未确认，未恢复 Pak",
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
                    self.config.game_install_dir, self.config.active_pak_names, self.config.active_extra_files)
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
            self._set_status("全自动后续待实现", "idle")
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
        self._set_status("半自动已完成", "success")
        self.write_log("半自动流程已结束，不再执行后续步骤或循环。请手动穿戴装备，等待地图恢复后切换全面战场并重连。")

    def _run_stage_four_redownload_tasks(self):
        self.set_step_state("redownload_map", "running")
        self.write_log(f"第四阶段第 3 步：选择{self.config.map_name}、点击下载，再按两次 ESC...")
        try:
            yield lambda: self.workflow.redownload_stage_four_map(
                self.config.map_template(self.config.redownload_map_choice_template), self.config.map_template(self.config.redownload_map_panel_template),
                self.config.template_match_threshold,
                self.config.navigation_step_timeout_seconds)
        except ControlInterrupted:
            raise
        except Exception as exc:
            self.set_step_state("redownload_map", "failed", str(exc))
            self.write_log(f"第四阶段地图下载请求失败：{exc}；Pak 已经恢复。")
            return False
        self.set_step_state("redownload_map", "success")
        self._set_status("地图恢复请求已发送", "success")
        return True


    # ── Debug & Step Status Management ───────────────────────────────────────

    def set_step_state(self, step_id: str, state: str, detail: str = "", *, checkpoint=None) -> None:
        if state == "running" and step_id != "open_paks":
            self.workflow.progress.enter(checkpoint or step_id)
        info = self._steps.get(step_id)
        title = info["title"] if info else step_id
        if info:
            info["state"] = state
        for stage, step_ids in enumerate(self._stage_step_ids):
            if step_id in step_ids:
                self._stages[stage] = state
        self._publish_steps()
        prefix = {"running": "正在执行", "success": "步骤完成", "failed": "步骤失败"}
        text = f"{prefix[state]}：{title}" if state in prefix else "待命就绪"
        self._set_status(text, state if state in prefix else "idle",
                         f"失败详情：{detail}" if state == "failed" and detail else "")

    def update_nav_substep_pills(self, active_index: int) -> None:
        """Mark navigation pills before the cursor as done and the cursor as running."""
        self._nav_states = ["success" if index < active_index else "running" if index == active_index else "idle"
                            for index in range(len(self._nav_states))]
        self._publish_steps()

    def reset_all_step_states(self) -> None:
        """Reset all steps, navigation pills and stage markers to idle."""
        self._resume_step = None
        self._set_ui(mapEnabled=not self._automation_active(),
                     continueEnabled=self.workflow.is_navigation_paused)
        self._build_steps()
        self._set_status("待命就绪", "idle")
        self._sync_pak_button_state()

    @property
    def execution_mode(self) -> str:
        return self._execution_mode

    @property
    def is_continuous_mode(self) -> bool:
        """Return True if continuous step execution mode is enabled."""
        return self.execution_mode == "continuous"

    def set_execution_mode(self, mode: str) -> None:
        """Switch between single-step, stage and continuous execution."""
        labels = {"step": "单步", "stage": "阶段", "continuous": "连续"}
        if mode == self._execution_mode or mode not in labels:
            return
        self._execution_mode = mode
        self._set_ui(executionMode=mode)
        self._navigation_mode = mode
        self._continue_after_navigation = self.is_continuous_mode
        self.write_log(f"执行模式已切换为：【{labels[mode]}】")

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
        if not (yield from self._require_pak_targets()):
            return
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
        if not (yield from self._require_pak_targets()):
            return
        game_process = (yield lambda: self.workflow.find_game_process())
        if game_process is None:
            self.write_log("未检测到三角洲行动游戏进程，请先启动游戏再点击步骤跳转。")
            return

        target_step = self.workflow.game_navigator.steps[step_index]
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

    def _sync_pak_button_state(self) -> None:
        disabled = self.workflow.get_pak_status(
            self.config.game_install_dir, self.config.active_pak_names) == "disabled"
        info = self._steps["rename_pak"]
        info["title"] = info["text"] = "恢复 Pak" if disabled else "屏蔽 Pak"
        info["tooltip"] = ("点击移除 .disabled 后缀，恢复为正常 .pak 文件" if disabled
                           else "点击重命名为 .disabled 以屏蔽加载，再点一次可恢复")
        if disabled or info["state"] not in ("running", "failed"):
            info["state"] = "success" if disabled else "idle"
        self._publish_steps()


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
                self.config.game_install_dir, self.config.active_pak_names) == "disabled" else "disable")
            action = "restored" if target == "restore" else "disabled"
            operation = self.workflow.restore_pak_files if target == "restore" else self.workflow.rename_pak_files
            results = yield lambda: operation(self.config.game_install_dir, self.config.active_pak_names,
                                              self.config.active_extra_files)
            for msg in results:
                self.write_log(f"  └─ {msg}")
            if action == "disabled":
                yield lambda: self.workflow.require_paks_disabled(
                    self.config.game_install_dir, self.config.active_pak_names, blocked_action="后续流程")
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
                self._set_status("步骤完成：恢复 Pak", "success")
                self.write_log("调试：【已恢复 Pak】已去除 .disabled 后缀，文件恢复正常（再点一次重新屏蔽）。")
                if self.is_continuous_mode:
                    self.write_log("连续模式：已恢复 Pak（未屏蔽），停止后续 WeGame 删包流程。")

            self._sync_pak_button_state()
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
