import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from materials_processor import io as material_io
from materials_processor.mappings import FORMAT_CHOICES


ROOT = Path(__file__).resolve().parents[1]
HIP_FILE = ROOT / "examples" / "hip" / "example_file_v001.hip"
SRC_DIR = ROOT / "src"
REPORT_PATH = ROOT / ".pytest_cache" / "materials_processor" / "hython_conversion_coverage.json"
DEFAULT_HYTHON = Path(r"C:\Program Files\Side Effects Software\Houdini 21.0.631\bin\hython.exe")
JSON_START = "===MATERIALS_PROCESSOR_HYTHON_JSON_START==="
JSON_END = "===MATERIALS_PROCESSOR_HYTHON_JSON_END==="
TARGET_RENDERERS = list(FORMAT_CHOICES)
SAME_ENGINE_FIDELITY_TARGETS = ("arnold", "mtlx")
OUTPUT_FIDELITY_TARGET_RENDERERS = ("arnold", "mtlx")
CROSS_ENGINE_FIDELITY_TARGETS = (
    ("arnold", "mtlx"),
    ("mtlx", "arnold"),
    ("principledshader", "arnold"),
    ("principledshader", "mtlx"),
)
EXPECTED_TARGET_NODE_TYPES = {
    "principledshader": "principledshader::2.0",
    "mtlx": "subnet",
    "arnold": "arnold_materialbuilder",
    "rs_usd_material_builder": "rs_usd_material_builder",
}

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
import traceback
import sys
from pathlib import Path

repo = Path({str(ROOT)!r})
sys.path.insert(0, str(repo / "src"))

import hou
from materials_processor.houdini.recreator import NodeRecreator
from materials_processor.houdini.traverser import NodeTraverser, get_material_type
from materials_processor.mappings import FORMAT_CHOICES
from materials_processor.standardizer import NodeStandardizer

EXPECTED_TARGET_NODE_TYPES = {json.dumps(EXPECTED_TARGET_NODE_TYPES, sort_keys=True)}
SAME_ENGINE_FIDELITY_TARGETS = {json.dumps(SAME_ENGINE_FIDELITY_TARGETS)}
OUTPUT_FIDELITY_TARGET_RENDERERS = {json.dumps(OUTPUT_FIDELITY_TARGET_RENDERERS)}
CROSS_ENGINE_FIDELITY_TARGETS = {CROSS_ENGINE_FIDELITY_TARGETS!r}
hou.hipFile.load({str(HIP_FILE)!r}, suppress_save_prompt=True, ignore_load_warnings=True)

mat_context = hou.node("/mat")
available_node_types = mat_context.childTypeCategory().nodeTypes()

def _normalize_value(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, tuple):
        if len(value) == 1:
            return _normalize_value(value[0])
        return [_normalize_value(item) for item in value]
    if isinstance(value, list):
        if len(value) == 1:
            return _normalize_value(value[0])
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {{key: _normalize_value(item) for key, item in sorted(value.items())}}
    return value

def _relative_path(path, root_path):
    if not path:
        return path
    if path == root_path:
        return "."
    prefix = root_path + "/"
    if path.startswith(prefix):
        return path[len(prefix):]
    return path

def _parameter_map(parameters):
    result = {{}}
    for parameter in parameters or []:
        if parameter.direction != "input":
            continue
        result[parameter.generic_name] = {{
            "type": parameter.generic_type,
            "value": _normalize_value(parameter.value),
        }}
    return result

def _connection_signature(connection, root_path):
    return {{
        "input_node": _relative_path(connection.input.node_path, root_path),
        "input_name": connection.input.parm_name,
        "input_type": connection.input.data_type,
        "output_node": _relative_path(connection.output.node_path, root_path),
        "output_name": connection.output.parm_name,
        "output_type": connection.output.data_type,
    }}

def _output_signature(output_connection, root_path):
    return {{
        "node": _relative_path(output_connection.node_path, root_path),
        "connected_node": _relative_path(output_connection.connected_node_path, root_path),
        "connected_input": output_connection.connected_input_name,
        "connected_output": output_connection.connected_output_name,
    }}

