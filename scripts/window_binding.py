from __future__ import annotations

from dataclasses import dataclass

import psutil
import win32con
import win32gui
import win32process

from scripts.dpi import physical_coordinates


@dataclass(frozen=True)
class BoundWindow:
    """Represents a user-selected target window."""

    handle: int
    title: str = ""
    process_name: str = ""
    process_id: int | None = None
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0


class WindowBinder:
    """Responsible for listing and binding target windows."""

    def list_windows(self) -> list[BoundWindow]:
        windows: list[BoundWindow] = []

        def collect(handle: int, _: object) -> bool:
            if win32gui.IsWindowVisible(handle):
                bound_window = self.bind_by_handle(handle)
                if bound_window.title:
                    windows.append(bound_window)
            return True

        win32gui.EnumWindows(collect, None)
        return windows

    def bind_by_handle(self, handle: int) -> BoundWindow:
        with physical_coordinates():
            root_handle = win32gui.GetAncestor(handle, win32con.GA_ROOT) or handle
            _, process_id = win32process.GetWindowThreadProcessId(root_handle)
            left, top, right, bottom = win32gui.GetWindowRect(root_handle)
            title = win32gui.GetWindowText(root_handle)

        try:
            process_name = psutil.Process(process_id).name()
        except psutil.Error:
            process_name = ""

        return BoundWindow(
            handle=root_handle,
            title=title,
            process_name=process_name,
            process_id=process_id,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
        )

    def bind_at_position(self, x: int, y: int) -> BoundWindow:
        with physical_coordinates():
            handle = win32gui.WindowFromPoint((x, y))
        if not handle:
            raise RuntimeError("没有识别到鼠标位置下的窗口。")

        return self.bind_by_handle(handle)

    def bind_by_process_id(self, process_id: int) -> BoundWindow | None:
        candidates: list[BoundWindow] = []

        def collect(handle: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(handle):
                return True

            _, window_process_id = win32process.GetWindowThreadProcessId(handle)
            if window_process_id != process_id:
                return True

            try:
                bound_window = self.bind_by_handle(handle)
            except Exception:
                return True

            if bound_window.right > bound_window.left and bound_window.bottom > bound_window.top:
                candidates.append(bound_window)
            return True

        with physical_coordinates():
            win32gui.EnumWindows(collect, None)

        if not candidates:
            return None

        # Prioritize windows with non-empty title (main game viewport vs splash),
        # then by largest area
        return max(
            candidates,
            key=lambda item: (
                bool(item.title.strip()),
                (item.right - item.left) * (item.bottom - item.top),
            ),
        )

    def bind_by_title(self, title_substring: str) -> BoundWindow | None:
        candidates: list[BoundWindow] = []

        def collect(handle: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(handle):
                return True
            
            window_title = win32gui.GetWindowText(handle)
            if title_substring in window_title:
                try:
                    bound_window = self.bind_by_handle(handle)
                    if bound_window.right > bound_window.left and bound_window.bottom > bound_window.top:
                        candidates.append(bound_window)
                except Exception:
                    pass
            return True

        with physical_coordinates():
            win32gui.EnumWindows(collect, None)

        if not candidates:
            return None

        # Return the one with the exact match if possible, else the first candidate
        for c in candidates:
            if c.title == title_substring:
                return c
        return candidates[0]

    def activate(self, bound_window: BoundWindow) -> BoundWindow:
        with physical_coordinates():
            if not win32gui.IsWindow(bound_window.handle):
                raise RuntimeError(f"无效的窗口句柄：{bound_window.handle}")

            if win32gui.IsIconic(bound_window.handle):
                win32gui.ShowWindow(bound_window.handle, win32con.SW_RESTORE)

            try:
                win32gui.SetForegroundWindow(bound_window.handle)
            except Exception:
                win32gui.ShowWindow(bound_window.handle, win32con.SW_SHOW)
                try:
                    win32gui.BringWindowToTop(bound_window.handle)
                    win32gui.SetForegroundWindow(bound_window.handle)
                except Exception:
                    pass

        return self.bind_by_handle(bound_window.handle)
