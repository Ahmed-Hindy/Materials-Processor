import contextlib
import io as stdlib_io
import json
from importlib import resources

import pytest
from pxr import Sdf, Usd, UsdShade

from materials_processor import io as material_io
from materials_processor.standardizer import NodeStandardizer
from materials_processor.usd.recreator import USDMaterialRecreator
from materials_processor.usd.traverser import USDTraverser


MATERIAL_NAME = "mtlxmaterial_full"
MATERIAL_PATH = Sdf.Path(f"/materials/{MATERIAL_NAME}")


USD_TARGETS = [
    pytest.param(
        "mtlx",
        {
            "ND_standard_surface_surfaceshader",
            "ND_image_color3",
            "ND_colorcorrect_color3",
            "ND_range_color3",
            "ND_bump_vector3",
        },
        {
            "surface": "mtlx:surface",
            "displacement": "mtlx:displacement",
        },
        id="mtlx",
    ),
    pytest.param(
        "arnold",
        {
            "arnold:standard_surface",
            "arnold:image",
            "arnold:color_correct",
            "arnold:range",
            "arnold:bump2d",
        },
        {
            "surface": "arnold:surface",
            "displacement": "arnold:displacement",
        },
        id="arnold",
    ),
    pytest.param(
        "rs_usd_material_builder",
        {
            "redshift::StandardMaterial",
            "redshift::TextureSampler",
            "redshift::RSColorCorrection",
            "redshift::RSColorRange",
            "redshift::Displacement",
        },
        {
            "surface": "Redshift:surface",
            "displacement": "Redshift:displacement",
        },
        id="rs-usd-material-builder",
    ),
]


def _load_houdini_mtlx_fixture():
    fixture_root = resources.files("materials_processor.fixtures")
    traversed_nodes = material_io.load_node_tree_json(fixture_root / "example_traversed_nodes_dict.json")
    output_nodes = material_io.load_node_tree_json(fixture_root / "example_output_nodes_dict.json")

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        return NodeStandardizer(
            traversed_nodes_dict=traversed_nodes,
            output_nodes_dict=output_nodes,
            material_type="mtlx",
            source_type="hou_vop_nodes",
        ).run()


def _build_usd_stage_from_houdini_json(target_renderer):
    nodeinfo_list, output_connections = _load_houdini_mtlx_fixture()
    stage = Usd.Stage.CreateInMemory()

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        USDMaterialRecreator(
            stage=stage,
            material_name=MATERIAL_NAME,
            nodeinfo_list=nodeinfo_list,
            output_connections=output_connections,
            target_renderer=target_renderer,
        )

    return stage


def _shader_ids(stage):
    ids = set()
    for prim in stage.Traverse():
        shader_id = prim.GetAttribute("info:id")
        if shader_id and shader_id.Get():
            ids.add(shader_id.Get())
    return ids


def _material_output_names(material):
    material_shader = UsdShade.Shader(material.GetPrim())
    return {output.GetBaseName() for output in material_shader.GetOutputs()}


@pytest.mark.parametrize(("target_renderer", "expected_shader_ids", "expected_output_labels"), USD_TARGETS)
def test_houdini_json_converts_to_usd_renderer_matrix(
    target_renderer,
    expected_shader_ids,
    expected_output_labels,
):
    stage = _build_usd_stage_from_houdini_json(target_renderer)

    material = UsdShade.Material.Get(stage, MATERIAL_PATH)
    assert material.GetPrim().IsValid()
    assert material.GetPrim().GetTypeName() == "Material"

    assert expected_shader_ids <= _shader_ids(stage)

    material_output_names = _material_output_names(material)
    assert {"surface", "displacement"} == {name.split(":")[-1] for name in material_output_names}
    assert set(expected_output_labels.values()) <= material_output_names

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        traversed_nodes, output_nodes = USDTraverser(
            stage=stage,
            material_prim=material.GetPrim(),
            material_type=target_renderer,
        ).run()

    assert traversed_nodes
    assert output_nodes
    assert set(output_nodes) == {"surface", "displacement"}
    assert {key: value["connected_output_name"] for key, value in output_nodes.items()} == expected_output_labels

    assert json.loads(json.dumps(traversed_nodes)) == traversed_nodes
    assert json.loads(json.dumps(output_nodes)) == output_nodes