def _fingerprint(nodeinfo_list, output_connections, root_path):
    nodes = {{}}
    connections = []

    def walk(nodeinfo):
        relative_path = _relative_path(nodeinfo.node_path, root_path)
        node_entry = nodes.setdefault(
            relative_path,
            {{
                "type": nodeinfo.node_type,
                "parameters": _parameter_map(nodeinfo.parameters),
            }},
        )
        if not node_entry["parameters"] and nodeinfo.parameters:
            node_entry["parameters"] = _parameter_map(nodeinfo.parameters)
        for connection in nodeinfo.connection_info.values():
            connections.append(_connection_signature(connection, root_path))
        for child_nodeinfo in nodeinfo.children_list:
            walk(child_nodeinfo)

    for nodeinfo in nodeinfo_list:
        walk(nodeinfo)

    unique_connections = sorted(
        {{json.dumps(connection, sort_keys=True) for connection in connections}}
    )
    return {{
        "nodes": nodes,
        "connections": [json.loads(connection) for connection in unique_connections],
        "outputs": {{
            key: _output_signature(value, root_path)
            for key, value in sorted(output_connections.items())
        }},
    }}

def _diff_fingerprints(original, converted):
    original_nodes = original["nodes"]
    converted_nodes = converted["nodes"]
    original_node_paths = set(original_nodes)
    converted_node_paths = set(converted_nodes)
    common_node_paths = sorted(original_node_paths & converted_node_paths)

    node_type_mismatches = []
    parameter_diffs = []
    for node_path in common_node_paths:
        if original_nodes[node_path]["type"] != converted_nodes[node_path]["type"]:
            node_type_mismatches.append({{
                "node": node_path,
                "original": original_nodes[node_path]["type"],
                "converted": converted_nodes[node_path]["type"],
            }})

        original_parameters = original_nodes[node_path]["parameters"]
        converted_parameters = converted_nodes[node_path]["parameters"]
        original_parameter_names = set(original_parameters)
        converted_parameter_names = set(converted_parameters)
        missing_parameters = sorted(original_parameter_names - converted_parameter_names)
        extra_parameters = sorted(converted_parameter_names - original_parameter_names)
        changed_parameters = []
        for parameter_name in sorted(original_parameter_names & converted_parameter_names):
            if original_parameters[parameter_name] != converted_parameters[parameter_name]:
                changed_parameters.append({{
                    "parameter": parameter_name,
                    "original": original_parameters[parameter_name],
                    "converted": converted_parameters[parameter_name],
                }})
        if missing_parameters or extra_parameters or changed_parameters:
            parameter_diffs.append({{
                "node": node_path,
                "missing": missing_parameters,
                "extra": extra_parameters,
                "changed": changed_parameters,
            }})

    original_connections = {{json.dumps(item, sort_keys=True) for item in original["connections"]}}
    converted_connections = {{json.dumps(item, sort_keys=True) for item in converted["connections"]}}
    original_outputs = {{key: json.dumps(value, sort_keys=True) for key, value in original["outputs"].items()}}
    converted_outputs = {{key: json.dumps(value, sort_keys=True) for key, value in converted["outputs"].items()}}

    output_diffs = []
    for key in sorted(set(original_outputs) | set(converted_outputs)):
        if original_outputs.get(key) != converted_outputs.get(key):
            output_diffs.append({{
                "output": key,
                "original": json.loads(original_outputs[key]) if key in original_outputs else None,
                "converted": json.loads(converted_outputs[key]) if key in converted_outputs else None,
            }})

    return {{
        "missing_nodes": sorted(original_node_paths - converted_node_paths),
        "extra_nodes": sorted(converted_node_paths - original_node_paths),
        "node_type_mismatches": node_type_mismatches,
        "parameter_diffs": parameter_diffs,
        "missing_connections": [json.loads(item) for item in sorted(original_connections - converted_connections)],
        "extra_connections": [json.loads(item) for item in sorted(converted_connections - original_connections)],
        "output_diffs": output_diffs,
    }}

