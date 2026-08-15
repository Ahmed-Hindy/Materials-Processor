"""Core adapter implementations for Blender materials."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from materials_processor.core.graph import MaterialData, MaterialGraph
from materials_processor.dcc.blender.recreator import BlenderNodeRecreator
from materials_processor.dcc.blender.traverser import BlenderNodeTraverser
from materials_processor.mappings import REGULAR_NODE_TYPES_TO_GENERIC, REGULAR_PARAM_NAMES_TO_GENERIC
from materials_processor.standardizer import NodeStandardizer

try:
    import bpy
except ImportError:
    bpy = None


@dataclass(frozen=True)
class BlenderConversionIssue:
    """One source-graph detail that prevents strict Blender reconstruction."""

    node_path: str
    detail: str


class BlenderMaterialConversionError(RuntimeError):
    """Raised when a Blender material cannot be recreated without omissions."""

    def __init__(self, material_name: str, issues: tuple[BlenderConversionIssue, ...]):
        self.material_name = material_name
        self.issues = issues
        details = "; ".join(f"{issue.node_path}: {issue.detail}" for issue in issues)
        super().__init__(f"Cannot strictly convert Blender material '{material_name}': {details}")


@dataclass(frozen=True)
class BlenderMaterialAnalysis:
    """Neutral graph and strict-recreation diagnostics for a Blender material."""

    graph: MaterialGraph
    issues: tuple[BlenderConversionIssue, ...]


def _iter_traversed_nodes(nodes: Mapping[str, Mapping[str, Any]]):
    """Yield raw Blender traversal nodes, including flattened group children."""
    for node in nodes.values():
        yield node
        for child in node.get("children_list") or []:
            yield from _iter_traversed_nodes({child["node_path"]: child})


def _strict_conversion_issues(
    material_name: str,
    traversed_nodes: Mapping[str, Mapping[str, Any]],
    output_nodes: Mapping[str, Mapping[str, Any]],
) -> tuple[BlenderConversionIssue, ...]:
    """Return details that would otherwise make a rebuilt material incomplete."""
    issues: set[tuple[str, str]] = set()
    node_types = REGULAR_NODE_TYPES_TO_GENERIC["blender"]["blender_shader_nodes"]

    if not output_nodes:
        issues.add((f"/mat/{material_name}", "no connected Material Output surface or displacement socket"))

    def validate_endpoint(endpoint: Mapping[str, Any]) -> None:
        node_type = endpoint["node_type"]
        generic_type = node_types.get(node_type)
        if generic_type is None:
            detail = "group output could not be flattened" if node_type == "ShaderNodeGroup" else f"unsupported node type {node_type}"
            issues.add((endpoint["node_path"], detail))
            return
        if generic_type == "GENERIC::null":
            return
        if endpoint["parm_name"] not in REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type, {}):
            issues.add((endpoint["node_path"], f"unsupported connected socket {endpoint['parm_name']}"))

    for node in _iter_traversed_nodes(traversed_nodes):
        node_type = node["node_type"]
        node_path = node["node_path"]
        generic_type = node_types.get(node_type)
        if generic_type is None:
            detail = "group output could not be flattened" if node_type == "ShaderNodeGroup" else f"unsupported node type {node_type}"
            issues.add((node_path, detail))
            continue

        if generic_type != "GENERIC::null":
            parameter_map = REGULAR_PARAM_NAMES_TO_GENERIC.get(node_type, {})
            for parameter in node.get("node_parms", {}).get("input", []):
                parameter_name = parameter["generic_name"]
                if parameter_name not in parameter_map:
                    issues.add((node_path, f"unsupported input {parameter_name}"))

        for connection in node.get("connections_dict", {}).values():
            validate_endpoint(connection["input"])
            validate_endpoint(connection["output"])

    return tuple(BlenderConversionIssue(node_path, detail) for node_path, detail in sorted(issues))


class BlenderMaterialReader:
    """Read Blender shader node materials into the neutral material graph."""

    def analyze(self, native_material: Any) -> BlenderMaterialAnalysis:
        """Read a material and report anything that prevents strict reconstruction."""
        material_name = getattr(native_material, "name", "blender_material")
        traversed_nodes, output_nodes = BlenderNodeTraverser(native_material).run()
        nodeinfo_list, output_connections = NodeStandardizer(
            traversed_nodes_dict=traversed_nodes,
            output_nodes_dict=output_nodes,
            material_type="blender",
            source_type="blender_shader_nodes",
        ).run()
        graph = MaterialData(
            material_name=material_name,
            material_path=f"/mat/{material_name}",
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
        )
        return BlenderMaterialAnalysis(
            graph=graph,
            issues=_strict_conversion_issues(material_name, traversed_nodes, output_nodes),
        )

    def read(self, native_material: Any) -> MaterialGraph:
        """Read a Blender material into a standardized material graph.

        Args:
            native_material: Blender material object with a shader node tree.

        Returns:
            Standardized material graph.
        """
        return self.analyze(native_material).graph


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


def convert_material(source_material: Any, *, target_name: str | None = None) -> Any:
    """Strictly rebuild a Blender material without modifying its source.

    Args:
        source_material: Blender material to standardize and recreate.
        target_name: Optional name for the new material. Defaults to the source
            name suffixed with ``_converted``.

    Returns:
        The newly created Blender material.

    Raises:
        BlenderMaterialConversionError: If any source detail would be omitted.
        RuntimeError: If called outside Blender.
    """
    if bpy is None:
        raise RuntimeError("Blender material conversion requires bpy.")

    analysis = BlenderMaterialReader().analyze(source_material)
    if analysis.issues:
        raise BlenderMaterialConversionError(analysis.graph.material_name, analysis.issues)

    target_material = bpy.data.materials.new(target_name or f"{source_material.name}_converted")
    target_material.use_nodes = True
    try:
        BlenderMaterialWriter().write(analysis.graph, target_material)
    except Exception:
        bpy.data.materials.remove(target_material, do_unlink=True)
        raise
    return target_material


def convert_active_material(active_object: Any, *, target_name: str | None = None) -> Any:
    """Rebuild and assign an object's active material slot without touching the source."""
    source_material = getattr(active_object, "active_material", None)
    if source_material is None:
        raise ValueError("The active object has no active material.")

    converted_material = convert_material(source_material, target_name=target_name)
    active_object.active_material = converted_material
    return converted_material
