"""
Logging Configuration for EarlyBird

Centralized logging setup with console and rotating file handlers.
Handles both initial configuration and force reconfiguration.

Extracted from src/main.py as part of the modular refactoring initiative.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

# Default log file path
DEFAULT_LOG_FILE = "earlybird.log"
DEFAULT_LOG_FILE_BACKUP = "earlybird_main.log"
MAX_BYTES = 5_000_000  # 5MB per file
BACKUP_COUNT = 3


def setup_logging(
    log_file: str = DEFAULT_LOG_FILE,
    reconfigure: bool = False,
    level: int = logging.INFO,
) -> None:
    """
    Configure EarlyBird logging with console and rotating file handlers.

    This function is idempotent - calling it multiple times with reconfigure=False
    has no additional effect after the first call.

    Args:
        log_file: Path to the primary log file (default: earlybird.log)
        reconfigure: If True, force reconfiguration even if handlers already exist.
                    Use this when you need to reset logging mid-module.
        level: Logging level (default: INFO)
    """
    root_logger = logging.getLogger()

    # If not reconfiguring and already has our handlers, skip
    if not reconfigure and root_logger.handlers:
        # Check if our specific handlers are already present
        has_console = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in root_logger.handlers
        )
        has_file = any(
            isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers
        )
        if has_console and has_file:
            return

    # Force reconfiguration: remove existing handlers
    if reconfigure:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    root_logger.setLevel(level)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Console handler with immediate flush (line buffering)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    if hasattr(console_handler.stream, "reconfigure"):
        console_handler.stream.reconfigure(line_buffering=True)

    # File handler with rotation (5MB max, 3 backups = 15MB total max)
    file_handler = RotatingFileHandler(log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    This is a convenience function that returns logger.getLogger(name)
    after ensuring the root logger is configured.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    # Ensure logging is set up before returning any logger
    if not logging.getLogger().handlers:
        setup_logging()
    return logging.getLogger(name)