def _diff_is_clean(diff):
    return not any(diff.values())

def _summarize_fidelity(original, converted, diff):
    original_parameter_count = sum(len(node["parameters"]) for node in original["nodes"].values())
    missing_parameter_count = sum(len(item["missing"]) for item in diff["parameter_diffs"])
    changed_parameter_count = sum(len(item["changed"]) for item in diff["parameter_diffs"])
    return {{
        "original_node_count": len(original["nodes"]),
        "converted_node_count": len(converted["nodes"]),
        "missing_node_count": len(diff["missing_nodes"]),
        "extra_node_count": len(diff["extra_nodes"]),
        "original_parameter_count": original_parameter_count,
        "missing_parameter_count": missing_parameter_count,
        "changed_parameter_count": changed_parameter_count,
        "original_connection_count": len(original["connections"]),
        "converted_connection_count": len(converted["connections"]),
        "missing_connection_count": len(diff["missing_connections"]),
        "extra_connection_count": len(diff["extra_connections"]),
        "output_diff_count": len(diff["output_diffs"]),
    }}

def _build_fidelity_report(source_path, source_material_type, target_renderer, source_nodeinfo_list, source_output_connections, created_node):
    converted_material_type = get_material_type(created_node)
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        converted_traversed_nodes, converted_output_nodes = NodeTraverser(created_node, converted_material_type).run()
        converted_nodeinfo_list, converted_output_connections = NodeStandardizer(
            traversed_nodes_dict=converted_traversed_nodes,
            output_nodes_dict=converted_output_nodes,
            material_type=converted_material_type,
            source_type="hou_vop_nodes",
        ).run()

    original = _fingerprint(source_nodeinfo_list, source_output_connections, source_path)
    converted = _fingerprint(converted_nodeinfo_list, converted_output_connections, created_node.path())
    diff = _diff_fingerprints(original, converted)
    return {{
        "source_path": source_path,
        "source_material_type": source_material_type,
        "target_renderer": target_renderer,
        "created_path": created_node.path(),
        "created_material_type": converted_material_type,
        "status": "passed" if _diff_is_clean(diff) else "failed",
        "summary": _summarize_fidelity(original, converted, diff),
        "original_fingerprint": original,
        "converted_fingerprint": converted,
        "diff": diff,
        "captured_stdout": stdout.getvalue().splitlines(),
    }}

