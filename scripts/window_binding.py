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

    def _window_candidates(self, process_id=None, title="") -> list[BoundWindow]:
        candidates = []
        def collect(handle, _):
            try:
                if not win32gui.IsWindowVisible(handle):
                    return True
                if process_id is not None and win32process.GetWindowThreadProcessId(handle)[1] != process_id:
                    return True
                if title and title not in win32gui.GetWindowText(handle):
                    return True
                window = self.bind_by_handle(handle)
                if window.right > window.left and window.bottom > window.top:
                    candidates.append(window)
            except Exception:
                pass  # Windows may disappear during enumeration.
            return True
        with physical_coordinates():
            win32gui.EnumWindows(collect, None)
        return candidates

    def bind_by_process_id(self, process_id: int) -> BoundWindow | None:
        return max(self._window_candidates(process_id=process_id), default=None,
                   key=lambda w: (bool(w.title.strip()), (w.right-w.left)*(w.bottom-w.top)))


    def bind_by_title(self, title_substring: str) -> BoundWindow | None:
        candidates = self._window_candidates(title=title_substring)
        return next((w for w in candidates if w.title == title_substring),
                    candidates[0] if candidates else None)


    def activate(self, bound_window: BoundWindow) -> BoundWindow:
        with physical_coordinates():
            if not win32gui.IsWindow(bound_window.handle):
                raise RuntimeError(f"无效的窗口句柄：{bound_window.handle}")

            if win32gui.IsIconic(bound_window.handle):
                win32gui.ShowWindow(bound_window.handle, win32con.SW_RESTORE)

            try:
                import win32api
                foreground_hwnd = win32gui.GetForegroundWindow()
                if foreground_hwnd and foreground_hwnd != bound_window.handle:
                    foreground_tid, _ = win32process.GetWindowThreadProcessId(foreground_hwnd)
                    current_tid = win32api.GetCurrentThreadId()

                    if foreground_tid != current_tid:
                        import ctypes
                        user32 = ctypes.windll.user32
                        user32.AttachThreadInput(current_tid, foreground_tid, True)
                        try:
                            win32gui.SetForegroundWindow(bound_window.handle)
                            win32gui.BringWindowToTop(bound_window.handle)
                        finally:
                            user32.AttachThreadInput(current_tid, foreground_tid, False)
                    else:
                        win32gui.SetForegroundWindow(bound_window.handle)
                        win32gui.BringWindowToTop(bound_window.handle)
                else:
                    win32gui.SetForegroundWindow(bound_window.handle)
                    win32gui.BringWindowToTop(bound_window.handle)
            except Exception:
                win32gui.ShowWindow(bound_window.handle, win32con.SW_SHOW)
                try:
                    win32gui.BringWindowToTop(bound_window.handle)
                    win32gui.SetForegroundWindow(bound_window.handle)
                except Exception:
                    pass

        return self.bind_by_handle(bound_window.handle)
