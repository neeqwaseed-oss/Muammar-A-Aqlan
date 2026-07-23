"""
Centralised logging setup.
Call setup_logger() once at startup; use get_logger(__name__) everywhere else.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logger(
    logs_dir: Path,
    level: str = "INFO",
    max_file_size_mb: int = 10,
    backup_count: int = 5,
) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "bot.log"

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_file_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
