from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from scripts.config import PROJECT_ROOT


LOG_FILE = PROJECT_ROOT / "dfAmmo.log"


def get_logger(name: str) -> logging.Logger:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        # The packaged app has no console, so errors must also reach a file.
        handlers.append(RotatingFileHandler(LOG_FILE, maxBytes=512 * 1024, backupCount=1, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    return logging.getLogger(name)
