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
    """Sets up a safe, rotating file logging handler for the package logger.

    If the specified log directory is not writable or creates an exception,
    this function will gracefully fall back to the system temporary directory.
    If the temporary directory is also not writable, it logs a warning and
    returns None to ensure the application never crashes due to logging issues.

    Args:
        logger_name: The name of the logger to configure. Defaults to "materials_processor".
        log_dir: Absolute path to the directory where logs should be stored. If None,
            it defaults to a subdirectory in the user's documents/home directory, or falls
            back to the system temp folder.
        max_bytes: Maximum size of each log file in bytes before rotation occurs.
            Defaults to 5MB.
        backup_count: Number of rotated log backup files to keep. Defaults to 3.

    Returns:
        The configured RotatingFileHandler, or None if file logging could not be set up safely.
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
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
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
