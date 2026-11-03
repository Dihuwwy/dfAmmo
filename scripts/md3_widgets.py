"""Presentation helpers for the Material-styled native Qt interface."""
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QCheckBox, QComboBox, QGraphicsDropShadowEffect, QListView, QSizePolicy, QWidget

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
    # A None fallback leaves the button text-only when no matching system icon exists.
    if qta:
        icon = qta.icon(f"mdi6.{name}", color=color)
    else:
        icon = QIcon() if fallback is None else button.style().standardIcon(fallback)
    if not qta and name == "play":
        pixmap = icon.pixmap(button.iconSize() * button.devicePixelRatioF())
        pixmap.setDevicePixelRatio(button.devicePixelRatioF())
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()
        icon = QIcon(pixmap)
    button.setIcon(icon)


class FilledCheckBox(QCheckBox):
    """Checkbox drawn as a filled square; the native one has an uneven hairline at fractional scales."""

    BOX = 18
    GAP = 6

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WA_Hover)

    def sizeHint(self):
        metrics = self.fontMetrics()
        return QSize(self.BOX + self.GAP + metrics.horizontalAdvance(self.text()) + 2,
                     max(self.BOX + 2, metrics.height() + 2))

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        top = (self.height() - self.BOX) / 2
        hovered = self.underMouse()
        if not self.isEnabled():
            fill = "#C4C6D0" if self.isChecked() else "#F1F0F4"
        elif self.isChecked():
            fill = "#1B66C9" if hovered else "#0B57D0"
        else:
            fill = "#D6DCE8" if hovered else "#E3E7EF"
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(QRectF(0, top, self.BOX, self.BOX), 6, 6)
        if self.isChecked():
            painter.setPen(QPen(QColor("#FFFFFF"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline(QPolygonF([QPointF(4.6, top + 9.4), QPointF(7.8, top + 12.5), QPointF(13.4, top + 6)]))
        painter.setPen(QColor("#44474E" if self.isEnabled() else "#A9ABB4"))
        painter.drawText(self.rect().adjusted(self.BOX + self.GAP, 0, 0, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, self.text())


class CompactComboBox(QComboBox):
    """Content-sized selector with a centered label on a filled background."""

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
        active = self.isEnabled() and (self.hasFocus() or self.underMouse())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#E1E7F3" if active else "#EDF0F6"))
        painter.drawRoundedRect(QRectF(self.rect()), 12, 12)
        text_color = "#0B57D0" if active else "#191C20"
        painter.setPen(QColor(text_color if self.isEnabled() else "#A9ABB4"))
        painter.drawText(self.rect().adjusted(22, 0, -22, 0), Qt.AlignCenter, self.currentText())
        painter.setPen(QPen(QColor("#64748B"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
