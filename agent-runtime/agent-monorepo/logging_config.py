"""Configure Python application logging for the shared agent runtime.

Runtime events remain in the EventHub store. This module owns normal Python
diagnostic logs and writes them beneath .agent-state/logs/system/runtime.
"""

from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_runtime_logging(log_root: str | Path | None = None) -> Path:
    """Configure package logging and return the active runtime log path."""
    root = (
        Path(log_root).expanduser().resolve()
        if log_root
        else Path(__file__).resolve().parents[2] / ".agent-state" / "logs" / "system" / "runtime"
    )
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / f"log-{datetime.now().date().isoformat()}.log"
    runtime_logger = logging.getLogger("agent_monorepo")

    has_file_handler = any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename).resolve() == log_path.resolve()
        for handler in runtime_logger.handlers
    )
    if not has_file_handler:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        runtime_logger.addHandler(handler)

    runtime_logger.setLevel(logging.INFO)
    runtime_logger.propagate = False
    runtime_logger.info("Runtime Python logging configured", extra={"log_path": str(log_path)})
    return log_path
