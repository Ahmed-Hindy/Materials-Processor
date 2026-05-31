"""Command line tools for Blender material workflows."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path, PureWindowsPath
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
MISSING_TEXTURE_POLICIES = ("warn", "error")


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


def _texture_remaps_from_args(values: list[str] | None) -> tuple[tuple[str, str], ...]:
    """Parse ``OLD=NEW`` texture remap arguments."""
    remaps = []
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"Texture remap must be in OLD=NEW form: {value}")
        old, new = value.split("=", 1)
        if not old or not new:
            raise ValueError(f"Texture remap must include both OLD and NEW paths: {value}")
        remaps.append((old, new))
    return tuple(remaps)


def _apply_texture_remaps_to_path(
    texture_path: str,
    *,
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
) -> str:
    """Apply prefix and search-root remaps to one texture path."""
    remapped = texture_path
    for old_prefix, new_prefix in remap_prefixes:
        old_norm = old_prefix.replace("\\", "/").rstrip("/")
        current_norm = remapped.replace("\\", "/")
        if current_norm == old_norm or current_norm.startswith(f"{old_norm}/"):
            suffix = current_norm[len(old_norm):].lstrip("/")
            remapped = str(Path(new_prefix) / Path(suffix.replace("/", "\\")))
            break

    if texture_root is not None and remapped == texture_path and not Path(remapped.replace("<UDIM>", "1001")).exists():
        texture_name = PureWindowsPath(texture_path).name or Path(texture_path).name
        candidate = Path(texture_root) / texture_name
        if candidate.exists():
            remapped = str(candidate)
        else:
            recursive_match = next(Path(texture_root).rglob(texture_name), None)
            if recursive_match is not None:
                remapped = str(recursive_match)

    return remapped


def _apply_texture_remaps(
    graph_payload: dict[str, Any],
    *,
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    """Apply texture remap options directly to extracted graph payload data."""
    if not texture_root and not remap_prefixes:
        return graph_payload

    remapped_textures = []
    for graph in graph_payload.get("graphs") or []:
        for node in _walk_node_dicts(graph.get("nodeinfo_list") or []):
            for parameter in node.get("parameters") or []:
                if parameter.get("generic_name") != "filename" or not parameter.get("value"):
                    continue
                original = str(parameter["value"])
                remapped = _apply_texture_remaps_to_path(
                    original,
                    texture_root=texture_root,
                    remap_prefixes=remap_prefixes,
                )
                if remapped != original:
                    parameter["value"] = remapped
                    remapped_textures.append(
                        {
                            "material": graph["material_name"],
                            "original": original,
                            "remapped": remapped,
                        }
                    )

    graph_payload["remapped_texture_paths"] = remapped_textures
    graph_payload["missing_texture_paths"] = _find_missing_texture_paths(graph_payload)
    return graph_payload


def _walk_node_dicts(nodes: list[dict[str, Any]]):
    """Yield node dictionaries recursively from JSON-compatible graph data."""
    for node in nodes:
        yield node
        yield from _walk_node_dicts(node.get("children_list") or [])


def _find_missing_texture_paths(graph_payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return missing texture paths from JSON-compatible graph data."""
    missing = []
    for graph in graph_payload.get("graphs") or []:
        for node in _walk_node_dicts(graph.get("nodeinfo_list") or []):
            for parameter in node.get("parameters") or []:
                if parameter.get("generic_name") != "filename" or not parameter.get("value"):
                    continue
                texture_path = str(parameter["value"])
                normalized = texture_path.replace("<UDIM>", "1001")
                if "<UDIM>" not in texture_path and not Path(normalized).exists():
                    missing.append({"material": graph["material_name"], "path": texture_path})
    return missing


