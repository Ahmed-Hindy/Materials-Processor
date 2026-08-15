"""Command line tools for Maya material workflows."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from materials_processor.dcc.maya.runtime import MayaRuntime, _run_mayapy, resolve_maya_runtime
from materials_processor.dcc.usd_cli import DEFAULT_EXPORT_TARGETS, build_usd_material_files, export_targets_from_args

MAYA_GRAPH_EXPORT_PREFIX = "MATERIALS_PROCESSOR_MAYA_GRAPH_EXPORT="
MISSING_TEXTURE_POLICIES = ("warn", "error")
DEFAULT_SHADING_ENGINES = ("initialShadingGroup", "initialParticleSE")


def _default_package_src() -> Path:
    return Path(__file__).resolve().parents[3]


def _iter_nodeinfos(nodes):
    for node in nodes:
        yield node
        yield from _iter_nodeinfos(node.children_list)


def _node_summary(node) -> dict[str, str | None]:
    return {
        "node_name": node.node_name,
        "node_path": node.node_path,
        "node_type": node.node_type,
    }


def _enforce_report_policies(
    report: dict[str, Any],
    *,
    fail_on_unsupported: bool = False,
    missing_textures: str = "warn",
) -> None:
    """Raise an error when the report contains findings that match the configured failure policies.
    
    Parameters:
    	report (dict[str, Any]): Report containing unsupported nodes and missing texture paths.
    	fail_on_unsupported (bool): Whether unsupported nodes should cause an error.
    	missing_textures (str): Policy for missing textures; `"error"` raises an error when any are found.
    """
    if fail_on_unsupported and report.get("unsupported_nodes"):
        raise RuntimeError(
            f"Unsupported Maya nodes were found: {json.dumps(report['unsupported_nodes'], sort_keys=True)}"
        )
    if missing_textures == "error" and report.get("missing_texture_paths"):
        raise RuntimeError(
            f"Missing texture paths were found: {json.dumps(report['missing_texture_paths'], sort_keys=True)}"
        )


def _extract_code(scene_path: Path, graph_json_path: Path) -> str:
    """
    Generate the Python script executed by mayapy to extract material graphs from a Maya scene.
    
    Parameters:
        scene_path (Path): Path to the Maya scene to process.
        graph_json_path (Path): Destination for the extracted graph data in JSON format.
    
    Returns:
        str: The mayapy script configured for the specified scene and output path.
    """
    return f"""
import json
from dataclasses import asdict
from pathlib import Path

import maya.cmds as cmds
import maya.standalone

from materials_processor.dcc.maya.adapters import MayaMaterialReader

SCENE_PATH = {str(scene_path)!r}
GRAPH_JSON_PATH = {str(graph_json_path)!r}
PREFIX = {MAYA_GRAPH_EXPORT_PREFIX!r}
DEFAULT_SHADING_ENGINES = set({DEFAULT_SHADING_ENGINES!r})


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


