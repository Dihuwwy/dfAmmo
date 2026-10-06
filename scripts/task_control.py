"""Cooperative interruption shared by recognition, waits, and input actions."""
from __future__ import annotations

import time
from threading import Event


class ControlInterrupted(Exception):
    pass


class TaskCancelled(ControlInterrupted):
    pass


class TaskPaused(ControlInterrupted):
    pass


class TaskControl:
    def __init__(self) -> None:
        self.cancelled = Event()
        self.paused = Event()

    def check(self) -> None:
        if self.cancelled.is_set():
            raise TaskCancelled()
        if self.paused.is_set():
            raise TaskPaused()

    def wait(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            self.check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.cancelled.wait(min(remaining, 0.02))