def _enforce_report_policies(
    report: dict[str, Any],
    *,
    fail_on_unsupported: bool = False,
    missing_textures: str = "warn",
) -> None:
    """Raise when report policy flags request hard failures."""
    if fail_on_unsupported and report.get("unsupported_nodes"):
        raise RuntimeError(f"Unsupported Blender nodes were found: {json.dumps(report['unsupported_nodes'], sort_keys=True)}")
    if missing_textures == "error" and report.get("missing_texture_paths"):
        raise RuntimeError(f"Missing texture paths were found: {json.dumps(report['missing_texture_paths'], sort_keys=True)}")


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
        "remapped_texture_paths": graph_payload.get("remapped_texture_paths", []),
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
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
    missing_textures: str = "warn",
    fail_on_unsupported: bool = False,
    report_json: str | Path | None = None,
    graph_json: str | Path | None = None,
) -> dict[str, Any]:
    """Export Blender scene materials to USD MaterialX/OpenPBR files."""
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_json_path = Path(graph_json).expanduser().resolve() if graph_json else output_dir / "blender_material_graphs.json"
    graph_json_path.parent.mkdir(parents=True, exist_ok=True)

    extract_blender_material_graphs(
        scene_path,
        graph_json_path,
        runtime=runtime,
        package_src=package_src,
        timeout=timeout,
    )
    graph_payload = json.loads(graph_json_path.read_text(encoding="utf-8"))
    graph_payload = _apply_texture_remaps(
        graph_payload,
        texture_root=texture_root,
        remap_prefixes=remap_prefixes,
    )
    graph_json_path.write_text(json.dumps(graph_payload, indent=2, sort_keys=True), encoding="utf-8")

    report = build_usd_material_files(graph_payload, output_dir, targets=targets)
    report["graph_json"] = str(graph_json_path)

    report_json_path = Path(report_json).expanduser().resolve() if report_json else output_dir / "export_report.json"
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report["report_json"] = str(report_json_path)
    report_json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    _enforce_report_policies(
        report,
        fail_on_unsupported=fail_on_unsupported,
        missing_textures=missing_textures,
    )
    return report


def inspect_blender_scene(
    scene_path: str | Path,
    *,
    runtime: BlenderRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
    texture_root: str | Path | None = None,
    remap_prefixes: tuple[tuple[str, str], ...] = (),
    graph_json: str | Path | None = None,
    report_json: str | Path | None = None,
    missing_textures: str = "warn",
    fail_on_unsupported: bool = False,
) -> dict[str, Any]:
    """Inspect a Blender scene's materials without writing USD files."""
    if graph_json:
        graph_json_path = Path(graph_json).expanduser().resolve()
        graph_json_path.parent.mkdir(parents=True, exist_ok=True)
        cleanup_dir = None
    else:
        cleanup_dir = tempfile.TemporaryDirectory(prefix="materials_processor_blender_inspect_")
        graph_json_path = Path(cleanup_dir.name) / "blender_material_graphs.json"

    try:
        extract_blender_material_graphs(
            scene_path,
            graph_json_path,
            runtime=runtime,
            package_src=package_src,
            timeout=timeout,
        )
        graph_payload = json.loads(graph_json_path.read_text(encoding="utf-8"))
        graph_payload = _apply_texture_remaps(
            graph_payload,
            texture_root=texture_root,
            remap_prefixes=remap_prefixes,
        )
        if graph_json:
            graph_json_path.write_text(json.dumps(graph_payload, indent=2, sort_keys=True), encoding="utf-8")

        graphs = graph_payload.get("graphs") or []
        report = {
            "scene": graph_payload.get("scene"),
            "material_count": graph_payload.get("material_count", 0),
            "node_material_count": graph_payload.get("node_material_count", 0),
            "graph_count": len(graphs),
            "read_failures": graph_payload.get("read_failures", []),
            "unsupported_nodes": graph_payload.get("unsupported_nodes", {}),
            "missing_texture_paths": graph_payload.get("missing_texture_paths", []),
            "remapped_texture_paths": graph_payload.get("remapped_texture_paths", []),
        }
        if graph_json:
            report["graph_json"] = str(graph_json_path)
        if report_json:
            report_json_path = Path(report_json).expanduser().resolve()
            report_json_path.parent.mkdir(parents=True, exist_ok=True)
            report["report_json"] = str(report_json_path)
            report_json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        _enforce_report_policies(
            report,
            fail_on_unsupported=fail_on_unsupported,
            missing_textures=missing_textures,
        )
        return report
    finally:
        if cleanup_dir is not None:
            cleanup_dir.cleanup()


def _targets_from_args(values: list[str]) -> tuple[str, ...]:
    targets = []
    values = values or ["all"]
    for value in values:
        if value == "all":
            targets.extend(DEFAULT_EXPORT_TARGETS)
        else:
            targets.append(TARGET_ALIASES[value])
    return tuple(dict.fromkeys(targets))