maya.standalone.initialize(name="python")
try:
    cmds.file(SCENE_PATH, open=True, force=True, prompt=False, ignoreVersion=True)
    reader = MayaMaterialReader()
    shading_engines = cmds.ls(type="shadingEngine") or []
    materials = []
    for shading_engine in shading_engines:
        if shading_engine in DEFAULT_SHADING_ENGINES:
            continue
        sources = cmds.listConnections(
            shading_engine + ".surfaceShader",
            source=True,
            destination=False,
            plugs=True,
        ) or []
        if sources:
            materials.append(shading_engine)

    result = {{
        "scene": SCENE_PATH,
        "material_count": len(shading_engines),
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
            result["read_failures"].append({{"material": material, "error": repr(exc)}})
            continue

        nodeinfos = list(iter_nodeinfos(graph.nodeinfo_list))
        unsupported = [node_summary(node) for node in nodeinfos if node.node_type is None]
        if unsupported:
            result["unsupported_nodes"][material] = unsupported

        for node in nodeinfos:
            for parameter in node.parameters or []:
                if parameter.generic_name != "filename" or not parameter.value:
                    continue
                texture_path = str(parameter.value)
                normalized = texture_path.replace("<UDIM>", "1001")
                if "<UDIM>" not in texture_path and not Path(normalized).exists():
                    result["missing_texture_paths"].append({{
                        "material": material,
                        "path": texture_path,
                    }})

        result["graphs"].append(asdict(graph))

    Path(GRAPH_JSON_PATH).write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = {{key: value for key, value in result.items() if key != "graphs"}}
    summary["graph_count"] = len(result["graphs"])
    print(PREFIX + json.dumps(summary, sort_keys=True))
finally:
    try:
        maya.standalone.uninitialize()
    except Exception:
        pass
""".strip()


def extract_maya_material_graphs(
    scene_path: str | Path,
    graph_json_path: str | Path,
    *,
    runtime: MayaRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Extract standardized Maya material graphs and write them to a JSON file.
    
    Parameters:
        scene_path (str | Path): Path to the Maya scene to process.
        graph_json_path (str | Path): Destination path for the extracted graph JSON.
        package_src (str | Path | None): Optional package source directory used by the Maya runtime.
        timeout (int): Maximum number of seconds allowed for extraction.
    
    Returns:
        dict[str, Any]: Summary of the extracted material graphs.
    
    Raises:
        FileNotFoundError: If the Maya scene does not exist.
        RuntimeError: If extraction fails or does not produce a summary.
    """
    scene = Path(scene_path).expanduser().resolve()
    if not scene.is_file():
        raise FileNotFoundError(f"Maya scene was not found: {scene}")

    graph_json = Path(graph_json_path).expanduser().resolve()
    graph_json.parent.mkdir(parents=True, exist_ok=True)
    package_src_path = Path(package_src).resolve() if package_src is not None else _default_package_src()
    runtime = runtime or resolve_maya_runtime()

    completed = _run_mayapy(
        runtime,
        _extract_code(scene, graph_json),
        package_src_path,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Maya material graph extraction failed with exit code "
            f"{completed.returncode}.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    for line in completed.stdout.splitlines():
        if line.startswith(MAYA_GRAPH_EXPORT_PREFIX):
            return json.loads(line[len(MAYA_GRAPH_EXPORT_PREFIX) :])

    raise RuntimeError(
        "Maya material graph extraction did not report a summary."
        f"\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def export_maya_scene_to_usd(
    scene_path: str | Path,
    out_dir: str | Path,
    *,
    targets: tuple[str, ...] = DEFAULT_EXPORT_TARGETS,
    runtime: MayaRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
    missing_textures: str = "warn",
    fail_on_unsupported: bool = False,
    report_json: str | Path | None = None,
    graph_json: str | Path | None = None,
) -> dict[str, Any]:
    """
    Export materials from a Maya scene to USD MaterialX/OpenPBR files and write an export report.
    
    Parameters:
        scene_path (str | Path): Path to the Maya scene.
        out_dir (str | Path): Directory for generated material files and the default report.
        targets (tuple[str, ...]): Material export targets to generate.
        missing_textures (str): Policy for missing textures, such as ``"warn"`` or ``"error"``.
        fail_on_unsupported (bool): Whether unsupported nodes should cause the export to fail.
        report_json (str | Path | None): Optional path for the export report.
        graph_json (str | Path | None): Optional path for the extracted material graph JSON.
    
    Returns:
        dict[str, Any]: The export report, including generated files, graph path, and report path.
    """
    output_dir = Path(out_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_json_path = (
        Path(graph_json).expanduser().resolve() if graph_json else output_dir / "maya_material_graphs.json"
    )
    graph_json_path.parent.mkdir(parents=True, exist_ok=True)

    extract_maya_material_graphs(
        scene_path,
        graph_json_path,
        runtime=runtime,
        package_src=package_src,
        timeout=timeout,
    )
    graph_payload = json.loads(graph_json_path.read_text(encoding="utf-8"))

    report = build_usd_material_files(graph_payload, output_dir, source_label="maya_scene", targets=targets)
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


def inspect_maya_scene(
    scene_path: str | Path,
    *,
    runtime: MayaRuntime | None = None,
    package_src: str | Path | None = None,
    timeout: int = 300,
    graph_json: str | Path | None = None,
    report_json: str | Path | None = None,
    missing_textures: str = "warn",
    fail_on_unsupported: bool = False,
) -> dict[str, Any]:
    """Inspect a Maya scene's materials without writing USD files."""
    if graph_json:
        graph_json_path = Path(graph_json).expanduser().resolve()
        graph_json_path.parent.mkdir(parents=True, exist_ok=True)
        cleanup_dir = None
    else:
        cleanup_dir = tempfile.TemporaryDirectory(prefix="materials_processor_maya_inspect_")
        graph_json_path = Path(cleanup_dir.name) / "maya_material_graphs.json"

    try:
        extract_maya_material_graphs(
            scene_path,
            graph_json_path,
            runtime=runtime,
            package_src=package_src,
            timeout=timeout,
        )
        graph_payload = json.loads(graph_json_path.read_text(encoding="utf-8"))
        graphs = graph_payload.get("graphs") or []
        report = {
            "scene": graph_payload.get("scene"),
            "material_count": graph_payload.get("material_count", 0),
            "node_material_count": graph_payload.get("node_material_count", 0),
            "graph_count": len(graphs),
            "read_failures": graph_payload.get("read_failures", []),
            "unsupported_nodes": graph_payload.get("unsupported_nodes", {}),
            "missing_texture_paths": graph_payload.get("missing_texture_paths", []),
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


def add_maya_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common Maya runtime options to an argument parser."""
    parser.add_argument("--maya-root", help="Explicit Maya install root.")
    parser.add_argument("--maya-version", default="2024", help="Maya version to resolve. Default: 2024.")
    parser.add_argument("--timeout", type=int, default=300, help="mayapy timeout in seconds.")
    parser.add_argument(
        "--package-src",
        default=None,
        help="Source directory to expose to mayapy. Defaults to this checkout's src directory.",
    )


def add_policy_arguments(parser: argparse.ArgumentParser) -> None:
    """Add report policy options to an argument parser."""
    parser.add_argument(
        "--missing-textures",
        choices=MISSING_TEXTURE_POLICIES,
        default="warn",
        help="Whether missing textures should warn in the report or fail the command.",
    )
    parser.add_argument(
        "--fail-on-unsupported",
        action="store_true",
        help="Fail when unsupported Maya nodes are found.",
    )


def add_maya_export_parser(subparsers) -> argparse.ArgumentParser:
    """Add the Maya ``export-usd`` subcommand to a subparser collection."""
    export_parser = subparsers.add_parser(
        "export-usd",
        help="Export node materials from a Maya scene to USD material files.",
    )
    export_parser.add_argument("scene", help="Path to the .ma or .mb scene.")
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
    export_parser.add_argument(
        "--graph-json", default=None, help="Explicit path for the extracted material graph JSON."
    )
    add_maya_runtime_arguments(export_parser)
    add_policy_arguments(export_parser)
    return export_parser


def add_maya_inspect_parser(subparsers) -> argparse.ArgumentParser:
    """Add the Maya ``inspect`` subcommand to a subparser collection."""
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect node materials in a Maya scene without writing USD files.",
    )
    inspect_parser.add_argument("scene", help="Path to the .ma or .mb scene.")
    inspect_parser.add_argument("--report-json", default=None, help="Optional path for the inspection report JSON.")
    inspect_parser.add_argument(
        "--graph-json", default=None, help="Optional path for the extracted material graph JSON."
    )
    add_maya_runtime_arguments(inspect_parser)
    add_policy_arguments(inspect_parser)
    return inspect_parser


def _runtime_from_args(args) -> MayaRuntime:
    """Resolve Maya runtime from parsed arguments."""
    return resolve_maya_runtime(version=args.maya_version, root=args.maya_root)


def run_export_from_args(args) -> dict[str, Any]:
    """Run Maya USD export from parsed CLI arguments."""
    out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="materials_processor_maya_usd_"))
    return export_maya_scene_to_usd(
        args.scene,
        out_dir,
        targets=export_targets_from_args(args.target),
        runtime=_runtime_from_args(args),
        package_src=args.package_src,
        timeout=args.timeout,
        missing_textures=args.missing_textures,
        fail_on_unsupported=args.fail_on_unsupported,
        report_json=args.report_json,
        graph_json=args.graph_json,
    )


def run_inspect_from_args(args) -> dict[str, Any]:
    """Run Maya material inspection from parsed CLI arguments."""
    return inspect_maya_scene(
        args.scene,
        runtime=_runtime_from_args(args),
        package_src=args.package_src,
        timeout=args.timeout,
        graph_json=args.graph_json,
        report_json=args.report_json,
        missing_textures=args.missing_textures,
        fail_on_unsupported=args.fail_on_unsupported,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="materials-processor-maya")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_maya_export_parser(subparsers)
    add_maya_inspect_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Maya command line interface."""
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
