"""Shared CLI helpers for writing USD material files from DCC graph payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from materials_processor.core.graph import MaterialGraph, NodeConnection, NodeInfo, NodeParameter, OutputConnection

DEFAULT_EXPORT_TARGETS = ("mtlx", "openpbr")
TARGET_ALIASES = {
    "materialx": "mtlx",
    "mtlx": "mtlx",
    "openpbr": "openpbr",
}
TARGET_FILE_LABELS = {
    "mtlx": "materialx",
    "openpbr": "openpbr",
}


def nodeinfo_from_dict(data: dict[str, Any]) -> NodeInfo:
    """
    Reconstruct a ``NodeInfo`` instance from serialized mapping data.
    
    Parameters:
    	data (dict[str, Any]): JSON-compatible node data, including nested child nodes.
    
    Returns:
    	NodeInfo: The reconstructed node information.
    """
    return NodeInfo(
        node_type=data.get("node_type"),
        node_name=data["node_name"],
        node_path=data["node_path"],
        parameters=[NodeParameter(**param) for param in data.get("parameters") or []],
        connection_info={
            key: NodeConnection.from_mapping(value) for key, value in (data.get("connection_info") or {}).items()
        },
        children_list=[nodeinfo_from_dict(child) for child in data.get("children_list") or []],
        is_output_node=data.get("is_output_node", False),
        output_type=data.get("output_type"),
        position=data.get("position"),
    )


def material_graph_from_dict(data: dict[str, Any]) -> MaterialGraph:
    """Rebuild a material graph from JSON-compatible data."""
    return MaterialGraph(
        material_name=data["material_name"],
        material_path=data.get("material_path"),
        nodeinfo_list=[nodeinfo_from_dict(node) for node in data.get("nodeinfo_list") or []],
        output_connections={
            key: OutputConnection.from_mapping(value) for key, value in (data.get("output_connections") or {}).items()
        },
    )


def export_targets_from_args(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Normalize CLI target values to internal USD renderer target names."""
    targets = []
    for value in values or ["all"]:
        if value == "all":
            targets.extend(DEFAULT_EXPORT_TARGETS)
        else:
            targets.append(TARGET_ALIASES[value])
    return tuple(dict.fromkeys(targets))


def build_usd_material_files(
    graph_payload: dict[str, Any],
    out_dir: str | Path,
    *,
    source_label: str,
    targets: tuple[str, ...] = DEFAULT_EXPORT_TARGETS,
) -> dict[str, Any]:
    """Build USD material files from extracted DCC material graph data."""
    from pxr import Sdf, Usd

    from materials_processor.usd.recreator import USDMaterialRecreator

    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    graphs = [material_graph_from_dict(graph) for graph in graph_payload.get("graphs") or []]
    report = {
        "scene": graph_payload.get("scene"),
        "output_dir": str(output_dir),
        "material_count": graph_payload.get("material_count", 0),
        "node_material_count": graph_payload.get("node_material_count", 0),
        "graph_count": len(graphs),
        "read_failures": graph_payload.get("read_failures", []),
        "unsupported_nodes": graph_payload.get("unsupported_nodes", {}),
        "missing_texture_paths": graph_payload.get("missing_texture_paths", []),
        "remapped_texture_paths": graph_payload.get("remapped_texture_paths", []),
        "usd_files": {},
    }

    for target in export_targets_from_args(targets):
        usd_path = output_dir / f"{source_label}_{TARGET_FILE_LABELS[target]}.usda"
        stage = Usd.Stage.CreateNew(str(usd_path))
        stage.SetDefaultPrim(stage.DefinePrim(Sdf.Path("/materials"), "Scope"))

        for graph in graphs:
            if not graph.nodeinfo_list or not graph.output_connections:
                continue
            USDMaterialRecreator(
                stage=stage,
                material_name=graph.material_name,
                nodeinfo_list=graph.nodeinfo_list,
                output_connections=graph.output_connections,
                parent_scope_path="/materials",
                target_renderer=target,
            ).run()

        stage.GetRootLayer().Save()
        opened_stage = Usd.Stage.Open(str(usd_path))
        if opened_stage is None:
            raise RuntimeError(f"USD file was written but could not be reopened: {usd_path}")

        shader_ids = {}
        materials = []
        for prim in opened_stage.Traverse():
            if prim.GetTypeName() == "Material":
                materials.append(prim.GetPath().pathString)
            attr = prim.GetAttribute("info:id")
            if attr and attr.Get():
                shader_id = attr.Get()
                shader_ids[shader_id] = shader_ids.get(shader_id, 0) + 1

        report["usd_files"][target] = {
            "path": str(usd_path),
            "material_prim_count": len(materials),
            "material_prims": materials,
            "shader_ids": shader_ids,
        }

    return report