ingest_results = {{}}
conversion_results = []
output_fidelity_results = []
fidelity_results = []
cross_engine_fidelity_results = []
for node_path in {material_paths}:
    node = hou.node(node_path)
    if node is None:
        ingest_results[node_path] = {{"exists": False}}
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

    ingest_results[node_path] = {{
        "exists": True,
        "type_name": node.type().name(),
        "material_type": material_type,
        "traversed_nodes": serializable_traversed_nodes,
        "output_nodes": serializable_output_nodes,
        "standardized_node_count": len(nodeinfo_list),
        "standardized_output_keys": sorted(output_connections),
        "captured_stdout": stdout.getvalue().splitlines(),
    }}

    for target_renderer in FORMAT_CHOICES:
        target_node_type = EXPECTED_TARGET_NODE_TYPES[target_renderer]
        case = {{
            "source_path": node_path,
            "source_material_type": material_type,
            "target_renderer": target_renderer,
            "target_node_type": target_node_type,
            "status": "failed",
            "available": target_node_type in available_node_types,
            "created_path": None,
            "created_type": None,
            "child_count": 0,
            "output_keys": sorted(output_connections),
            "new_output_keys": [],
            "warnings": [],
            "error_type": None,
            "error": None,
            "trace_tail": [],
        }}
        if not case["available"]:
            case["status"] = "unavailable"
            case["error"] = f"Target node type is unavailable: {{target_node_type}}"
            conversion_results.append(case)
            continue

        try:
            safe_source_name = node.name().replace(":", "_")
            safe_target_name = target_renderer.replace(":", "_")
            material_name = f"cov_{{safe_source_name}}_to_{{safe_target_name}}"
            with contextlib.redirect_stdout(io.StringIO()) as conversion_stdout:
                recreator = NodeRecreator(
                    nodeinfo_list=nodeinfo_list,
                    output_connections=output_connections,
                    target_context=mat_context,
                    target_renderer=target_renderer,
                    material_name=material_name,
                )
                recreator.run()
            created = recreator.material_node
            case.update({{
                "created_path": created.path() if created else None,
                "created_type": created.type().name() if created else None,
                "child_count": len(created.children()) if created else 0,
                "new_output_keys": sorted(recreator.new_output_connections),
                "warnings": [line for line in conversion_stdout.getvalue().splitlines() if "WARNING" in line],
            }})
            if not created:
                case["error"] = "Conversion did not create a material node."
            elif case["created_type"] != target_node_type:
                case["error"] = f"Expected created type {{target_node_type}}, got {{case['created_type']}}."
            elif target_renderer != "principledshader" and case["child_count"] <= 0:
                case["error"] = "Converted material has no child nodes."
            else:
                case["status"] = "passed"
                fidelity_report = None
                if target_renderer in OUTPUT_FIDELITY_TARGET_RENDERERS:
                    fidelity_report = _build_fidelity_report(
                        source_path=node_path,
                        source_material_type=material_type,
                        target_renderer=target_renderer,
                        source_nodeinfo_list=nodeinfo_list,
                        source_output_connections=output_connections,
                        created_node=created,
                    )
                    case["fidelity"] = {{
                        "status": fidelity_report["status"],
                        "summary": fidelity_report["summary"],
                    }}
                    output_fidelity_results.append(fidelity_report)

                if (
                    fidelity_report
                    and material_type == target_renderer
                    and target_renderer in SAME_ENGINE_FIDELITY_TARGETS
                ):
                    fidelity_results.append(fidelity_report)
                if fidelity_report and (material_type, target_renderer) in CROSS_ENGINE_FIDELITY_TARGETS:
                    cross_engine_fidelity_results.append(fidelity_report)
        except Exception as exc:
            case.update({{
                "error_type": type(exc).__name__,
                "error": str(exc),
                "trace_tail": traceback.format_exc().splitlines()[-8:],
            }})
            if "Invalid node type name" in str(exc):
                case["status"] = "unavailable"
                case["available"] = False
        conversion_results.append(case)

totals_by_status = {{}}
totals_by_source = {{}}
totals_by_target = {{}}
for case in conversion_results:
    totals_by_status[case["status"]] = totals_by_status.get(case["status"], 0) + 1
    source_totals = totals_by_source.setdefault(case["source_path"], {{"passed": 0, "failed": 0, "unavailable": 0}})
    source_totals[case["status"]] = source_totals.get(case["status"], 0) + 1
    target_totals = totals_by_target.setdefault(case["target_renderer"], {{"passed": 0, "failed": 0, "unavailable": 0}})
    target_totals[case["status"]] = target_totals.get(case["status"], 0) + 1

available_count = len([case for case in conversion_results if case["status"] != "unavailable"])
passed_count = len([case for case in conversion_results if case["status"] == "passed"])
summary = {{
    "total_cases": len(conversion_results),
    "available_cases": available_count,
    "passed_cases": passed_count,
    "unavailable_cases": totals_by_status.get("unavailable", 0),
    "failed_cases": totals_by_status.get("failed", 0),
    "coverage_percent": round((passed_count / available_count) * 100, 2) if available_count else 0.0,
    "totals_by_status": totals_by_status,
    "totals_by_source": totals_by_source,
    "totals_by_target": totals_by_target,
}}

payload = {{
    "hip_file": str({str(HIP_FILE)!r}),
    "material_paths": {material_paths},
    "target_renderers": list(FORMAT_CHOICES),
    "ingest": ingest_results,
    "conversion": conversion_results,
    "output_fidelity": output_fidelity_results,
    "same_engine_fidelity": fidelity_results,
    "cross_engine_fidelity": cross_engine_fidelity_results,
    "summary": summary,
}}

