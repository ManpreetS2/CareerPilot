"""Central logging setup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO") -> None:
    """Configure stdout + file logging. Log files stay under logs/ (gitignored)."""
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level.upper())
        return

    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(logs_dir / "careerpilot.log", encoding="utf-8"),
        ],
    )
