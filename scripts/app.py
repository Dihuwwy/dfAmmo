from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from scripts.config import APP_ICON_PATH
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
        # The default DirectWrite engine draws text with coloured subpixel fringes.
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=freetype")
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.window = MainWindow()
        self.window.show()
        self.window.startup_updates()
        return self.qt_app.exec()
