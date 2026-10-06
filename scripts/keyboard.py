from __future__ import annotations

from scripts.task_control import TaskControl

import win32api
import win32con


class KeyboardController:
    """Send simple key presses to the current foreground window."""

    def __init__(self, control: TaskControl | None = None):
        self.control = control or TaskControl()

    def press(self, virtual_key: int, repeat: int = 1, interval: float = 0.12) -> None:
        for index in range(repeat):
            self.control.check()
            win32api.keybd_event(virtual_key, 0, 0, 0)
            try:
                self.control.wait(0.045)
            finally:
                win32api.keybd_event(virtual_key, 0, win32con.KEYEVENTF_KEYUP, 0)
            if index + 1 < repeat:
                self.control.wait(interval)

    def press_sequence(
        self,
        sequence: list[tuple[int, int]] | tuple[tuple[int, int], ...],
        pause_between: float = 0.25,
    ) -> None:
        for index, (vk, repeat) in enumerate(sequence):
            self.press(vk, repeat=repeat)
            if index + 1 < len(sequence):
                self.control.wait(pause_between)


