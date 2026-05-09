"""Loguru configuration.  Private keys are NEVER written to log files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from loguru import logger

_RE_HEX_KEY = re.compile(r"\b[0-9a-fA-F]{64}\b")
_RE_WIF_KEY = re.compile(r"\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b")


def setup_logger(
    level: str = "INFO",
    logs_dir: str = "logs",
    rotation: str = "50 MB",
    retention: str = "7 days",
) -> None:
    """
    Configure Loguru with:
      - Coloured stdout output
      - Rotating file sink (INFO+)
      - Separate error file sink (WARNING+)
    """
    log_path = Path(logs_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Stdout — coloured, human-friendly
    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        filter=_no_private_key_filter,
    )

    # Rotating main log file
    logger.add(
        log_path / "scanner_{time}.log",
        level="INFO",
        rotation=rotation,
        retention=retention,
        compression="gz",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} — {message}",
        filter=_no_private_key_filter,
    )

    # Separate error file
    logger.add(
        log_path / "errors_{time}.log",
        level="WARNING",
        rotation="10 MB",
        retention=retention,
        compression="gz",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} — {message}",
        filter=_no_private_key_filter,
    )


def _no_private_key_filter(record: dict) -> bool:
    """
    Drops any log record whose message contains what looks like a private key.
    This is a safety net — callers should not log private keys in the first place.
    """
    msg = record.get("message", "")
    if _RE_HEX_KEY.search(msg) or _RE_WIF_KEY.search(msg):
        return False
    return True
