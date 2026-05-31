"""Core adapter implementations for Maya materials."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from materials_processor.core.graph import MaterialData, MaterialGraph
from materials_processor.dcc.maya.recreator import MayaNodeRecreator
from materials_processor.dcc.maya.traverser import MayaNodeTraverser
from materials_processor.standardizer import NodeStandardizer


class MayaMaterialReader:
    """Read Maya shading networks into the neutral material graph."""

    def read(self, native_material: Any) -> MaterialGraph:
        """Read a Maya shader or shadingEngine node into a standardized graph.

        Args:
            native_material: Maya shader or shadingEngine node name.

        Returns:
            Standardized material graph.
        """
        material_node = str(native_material)
        traversed_nodes, output_nodes = MayaNodeTraverser(material_node).run()
        nodeinfo_list, output_connections = NodeStandardizer(
            traversed_nodes_dict=traversed_nodes,
            output_nodes_dict=output_nodes,
            material_type="maya",
            source_type="maya_nodes",
        ).run()

        material_name = next(iter(output_nodes.values()))["node_name"] if output_nodes else material_node
        return MaterialData(
            material_name=material_name,
            material_path=f"/maya/{material_name}",
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
        )


class MayaMaterialWriter:
    """Write neutral material graphs into Maya shading networks."""

    def write(self, graph: MaterialGraph, target_context: Any = None) -> str:
        """Write a material graph into Maya.

        Args:
            graph: Standardized material graph to recreate.
            target_context: Existing shadingEngine node, a mapping containing
                ``shading_engine`` or ``material_name``, a material name string,
                or ``None`` to derive the target name from ``graph``.

        Returns:
            Created or reused Maya shadingEngine node name.

        Raises:
            RuntimeError: If recreation fails.
        """
        material_name = self._material_name(graph, target_context)
        shading_engine = MayaNodeRecreator(
            nodeinfo_list=graph.nodeinfo_list,
            output_connections=graph.output_connections,
            target_context=target_context,
            material_name=material_name,
        ).run()
        if not shading_engine:
            raise RuntimeError(f"Failed to recreate Maya material '{material_name}'.")
        return shading_engine

    @staticmethod
    def _material_name(graph: MaterialGraph, target_context: Any) -> str:
        if isinstance(target_context, Mapping):
            return str(target_context.get("material_name") or target_context.get("name") or graph.material_name)
        if isinstance(target_context, str):
            return target_context
        return graph.material_name
