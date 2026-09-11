"""Configure Python application logging for the internal messaging package."""

from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_messaging_logging(log_root: str | Path | None = None) -> Path:
    """Configure package logging and return the active messaging log path."""
    root = (
        Path(log_root).expanduser().resolve()
        if log_root
        else Path(__file__).resolve().parents[3] / ".agent-state" / "logs" / "system" / "messaging"
    )
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / f"log-{datetime.now().date().isoformat()}.log"
    messaging_logger = logging.getLogger("agents_internal_messaging")

    has_file_handler = any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename).resolve() == log_path.resolve()
        for handler in messaging_logger.handlers
    )
    if not has_file_handler:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        messaging_logger.addHandler(handler)

    messaging_logger.setLevel(logging.INFO)
    messaging_logger.propagate = False
    messaging_logger.info("Internal messaging Python logging configured")
    return log_path
