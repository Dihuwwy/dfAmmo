from __future__ import annotations

from scripts.clicker import Clicker
from scripts.task_control import TaskControl


class KeyboardController:
    """Send simple key presses to the current foreground window."""

    def __init__(self, control: TaskControl | None = None):
        self.control = control or TaskControl()
        self.input = Clicker(self.control)

    def press(self, virtual_key: int, repeat: int = 1, interval: float = 0.12) -> None:
        self.input.press(virtual_key, repeat=repeat, interval=interval)

    def press_sequence(
        self,
        sequence: list[tuple[int, int]] | tuple[tuple[int, int], ...],
        pause_between: float = 0.25,
    ) -> None:
        for index, (vk, repeat) in enumerate(sequence):
            self.press(vk, repeat=repeat)
            if index + 1 < len(sequence):
                self.control.wait(pause_between)