def add_blender_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common Blender runtime options to an argument parser."""
    parser.add_argument("--blender-exe", help="Explicit path to blender.exe.")
    parser.add_argument("--blender-root", help="Explicit Blender install root.")
    parser.add_argument("--blender-version", help="Blender version to discover, e.g. 4.5.")
    parser.add_argument("--timeout", type=int, default=300, help="Headless Blender timeout in seconds.")
    parser.add_argument(
        "--package-src",
        default=None,
        help="Source directory to expose to Blender. Defaults to this checkout's src directory.",
    )


def add_texture_arguments(parser: argparse.ArgumentParser) -> None:
    """Add texture reporting/remap options to an argument parser."""
    parser.add_argument(
        "--texture-root",
        default=None,
        help="Directory to search by filename for missing texture paths.",
    )
    parser.add_argument(
        "--remap-prefix",
        action="append",
        default=None,
        metavar="OLD=NEW",
        help="Remap texture paths with the given prefix replacement. Can be passed more than once.",
    )
    parser.add_argument(
        "--missing-textures",
        choices=MISSING_TEXTURE_POLICIES,
        default="warn",
        help="Whether missing textures should warn in the report or fail the command.",
    )
    parser.add_argument(
        "--fail-on-unsupported",
        action="store_true",
        help="Fail when unsupported Blender nodes are found.",
    )


def add_blender_export_parser(subparsers) -> argparse.ArgumentParser:
    """Add the Blender ``export-usd`` subcommand to a subparser collection."""
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
    export_parser.add_argument("--report-json", default=None, help="Explicit path for the export report JSON.")
    export_parser.add_argument("--graph-json", default=None, help="Explicit path for the extracted material graph JSON.")
    add_blender_runtime_arguments(export_parser)
    add_texture_arguments(export_parser)
    return export_parser


def add_blender_inspect_parser(subparsers) -> argparse.ArgumentParser:
    """Add the Blender ``inspect`` subcommand to a subparser collection."""
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect node materials in a .blend scene without writing USD files.",
    )
    inspect_parser.add_argument("scene", help="Path to the .blend scene.")
    inspect_parser.add_argument("--report-json", default=None, help="Optional path for the inspection report JSON.")
    inspect_parser.add_argument("--graph-json", default=None, help="Optional path for the extracted material graph JSON.")
    add_blender_runtime_arguments(inspect_parser)
    add_texture_arguments(inspect_parser)
    return inspect_parser


def _runtime_from_args(args) -> BlenderRuntime:
    """Resolve Blender runtime from parsed arguments."""
    return resolve_blender_runtime(
        version=args.blender_version,
        root=args.blender_root,
        blender_exe=args.blender_exe,
    )


def run_export_from_args(args) -> dict[str, Any]:
    """Run Blender USD export from parsed CLI arguments."""
    out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="materials_processor_blender_usd_"))
    return export_blender_scene_to_usd(
        args.scene,
        out_dir,
        targets=_targets_from_args(args.target),
        runtime=_runtime_from_args(args),
        package_src=args.package_src,
        timeout=args.timeout,
        texture_root=args.texture_root,
        remap_prefixes=_texture_remaps_from_args(args.remap_prefix),
        missing_textures=args.missing_textures,
        fail_on_unsupported=args.fail_on_unsupported,
        report_json=args.report_json,
        graph_json=args.graph_json,
    )


def run_inspect_from_args(args) -> dict[str, Any]:
    """Run Blender material inspection from parsed CLI arguments."""
    return inspect_blender_scene(
        args.scene,
        runtime=_runtime_from_args(args),
        package_src=args.package_src,
        timeout=args.timeout,
        texture_root=args.texture_root,
        remap_prefixes=_texture_remaps_from_args(args.remap_prefix),
        graph_json=args.graph_json,
        report_json=args.report_json,
        missing_textures=args.missing_textures,
        fail_on_unsupported=args.fail_on_unsupported,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="materials-processor-blender")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_blender_export_parser(subparsers)
    add_blender_inspect_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Blender command line interface."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "export-usd":
            report = run_export_from_args(args)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        if args.command == "inspect":
            report = run_inspect_from_args(args)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
