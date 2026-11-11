from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from scripts.config import APP_ICON_PATH
from scripts.gui import MainController
from scripts.logger import get_logger


class App:
    """Application entry and module coordinator."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.qt_app: QApplication | None = None
        self.controller: MainController | None = None

    def _report_uncaught(self, exc_type, exc, traceback) -> None:
        """Record errors raised in Qt slots, which would otherwise vanish without a console."""
        self.logger.error("Unhandled exception", exc_info=(exc_type, exc, traceback))
        if self.controller is not None:
            self.controller.write_log(f"内部错误：{exc_type.__name__}: {exc}（详情见 dfAmmo.log）")

    def run(self) -> int:
        self.logger.info("Application started.")
        # QApplication rather than QGuiApplication: the capture overlay and
        # the folder dialog are still widgets.
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        # The window is hidden while a template is captured; quitting is explicit.
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        sys.excepthook = self._report_uncaught
        self.controller = MainController()
        self.controller.show()
        self.controller.startup_updates()
        return self.qt_app.exec()
