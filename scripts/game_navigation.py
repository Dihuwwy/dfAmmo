from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time
from typing import Literal

import win32con
import win32gui

from scripts.task_control import TaskControl, ControlInterrupted
from scripts.clicker import Clicker
from scripts.element_locator import ElementLocator
from scripts.keyboard import KeyboardController
from scripts.window_binding import BoundWindow, WindowBinder


class NavigationStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class NavigationEvent:
    status: NavigationStatus
    message: str
    step_completed: bool = False


@dataclass(frozen=True)
class NavigationStep:
    name: str
    action: Literal["click", "press", "press_sequence", "press_when_visible", "detect"]
    template_name: str = ""
    virtual_key: int = 0
    repeat: int = 1
    key_sequence: tuple[tuple[int, int], ...] = ()
    delay_after: float = 1.2


NAVIGATION_STEPS = (
    NavigationStep("选择烽火地带模式", "click", "df_mode_choose.png", delay_after=2.0),
    NavigationStep(
        "进入烽火地带大厅",
        "press_sequence",
        key_sequence=((win32con.VK_SPACE, 2), (win32con.VK_TAB, 1)),
        delay_after=2.5,
    ),
    NavigationStep("打开地图选择", "click", "df_map_choose.png", delay_after=1.2),
    NavigationStep("选择长弓溪谷", "click", "df_changgong_choose.png", delay_after=1.2),
    NavigationStep("开始行动", "click", "df_start_manoeuver.png", delay_after=1.5),
    NavigationStep("确认配装", "click", "df_confirm_loadout.png", delay_after=1.0),
    NavigationStep("确认继续", "click", "df_still_continue.png", delay_after=1.0),
    NavigationStep("点击出发", "click", "df_go.png", delay_after=2.0),
    NavigationStep("等待选人界面", "detect", "df_operator_select.png", delay_after=0.0),
)



