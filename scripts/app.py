from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from scripts.dpi import enable_dpi_awareness
from scripts.gui import MainWindow
from scripts.logger import get_logger


class App:
    """Application entry and module coordinator."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.qt_app: QApplication | None = None
        self.window: MainWindow | None = None

    def run(self) -> int:
        self.logger.info("Application started.")
        enable_dpi_awareness()
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.window = MainWindow()
        self.window.show()
        return self.qt_app.exec()
