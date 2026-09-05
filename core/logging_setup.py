"""Logging setup for development and packaged Catch runs."""

from __future__ import annotations

import logging
import os
from pathlib import Path


def configure_logging(level: str = "INFO") -> Path:
    """Configure console and user-local file logging, returning the log path."""
    log_directory = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Catch" / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / "catch.log"
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    return log_path