class GameNavigator:
    """Advance through menu states and stop at the operator selection screen."""

    def __init__(
        self,
        template_dir: Path,
        threshold: float,
        step_timeout_seconds: int,
        window_timeout_seconds: int,
        window_binder: WindowBinder,
        locator: ElementLocator,
        clicker: Clicker,
        keyboard: KeyboardController,
        control: TaskControl | None = None,
    ) -> None:
        self.control = control or TaskControl()
        self.template_dir = template_dir
        self.threshold = threshold
        self.step_timeout_seconds = step_timeout_seconds
        self.window_timeout_seconds = window_timeout_seconds
        self.window_binder = window_binder
        self.locator = locator
        self.clicker = clicker
        self.keyboard = keyboard
        self.process_id: int | None = None
        self.bound_window: BoundWindow | None = None
        self.step_index = 0
        self.deadline = 0.0
        self.next_action_at = 0.0
        self.finished = True
        self.is_paused = False
        self._last_resync_check = 0.0
        self._last_esc_retry = 0.0
        self.last_confidence = 0.0
        self.best_confidence = 0.0
        self.auto_align = True

    def start(self, process_id: int, initial_step: int = 0, auto_align: bool = True) -> NavigationEvent:
        self.auto_align = auto_align
        self.process_id = process_id
        self.bound_window = None
        self.step_index = max(0, min(initial_step, len(NAVIGATION_STEPS) - 1))
        self.deadline = time.monotonic() + self.window_timeout_seconds
        self.next_action_at = 0.0
        self.finished = False
        self.is_paused = False
        self._last_resync_check = 0.0
        self._last_esc_retry = 0.0
        self.last_confidence = 0.0
        self.best_confidence = 0.0
        if self.step_index > 0:
            step_name = NAVIGATION_STEPS[self.step_index].name
            return NavigationEvent(
                NavigationStatus.RUNNING,
                f"正在连接游戏窗口，准备从步骤【{step_name}】推进...",
            )
        return NavigationEvent(NavigationStatus.RUNNING, "正在等待三角洲行动主窗口...")

    def jump_to_step(self, step_index: int) -> NavigationEvent:
        """Manually jump to a specific step index and immediately prepare for execution."""
        if step_index < 0:
            step_index = 0
        elif step_index >= len(NAVIGATION_STEPS):
            step_index = len(NAVIGATION_STEPS) - 1

        self.step_index = step_index
        self.auto_align = False
        self.deadline = time.monotonic() + self.step_timeout_seconds
        self.next_action_at = 0.0
        self.finished = False
        self.is_paused = False
        self._last_esc_retry = 0.0
        self.last_confidence = 0.0
        self.best_confidence = 0.0


        target_step = NAVIGATION_STEPS[step_index]
        return NavigationEvent(
            NavigationStatus.RUNNING,
            f"[跳转] 手动跳转至步骤【{target_step.name}】，立即执行...",
        )

    def cancel(self) -> None:
        self.finished = True
        self.is_paused = False

    def pause(self) -> NavigationEvent:
        self.is_paused = True
        step_name = (
            NAVIGATION_STEPS[self.step_index].name
            if self.step_index < len(NAVIGATION_STEPS)
            else "当前步骤"
        )
        return NavigationEvent(
            NavigationStatus.PAUSED,
            f"[已暂停] 自动化已暂停（当前处于：{step_name}）。"
            "请在游戏中处理弹窗/违禁物品，处理完毕后按 F12 或点击“继续”恢复运行。",
        )

    def resume(self) -> NavigationEvent:
        self.is_paused = False
        self.deadline = time.monotonic() + self.step_timeout_seconds
        self.next_action_at = 0.0
        self._last_esc_retry = 0.0
        resync_event = self.resync_state()
        if resync_event is not None:
            return resync_event

        step_name = (
            NAVIGATION_STEPS[self.step_index].name
            if self.step_index < len(NAVIGATION_STEPS)
            else "未知步骤"
        )
        return NavigationEvent(
            NavigationStatus.RUNNING,
            f"[已继续] 自动化已恢复运行，正在推进步骤：【{step_name}】。",
        )

    def resync_state(self) -> NavigationEvent | None:
        """Scan current game window across candidate steps and align step_index to actual UI."""
        self.control.check()
        if self.process_id is None or self.finished:
            return None

        if self.bound_window is None or not win32gui.IsWindow(self.bound_window.handle):
            self.bound_window = self.window_binder.bind_by_process_id(self.process_id)
            if self.bound_window is None:
                return None

        self.bound_window = self.window_binder.bind_by_handle(self.bound_window.handle)
        try:
            source = self.locator.grab_window_bgr(self.bound_window)
        except ControlInterrupted:
            raise
        except Exception:
            return None

        # 1. Check for forbidden items / popup alert template if exists
        for forbidden_name in ("df_forbidden.png", "df_popup_forbidden.png"):
            forb_path = self.template_dir / forbidden_name
            if forb_path.exists():
                res = self.locator.match_in_source(
                    source, forb_path, self.bound_window, self.threshold
                )
                if res.matched:
                    self.is_paused = True
                    return NavigationEvent(
                        NavigationStatus.PAUSED,
                        "[警告] 检测到违禁物品弹窗，游戏提示禁止进入！已自动为您暂停。"
                        "请在游戏中移出保险箱中的四级弹/违禁物品，处理完毕后按 F12 继续！",
                    )

        # 2. Candidate step indices to inspect, ordered from downstream to upstream
        candidate_indices = [8, 7, 6, 5, 4, 3, 2, 0]
        if self.step_index <= 2:
            candidate_indices = [8, 7, 6, 5, 3, 2, 4, 0]
        for idx in candidate_indices:
            if idx >= len(NAVIGATION_STEPS):
                continue
            cand_step = NAVIGATION_STEPS[idx]
            candidate_tmpl_names = [cand_step.template_name]
            if idx == 0:
                candidate_tmpl_names.extend(["df_change_mode.png", "df_mode_init.png"])
            elif idx == 2:
                candidate_tmpl_names.append("df_map_choose_selected.png")
            elif cand_step.template_name == "df_mode_init.png":
                candidate_tmpl_names.append("df_mode_choose.png")

            match_res = None
            for tname in candidate_tmpl_names:
                tmpl_path = self.template_dir / tname
                if not tmpl_path.exists():
                    continue
                res = self.locator.match_in_source(
                    source, tmpl_path, self.bound_window, max(self.threshold, 0.90)
                )
                if res.matched and res.position.confidence >= max(self.threshold, 0.90):
                    match_res = res
                    break

            if match_res is not None and match_res.matched:
                if idx == 4 and self.step_index <= 2:
                    self.is_paused = True
                    return NavigationEvent(
                        NavigationStatus.PAUSED,
                        "已识别到烽火大厅，但地图入口未匹配。请采集已选地图卡片为 df_map_choose_selected.png，"
                        "或手动打开地图选择后继续；未发送 ESC 或 Tab。",
                    )
                conf = (
                    float(match_res.position.confidence)
                    if hasattr(match_res.position, "confidence") and isinstance(match_res.position.confidence, (int, float))
                    else 0.0
                )
                old_index = self.step_index
                self.step_index = idx
                self.deadline = time.monotonic() + self.step_timeout_seconds
                self.next_action_at = 0.0
                self.last_confidence = conf
                self.best_confidence = conf

                if cand_step.action == "detect":
                    return self._complete()

                if old_index != idx:
                    return NavigationEvent(
                        NavigationStatus.RUNNING,
                        f"[对齐] 识别到游戏画面处于【{cand_step.name}】"
                        f"（相似度={conf:.3f}），已同步执行进度！",
                    )
                return NavigationEvent(
                    NavigationStatus.RUNNING,
                    f"[对齐] 当前画面对齐【{cand_step.name}】（相似度={conf:.3f}），继续执行...",
                )

        return None

    def tick(self) -> NavigationEvent | None:
        if self.finished or self.process_id is None or self.is_paused:
            return None

        self.control.check()
        now = time.monotonic()
        need_rebind = False
        if self.bound_window is None or not win32gui.IsWindow(self.bound_window.handle):
            need_rebind = True
        elif not self.bound_window.title.strip():
            candidate = self.window_binder.bind_by_process_id(self.process_id)
            if candidate and candidate.handle != self.bound_window.handle and candidate.title.strip():
                self.bound_window = candidate
                return NavigationEvent(
                    NavigationStatus.RUNNING,
                    f"已切换至游戏主窗口：{self.bound_window.title} | handle={self.bound_window.handle}",
                )

        if need_rebind:
            self.bound_window = self.window_binder.bind_by_process_id(self.process_id)
            if self.bound_window is None:
                if now >= self.deadline:
                    return self._fail("等待三角洲行动主窗口超时。")
                return None

            self.deadline = now + self.step_timeout_seconds
            # Takeovers align from the remembered step; explicit jumps retain their target.
            resync_msg = ""
            if self.auto_align:
                resync_event = self.resync_state()
                if resync_event is not None:
                    if resync_event.status in (NavigationStatus.COMPLETE, NavigationStatus.PAUSED):
                        return resync_event
                    resync_msg = f" | {resync_event.message}"

            return NavigationEvent(
                NavigationStatus.RUNNING,
                f"已绑定游戏窗口：{self.bound_window.title or '<无标题>'} | "
                f"handle={self.bound_window.handle}{resync_msg}",
            )

        if now < self.next_action_at:
            return None

        self.bound_window = self.window_binder.bind_by_handle(self.bound_window.handle)
        if self.step_index >= len(NAVIGATION_STEPS):
            return self._complete()

        step = NAVIGATION_STEPS[self.step_index]
        if self.step_index == 1:
            aligned = self.resync_state()
            if aligned is not None and (self.step_index != 1 or aligned.status != NavigationStatus.RUNNING):
                return aligned
        position = None
        matched_cand_name = ""
        if step.template_name:
            candidate_names: list[str] = [step.template_name]
            if self.step_index == 0:
                candidate_names.append("df_change_mode.png")
                if step.template_name == "df_mode_choose.png":
                    candidate_names.append("df_mode_init.png")
                elif step.template_name == "df_mode_init.png":
                    candidate_names.append("df_mode_choose.png")
            elif self.step_index == 2:
                candidate_names.append("df_map_choose_selected.png")

            matched_result = None
            best_cand_confidence = 0.0

            source = self.locator.grab_window_bgr(self.bound_window)
            for cand_name in candidate_names:
                self.control.check()
                tmpl_path = self.template_dir / cand_name
                if not tmpl_path.exists():
                    continue
                cand_res = self.locator.match_in_source(
                    source, tmpl_path,
                    self.bound_window,
                    self.threshold,
                )
                if cand_res.position.confidence > best_cand_confidence:
                    best_cand_confidence = cand_res.position.confidence
                if cand_res.matched:
                    matched_result = cand_res
                    matched_cand_name = cand_name
                    break

            self.last_confidence = best_cand_confidence
            self.best_confidence = max(self.best_confidence, self.last_confidence)

            if matched_result is None or not matched_result.matched:
                step_elapsed = now - (self.deadline - self.step_timeout_seconds)

                # Align before any recovery key: the user may already be in a lobby.
                if self.step_index in (0, 2) or (step_elapsed >= 3.0 and now - self._last_resync_check >= 2.5):
                    self._last_resync_check = now
                    aligned = self.resync_state()
                    if aligned is not None:
                        return aligned

                if now >= self.deadline:
                    return self._fail(
                        f"步骤“{step.name}”匹配超时，"
                        f"最高相似度={self.best_confidence:.3f}。"
                    )
                return None
            position = matched_result.position

        recognized_window = self.bound_window
        # Only activate window when ready to perform an action (click or keypress),
        # so polling doesn't repeatedly steal foreground focus from user
        try:
            self.bound_window = self.window_binder.activate(self.bound_window)
            self.control.wait(0.15)
        except ControlInterrupted:
            raise
        except Exception as exc:
            rebound = self.window_binder.bind_by_process_id(self.process_id)
            if rebound is not None and rebound.handle != self.bound_window.handle:
                try:
                    self.bound_window = self.window_binder.activate(rebound)
                    self.control.wait(0.15)
                except ControlInterrupted:
                    raise
                except Exception as inner_exc:
                    return self._fail(f"激活游戏窗口失败：{inner_exc}")
            else:
                return self._fail(f"激活游戏窗口失败：{exc}")

        self.control.check()
        if position is not None and self.bound_window != recognized_window:
            if (self.bound_window.right - self.bound_window.left, self.bound_window.bottom - self.bound_window.top) != (recognized_window.right - recognized_window.left, recognized_window.bottom - recognized_window.top):
                return None
            from dataclasses import replace
            position = replace(position, x=position.x + self.bound_window.left - recognized_window.left, y=position.y + self.bound_window.top - recognized_window.top)
        if step.action == "click" and position is not None:
            self.clicker.click(position, self.bound_window.handle)
        elif step.action == "press_sequence" and step.key_sequence:
            self.keyboard.press_sequence(step.key_sequence)
        elif step.action in ("press", "press_when_visible"):
            self.keyboard.press(step.virtual_key, step.repeat)
        elif step.action == "detect":
            return self._complete()


        self.step_index += 1
        self.next_action_at = time.monotonic() + step.delay_after
        self.deadline = self.next_action_at + self.step_timeout_seconds
        matched_confidence = self.last_confidence
        self.last_confidence = 0.0
        self.best_confidence = 0.0
        extra_note = ""
        if self.step_index - 1 == 0 and matched_cand_name == "df_change_mode.png":
            extra_note = "（通过模式切换菜单匹配）"
        return NavigationEvent(
            NavigationStatus.RUNNING,
            f"步骤完成：{step.name}{extra_note}"
            + (f" | confidence={matched_confidence:.3f}" if step.template_name else ""),
            step_completed=True,
        )

    def _complete(self) -> NavigationEvent:
        self.finished = True
        self.is_paused = False
        return NavigationEvent(
            NavigationStatus.COMPLETE,
            "已识别到选人界面，自动导航已停止。"
            f"相似度={self.last_confidence:.3f}",
        )

    def _fail(self, message: str) -> NavigationEvent:
        self.finished = True
        self.is_paused = False
        return NavigationEvent(NavigationStatus.FAILED, message)