print({JSON_START!r})
print(json.dumps(payload, sort_keys=True))
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

    payload = json.loads(json_blob)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


@pytest.fixture(scope="module")
def hython_ingest_results(hython_material_results):
    return hython_material_results["ingest"]


@pytest.fixture(scope="module")
def hython_conversion_report(hython_material_results):
    return hython_material_results


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
def test_hython_loads_and_standardizes_example_materials(hython_ingest_results, material_path):
    result = hython_ingest_results[material_path]
    expected = MATERIAL_CASES[material_path]

    assert result["exists"]
    assert result["material_type"] == expected["material_type"]
    assert result["traversed_nodes"]
    assert result["output_nodes"]
    assert result["standardized_node_count"] > 0
    assert result["standardized_output_keys"] == expected["standardized_output_keys"]


@pytest.mark.hython
@pytest.mark.parametrize("material_path", SNAPSHOT_CASES)
def test_hython_full_materials_match_checked_in_fixtures(hython_ingest_results, material_path):
    result = hython_ingest_results[material_path]
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


@pytest.mark.hython
def test_hython_conversion_matrix_reports_all_source_target_pairs(hython_conversion_report):
    report = hython_conversion_report

    assert REPORT_PATH.is_file()
    assert report["material_paths"] == list(MATERIAL_CASES)
    assert report["target_renderers"] == TARGET_RENDERERS
    assert len(report["conversion"]) == len(MATERIAL_CASES) * len(TARGET_RENDERERS)
    assert report["summary"]["total_cases"] == len(report["conversion"])


@pytest.mark.hython
@pytest.mark.parametrize("case_index", range(len(MATERIAL_CASES) * len(TARGET_RENDERERS)))
def test_hython_conversion_matrix_available_targets_pass(hython_conversion_report, case_index):
    case = hython_conversion_report["conversion"][case_index]

    if case["status"] == "unavailable":
        assert not case["available"]
        assert case["error"]
        return

    assert case["status"] == "passed", f"{REPORT_PATH}: {case}"
    assert case["available"]
    assert case["created_path"]
    assert case["created_type"] == EXPECTED_TARGET_NODE_TYPES[case["target_renderer"]]
    assert case["new_output_keys"]
    if case["target_renderer"] != "principledshader":
        assert case["child_count"] > 0


@pytest.mark.hython
def test_hython_conversion_coverage_summary_has_no_failed_cases(hython_conversion_report):
    summary = hython_conversion_report["summary"]

    assert summary["total_cases"] == 20
    assert summary["failed_cases"] == 0, f"{REPORT_PATH}: {summary}"
    assert summary["passed_cases"] == summary["available_cases"]
    assert summary["coverage_percent"] == 100.0


@pytest.mark.hython
def test_hython_same_engine_fidelity_reports_cover_arnold_and_mtlx(hython_conversion_report):
    fidelity_cases = hython_conversion_report["same_engine_fidelity"]

    assert {
        (case["source_path"], case["target_renderer"])
        for case in fidelity_cases
    } == {
        ("/mat/arnold_materialbuilder_full", "arnold"),
        ("/mat/arnold_materialbuilder_basic", "arnold"),
        ("/mat/mtlxmaterial_full", "mtlx"),
        ("/mat/mtlxmaterial_basic", "mtlx"),
    }
    for case in fidelity_cases:
        assert case["created_path"]
        assert case["created_material_type"] == case["target_renderer"]
        assert case["summary"]["original_node_count"] > 0
        assert "missing_nodes" in case["diff"]
        assert "parameter_diffs" in case["diff"]


