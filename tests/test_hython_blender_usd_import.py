"""Validate that Houdini Solaris can load Blender-exported USD materials."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from materials_processor.core.graph import MaterialGraph, NodeInfo, OutputConnection
from materials_processor.dcc.blender.cli import build_usd_material_files
from materials_processor.dcc.houdini.runtime import resolve_hython


JSON_START = "===MATERIALS_PROCESSOR_SOLARIS_JSON_START==="
JSON_END = "===MATERIALS_PROCESSOR_SOLARIS_JSON_END==="


def _blender_graph_payload() -> dict[str, object]:
    """Return the smallest graph shape emitted by the Blender material exporter."""
    material_name = "Solaris Material"
    graph = MaterialGraph(
        material_name=material_name,
        material_path=f"/mat/{material_name}",
        nodeinfo_list=[
            NodeInfo(
                node_type="GENERIC::standard_surface",
                node_name="Principled BSDF",
                node_path=f"/mat/{material_name}/Principled BSDF",
                parameters=[],
                connection_info={},
                children_list=[],
            )
        ],
        output_connections={
            "GENERIC::output_surface": OutputConnection(
                node_name="Material Output",
                node_path=f"/mat/{material_name}/Material Output",
                connected_node_name="Principled BSDF",
                connected_node_path=f"/mat/{material_name}/Principled BSDF",
                connected_input_index=0,
                connected_input_name="Surface",
                connected_output_name="surface",
            )
        },
    )
    return {
        "scene": "C:/scenes/solaris_validation.blend",
        "material_count": 1,
        "node_material_count": 1,
        "graphs": [
            {
                "material_name": graph.material_name,
                "material_path": graph.material_path,
                "nodeinfo_list": [
                    {
                        "node_type": graph.nodeinfo_list[0].node_type,
                        "node_name": graph.nodeinfo_list[0].node_name,
                        "node_path": graph.nodeinfo_list[0].node_path,
                        "parameters": [],
                        "connection_info": {},
                        "children_list": [],
                        "is_output_node": False,
                        "output_type": None,
                        "position": None,
                    }
                ],
                "output_connections": {
                    key: value.to_dict() for key, value in graph.output_connections.items()
                },
            }
        ],
        "read_failures": [],
        "unsupported_nodes": {},
        "missing_texture_paths": [],
    }


def _load_in_solaris(hython: str, usd_path: Path, material_path: str, shader_path: str) -> dict[str, object]:
    """Cook a Solaris sublayer LOP and return its loaded USD material details."""
    script = "\n".join(
        [
            "import json",
            "import hou",
            f"usd_path = {str(usd_path)!r}",
            f"material_path = {material_path!r}",
            f"shader_path = {shader_path!r}",
            "sublayer = hou.node('/stage').createNode('sublayer', 'materials_processor_blender_usd')",
            "sublayer.parm('filepath1').set(usd_path)",
            "stage = sublayer.stage()",
            "material = stage.GetPrimAtPath(material_path)",
            "shader = stage.GetPrimAtPath(shader_path)",
            "payload = {'material_is_valid': material.IsValid(), 'shader_is_valid': shader.IsValid(),",
            "           'shader_id': shader.GetAttribute('info:id').Get() if shader.IsValid() else None}",
            f"print({JSON_START!r})",
            "print(json.dumps(payload, sort_keys=True))",
            f"print({JSON_END!r})",
        ]
    )
    completed = subprocess.run(
        [hython, "-"],
        input=script,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        pytest.fail(f"Hython Solaris import failed with exit code {completed.returncode}\n{output}")
    try:
        return json.loads(output.split(JSON_START, 1)[1].split(JSON_END, 1)[0].strip())
    except (IndexError, json.JSONDecodeError) as exc:
        pytest.fail(f"Hython Solaris import did not return its JSON payload\n{output}\n{exc}")


@pytest.mark.hython
@pytest.mark.parametrize(
    ("target", "expected_shader_id"),
    [
        pytest.param("mtlx", "ND_standard_surface_surfaceshader", id="materialx"),
        pytest.param("openpbr", "ND_open_pbr_surface_surfaceshader", id="openpbr"),
    ],
)
def test_hython_solaris_loads_blender_exported_material_usd(tmp_path, target, expected_shader_id):
    """Ensure Blender material USD can be loaded and cooked by Houdini Solaris."""
    hython = resolve_hython()
    if not hython:
        pytest.skip("Hython is not available")
    report = build_usd_material_files(_blender_graph_payload(), tmp_path, targets=(target,))
    usd_path = Path(report["usd_files"][target]["path"])
    material_path = "/materials/Solaris_Material"
    loaded = _load_in_solaris(hython, usd_path, material_path, f"{material_path}/Principled_BSDF")
    assert loaded == {
        "material_is_valid": True,
        "shader_is_valid": True,
        "shader_id": expected_shader_id,
    }
