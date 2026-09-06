from __future__ import annotations

import ctypes
import random
import time

import win32api
import win32con
import win32gui
from pywinauto import mouse

from scripts.dpi import physical_coordinates
from scripts.element_locator import ElementPosition


INPUT_MOUSE = 0
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000


class MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    )


class InputUnion(ctypes.Union):
    _fields_ = (("mi", MouseInput),)


class Input(ctypes.Structure):
    _fields_ = (
        ("type", ctypes.c_ulong),
        ("union", InputUnion),
    )


class Clicker:
    """Responsible for mouse click actions."""

    def move_to(self, position: ElementPosition) -> tuple[int, int]:
        x, y = int(position.x), int(position.y)
        with physical_coordinates():
            return self._move_to_point(x, y)

    def _move_to_point(self, x: int, y: int) -> tuple[int, int]:
        self._ensure_point_on_screen(x, y)
        errors: list[str] = []

        for move_method in (
            self._move_with_user32,
            self._move_with_send_input,
            self._move_with_pywinauto,
        ):
            try:
                move_method(x, y)
                if self._cursor_is_near(x, y):
                    return x, y
                current_x, current_y = win32api.GetCursorPos()
                errors.append(
                    f"{move_method.__name__}: 调用成功但鼠标未到位，"
                    f"current=({current_x}, {current_y})"
                )
            except Exception as exc:
                errors.append(f"{move_method.__name__}: {exc}")

        raise RuntimeError("所有移动方式都失败：" + " | ".join(errors))

    def _move_with_send_input(self, x: int, y: int) -> None:
        left, top, right, bottom = self._screen_bounds()
        absolute_x = round((x - left) * 65535 / max(1, right - left - 1))
        absolute_y = round((y - top) * 65535 / max(1, bottom - top - 1))
        self._send_inputs(
            (
                self._mouse_input(
                    absolute_x,
                    absolute_y,
                    MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                ),
            ),
            x,
            y,
        )

    def _move_with_user32(self, x: int, y: int) -> None:
        if not ctypes.windll.user32.SetCursorPos(x, y):
            raise RuntimeError(f"SetCursorPos 失败：x={x}, y={y}")

    def _move_with_pywinauto(self, x: int, y: int) -> None:
        mouse.move(coords=(x, y))

    def _cursor_is_near(self, x: int, y: int, tolerance: int = 3) -> bool:
        current_x, current_y = win32api.GetCursorPos()
        return abs(current_x - x) <= tolerance and abs(current_y - y) <= tolerance

    def click(self, position: ElementPosition, window_handle: int | None = None) -> bool:
        x, y = self._humanized_point(position)
        with physical_coordinates():
            self._move_to_point(x, y)
            time.sleep(random.uniform(0.08, 0.18))
            self._click_with_user32(x, y)
        return True

    def _humanized_point(self, position: ElementPosition) -> tuple[int, int]:
        max_offset_x = max(0, min(8, position.width // 4))
        max_offset_y = max(0, min(6, position.height // 4))
        x = int(position.x) + random.randint(-max_offset_x, max_offset_x)
        y = int(position.y) + random.randint(-max_offset_y, max_offset_y)
        return x, y

    def _click_with_send_input(self, x: int, y: int) -> None:
        left, top, right, bottom = self._screen_bounds()
        absolute_x = round((x - left) * 65535 / max(1, right - left - 1))
        absolute_y = round((y - top) * 65535 / max(1, bottom - top - 1))

        self._send_inputs(
            (
                self._mouse_input(
                    absolute_x,
                    absolute_y,
                    MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                ),
                self._mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN),
            ),
            x,
            y,
        )
        time.sleep(random.uniform(0.045, 0.095))
        self._send_inputs((self._mouse_input(0, 0, MOUSEEVENTF_LEFTUP),), x, y)

    def _click_with_user32(self, x: int, y: int) -> None:
        user32 = ctypes.windll.user32
        if not user32.SetCursorPos(x, y):
            raise RuntimeError(f"SetCursorPos 失败：x={x}, y={y}")

        time.sleep(0.08)
        user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(random.uniform(0.045, 0.095))
        user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _click_with_pywinauto(self, x: int, y: int) -> None:
        mouse.click(button="left", coords=(x, y))

    def _click_with_window_message(self, window_handle: int, x: int, y: int) -> None:
        target_handle = win32gui.WindowFromPoint((x, y)) or window_handle
        client_x, client_y = win32gui.ScreenToClient(target_handle, (x, y))
        lparam = win32api.MAKELONG(client_x, client_y)

        win32gui.PostMessage(target_handle, win32con.WM_MOUSEMOVE, 0, lparam)
        time.sleep(0.04)
        win32gui.PostMessage(target_handle, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(random.uniform(0.045, 0.095))
        win32gui.PostMessage(target_handle, win32con.WM_LBUTTONUP, 0, lparam)

    def _send_inputs(self, events: tuple[Input, ...], x: int, y: int) -> None:
        sent = ctypes.windll.user32.SendInput(
            len(events),
            (Input * len(events))(*events),
            ctypes.sizeof(Input),
        )
        if sent != len(events):
            raise RuntimeError(f"SendInput 失败：x={x}, y={y}, sent={sent}/{len(events)}")

    def _mouse_input(self, x: int, y: int, flags: int) -> Input:
        return Input(
            type=INPUT_MOUSE,
            union=InputUnion(
                mi=MouseInput(
                    dx=x,
                    dy=y,
                    mouseData=0,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

    def _ensure_point_on_screen(self, x: int, y: int) -> None:
        left, top, right, bottom = self._screen_bounds()
        if not (left <= x < right and top <= y < bottom):
            raise ValueError(
                "点击坐标不在当前屏幕范围内："
                f"point=({x}, {y}), "
                f"screen=({left}, {top})-({right}, {bottom})"
            )

    def _screen_bounds(self) -> tuple[int, int, int, int]:
        user32 = ctypes.windll.user32
        left = user32.GetSystemMetrics(76)
        top = user32.GetSystemMetrics(77)
        width = user32.GetSystemMetrics(78)
        height = user32.GetSystemMetrics(79)
        return left, top, left + width, top + height
