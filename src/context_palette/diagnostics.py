from __future__ import annotations

from logging.handlers import RotatingFileHandler
import logging
from pathlib import Path


LOGGER_NAME = "context_palette"


def configure_logging(path: Path) -> logging.Logger:
    """Configure one bounded local diagnostic log without duplicating handlers."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            path,
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