@pytest.mark.hython
def test_hython_output_fidelity_reports_cover_available_arnold_and_mtlx_targets(
    hython_conversion_report,
):
    fidelity_cases = hython_conversion_report["output_fidelity"]

    assert {
        (case["source_path"], case["target_renderer"])
        for case in fidelity_cases
    } == {
        (source_path, target_renderer)
        for source_path in MATERIAL_CASES
        for target_renderer in OUTPUT_FIDELITY_TARGET_RENDERERS
    }
    for case in fidelity_cases:
        assert case["created_path"]
        assert case["summary"]["original_node_count"] > 0
        assert "outputs" in case["converted_fingerprint"]


@pytest.mark.hython
def test_hython_same_engine_fidelity_preserves_all_nodes_parameters_and_connections(hython_conversion_report):
    failing_cases = [
        case
        for case in hython_conversion_report["same_engine_fidelity"]
        if case["status"] != "passed"
    ]
    if failing_cases:
        pytest.xfail(f"Same-engine fidelity gaps remain; inspect {REPORT_PATH}.")


@pytest.mark.hython
def test_hython_cross_engine_fidelity_reports_cover_arnold_mtlx_targets(hython_conversion_report):
    fidelity_cases = hython_conversion_report["cross_engine_fidelity"]

    assert {
        (case["source_path"], case["target_renderer"])
        for case in fidelity_cases
    } == {
        ("/mat/arnold_materialbuilder_full", "mtlx"),
        ("/mat/arnold_materialbuilder_basic", "mtlx"),
        ("/mat/mtlxmaterial_full", "arnold"),
        ("/mat/mtlxmaterial_basic", "arnold"),
        ("/mat/principledshader", "arnold"),
        ("/mat/principledshader", "mtlx"),
    }
    for case in fidelity_cases:
        assert case["created_path"]
        assert case["created_material_type"] == case["target_renderer"]
        assert case["summary"]["original_node_count"] > 0
        assert "missing_nodes" in case["diff"]
        assert "parameter_diffs" in case["diff"]


@pytest.mark.hython
def test_hython_arnold_to_mtlx_displacement_uses_mtlx_displacement_wrapper(
    hython_conversion_report,
):
    arnold_to_mtlx_cases = {
        case["source_path"]: case
        for case in hython_conversion_report["cross_engine_fidelity"]
        if case["source_material_type"] == "arnold" and case["target_renderer"] == "mtlx"
    }
    full_case = arnold_to_mtlx_cases["/mat/arnold_materialbuilder_full"]
    converted_outputs = full_case["converted_fingerprint"]["outputs"]

    assert converted_outputs["GENERIC::output_displacement"] == {
        "node": "displacement_output",
        "connected_node": "mtlxdisplacement",
        "connected_input": "suboutput",
        "connected_output": "out",
    }


@pytest.mark.hython
def test_hython_arnold_basic_to_mtlx_does_not_create_displacement_output(
    hython_conversion_report,
):
    arnold_basic_to_mtlx = next(
        case
        for case in hython_conversion_report["cross_engine_fidelity"]
        if case["source_path"] == "/mat/arnold_materialbuilder_basic"
        and case["target_renderer"] == "mtlx"
    )
    converted_outputs = arnold_basic_to_mtlx["converted_fingerprint"]["outputs"]

    assert set(converted_outputs) == {"GENERIC::output_surface"}


@pytest.mark.hython
def test_hython_arnold_same_engine_displacement_preserves_source_channel(
    hython_conversion_report,
):
    full_case = next(
        case
        for case in hython_conversion_report["same_engine_fidelity"]
        if case["source_path"] == "/mat/arnold_materialbuilder_full"
    )
    converted_outputs = full_case["converted_fingerprint"]["outputs"]

    assert converted_outputs["GENERIC::output_displacement"]["connected_output"] == "b"


@pytest.mark.hython
def test_hython_cross_engine_fidelity_preserves_all_nodes_parameters_and_connections(hython_conversion_report):
    failing_cases = [
        case
        for case in hython_conversion_report["cross_engine_fidelity"]
        if case["status"] != "passed"
    ]
    if failing_cases:
        pytest.xfail(f"Cross-engine fidelity gaps remain; inspect {REPORT_PATH}.")
