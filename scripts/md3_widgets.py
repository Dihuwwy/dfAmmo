"""Presentation helpers for the Material-styled native Qt interface."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

try:
    import qtawesome as qta
except ImportError:
    qta = None


def apply_md_shadow(widget):
    widget.setProperty("md3_card", True)
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(20)
    shadow.setColor(QColor(11, 87, 208, 12))
    shadow.setOffset(0, 4)
    widget.setGraphicsEffect(shadow)


def set_md_icon(button, name, color, fallback):
    icon = qta.icon(f"mdi6.{name}", color=color) if qta else button.style().standardIcon(fallback)
    button.setIcon(icon)


class Timeline(QWidget):
    """Draw the connector behind the stage markers at their actual positions."""

    dots = ()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.dots:
            return
        first, last = self.dots[0], self.dots[-1]
        start = first.mapTo(self, first.rect().center())
        end = last.mapTo(self, last.rect().center())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#E2E8F0"), 2, Qt.SolidLine))
        painter.drawLine(start, end)
