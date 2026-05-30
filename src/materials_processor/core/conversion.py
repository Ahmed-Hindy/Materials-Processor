"""DCC-neutral material conversion orchestration."""

from __future__ import annotations

from typing import Any

from materials_processor.core.adapters import MaterialReader, MaterialWriter


class ConversionService:
    """Convert a native material through a reader and writer pair."""

    def __init__(self, reader: MaterialReader, writer: MaterialWriter):
        """Store the reader and writer dependencies."""
        self.reader = reader
        self.writer = writer

    def convert(self, native_material: Any, target_context: Any) -> Any:
        """Convert a native material into the target DCC context."""
        graph = self.reader.read(native_material)
        return self.writer.write(graph, target_context)
