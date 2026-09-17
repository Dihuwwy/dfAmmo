from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QPushButton
import win32api

from scripts.dpi import physical_coordinates


class BindButton(QPushButton):
    """Button that picks a window by press-drag-release."""

    released_at = Signal(int, int)

    def __init__(self, text: str = "拖拽至 WeGame 窗口绑定") -> None:
        super().__init__(text)
        self.default_text = text
        self.setObjectName("bindButton")
        self.setCursor(Qt.OpenHandCursor)
        self.setMinimumHeight(30)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.setText("松开鼠标完成绑定")
            self.setCursor(Qt.CrossCursor)
            QApplication.setOverrideCursor(QCursor(Qt.CrossCursor))
            self.grabMouse()
            event.accept()
            return


        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.releaseMouse()
            QApplication.restoreOverrideCursor()
            self.setCursor(Qt.OpenHandCursor)
            self.setText(self.default_text)

            # Qt coordinates can be logical pixels on a scaled desktop. Read
            # the release point from Win32 so binding uses the same space as
            # the later screenshot and mouse operations.
            with physical_coordinates():
                x, y = win32api.GetCursorPos()
            self.released_at.emit(x, y)
            event.accept()
            return

        super().mouseReleaseEvent(event)
