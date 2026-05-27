import contextlib
import io as stdlib_io
import json
from dataclasses import dataclass
from importlib import resources

import pytest
from pxr import Sdf, Usd, UsdShade

from materials_processor import io as material_io
from materials_processor.standardizer import NodeStandardizer
from materials_processor.usd.recreator import USDMaterialRecreator
from materials_processor.usd.traverser import USDTraverser


@dataclass(frozen=True)
class HoudiniJsonFixture:
    material_name: str
    material_type: str
    traversed_nodes_file: str
    output_nodes_file: str

    @property
    def material_path(self):
        return Sdf.Path(f"/materials/{self.material_name}")


HOUDINI_MTLX_FULL = HoudiniJsonFixture(
    material_name="mtlxmaterial_full",
    material_type="mtlx",
    traversed_nodes_file="houdini_mtlx_full_traversed_nodes.json",
    output_nodes_file="houdini_mtlx_full_output_nodes.json",
)
HOUDINI_ARNOLD_FULL = HoudiniJsonFixture(
    material_name="arnold_materialbuilder_full",
    material_type="arnold",
    traversed_nodes_file="houdini_arnold_full_traversed_nodes.json",
    output_nodes_file="houdini_arnold_full_output_nodes.json",
)
HOUDINI_PRINCIPLED_TO_MTLX = HoudiniJsonFixture(
    material_name="principledshader",
    material_type="principledshader",
    traversed_nodes_file="houdini_principled_to_mtlx_traversed_nodes.json",
    output_nodes_file="houdini_principled_to_mtlx_output_nodes.json",
)


USD_CONVERSION_CASES = [
    pytest.param(
        HOUDINI_MTLX_FULL,
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
        id="houdini-mtlx-to-usd-mtlx",
    ),
    pytest.param(
        HOUDINI_MTLX_FULL,
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
        id="houdini-mtlx-to-usd-arnold",
    ),
    pytest.param(
        HOUDINI_MTLX_FULL,
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
        id="houdini-mtlx-to-usd-redshift",
    ),
    pytest.param(
        HOUDINI_ARNOLD_FULL,
        "arnold",
        {
            "arnold:standard_surface",
            "arnold:image",
            "arnold:color_correct",
            "arnold:curvature",
            "arnold:layer_rgba",
            "arnold:mix_rgba",
            "arnold:range",
        },
        {
            "surface": "arnold:surface",
            "displacement": "arnold:displacement",
        },
        id="houdini-arnold-to-usd-arnold",
    ),
    pytest.param(
        HOUDINI_ARNOLD_FULL,
        "rs_usd_material_builder",
        {
            "redshift::StandardMaterial",
            "redshift::TextureSampler",
            "redshift::RSColorCorrection",
            "redshift::RSColorRange",
        },
        {
            "surface": "Redshift:surface",
            "displacement": "Redshift:displacement",
        },
        id="houdini-arnold-to-usd-redshift",
    ),
    pytest.param(
        HOUDINI_PRINCIPLED_TO_MTLX,
        "mtlx",
        {
            "ND_standard_surface_surfaceshader",
            "ND_image_color3",
            "ND_bump_vector3",
        },
        {
            "surface": "mtlx:surface",
            "displacement": "mtlx:displacement",
        },
        marks=pytest.mark.xfail(
            raises=KeyError,
            strict=True,
            reason=(
                "Current principled-to-MTLX JSON references displacement at "
                "/mat/principledshader/mtlxdisplacement, but the traversed node path is "
                "/mat/principledshaderl/mtlxdisplacement."
            ),
        ),
        id="houdini-principled-to-usd-mtlx",
    ),
]


def _load_houdini_fixture(fixture):
    fixture_root = resources.files("materials_processor.fixtures")
    traversed_nodes = material_io.load_node_tree_json(fixture_root / fixture.traversed_nodes_file)
    output_nodes = material_io.load_node_tree_json(fixture_root / fixture.output_nodes_file)

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        return NodeStandardizer(
            traversed_nodes_dict=traversed_nodes,
            output_nodes_dict=output_nodes,
            material_type=fixture.material_type,
            source_type="hou_vop_nodes",
        ).run()


def _build_usd_stage_from_houdini_json(fixture, target_renderer):
    nodeinfo_list, output_connections = _load_houdini_fixture(fixture)
    stage = Usd.Stage.CreateInMemory()

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        USDMaterialRecreator(
            stage=stage,
            material_name=fixture.material_name,
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


@pytest.mark.parametrize(
    ("fixture", "target_renderer", "expected_shader_ids", "expected_output_labels"),
    USD_CONVERSION_CASES,
)
def test_houdini_json_converts_to_usd_renderer_matrix(
    fixture,
    target_renderer,
    expected_shader_ids,
    expected_output_labels,
):
    stage = _build_usd_stage_from_houdini_json(fixture, target_renderer)

    material = UsdShade.Material.Get(stage, fixture.material_path)
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


def test_usd_recreator_legacy_texture_collect_builder_smoke():
    stage = Usd.Stage.CreateInMemory()
    recreator = USDMaterialRecreator(
        stage=stage,
        material_name="smoke_glass",
        nodeinfo_list=[],
        output_connections={},
    )
    recreator.material_dict = {
        "basecolor": {"path": "C:/textures/basecolor.exr"},
        "roughness": {"path": "C:/textures/roughness.exr"},
    }
    recreator.is_transmissive = recreator.detect_if_transmissive(recreator.material_name)

    collect = recreator._create_collect_prim(
        "/texture_smoke",
        create_usd_preview=True,
        create_arnold=True,
        create_mtlx=True,
    )

    assert collect.GetPrim().IsValid()
    assert stage.GetPrimAtPath("/texture_smoke/mat_smoke_glass_collect/arnold_standard_surface1").IsValid()
    assert stage.GetPrimAtPath("/texture_smoke/mat_smoke_glass_collect/mtlx_mtlxstandard_surface1").IsValid()
    assert stage.GetPrimAtPath(
        "/texture_smoke/mat_smoke_glass_collect/UsdPreviewMaterial/UsdPreviewNodeGraph/UsdPreviewSurface"
    ).IsValid()
