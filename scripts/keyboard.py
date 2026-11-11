from __future__ import annotations

from scripts.clicker import Clicker
from scripts.task_control import TaskControl


class KeyboardController:
    """Send simple key presses to the current foreground window."""

    def __init__(self, control: TaskControl | None = None):
        self.control = control or TaskControl()
        self.input = Clicker(self.control)

    def press(self, virtual_key: int, repeat: int = 1, interval: float = 0.12,
              window_handle: int | None = None) -> None:
        self.input.press(virtual_key, repeat=repeat, interval=interval, window_handle=window_handle)
