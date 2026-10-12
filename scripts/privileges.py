from __future__ import annotations

import ctypes
from pathlib import Path
import subprocess
import sys

import win32con


def is_elevated() -> bool:
    """Return whether this process is running with administrator rights."""
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def hide_console_window() -> None:
    """Hide the console created by an elevated uv/Python launcher."""
    get_console_window = ctypes.windll.kernel32.GetConsoleWindow
    get_console_window.restype = ctypes.c_void_p
    console_window = get_console_window()
    if console_window:
        ctypes.windll.user32.ShowWindow(console_window, win32con.SW_HIDE)


def relaunch_as_admin() -> bool:
    """Relaunch the current Python command through the standard UAC prompt."""
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.argtypes = (
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    )
    shell_execute.restype = ctypes.c_void_p

    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        arguments = sys.argv[1:]
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        executable = pythonw if pythonw.exists() else Path(sys.executable)
        arguments = sys.argv
    parameters = subprocess.list2cmdline(arguments)
    result = shell_execute(
        None,
        "runas",
        str(executable),
        parameters,
        str(Path.cwd()),
        win32con.SW_HIDE,
    )
    return bool(result and int(result) > 32)
