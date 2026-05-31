"""Command line tools for Blender material workflows."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from materials_processor.core.graph import MaterialGraph, NodeConnection, NodeInfo, NodeParameter, OutputConnection
from materials_processor.dcc.blender.runtime import BlenderRuntime, _run_blender_python, resolve_blender_runtime

BLENDER_GRAPH_EXPORT_PREFIX = "MATERIALS_PROCESSOR_BLENDER_GRAPH_EXPORT="
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


def _default_package_src() -> Path:
    return Path(__file__).resolve().parents[3]


def _nodeinfo_from_dict(data: dict[str, Any]) -> NodeInfo:
    """Rebuild a ``NodeInfo`` from JSON-compatible data."""
    return NodeInfo(
        node_type=data.get("node_type"),
        node_name=data["node_name"],
        node_path=data["node_path"],
        parameters=[NodeParameter(**param) for param in data.get("parameters") or []],
        connection_info={
            key: NodeConnection.from_mapping(value)
            for key, value in (data.get("connection_info") or {}).items()
        },
        children_list=[_nodeinfo_from_dict(child) for child in data.get("children_list") or []],
        is_output_node=data.get("is_output_node", False),
        output_type=data.get("output_type"),
        position=data.get("position"),
    )


def _material_graph_from_dict(data: dict[str, Any]) -> MaterialGraph:
    """Rebuild a material graph from JSON-compatible data."""
    return MaterialGraph(
        material_name=data["material_name"],
        material_path=data.get("material_path"),
        nodeinfo_list=[_nodeinfo_from_dict(node) for node in data.get("nodeinfo_list") or []],
        output_connections={
            key: OutputConnection.from_mapping(value)
            for key, value in (data.get("output_connections") or {}).items()
        },
    )


def _iter_nodeinfos(nodes: list[NodeInfo]):
    for node in nodes:
        yield node
        yield from _iter_nodeinfos(node.children_list)


def _extract_code(scene_path: Path, graph_json_path: Path) -> str:
    """Return the Python script executed inside Blender to extract material graphs."""
    return f"""
import json
from dataclasses import asdict
from pathlib import Path

import bpy

from materials_processor.dcc.blender.adapters import BlenderMaterialReader

SCENE_PATH = {str(scene_path)!r}
GRAPH_JSON_PATH = {str(graph_json_path)!r}
PREFIX = {BLENDER_GRAPH_EXPORT_PREFIX!r}


def iter_nodeinfos(nodes):
    for node in nodes:
        yield node
        yield from iter_nodeinfos(node.children_list)


def node_summary(node):
    return {{
        "node_name": node.node_name,
        "node_path": node.node_path,
        "node_type": node.node_type,
    }}


bpy.ops.wm.open_mainfile(filepath=SCENE_PATH)
reader = BlenderMaterialReader()
materials = [
    material
    for material in bpy.data.materials
    if getattr(material, "use_nodes", False) and getattr(material, "node_tree", None)
]
result = {{
    "scene": SCENE_PATH,
    "material_count": len(bpy.data.materials),
    "node_material_count": len(materials),
    "graphs": [],
    "read_failures": [],
    "unsupported_nodes": {{}},
    "missing_texture_paths": [],
}}

for material in materials:
    try:
        graph = reader.read(material)
    except Exception as exc:
        result["read_failures"].append({{"material": material.name, "error": repr(exc)}})
        continue

    nodeinfos = list(iter_nodeinfos(graph.nodeinfo_list))
    unsupported = [node_summary(node) for node in nodeinfos if node.node_type is None]
    if unsupported:
        result["unsupported_nodes"][material.name] = unsupported

    for node in nodeinfos:
        for parameter in node.parameters or []:
            if parameter.generic_name != "filename" or not parameter.value:
                continue
            texture_path = str(parameter.value)
            normalized = texture_path.replace("<UDIM>", "1001")
            if "<UDIM>" not in texture_path and not Path(normalized).exists():
                result["missing_texture_paths"].append({{
                    "material": material.name,
                    "path": texture_path,
                }})

    result["graphs"].append(asdict(graph))

