"""Presentation helpers for the Material-styled native Qt interface."""
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QComboBox, QGraphicsDropShadowEffect, QListView, QSizePolicy, QWidget

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


class CompactComboBox(QComboBox):
    """Content-sized selector with a centered label and a smooth HiDPI outline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setView(QListView())
        self.view().setStyleSheet(
            "QListView { background: white; border: 1px solid #E0E2EC; outline: none; }"
            "QListView::item { min-height: 30px; padding: 0 8px; border: none; }"
            "QListView::item:selected { background: #D3E3FD; color: #0B57D0; }")

    def sizeHint(self):
        width = max((self.fontMetrics().horizontalAdvance(self.itemText(i))
                     for i in range(self.count())), default=0)
        return QSize(width + 56, max(34, self.fontMetrics().height() + 14))

    def minimumSizeHint(self):
        return self.sizeHint()

    def showPopup(self):
        for index in range(self.count()):
            self.setItemData(index, Qt.AlignCenter, Qt.TextAlignmentRole)
        super().showPopup()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dpr = self.devicePixelRatioF()
        # Keep the stroke edges on physical pixels at fractional display scales.
        stroke = max(1, round(dpr)) / dpr
        rect = QRectF(stroke / 2, stroke / 2,
                      round(self.width() * dpr) / dpr - stroke,
                      round(self.height() * dpr) / dpr - stroke)
        active = self.isEnabled() and (self.hasFocus() or self.underMouse())
        painter.setPen(QPen(QColor("#0B57D0" if active else "#E0E2EC"), stroke))
        painter.setBrush(QColor("#FFFFFF" if active else "#F0F4F9"))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(QColor("#191C20" if self.isEnabled() else "#A9ABB4"))
        painter.drawText(self.rect().adjusted(22, 0, -22, 0), Qt.AlignCenter, self.currentText())
        painter.setPen(QPen(QColor("#64748B"), stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x, y = self.width() - 14, self.height() / 2
        painter.drawPolyline(QPolygonF([QPointF(x - 3, y - 2), QPointF(x, y + 1), QPointF(x + 3, y - 2)]))


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
