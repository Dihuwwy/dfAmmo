from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget


class TemplateCaptureOverlay(QWidget):
    """Full-screen rubber-band selector for template capture."""

    selected = Signal(QRect)
    canceled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.start_pos = QPoint()
        self.current_rect = QRect()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

    def begin(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        self.setGeometry(screen.geometry())
        self.current_rect = QRect()
        self.showFullScreen()
        self.activateWindow()
        self.raise_()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        if not self.current_rect.isNull():
            rect = self.current_rect.normalized()
            painter.fillRect(rect, QColor(255, 255, 255, 25))
            painter.setPen(QColor(31, 122, 236))
            painter.drawRect(rect)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.start_pos = event.position().toPoint()
            self.current_rect = QRect(self.start_pos, self.start_pos)
            self.update()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            self.current_rect = QRect(self.start_pos, event.position().toPoint())
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            selected_rect = QRect(self.start_pos, event.position().toPoint()).normalized()
            self.hide()
            QApplication.processEvents()
            if selected_rect.width() < 8 or selected_rect.height() < 8:
                self.canceled.emit()
            else:
                selected_rect.translate(self.geometry().topLeft())
                self.selected.emit(selected_rect)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
            QApplication.processEvents()
            self.canceled.emit()
            event.accept()
            return

        super().keyPressEvent(event)
