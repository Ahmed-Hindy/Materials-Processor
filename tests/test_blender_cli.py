"""Tests for Blender command line export support."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pxr import Sdf, Usd

from materials_processor.core.graph import MaterialGraph, NodeInfo, OutputConnection
from materials_processor.dcc.blender import cli


def _graph_payload(material_name="Cli Material"):
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
        "scene": "C:/scenes/example.blend",
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
                    key: value.to_dict()
                    for key, value in graph.output_connections.items()
                },
            }
        ],
        "read_failures": [],
        "unsupported_nodes": {},
        "missing_texture_paths": [],
    }


def test_build_usd_material_files_writes_materialx_and_openpbr(tmp_path):
    report = cli.build_usd_material_files(_graph_payload(), tmp_path)

    materialx_path = Path(report["usd_files"]["mtlx"]["path"])
    openpbr_path = Path(report["usd_files"]["openpbr"]["path"])

    assert materialx_path.is_file()
    assert openpbr_path.is_file()
    assert report["graph_count"] == 1
    assert report["usd_files"]["mtlx"]["material_prim_count"] == 1
    assert report["usd_files"]["openpbr"]["material_prim_count"] == 1
    assert report["usd_files"]["mtlx"]["shader_ids"] == {"ND_standard_surface_surfaceshader": 1}
    assert report["usd_files"]["openpbr"]["shader_ids"] == {"ND_open_pbr_surface_surfaceshader": 1}

    materialx_stage = Usd.Stage.Open(str(materialx_path))
    openpbr_stage = Usd.Stage.Open(str(openpbr_path))

    assert materialx_stage.GetPrimAtPath(Sdf.Path("/materials/Cli_Material")).IsValid()
    assert openpbr_stage.GetPrimAtPath(Sdf.Path("/materials/Cli_Material")).IsValid()


def test_export_blender_scene_to_usd_writes_graph_and_report(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(json.dumps(_graph_payload()), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_blender_material_graphs", fake_extract)

    report = cli.export_blender_scene_to_usd(scene, tmp_path / "export", targets=("mtlx",))

    assert Path(report["graph_json"]).is_file()
    assert Path(report["report_json"]).is_file()
    assert set(report["usd_files"]) == {"mtlx"}
    assert Path(report["usd_files"]["mtlx"]["path"]).is_file()


def test_build_usd_material_files_honors_single_target_alias(tmp_path):
    report = cli.build_usd_material_files(_graph_payload(), tmp_path, targets=("materialx",))

    assert set(report["usd_files"]) == {"mtlx"}
    assert Path(report["usd_files"]["mtlx"]["path"]).name == "blender_scene_materialx.usda"
    assert not (tmp_path / "blender_scene_openpbr.usda").exists()


def test_blender_cli_export_usd_dispatches_to_exporter(tmp_path, monkeypatch, capsys):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    captured = {}

    monkeypatch.setattr(cli, "resolve_blender_runtime", lambda **kwargs: "runtime")

    def fake_export(scene_path, out_dir, **kwargs):
        captured["scene_path"] = scene_path
        captured["out_dir"] = out_dir
        captured["kwargs"] = kwargs
        return {
            "output_dir": str(out_dir),
            "usd_files": {
                "mtlx": {"path": str(Path(out_dir) / "blender_scene_materialx.usda")},
                "openpbr": {"path": str(Path(out_dir) / "blender_scene_openpbr.usda")},
            },
        }

    monkeypatch.setattr(cli, "export_blender_scene_to_usd", fake_export)

    exit_code = cli.main([
        "export-usd",
        str(scene),
        "--out-dir",
        str(tmp_path / "out"),
        "--target",
        "materialx",
        "--target",
        "openpbr",
        "--timeout",
        "7",
    ])

    assert exit_code == 0
    assert captured["scene_path"] == str(scene)
    assert captured["kwargs"]["runtime"] == "runtime"
    assert captured["kwargs"]["targets"] == ("mtlx", "openpbr")
    assert captured["kwargs"]["timeout"] == 7
    assert "blender_scene_openpbr.usda" in capsys.readouterr().out


def test_blender_cli_targets_all_expands_without_duplicates():
    assert cli._targets_from_args(["materialx", "all", "mtlx"]) == ("mtlx", "openpbr")


def test_blender_cli_targets_default_to_all():
    assert cli._targets_from_args([]) == ("mtlx", "openpbr")
