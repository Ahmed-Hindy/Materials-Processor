"""Core adapter implementations for Blender materials."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from materials_processor.core.graph import MaterialData, MaterialGraph
from materials_processor.dcc.blender.recreator import BlenderNodeRecreator
from materials_processor.dcc.blender.traverser import BlenderNodeTraverser
from materials_processor.standardizer import NodeStandardizer

try:
    import bpy
except ImportError:
    bpy = None


class BlenderMaterialReader:
    """Read Blender shader node materials into the neutral material graph."""

    def read(self, native_material: Any) -> MaterialGraph:
        """Read a Blender material into a standardized material graph.

        Args:
            native_material: Blender material object with a shader node tree.

        Returns:
            Standardized material graph.
        """
        traversed_nodes, output_nodes = BlenderNodeTraverser(native_material).run()
        nodeinfo_list, output_connections = NodeStandardizer(
            traversed_nodes_dict=traversed_nodes,
            output_nodes_dict=output_nodes,
            material_type="blender",
            source_type="blender_shader_nodes",
        ).run()

        material_name = getattr(native_material, "name", "blender_material")
        return MaterialData(
            material_name=material_name,
            material_path=f"/mat/{material_name}",
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
        )


class BlenderMaterialWriter:
    """Write neutral material graphs into Blender shader node materials."""

    def write(self, graph: MaterialGraph, target_context: Any = None) -> Any:
        """Write a material graph into a Blender material.

        Args:
            graph: Standardized material graph to recreate.
            target_context: Target Blender material, a mapping containing a
                ``material`` or ``material_name`` entry, a material name string,
                or ``None`` to create a material when running inside Blender.

        Returns:
            The target Blender material.

        Raises:
            RuntimeError: If recreation fails.
            ValueError: If no target material can be resolved.
        """
        target_material = self._resolve_target_material(graph, target_context)
        recreated = BlenderNodeRecreator(
            nodeinfo_list=graph.nodeinfo_list,
            output_connections=graph.output_connections,
            target_material=target_material,
            material_name=target_material.name,
        ).run()

        if not recreated:
            raise RuntimeError(f"Failed to recreate Blender material '{target_material.name}'.")

        return target_material

    def _resolve_target_material(self, graph: MaterialGraph, target_context: Any) -> Any:
        if self._looks_like_material(target_context):
            return target_context

        if isinstance(target_context, Mapping):
            material = target_context.get("material")
            if self._looks_like_material(material):
                return material
            material_name = target_context.get("material_name") or graph.material_name
            return self._create_material(str(material_name))

        if isinstance(target_context, str):
            return self._create_material(target_context)

        if target_context is None:
            return self._create_material(graph.material_name)

        raise ValueError(f"Unsupported Blender target context: {target_context!r}")

    @staticmethod
    def _looks_like_material(value: Any) -> bool:
        return value is not None and hasattr(value, "name") and hasattr(value, "node_tree")

    @staticmethod
    def _create_material(material_name: str) -> Any:
        if bpy is None:
            raise ValueError("A target Blender material is required outside Blender.")

        material = bpy.data.materials.new(material_name)
        material.use_nodes = True
        return material
