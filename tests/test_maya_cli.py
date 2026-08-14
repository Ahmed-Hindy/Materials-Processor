"""Tests for Maya command line export support."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pxr import Sdf, Usd

from materials_processor.core.graph import MaterialGraph, NodeInfo, OutputConnection
from materials_processor.dcc.maya import cli


def _graph_payload(material_name="Maya Cli Material"):
    graph = MaterialGraph(
        material_name=material_name,
        material_path=f"/maya/{material_name}",
        nodeinfo_list=[
            NodeInfo(
                node_type="GENERIC::standard_surface",
                node_name="mayaSurface",
                node_path=f"/maya/{material_name}/mayaSurface",
                parameters=[],
                connection_info={},
                children_list=[],
            )
        ],
        output_connections={
            "GENERIC::output_surface": OutputConnection(
                node_name=f"{material_name}SG",
                node_path=f"/maya/{material_name}/{material_name}SG",
                connected_node_name="mayaSurface",
                connected_node_path=f"/maya/{material_name}/mayaSurface",
                connected_input_index=0,
                connected_input_name="surfaceShader",
                connected_output_name="surface",
            )
        },
    )
    return {
        "scene": "C:/scenes/example.ma",
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
                "output_connections": {key: value.to_dict() for key, value in graph.output_connections.items()},
            }
        ],
        "read_failures": [],
        "unsupported_nodes": {},
        "missing_texture_paths": [],
    }


def _texture_graph_payload(texture_path):
    payload = _graph_payload("Maya Textured Material")
    payload["graphs"][0]["nodeinfo_list"][0]["node_type"] = "GENERIC::image"
    payload["graphs"][0]["nodeinfo_list"][0]["parameters"] = [
        {
            "generic_name": "filename",
            "generic_type": "string1",
            "direction": "input",
            "value": texture_path,
        }
    ]
    payload["missing_texture_paths"] = [{"material": "Maya Textured Material", "path": texture_path}]
    return payload


def test_export_maya_scene_to_usd_writes_graph_and_report(tmp_path, monkeypatch):
    scene = tmp_path / "scene.ma"
    scene.write_text("// fake maya scene", encoding="utf-8")

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(json.dumps(_graph_payload()), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_maya_material_graphs", fake_extract)

    report = cli.export_maya_scene_to_usd(scene, tmp_path / "export", targets=("mtlx",))

    usd_path = Path(report["usd_files"]["mtlx"]["path"])
    assert usd_path.name == "maya_scene_materialx.usda"
    assert usd_path.is_file()
    assert Path(report["graph_json"]).is_file()
    assert Path(report["report_json"]).is_file()

    stage = Usd.Stage.Open(str(usd_path))
    assert stage.GetPrimAtPath(Sdf.Path("/materials/Maya_Cli_Material")).IsValid()


def test_inspect_maya_scene_reports_without_writing_usd(tmp_path, monkeypatch):
    scene = tmp_path / "scene.ma"
    scene.write_text("// fake maya scene", encoding="utf-8")
    report_json = tmp_path / "inspect_report.json"

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(json.dumps(_graph_payload()), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_maya_material_graphs", fake_extract)

    report = cli.inspect_maya_scene(scene, report_json=report_json)

    assert report["graph_count"] == 1
    assert report["report_json"] == str(report_json.resolve())
    assert report_json.is_file()
    assert "usd_files" not in report


def test_inspect_maya_scene_writes_report_before_missing_texture_failure(tmp_path, monkeypatch):
    scene = tmp_path / "scene.ma"
    scene.write_text("// fake maya scene", encoding="utf-8")
    report_json = tmp_path / "inspect_report.json"

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(
            json.dumps(_texture_graph_payload("C:/missing/basecolor.png")), encoding="utf-8"
        )
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_maya_material_graphs", fake_extract)

    with pytest.raises(RuntimeError, match="Missing texture paths"):
        cli.inspect_maya_scene(scene, report_json=report_json, missing_textures="error")

    assert report_json.is_file()
    assert json.loads(report_json.read_text(encoding="utf-8"))["missing_texture_paths"]


def test_maya_cli_export_usd_dispatches_to_exporter(tmp_path, monkeypatch, capsys):
    scene = tmp_path / "scene.ma"
    scene.write_text("// fake maya scene", encoding="utf-8")

    monkeypatch.setattr(cli, "resolve_maya_runtime", lambda **kwargs: "runtime")
    monkeypatch.setattr(
        cli,
        "export_maya_scene_to_usd",
        lambda *args, **kwargs: {"scene": str(scene), "usd_files": {"mtlx": {"path": "maya_scene_materialx.usda"}}},
    )

    exit_code = cli.main(["export-usd", str(scene), "--target", "materialx", "--out-dir", str(tmp_path / "out")])

    assert exit_code == 0
    assert "maya_scene_materialx.usda" in capsys.readouterr().out


def test_maya_cli_reports_runtime_errors_without_traceback(tmp_path, monkeypatch, capsys):
    scene = tmp_path / "scene.ma"
    scene.write_text("// fake maya scene", encoding="utf-8")

    def fail(args):
        raise RuntimeError("unsupported nodes")

    monkeypatch.setattr(cli, "run_inspect_from_args", fail)

    exit_code = cli.main(["inspect", str(scene)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err == "error: unsupported nodes\n"
    assert "Traceback" not in captured.err