Path(GRAPH_JSON_PATH).write_text(json.dumps(result, indent=2), encoding="utf-8")
summary = {{key: value for key, value in result.items() if key != "graphs"}}
summary["graph_count"] = len(result["graphs"])
print(PREFIX + json.dumps(summary, sort_keys=True))
""".strip()


def extract_blender_material_graphs(
    scene_path: str | Path,
    graph_json_path: str | Path,
    *,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Extract standardized Blender material graphs into a JSON file.

    Args:
        scene_path: ``.blend`` scene to open in headless Blender.
        graph_json_path: JSON file to write graph data to.
        runtime: Optional resolved Blender runtime.
        package_src: Source directory to expose to Blender's ``PYTHONPATH``.
        timeout: Maximum seconds to wait for Blender.

    Returns:
        A summary of the extracted graphs, excluding the full graph payload.
    """
    scene = Path(scene_path).expanduser().resolve()
    if not scene.is_file():
        raise FileNotFoundError(f"Blender scene was not found: {scene}")

    graph_json = Path(graph_json_path).expanduser().resolve()
    graph_json.parent.mkdir(parents=True, exist_ok=True)
    package_src_path = Path(package_src).resolve() if package_src is not None else _default_package_src()
    runtime = runtime or resolve_blender_runtime(version=None)

    completed = _run_blender_python(
        runtime,
        _extract_code(scene, graph_json),
        package_src_path,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Blender material graph extraction failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    for line in completed.stdout.splitlines():
        if line.startswith(BLENDER_GRAPH_EXPORT_PREFIX):
            return json.loads(line[len(BLENDER_GRAPH_EXPORT_PREFIX):])

    raise RuntimeError(
        "Blender material graph extraction did not report a summary."
        f"\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def build_usd_material_files(
    graph_payload: dict[str, Any],
    out_dir: str | Path,
    *,
    targets: tuple[str, ...] = DEFAULT_EXPORT_TARGETS,
) -> dict[str, Any]:
    """Build USD material files from extracted Blender material graph data."""
    from pxr import Sdf, Usd

    from materials_processor.usd.recreator import USDMaterialRecreator

    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    graphs = [_material_graph_from_dict(graph) for graph in graph_payload.get("graphs") or []]
    report = {
        "scene": graph_payload.get("scene"),
        "output_dir": str(output_dir),
        "material_count": graph_payload.get("material_count", 0),
        "node_material_count": graph_payload.get("node_material_count", 0),
        "graph_count": len(graphs),
        "read_failures": graph_payload.get("read_failures", []),
        "unsupported_nodes": graph_payload.get("unsupported_nodes", {}),
        "missing_texture_paths": graph_payload.get("missing_texture_paths", []),
        "usd_files": {},
    }

    for target in _targets_from_args(list(targets)):
        usd_path = output_dir / f"blender_scene_{TARGET_FILE_LABELS[target]}.usda"
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


def export_blender_scene_to_usd(
    scene_path: str | Path,
    out_dir: str | Path,
    *,
    targets: tuple[str, ...] = DEFAULT_EXPORT_TARGETS,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Export Blender scene materials to USD MaterialX/OpenPBR files."""
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_json = output_dir / "blender_material_graphs.json"

    extract_blender_material_graphs(
        scene_path,
        graph_json,
        runtime=runtime,
        package_src=package_src,
        timeout=timeout,
    )
    graph_payload = json.loads(graph_json.read_text(encoding="utf-8"))
    report = build_usd_material_files(graph_payload, output_dir, targets=targets)
    report["graph_json"] = str(graph_json)

    report_json = output_dir / "export_report.json"
    report["report_json"] = str(report_json)
    report_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _targets_from_args(values: list[str]) -> tuple[str, ...]:
    targets = []
    values = values or ["all"]
    for value in values:
        if value == "all":
            targets.extend(DEFAULT_EXPORT_TARGETS)
        else:
            targets.append(TARGET_ALIASES[value])
    return tuple(dict.fromkeys(targets))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="materials-processor-blender")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export-usd",
        help="Export node materials from a .blend scene to USD material files.",
    )
    export_parser.add_argument("scene", help="Path to the .blend scene.")
    export_parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to write USD files and reports. Defaults to a temp directory.",
    )
    export_parser.add_argument(
        "--target",
        choices=("materialx", "mtlx", "openpbr", "all"),
        action="append",
        default=None,
        help="USD material target to export. Can be passed more than once. Default: all.",
    )
    export_parser.add_argument("--blender-exe", help="Explicit path to blender.exe.")
    export_parser.add_argument("--blender-root", help="Explicit Blender install root.")
    export_parser.add_argument("--blender-version", help="Blender version to discover, e.g. 4.5.")
    export_parser.add_argument("--timeout", type=int, default=300, help="Headless Blender timeout in seconds.")
    export_parser.add_argument(
        "--package-src",
        default=None,
        help="Source directory to expose to Blender. Defaults to this checkout's src directory.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Blender command line interface."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "export-usd":
        out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="materials_processor_blender_usd_"))
        runtime = resolve_blender_runtime(
            version=args.blender_version,
            root=args.blender_root,
            blender_exe=args.blender_exe,
        )
        report = export_blender_scene_to_usd(
            args.scene,
            out_dir,
            targets=_targets_from_args(args.target),
            runtime=runtime,
            package_src=args.package_src,
            timeout=args.timeout,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
