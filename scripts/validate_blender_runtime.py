"""Validate that Materials Processor can load in Blender headless mode."""

from __future__ import annotations

import argparse
from pathlib import Path

from materials_processor.dcc.blender.runtime import (
    resolve_blender_runtime,
    validate_blender_material_smoke,
    validate_blender_runtime,
)


def main() -> int:
    """Run Blender runtime validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Blender version used for default install discovery.")
    parser.add_argument("--root", help="Blender installation root.")
    parser.add_argument("--exe", help="Direct path to blender.exe.")
    parser.add_argument("--src", default=str(Path(__file__).resolve().parents[1] / "src"), help="Package src path.")
    parser.add_argument("--timeout", default=120, type=int, help="Validation timeout in seconds.")
    parser.add_argument(
        "--smoke-material",
        action="store_true",
        help="Also run a tiny traversal/standardization/recreation smoke test inside Blender.",
    )
    args = parser.parse_args()

    runtime = resolve_blender_runtime(version=args.version, root=args.root, blender_exe=args.exe)
    validated = validate_blender_runtime(runtime=runtime, package_src=args.src, timeout=args.timeout)
    print(
        "Blender "
        f"{validated.version} runtime OK: {validated.blender_exe} "
        f"(Python {validated.python_version}, API {validated.api_version})"
    )

    if args.smoke_material:
        result = validate_blender_material_smoke(runtime=validated, package_src=args.src, timeout=args.timeout)
        print(
            "Blender material smoke OK: "
            f"{result['node_count']} standardized node(s), "
            f"{result['output_count']} output connection(s)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
