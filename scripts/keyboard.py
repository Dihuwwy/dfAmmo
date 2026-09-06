from __future__ import annotations

import time

import win32api
import win32con


class KeyboardController:
    """Send simple key presses to the current foreground window."""

    def press(self, virtual_key: int, repeat: int = 1, interval: float = 0.12) -> None:
        for index in range(repeat):
            win32api.keybd_event(virtual_key, 0, 0, 0)
            time.sleep(0.045)
            win32api.keybd_event(virtual_key, 0, win32con.KEYEVENTF_KEYUP, 0)
            if index + 1 < repeat:
                time.sleep(interval)

