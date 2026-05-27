import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from materials_processor import io as material_io


ROOT = Path(__file__).resolve().parents[1]
HIP_FILE = ROOT / "examples" / "hip" / "example_file_v001.hip"
SRC_DIR = ROOT / "src"
DEFAULT_HYTHON = Path(r"C:\Program Files\Side Effects Software\Houdini 21.0.631\bin\hython.exe")
JSON_START = "===MATERIALS_PROCESSOR_HYTHON_JSON_START==="
JSON_END = "===MATERIALS_PROCESSOR_HYTHON_JSON_END==="

MATERIAL_CASES = {
    "/mat/arnold_materialbuilder_full": {
        "material_type": "arnold",
        "standardized_output_keys": ["GENERIC::output_displacement", "GENERIC::output_surface"],
    },
    "/mat/arnold_materialbuilder_basic": {
        "material_type": "arnold",
        "standardized_output_keys": ["GENERIC::output_surface"],
    },
    "/mat/mtlxmaterial_full": {
        "material_type": "mtlx",
        "standardized_output_keys": ["GENERIC::output_displacement", "GENERIC::output_surface"],
    },
    "/mat/mtlxmaterial_basic": {
        "material_type": "mtlx",
        "standardized_output_keys": ["GENERIC::output_displacement", "GENERIC::output_surface"],
    },
    "/mat/principledshader": {
        "material_type": "principledshader",
        "standardized_output_keys": ["GENERIC::output_displacement", "GENERIC::output_surface"],
    },
}

SNAPSHOT_CASES = {
    "/mat/arnold_materialbuilder_full": {
        "traversed": "houdini_arnold_full_traversed_nodes.json",
        "outputs": "houdini_arnold_full_output_nodes.json",
        "round_positions": False,
    },
    "/mat/mtlxmaterial_full": {
        "traversed": "houdini_mtlx_full_traversed_nodes.json",
        "outputs": "houdini_mtlx_full_output_nodes.json",
        "round_positions": True,
    },
    "/mat/principledshader": {
        "traversed": "houdini_principled_to_mtlx_traversed_nodes.json",
        "outputs": "houdini_principled_to_mtlx_output_nodes.json",
        "round_positions": False,
    },
}


def _resolve_hython():
    env_hython = os.environ.get("MATERIALS_PROCESSOR_HYTHON")
    if env_hython:
        path = Path(env_hython)
        if path.is_file():
            return str(path)

    path_hython = shutil.which("hython")
    if path_hython:
        return path_hython

    hfs = os.environ.get("HFS")
    if hfs:
        for name in ("hython.exe", "hython"):
            path = Path(hfs) / "bin" / name
            if path.is_file():
                return str(path)

    if DEFAULT_HYTHON.is_file():
        return str(DEFAULT_HYTHON)

    return None


def _hython_script():
    material_paths = json.dumps(list(MATERIAL_CASES))
    return f"""
import contextlib
import io
import json
import sys
from pathlib import Path

repo = Path({str(ROOT)!r})
sys.path.insert(0, str(repo / "src"))

import hou
from materials_processor.houdini.traverser import NodeTraverser, get_material_type
from materials_processor.standardizer import NodeStandardizer

hou.hipFile.load({str(HIP_FILE)!r}, suppress_save_prompt=True, ignore_load_warnings=True)

results = {{}}
for node_path in {material_paths}:
    node = hou.node(node_path)
    if node is None:
        results[node_path] = {{"exists": False}}
        continue

    material_type = get_material_type(node)
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        traversed_nodes, output_nodes = NodeTraverser(node, material_type).run()
        serializable_traversed_nodes = json.loads(json.dumps(traversed_nodes, default=str))
        serializable_output_nodes = json.loads(json.dumps(output_nodes, default=str))
        nodeinfo_list, output_connections = NodeStandardizer(
            traversed_nodes_dict=traversed_nodes,
            output_nodes_dict=output_nodes,
            material_type=material_type,
            source_type="hou_vop_nodes",
        ).run()

    results[node_path] = {{
        "exists": True,
        "type_name": node.type().name(),
        "material_type": material_type,
        "traversed_nodes": serializable_traversed_nodes,
        "output_nodes": serializable_output_nodes,
        "standardized_node_count": len(nodeinfo_list),
        "standardized_output_keys": sorted(output_connections),
        "captured_stdout": stdout.getvalue().splitlines(),
    }}

print({JSON_START!r})
print(json.dumps(results, sort_keys=True))
print({JSON_END!r})
"""


@pytest.fixture(scope="module")
def hython_material_results():
    hython = _resolve_hython()
    if not hython:
        pytest.skip("hython is not available")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] += os.pathsep + os.environ["PYTHONPATH"]
    completed = subprocess.run(
        [hython, "-"],
        input=_hython_script(),
        text=True,
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        pytest.fail(f"hython exited with {completed.returncode}\n{output}")

    try:
        json_blob = output.split(JSON_START, 1)[1].split(JSON_END, 1)[0].strip()
    except IndexError:
        pytest.fail(f"hython output did not include JSON sentinels\n{output}")

    return json.loads(json_blob)


def _load_fixture(name):
    return material_io.load_node_tree_json(ROOT / "src" / "materials_processor" / "fixtures" / name)


def _round_node_positions(value):
    if isinstance(value, dict):
        return {
            key: [round(item, 3) for item in item_value]
            if key == "node_position" and isinstance(item_value, list)
            else _round_node_positions(item_value)
            for key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_round_node_positions(item) for item in value]
    return value


def _renumber_connection_keys(value):
    if isinstance(value, dict):
        if value and all(key.startswith("connection_") for key in value):
            connections = [_renumber_connection_keys(item) for item in value.values()]
            connections.sort(key=lambda item: json.dumps(item, sort_keys=True))
            return {f"connection_{index}": item for index, item in enumerate(connections)}
        return {key: _renumber_connection_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_renumber_connection_keys(item) for item in value]
    return value


def _normalize_mtlx_snapshot(value):
    return _renumber_connection_keys(_round_node_positions(value))


@pytest.mark.hython
@pytest.mark.parametrize("material_path", MATERIAL_CASES)
def test_hython_loads_and_standardizes_example_materials(hython_material_results, material_path):
    result = hython_material_results[material_path]
    expected = MATERIAL_CASES[material_path]

    assert result["exists"]
    assert result["material_type"] == expected["material_type"]
    assert result["traversed_nodes"]
    assert result["output_nodes"]
    assert result["standardized_node_count"] > 0
    assert result["standardized_output_keys"] == expected["standardized_output_keys"]


@pytest.mark.hython
@pytest.mark.parametrize("material_path", SNAPSHOT_CASES)
def test_hython_full_materials_match_checked_in_fixtures(hython_material_results, material_path):
    result = hython_material_results[material_path]
    snapshot = SNAPSHOT_CASES[material_path]

    expected_traversed = _load_fixture(snapshot["traversed"])
    expected_outputs = _load_fixture(snapshot["outputs"])
    actual_traversed = result["traversed_nodes"]
    actual_outputs = result["output_nodes"]

    if snapshot["round_positions"]:
        actual_traversed = _normalize_mtlx_snapshot(actual_traversed)
        expected_traversed = _normalize_mtlx_snapshot(expected_traversed)

    assert actual_traversed == expected_traversed
    assert actual_outputs == expected_outputs
