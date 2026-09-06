from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time
from typing import Literal

import win32con
import win32gui

from scripts.clicker import Clicker
from scripts.element_locator import ElementLocator
from scripts.keyboard import KeyboardController
from scripts.window_binding import BoundWindow, WindowBinder


class NavigationStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class NavigationEvent:
    status: NavigationStatus
    message: str


@dataclass(frozen=True)
class NavigationStep:
    name: str
    action: Literal["click", "press", "press_when_visible", "detect"]
    template_name: str = ""
    virtual_key: int = 0
    repeat: int = 1
    delay_after: float = 1.2


NAVIGATION_STEPS = (
    NavigationStep("选择烽火地带模式", "click", "df_mode_choose.png", delay_after=2.0),
    NavigationStep(
        "关闭活动弹窗",
        "press",
        virtual_key=win32con.VK_SPACE,
        repeat=5,
        delay_after=1.5,
    ),
    NavigationStep(
        "进入烽火地带大厅",
        "press_when_visible",
        "df_enter_game.png",
        virtual_key=win32con.VK_TAB,
        delay_after=2.0,
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
    ) -> None:
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
        self.last_confidence = 0.0
        self.best_confidence = 0.0

    def start(self, process_id: int) -> NavigationEvent:
        self.process_id = process_id
        self.bound_window = None
        self.step_index = 0
        self.deadline = time.monotonic() + self.window_timeout_seconds
        self.next_action_at = 0.0
        self.finished = False
        self.last_confidence = 0.0
        self.best_confidence = 0.0
        return NavigationEvent(NavigationStatus.RUNNING, "正在等待三角洲行动主窗口...")

    def cancel(self) -> None:
        self.finished = True

    def tick(self) -> NavigationEvent | None:
        if self.finished or self.process_id is None:
            return None

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
            return NavigationEvent(
                NavigationStatus.RUNNING,
                f"已绑定游戏窗口：{self.bound_window.title or '<无标题>'} | "
                f"handle={self.bound_window.handle}",
            )

        if now < self.next_action_at:
            return None

        if self.step_index >= len(NAVIGATION_STEPS):
            return self._complete()

        step = NAVIGATION_STEPS[self.step_index]
        position = None
        if step.template_name:
            template_path = self.template_dir / step.template_name
            if not template_path.exists():
                alt_name = "df_mode_init.png" if step.template_name == "df_mode_choose.png" else ("df_mode_choose.png" if step.template_name == "df_mode_init.png" else "")
                if alt_name and (self.template_dir / alt_name).exists():
                    template_path = self.template_dir / alt_name
                else:
                    return self._fail(f"缺少模板：{step.template_name}")

            result = self.locator.match_by_image(
                template_path,
                self.bound_window,
                self.threshold,
            )
            self.last_confidence = result.position.confidence
            self.best_confidence = max(self.best_confidence, self.last_confidence)
            if not result.matched:
                if now >= self.deadline:
                    return self._fail(
                        f"步骤“{step.name}”匹配超时，"
                        f"最高相似度={self.best_confidence:.3f}。"
                    )
                return None
            position = result.position

        # Only activate window when ready to perform an action (click or keypress),
        # so polling doesn't repeatedly steal foreground focus from user
        try:
            self.bound_window = self.window_binder.activate(self.bound_window)
            time.sleep(0.15)
        except Exception as exc:
            rebound = self.window_binder.bind_by_process_id(self.process_id)
            if rebound is not None and rebound.handle != self.bound_window.handle:
                try:
                    self.bound_window = self.window_binder.activate(rebound)
                    time.sleep(0.15)
                except Exception as inner_exc:
                    return self._fail(f"激活游戏窗口失败：{inner_exc}")
            else:
                return self._fail(f"激活游戏窗口失败：{exc}")

        if step.action == "click" and position is not None:
            self.clicker.click(position, self.bound_window.handle)
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
        return NavigationEvent(
            NavigationStatus.RUNNING,
            f"步骤完成：{step.name}"
            + (f" | confidence={matched_confidence:.3f}" if step.template_name else ""),
        )

    def _complete(self) -> NavigationEvent:
        self.finished = True
        return NavigationEvent(
            NavigationStatus.COMPLETE,
            "已识别到选人界面，自动导航已停止。"
            f"相似度={self.last_confidence:.3f}",
        )

    def _fail(self, message: str) -> NavigationEvent:
        self.finished = True
        return NavigationEvent(NavigationStatus.FAILED, message)
