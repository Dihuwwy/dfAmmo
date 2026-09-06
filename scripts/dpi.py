from __future__ import annotations

import ctypes
from collections.abc import Iterator
from contextlib import contextmanager
import os


_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(
    (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 4
)


def enable_dpi_awareness() -> None:
    """Use Qt's normal high-DPI scaling so the GUI keeps a comfortable size."""
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")


@contextmanager
def physical_coordinates() -> Iterator[None]:
    """Temporarily make Win32 coordinate APIs use physical screen pixels."""
    user32 = ctypes.windll.user32
    set_context = getattr(user32, "SetThreadDpiAwarenessContext", None)
    if set_context is None:
        yield
        return

    set_context.argtypes = [ctypes.c_void_p]
    set_context.restype = ctypes.c_void_p
    previous = set_context(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    try:
        yield
    finally:
        if previous:
            set_context(previous)
