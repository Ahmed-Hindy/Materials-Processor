"""Qt-aware logging handlers for the Material Processor UI."""

from __future__ import annotations

import logging


class TextEditLogger(logging.Handler):
    """Logging handler that appends formatted records into a Qt text edit."""

    def __init__(self, log_area):
        super().__init__()
        self.log_area = log_area

    def emit(self, record: logging.LogRecord) -> None:
        """Append a formatted log record to the configured text edit."""
        self.log_area.append(self.format(record))
