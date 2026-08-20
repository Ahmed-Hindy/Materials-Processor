"""Tests for Blender command line export support."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pxr import Sdf, Usd, UsdShade

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


def _texture_graph_payload(texture_path):
    payload = _graph_payload("Textured Material")
    payload["graphs"][0]["nodeinfo_list"][0]["node_type"] = "GENERIC::image"
    payload["graphs"][0]["nodeinfo_list"][0]["parameters"] = [
        {
            "generic_name": "filename",
            "generic_type": "string1",
            "direction": "input",
            "value": texture_path,
        }
    ]
    payload["missing_texture_paths"] = [{"material": "Textured Material", "path": texture_path}]
    return payload


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


def test_export_blender_scene_to_usd_creates_explicit_graph_json_parent(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    graph_json = tmp_path / "nested" / "graphs" / "materials.json"

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(json.dumps(_graph_payload()), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_blender_material_graphs", fake_extract)

    report = cli.export_blender_scene_to_usd(
        scene,
        tmp_path / "export",
        targets=("mtlx",),
        graph_json=graph_json,
    )

    assert report["graph_json"] == str(graph_json.resolve())
    assert graph_json.is_file()


def test_export_blender_scene_to_usd_applies_texture_prefix_remap(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    texture_root = tmp_path / "textures"
    texture_root.mkdir()
    fixed_texture = texture_root / "basecolor.png"
    fixed_texture.write_text("fake image", encoding="utf-8")

    def fake_extract(scene_path, graph_json_path, **kwargs):
        payload = _texture_graph_payload(r"C:\PROJECT\textures\basecolor.png")
        Path(graph_json_path).write_text(json.dumps(payload), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_blender_material_graphs", fake_extract)

    report = cli.export_blender_scene_to_usd(
        scene,
        tmp_path / "export",
        targets=("mtlx",),
        remap_prefixes=((r"C:\PROJECT\textures", str(texture_root)),),
    )

    assert report["missing_texture_paths"] == []
    assert report["remapped_texture_paths"] == [
        {
            "material": "Textured Material",
            "original": r"C:\PROJECT\textures\basecolor.png",
            "remapped": str(fixed_texture),
        }
    ]


def test_export_blender_scene_to_usd_applies_texture_root_recursive_remap(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    nested_texture = tmp_path / "textures" / "asset" / "basecolor.png"
    nested_texture.parent.mkdir(parents=True)
    nested_texture.write_text("fake image", encoding="utf-8")

    def fake_extract(scene_path, graph_json_path, **kwargs):
        payload = _texture_graph_payload(r"C:\missing\basecolor.png")
        Path(graph_json_path).write_text(json.dumps(payload), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_blender_material_graphs", fake_extract)

    report = cli.export_blender_scene_to_usd(
        scene,
        tmp_path / "export",
        targets=("mtlx",),
        texture_root=tmp_path / "textures",
    )

    assert report["missing_texture_paths"] == []
    assert report["remapped_texture_paths"][0]["remapped"] == str(nested_texture)


def test_inspect_blender_scene_reports_without_writing_usd(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    report_json = tmp_path / "inspect_report.json"

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(json.dumps(_graph_payload()), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_blender_material_graphs", fake_extract)

    report = cli.inspect_blender_scene(scene, report_json=report_json)

    assert report["graph_count"] == 1
    assert report["report_json"] == str(report_json.resolve())
    assert report_json.is_file()
    assert "usd_files" not in report


def test_inspect_blender_scene_can_fail_on_unsupported_nodes(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    payload = _graph_payload()
    payload["unsupported_nodes"] = {"Mat": [{"node_name": "Group", "node_path": "/mat/Mat/Group"}]}

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(json.dumps(payload), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_blender_material_graphs", fake_extract)

    with pytest.raises(RuntimeError, match="Unsupported Blender nodes"):
        cli.inspect_blender_scene(scene, fail_on_unsupported=True)


def test_inspect_blender_scene_writes_report_before_missing_texture_failure(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    report_json = tmp_path / "inspect_report.json"

    def fake_extract(scene_path, graph_json_path, **kwargs):
        Path(graph_json_path).write_text(json.dumps(_texture_graph_payload(r"C:\missing\basecolor.png")), encoding="utf-8")
        return {"graph_count": 1}

    monkeypatch.setattr(cli, "extract_blender_material_graphs", fake_extract)

    with pytest.raises(RuntimeError, match="Missing texture paths"):
        cli.inspect_blender_scene(scene, report_json=report_json, missing_textures="error")

    assert report_json.is_file()
    assert json.loads(report_json.read_text(encoding="utf-8"))["missing_texture_paths"]


def test_build_usd_material_files_honors_single_target_alias(tmp_path):
    report = cli.build_usd_material_files(_graph_payload(), tmp_path, targets=("materialx",))

    assert set(report["usd_files"]) == {"mtlx"}
    assert Path(report["usd_files"]["mtlx"]["path"]).name == "blender_scene_materialx.usda"
    assert not (tmp_path / "blender_scene_openpbr.usda").exists()


def test_copy_native_materials_creates_material_only_usd(tmp_path):
    source_path = tmp_path / "native_scene.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    source_material = UsdShade.Material.Define(source_stage, Sdf.Path("/root/_materials/ComplexMaterial"))
    source_shader = UsdShade.Shader.Define(source_stage, Sdf.Path("/root/_materials/ComplexMaterial/Surface"))
    source_shader.CreateIdAttr("ND_standard_surface_surfaceshader")
    source_material.CreateSurfaceOutput("mtlx").ConnectToSource(source_shader.ConnectableAPI(), "out")
    source_stage.GetRootLayer().Save()

    result = cli._copy_native_materials(source_path, tmp_path / "native_materials.usda")
    copied_stage = Usd.Stage.Open(result["path"])
    copied_shader = copied_stage.GetPrimAtPath(Sdf.Path("/materials/ComplexMaterial/Surface"))

    assert result["material_prims"] == ["/materials/ComplexMaterial"]
    assert result["suspect_magenta_materials"] == []
    assert copied_stage.GetPrimAtPath(Sdf.Path("/materials/ComplexMaterial")).IsValid()
    assert copied_shader.GetAttribute("info:id").Get() == "ND_standard_surface_surfaceshader"


def test_copy_native_materials_reports_blender_magenta_materialx_fallback(tmp_path):
    source_path = tmp_path / "native_scene.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    source_material = UsdShade.Material.Define(source_stage, Sdf.Path("/root/_materials/UnsupportedGroup"))
    source_shader = UsdShade.Shader.Define(source_stage, Sdf.Path("/root/_materials/UnsupportedGroup/Surface"))
    source_shader.CreateIdAttr("ND_open_pbr_surface_surfaceshader")
    source_shader.CreateInput("base_color", Sdf.ValueTypeNames.Color3f).Set((1.0, 0.0, 1.0))
    source_material.CreateSurfaceOutput("mtlx").ConnectToSource(source_shader.ConnectableAPI(), "out")
    source_stage.GetRootLayer().Save()

    result = cli._copy_native_materials(source_path, tmp_path / "native_materials.usda")

    assert result["suspect_magenta_materials"] == ["/materials/UnsupportedGroup"]


def test_write_baked_usd_material_file_creates_texture_driven_material(tmp_path):
    maps = {
        "base_color": str(tmp_path / "base_color.png"),
        "metalness": str(tmp_path / "metalness.png"),
        "roughness": str(tmp_path / "roughness.png"),
        "normal": str(tmp_path / "normal.png"),
        "opacity": str(tmp_path / "opacity.png"),
        "emission_color": str(tmp_path / "emission_color.png"),
    }

    result = cli._write_baked_usd_material_file(
        [{"material": "Felt Fabric", "maps": maps}],
        tmp_path / "baked_materials.usda",
        "mtlx",
    )
    stage = Usd.Stage.Open(result["path"])
    surface = UsdShade.Shader(stage.GetPrimAtPath("/materials/Felt_Fabric/surface"))

    assert result["material_prims"] == ["/materials/Felt_Fabric"]
    material = stage.GetPrimAtPath("/materials/Felt_Fabric")
    assert material.GetAttribute("config:mtlx:version").Get() == "1.39"
    exported_usda = Path(result["path"]).read_text(encoding="utf-8")
    assert 'prepend apiSchemas = ["MaterialXConfigAPI"]' in exported_usda
    assert surface.GetIdAttr().Get() == "ND_standard_surface_surfaceshader"
    assert surface.GetInput("base").Get() == 1.0
    assert UsdShade.Material(stage.GetPrimAtPath("/materials/Felt_Fabric")).GetSurfaceOutput("kma").HasConnectedSource()
    assert surface.GetInput("base_color").HasConnectedSource()
    assert surface.GetInput("metalness").HasConnectedSource()
    assert surface.GetInput("specular_roughness").HasConnectedSource()
    assert surface.GetInput("normal").HasConnectedSource()
    assert surface.GetInput("opacity").HasConnectedSource()
    assert surface.GetInput("emission_color").HasConnectedSource()
    assert stage.GetPrimAtPath("/materials/Felt_Fabric/normal_image").GetAttribute("info:id").Get() == "ND_gltf_normalmap_vector3_1_0"
    assert not stage.GetPrimAtPath("/materials/Felt_Fabric/normalmap").IsValid()
    assert stage.GetPrimAtPath("/materials/Felt_Fabric/base_color_image").GetAttribute("inputs:file").GetColorSpace() == "lin_ap1"
    assert stage.GetPrimAtPath("/materials/Felt_Fabric/roughness_image").GetAttribute("inputs:file").GetColorSpace() == "raw"
    assert "\\" not in stage.GetPrimAtPath("/materials/Felt_Fabric/base_color_image").GetAttribute("inputs:file").Get().path

    openpbr_result = cli._write_baked_usd_material_file(
        [{"material": "Felt Fabric", "maps": maps}],
        tmp_path / "baked_openpbr_materials.usda",
        "openpbr",
    )
    openpbr_stage = Usd.Stage.Open(openpbr_result["path"])
    openpbr_surface = UsdShade.Shader(openpbr_stage.GetPrimAtPath("/materials/Felt_Fabric/surface"))
    assert openpbr_surface.GetInput("base_weight").Get() == 1.0
    assert UsdShade.Material(openpbr_stage.GetPrimAtPath("/materials/Felt_Fabric")).GetSurfaceOutput("kma").HasConnectedSource()


def test_write_baked_usd_material_file_uses_the_recorded_color_space(tmp_path):
    result = cli._write_baked_usd_material_file(
        [
            {
                "material": "Calibrated",
                "maps": {"base_color": str(tmp_path / "calibrated.exr")},
                "stream_color_space": "lin_rec709",
            }
        ],
        tmp_path / "calibrated.usda",
        "mtlx",
    )
    stage = Usd.Stage.Open(result["path"])

    assert stage.GetPrimAtPath("/materials/Calibrated/base_color_image").GetAttribute("inputs:file").GetColorSpace() == "lin_rec709"


def test_bake_script_reports_requested_materials_missing_from_scene(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", ("missing",), 1024, False)

    assert "material name was not found in the Blender scene" in code
    assert "available_material_names" in code
    assert code.index("bake_source_kind, bake_source, reason = active_bake_source(material)") < code.index("if not obj.data.uv_layers")


def test_bake_script_writes_unlinked_principled_values_as_texture_maps(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False)

    assert "def write_constant_map" in code
    assert "maps[map_name] = write_constant_map(material, map_name, source_input, stream_kind)" in code


def test_bake_script_writes_linear_colour_streams_without_gamma_compensation(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False)

    assert "ShaderNodeGamma" not in code
    assert "0.454545" not in code
    assert 'for link in list(output.inputs["Surface"].links):' in code
    assert '"baked_color_space": COLOR_SPACE' in code
    assert "def bake_group_stream" in code
    assert '"Utility - Raw"' in code


def test_bake_script_uses_tangent_space_normal_bake(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False)

    assert ("normal", "Normal", "normal") in cli.BAKE_STREAM_SPECS
    assert 'scene.render.bake.normal_space = "TANGENT"' in code
    assert 'bpy.ops.object.bake(type="NORMAL", use_clear=True, margin=16)' in code
    assert 'if stream_kind != "normal" and not source_input.is_linked:' in code


def test_bake_script_uses_explicit_group_pbr_stream_outputs(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False)

    assert "GROUP_BAKE_OUTPUT_NAMES" in code
    assert "'Color Bake'" in code
    assert "def bake_group_stream" in code
    assert 'return "group_streams", (shader, stream_outputs), None' in code
    assert "bake_group_stream(material, obj, group.name, map_name, output_socket_name, stream_kind)" in code


def test_bake_script_exposes_direct_internal_principled_group_streams(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False)

    assert 'return "group_principled", (shader, internal_shader.name), None' in code
    assert "def expose_group_principled_stream" in code
    assert 'group_tree.interface.new_socket(name=exposed_name, in_out="OUTPUT"' in code
    assert "def bake_group_principled_stream" in code
    assert "bake_group_principled_stream(" in code


def test_bake_script_reports_complex_group_closure_types(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False)

    assert "def group_closure_summary(group_node):" in code
    assert 'node.bl_idname == "ShaderNodeMixShader"' in code
    assert "complex group closure" in code


def test_bake_script_rejects_mixed_closures_from_the_pbr_route(tmp_path):
    code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False)

    rejection = 'return None, None, f"complex group closure ({closure_summary}) is not a portable PBR material"'
    assert rejection in code
    assert "fabric_lobes" not in code
    assert "bake_group_node_input_stream" not in code


def test_bake_script_supports_explicit_beauty_and_auto_modes(tmp_path):
    auto_code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False, "auto")
    beauty_code = cli._bake_materials_code(tmp_path / "scene.blend", tmp_path / "textures", None, 1024, False, "beauty")

    assert "BAKE_MODE = 'auto'" in auto_code
    assert 'if BAKE_MODE == "auto":' in auto_code
    assert "def bake_beauty(material, obj):" in auto_code
    assert 'bpy.ops.object.bake(type="COMBINED"' in beauty_code
    assert '"bake_mode": "beauty" if bake_source_kind == "beauty" else "pbr"' in beauty_code


def test_write_baked_usd_material_file_writes_beauty_as_unlit(tmp_path):
    result = cli._write_baked_usd_material_file(
        [{"material": "Toon", "maps": {"beauty": str(tmp_path / "toon.exr")}, "bake_mode": "beauty"}],
        tmp_path / "beauty.usda",
        "mtlx",
    )
    stage = Usd.Stage.Open(result["path"])
    surface = UsdShade.Shader(stage.GetPrimAtPath("/materials/Toon/surface"))

    assert surface.GetIdAttr().Get() == "ND_surface_unlit"
    assert surface.GetInput("emission_color").HasConnectedSource()
    assert stage.GetPrimAtPath("/materials/Toon/beauty_image").GetAttribute("inputs:file").GetColorSpace() == "lin_ap1"


def test_export_baked_blender_materials_writes_target_files(tmp_path, monkeypatch):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    baked_texture = tmp_path / "baked_textures" / "felt_base_color.png"
    baked_texture.parent.mkdir()
    baked_texture.write_bytes(b"fake")
    payload = {
        "scene": str(scene),
        "texture_dir": str(baked_texture.parent),
        "baked_materials": [
            {
                "material": "felt",
                "maps": {"base_color": str(baked_texture), "roughness": str(baked_texture), "normal": str(baked_texture)},
                "generated_uv": False,
            }
        ],
        "skipped_materials": [],
    }
    completed = SimpleNamespace(
        returncode=0,
        stdout=f"{cli.BAKED_MATERIAL_EXPORT_PREFIX}{json.dumps(payload)}\n",
        stderr="",
    )
    monkeypatch.setattr(cli, "_run_blender_python", lambda *args, **kwargs: completed)
    monkeypatch.setattr(cli, "resolve_blender_runtime", lambda **kwargs: "runtime")

    result = cli.export_baked_blender_materials(scene, tmp_path / "export", targets=("mtlx", "openpbr"))

    assert result["source"] == "blender-baked-materials"
    assert result["bake_mode"] == "pbr"
    assert set(result["usd_files"]) == {"mtlx", "openpbr"}
    assert Path(result["usd_files"]["mtlx"]["path"]).is_file()
    assert Path(result["usd_files"]["openpbr"]["path"]).is_file()


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
        "--native-materialx",
        "--bake-resolution",
        "2048",
        "--bake-color-space",
        "lin_rec709",
    ])

    assert exit_code == 0
    assert captured["scene_path"] == str(scene)
    assert captured["kwargs"]["runtime"] == "runtime"
    assert captured["kwargs"]["targets"] == ("mtlx", "openpbr")
    assert captured["kwargs"]["timeout"] == 7
    assert captured["kwargs"]["native_materialx"] is True
    assert captured["kwargs"]["bake_materials"] is None
    assert captured["kwargs"]["bake_resolution"] == 2048
    assert captured["kwargs"]["bake_color_space"] == "lin_rec709"
    assert captured["kwargs"]["bake_mode"] == "pbr"
    assert "blender_scene_openpbr.usda" in capsys.readouterr().out


def test_blender_cli_bake_without_a_material_selects_all(tmp_path, monkeypatch, capsys):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(cli, "resolve_blender_runtime", lambda **kwargs: "runtime")

    def fake_export(scene_path, out_dir, **kwargs):
        captured["kwargs"] = kwargs
        return {"output_dir": str(out_dir), "usd_files": {}}

    monkeypatch.setattr(cli, "export_blender_scene_to_usd", fake_export)

    assert cli.main(["export-usd", str(scene), "--bake", "--bake-mode", "auto", "--bake-auto-unwrap"]) == 0
    assert captured["kwargs"]["bake_materials"] == ("all",)
    assert captured["kwargs"]["bake_auto_unwrap"] is True
    assert captured["kwargs"]["bake_mode"] == "auto"
    assert captured["kwargs"]["bake_color_space"] == "lin_ap1"
    assert "output_dir" in capsys.readouterr().out


def test_blender_cli_reports_runtime_errors_without_traceback(tmp_path, monkeypatch, capsys):
    scene = tmp_path / "scene.blend"
    scene.write_text("fake blend", encoding="utf-8")

    def fail(args):
        raise RuntimeError("unsupported nodes")

    monkeypatch.setattr(cli, "run_inspect_from_args", fail)

    exit_code = cli.main(["inspect", str(scene)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err == "error: unsupported nodes\n"
    assert "Traceback" not in captured.err


def test_blender_cli_targets_all_expands_without_duplicates():
    assert cli._targets_from_args(["materialx", "all", "mtlx"]) == ("mtlx", "openpbr")


def test_blender_cli_targets_default_to_all():
    assert cli._targets_from_args([]) == ("mtlx", "openpbr")


def test_texture_remaps_require_old_equals_new_form():
    with pytest.raises(ValueError, match="OLD=NEW"):
        cli._texture_remaps_from_args(["C:/old"])
