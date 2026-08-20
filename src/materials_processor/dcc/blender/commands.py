"""Public Blender command entrypoints for add-on and automation callers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from materials_processor.dcc.blender.adapters import (
    BlenderMaterialAnalysis,
    BlenderMaterialReader,
    convert_active_material,
    convert_material,
    convert_selected_active_materials,
)


def ingest_material(material: Any) -> BlenderMaterialAnalysis:
    """Analyze one Blender material before strict reconstruction.

    Args:
        material: A Blender material datablock.

    Returns:
        The standardized graph together with strict-reconstruction diagnostics.
    """
    return BlenderMaterialReader().analyze(material)


def run(material: Any, *, target_name: str | None = None) -> Any:
    """Rebuild one Blender material as a separate datablock.

    Args:
        material: Source Blender material datablock.
        target_name: Optional result material name.

    Returns:
        The reconstructed Blender material.
    """
    return convert_material(material, target_name=target_name)


def run_for_active_object(active_object: Any, *, target_name: str | None = None) -> Any:
    """Rebuild and assign an object's active material slot.

    Args:
        active_object: Blender object whose active material slot is converted.
        target_name: Optional result material name.

    Returns:
        The reconstructed Blender material assigned to the active slot.
    """
    return convert_active_material(active_object, target_name=target_name)


def run_for_selected_objects(objects: Sequence[Any]) -> tuple[Any, ...]:
    """Atomically rebuild active material slots on selected Blender objects.

    Args:
        objects: Objects whose active material slots will be converted.

    Returns:
        Newly created materials, one for each distinct source material.
    """
    return convert_selected_active_materials(list(objects))
