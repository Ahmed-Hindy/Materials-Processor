"""Top-level command line interface for Materials Processor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_processor.dcc.blender import cli as blender_cli


def _default_package_src() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _add_runtime_parser(subparsers) -> argparse.ArgumentParser:
    runtime_parser = subparsers.add_parser("runtime", help="Runtime discovery and validation commands.")
    runtime_subparsers = runtime_parser.add_subparsers(dest="runtime_command", required=True)

    validate_parser = runtime_subparsers.add_parser("validate", help="Validate an installed DCC runtime.")
    validate_parser.add_argument(
        "--dcc",
        choices=("blender", "maya"),
        required=True,
        help="DCC runtime to validate.",
    )
    validate_parser.add_argument("--timeout", type=int, default=120, help="Validation timeout in seconds.")
    validate_parser.add_argument(
        "--package-src",
        default=None,
        help="Source directory to expose to the DCC. Defaults to this checkout's src directory.",
    )
    validate_parser.add_argument("--material-smoke", action="store_true", help="Run material traversal/recreation smoke.")

    blender_group = validate_parser.add_argument_group("Blender")
    blender_group.add_argument("--blender-exe", help="Explicit path to blender.exe.")
    blender_group.add_argument("--blender-root", help="Explicit Blender install root.")
    blender_group.add_argument("--blender-version", help="Blender version to discover, e.g. 4.5.")

    maya_group = validate_parser.add_argument_group("Maya")
    maya_group.add_argument("--maya-root", help="Explicit Maya install root.")
    maya_group.add_argument("--maya-version", default="2024", help="Maya version to resolve. Default: 2024.")

    return runtime_parser


def _add_blender_parser(subparsers) -> argparse.ArgumentParser:
    blender_parser = subparsers.add_parser("blender", help="Blender scene inspection and export commands.")
    blender_subparsers = blender_parser.add_subparsers(dest="blender_command", required=True)
    blender_cli.add_blender_export_parser(blender_subparsers)
    blender_cli.add_blender_inspect_parser(blender_subparsers)
    return blender_parser


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(prog="materials-processor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_blender_parser(subparsers)
    _add_runtime_parser(subparsers)
    return parser


def _validate_blender_runtime(args) -> dict:
    from materials_processor.dcc.blender.runtime import (
        resolve_blender_runtime,
        validate_blender_material_smoke,
        validate_blender_runtime,
    )

    runtime = resolve_blender_runtime(
        version=args.blender_version,
        root=args.blender_root,
        blender_exe=args.blender_exe,
    )
    package_src = args.package_src or _default_package_src()
    validated = validate_blender_runtime(runtime=runtime, package_src=package_src, timeout=args.timeout)
    result = {
        "dcc": "blender",
        "root": str(validated.root),
        "blender_exe": str(validated.blender_exe),
        "version": validated.version,
        "python_version": validated.python_version,
        "api_version": validated.api_version,
    }
    if args.material_smoke:
        result["material_smoke"] = validate_blender_material_smoke(
            runtime=validated,
            package_src=package_src,
            timeout=args.timeout,
        )
    return result


def _validate_maya_runtime(args) -> dict:
    from materials_processor.dcc.maya.runtime import (
        resolve_maya_runtime,
        validate_maya_material_smoke,
        validate_maya_runtime,
    )

    runtime = resolve_maya_runtime(version=args.maya_version, root=args.maya_root)
    package_src = args.package_src or _default_package_src()
    validated = validate_maya_runtime(runtime=runtime, package_src=package_src, timeout=args.timeout)
    result = {
        "dcc": "maya",
        "root": str(validated.root),
        "maya_exe": str(validated.maya_exe),
        "mayapy_exe": str(validated.mayapy_exe),
        "version": validated.version,
        "api_version": validated.api_version,
    }
    if args.material_smoke:
        result["material_smoke"] = validate_maya_material_smoke(
            runtime=validated,
            package_src=package_src,
            timeout=args.timeout,
        )
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the top-level command line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "blender":
            if args.blender_command == "export-usd":
                _print_json(blender_cli.run_export_from_args(args))
                return 0
            if args.blender_command == "inspect":
                _print_json(blender_cli.run_inspect_from_args(args))
                return 0

        if args.command == "runtime" and args.runtime_command == "validate":
            if args.dcc == "blender":
                _print_json(_validate_blender_runtime(args))
                return 0
            if args.dcc == "maya":
                _print_json(_validate_maya_runtime(args))
                return 0

        parser.error("Unsupported command.")
        return 2
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
