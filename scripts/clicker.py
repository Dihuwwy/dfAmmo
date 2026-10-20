from __future__ import annotations

import ctypes
import random

import win32api
import win32con
import win32gui
import win32process

from scripts.task_control import TaskControl, ControlInterrupted
from scripts.dpi import physical_coordinates
from scripts.element_locator import ElementPosition


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
KEYEVENTF_KEYUP = 0x0002
WHEEL_DELTA = 120


class MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    )


class KeyboardInput(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    )


class InputUnion(ctypes.Union):
    _fields_ = (("mi", MouseInput), ("ki", KeyboardInput))


class Input(ctypes.Structure):
    _fields_ = (
        ("type", ctypes.c_ulong),
        ("union", InputUnion),
    )


class Clicker:
    """Responsible for mouse click actions."""

    def __init__(self, control: TaskControl | None = None):
        self.control = control or TaskControl()


    def _move_to_point(self, x: int, y: int) -> tuple[int, int]:
        self._ensure_point_on_screen(x, y)
        errors: list[str] = []

        for move_method in (
            self._move_with_user32,
            self._move_with_send_input,
        ):
            self.control.check()
            try:
                move_method(x, y)
                if self._cursor_is_near(x, y):
                    return x, y
                current_x, current_y = win32api.GetCursorPos()
                errors.append(
                    f"{move_method.__name__}: 调用成功但鼠标未到位，"
                    f"current=({current_x}, {current_y})"
                )
            except ControlInterrupted:
                raise
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

    def _cursor_is_near(self, x: int, y: int, tolerance: int = 3) -> bool:
        current_x, current_y = win32api.GetCursorPos()
        return abs(current_x - x) <= tolerance and abs(current_y - y) <= tolerance

    def click(self, position: ElementPosition, window_handle: int | None = None) -> bool:
        self.control.check()
        if window_handle is not None:
            self._require_foreground(window_handle)
        x, y = self._humanized_point(position)
        with physical_coordinates():
            self._move_to_point(x, y)
            self.control.wait(random.uniform(0.08, 0.15))
            self._click_with_send_input(x, y)
        return True

    def _require_foreground(self, window_handle: int) -> None:
        """Refuse to click when the intended window is not the active one."""
        if not win32gui.IsWindow(window_handle):
            raise RuntimeError(f"点击目标窗口句柄无效：handle={window_handle}。未发送点击。")
        if self._foreground_belongs_to(window_handle):
            return
        foreground = win32gui.GetForegroundWindow()
        raise RuntimeError(
            "目标窗口不在前台，已取消此次点击以免误操作："
            f"目标={self._window_label(window_handle)}，"
            f"当前前台={self._window_label(foreground)}。请重新绑定或让目标窗口回到前台。"
        )

    def _foreground_belongs_to(self, window_handle: int) -> bool:
        """Accept the target, its root owner, or another window of the same client.

        WeGame opens the resource manager and confirmation dialogs as separate
        windows, so an exact handle comparison would reject legitimate targets.
        """
        foreground = win32gui.GetForegroundWindow()
        if not foreground:
            return False
        target_root = win32gui.GetAncestor(window_handle, win32con.GA_ROOT) or window_handle
        foreground_root = win32gui.GetAncestor(foreground, win32con.GA_ROOT) or foreground
        if foreground in (window_handle, target_root) or foreground_root == target_root:
            return True
        try:
            target_pid = win32process.GetWindowThreadProcessId(target_root)[1]
            foreground_pid = win32process.GetWindowThreadProcessId(foreground_root)[1]
        except win32gui.error:
            return False
        return bool(target_pid) and target_pid == foreground_pid

    @staticmethod
    def _window_label(handle: int) -> str:
        if not handle:
            return "<无前台窗口>"
        try:
            title = win32gui.GetWindowText(handle)
        except win32gui.error:
            title = ""
        return f"“{title}” (handle={handle})" if title else f"<无标题> (handle={handle})"

    def move(self, position: ElementPosition) -> None:
        """Move without clicking so hover-only controls can appear."""
        self.control.check()
        with physical_coordinates():
            self._move_to_point(position.x, position.y)

    def press(self, virtual_key: int, repeat: int = 1, interval: float = 0.12) -> None:
        """Send key presses through the same SendInput path as mouse clicks."""
        for index in range(repeat):
            self.control.check()
            self._send_inputs((self._keyboard_input(virtual_key, 0),), 0, 0)
            try:
                self.control.wait(0.045)
            finally:
                self._send_inputs((self._keyboard_input(virtual_key, KEYEVENTF_KEYUP),), 0, 0)
            if index + 1 < repeat:
                self.control.wait(interval)

    def scroll(self, clicks: int, hwnd: int | None = None) -> None:
        """Scroll downward over the given window, or the foreground window.

        The cursor is centred first: frameworks such as WeGame's CEF only
        deliver the wheel event to the control under the pointer.
        """
        self.control.check()
        with physical_coordinates():
            target = hwnd or win32gui.GetForegroundWindow()
            if not target:
                raise RuntimeError("滚动失败：没有可用的目标窗口。")
            left, top, right, bottom = win32gui.GetWindowRect(target)
            self._move_to_point((left + right) // 2, (top + bottom) // 2)
            self._send_inputs(
                (self._mouse_input(0, 0, MOUSEEVENTF_WHEEL, -WHEEL_DELTA * clicks),),
                (left + right) // 2,
                (top + bottom) // 2,
            )

    def _humanized_point(self, position: ElementPosition) -> tuple[int, int]:
        max_offset_x = max(0, min(8, position.width // 4))
        max_offset_y = max(0, min(6, position.height // 4))
        x = int(position.x) + random.randint(-max_offset_x, max_offset_x)
        y = int(position.y) + random.randint(-max_offset_y, max_offset_y)
        return x, y

    def _click_with_send_input(self, x: int, y: int) -> None:
        self.control.check()
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
        try:
            self.control.wait(random.uniform(0.09, 0.16))
        finally:
            self._send_inputs((self._mouse_input(0, 0, MOUSEEVENTF_LEFTUP),), x, y)

    def _send_inputs(self, events: tuple[Input, ...], x: int, y: int) -> None:
        sent = ctypes.windll.user32.SendInput(
            len(events),
            (Input * len(events))(*events),
            ctypes.sizeof(Input),
        )
        if sent != len(events):
            raise RuntimeError(f"SendInput 失败：x={x}, y={y}, sent={sent}/{len(events)}")

    def _mouse_input(self, x: int, y: int, flags: int, mouse_data: int = 0) -> Input:
        return Input(
            type=INPUT_MOUSE,
            union=InputUnion(
                mi=MouseInput(
                    dx=x,
                    dy=y,
                    mouseData=mouse_data,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

    def _keyboard_input(self, virtual_key: int, flags: int) -> Input:
        return Input(
            type=INPUT_KEYBOARD,
            union=InputUnion(
                ki=KeyboardInput(
                    wVk=virtual_key,
                    wScan=0,
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
