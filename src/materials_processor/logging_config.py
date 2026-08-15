"""Logging configuration and helpers for the materials processor package."""

import logging
from logging.handlers import RotatingFileHandler
import os
import tempfile


def setup_file_logging(
    logger_name: str = "materials_processor",
    log_dir: str | None = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.FileHandler | None:
    """
    Configure rotating file logging for a named logger.
    
    Uses the provided directory when available, then falls back to user and
    system temporary directories. If the logger already has a file handler, that
    handler is returned unchanged.
    
    Parameters:
        logger_name (str): Name of the logger to configure.
        log_dir (str | None): Preferred directory for the log file.
        max_bytes (int): Maximum log file size before rotation.
        backup_count (int): Number of rotated log files to retain.
    
    Returns:
        logging.FileHandler | None: The configured file handler, or None if no
        candidate directory can be used.
    """
    logger = logging.getLogger(logger_name)

    # Check if a FileHandler is already attached to this logger to avoid duplicates
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            return handler

    # Safe log directory resolution
    possible_dirs = []
    if log_dir:
        possible_dirs.append(log_dir)

    # Sensible user directory default
    home_dir = os.path.expanduser("~")
    possible_dirs.append(os.path.join(home_dir, "Documents", "houdiniTools", "Materials-Processor", "logs"))
    possible_dirs.append(os.path.join(tempfile.gettempdir(), "MaterialsProcessor", "Logs"))

    configured_handler = None

    for candidate_dir in possible_dirs:
        try:
            os.makedirs(candidate_dir, exist_ok=True)
            log_file = os.path.join(candidate_dir, "materials_processor.log")

            # Test file writability
            with open(log_file, "a", encoding="utf-8") as f:
                pass

            handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(handler)
            logger.info("File logging successfully initialized at: %s", log_file)
            configured_handler = handler
            break
        except Exception:
            # Continue trying fallback directories
            continue

    if not configured_handler:
        # Fallback to standard console warning if we couldn't write logs anywhere
        logging.warning("Unable to initialize file logging in any candidate directory.")

    return configured_handler
