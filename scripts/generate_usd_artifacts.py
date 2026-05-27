"""Generate .usd files from the bundled Houdini JSON fixtures.

Runs every valid fixture → renderer combination and writes each resulting
USD stage to an output directory (default: ``usd_artifacts/``).
"""

import argparse
import contextlib
import io as stdlib_io
import sys
from importlib import resources
from pathlib import Path

from pxr import Usd

from materials_processor import io as material_io
from materials_processor.standardizer import NodeStandardizer
from materials_processor.usd.recreator import USDMaterialRecreator

# ---------------------------------------------------------------------------
# Conversion matrix – mirrors the parametrize table in test_usd_json_conversion.py
# (xfail cases are intentionally omitted)
# ---------------------------------------------------------------------------
CONVERSIONS = [
    dict(
        label="houdini-mtlx-to-usd-mtlx",
        material_name="mtlxmaterial_full",
        material_type="mtlx",
        traversed_nodes_file="houdini_mtlx_full_traversed_nodes.json",
        output_nodes_file="houdini_mtlx_full_output_nodes.json",
        target_renderer="mtlx",
    ),
    dict(
        label="houdini-mtlx-to-usd-arnold",
        material_name="mtlxmaterial_full",
        material_type="mtlx",
        traversed_nodes_file="houdini_mtlx_full_traversed_nodes.json",
        output_nodes_file="houdini_mtlx_full_output_nodes.json",
        target_renderer="arnold",
    ),
    dict(
        label="houdini-mtlx-to-usd-redshift",
        material_name="mtlxmaterial_full",
        material_type="mtlx",
        traversed_nodes_file="houdini_mtlx_full_traversed_nodes.json",
        output_nodes_file="houdini_mtlx_full_output_nodes.json",
        target_renderer="rs_usd_material_builder",
    ),
    dict(
        label="houdini-arnold-to-usd-arnold",
        material_name="arnold_materialbuilder_full",
        material_type="arnold",
        traversed_nodes_file="houdini_arnold_full_traversed_nodes.json",
        output_nodes_file="houdini_arnold_full_output_nodes.json",
        target_renderer="arnold",
    ),
    dict(
        label="houdini-arnold-to-usd-redshift",
        material_name="arnold_materialbuilder_full",
        material_type="arnold",
        traversed_nodes_file="houdini_arnold_full_traversed_nodes.json",
        output_nodes_file="houdini_arnold_full_output_nodes.json",
        target_renderer="rs_usd_material_builder",
    ),
]


def _convert(conv: dict, out_dir: Path) -> Path:
    fixture_root = resources.files("materials_processor.fixtures")

    traversed_nodes = material_io.load_node_tree_json(fixture_root / conv["traversed_nodes_file"])
    output_nodes = material_io.load_node_tree_json(fixture_root / conv["output_nodes_file"])

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        nodeinfo_list, output_connections = NodeStandardizer(
            traversed_nodes_dict=traversed_nodes,
            output_nodes_dict=output_nodes,
            material_type=conv["material_type"],
            source_type="hou_vop_nodes",
        ).run()

    out_path = out_dir / f"{conv['label']}.usd"
    stage = Usd.Stage.CreateNew(str(out_path))

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        USDMaterialRecreator(
            stage=stage,
            material_name=conv["material_name"],
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
            target_renderer=conv["target_renderer"],
        )

    stage.Save()
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default="usd_artifacts",
        help="Directory to write .usd files into (default: usd_artifacts/)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    failed = []
    for conv in CONVERSIONS:
        try:
            out_path = _convert(conv, out_dir)
            print(f"  ok  {out_path}")
        except Exception as exc:
            print(f"  FAIL  {conv['label']}: {exc}", file=sys.stderr)
            failed.append(conv["label"])

    if failed:
        print(f"\n{len(failed)} conversion(s) failed.", file=sys.stderr)
        sys.exit(1)

    print(f"\nAll {len(CONVERSIONS)} conversions written to '{out_dir}/'.")


if __name__ == "__main__":
    main()
