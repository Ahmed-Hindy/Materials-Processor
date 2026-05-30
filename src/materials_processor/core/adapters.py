"""Reader and writer contracts for DCC material adapters."""

from __future__ import annotations

from typing import Any, Protocol

from materials_processor.core.graph import MaterialGraph


class MaterialReader(Protocol):
    """Reads a native DCC material into a DCC-neutral graph."""

    def read(self, native_material: Any) -> MaterialGraph:
        """Read a native material object into a material graph."""
        ...


class MaterialWriter(Protocol):
    """Writes a DCC-neutral graph into a native DCC material."""

    def write(self, graph: MaterialGraph, target_context: Any) -> Any:
        """Write a material graph into the target DCC context."""
        ...
