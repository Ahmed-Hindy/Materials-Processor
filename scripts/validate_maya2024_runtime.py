"""Validate that Materials Processor can load in Maya 2024 mayapy."""

from __future__ import annotations

import argparse
from pathlib import Path

from materials_processor.dcc.maya.runtime import (
    resolve_maya_runtime,
    validate_maya_material_smoke,
    validate_maya_runtime,
)


def main() -> int:
    """Run Maya 2024 runtime validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Maya 2024 installation root.")
    parser.add_argument("--src", default=str(Path(__file__).resolve().parents[1] / "src"), help="Package src path.")
    parser.add_argument("--timeout", default=120, type=int, help="Validation timeout in seconds.")
    parser.add_argument(
        "--smoke-material",
        action="store_true",
        help="Also run a tiny traversal/standardization/recreation smoke test inside Maya.",
    )
    args = parser.parse_args()

    runtime = resolve_maya_runtime(version="2024", root=args.root)
    validated = validate_maya_runtime(runtime=runtime, package_src=args.src, timeout=args.timeout)
    print(f"Maya {validated.version} runtime OK: {validated.mayapy_exe} (API {validated.api_version})")

    if args.smoke_material:
        result = validate_maya_material_smoke(runtime=validated, package_src=args.src, timeout=args.timeout)
        print(
            "Maya material smoke OK: "
            f"{result['node_count']} standardized node(s), "
            f"{result['output_count']} output connection(s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
