import contextlib
import io as stdlib_io
import json
from dataclasses import dataclass
from importlib import resources

import pytest
from pxr import Sdf, Usd, UsdShade

from materials_processor import io as material_io
from materials_processor.core.graph import ConnectionEndpoint, NodeConnection, NodeInfo, NodeParameter, OutputConnection
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
    traversed_nodes_file="houdini_principled_native_traversed_nodes.json",
    output_nodes_file="houdini_principled_native_output_nodes.json",
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
        "openpbr",
        {
            "ND_open_pbr_surface_surfaceshader",
            "ND_image_color3",
            "ND_colorcorrect_color3",
            "ND_range_color3",
            "ND_bump_vector3",
        },
        {
            "surface": "mtlx:surface",
            "displacement": "mtlx:displacement",
        },
        id="houdini-mtlx-to-usd-openpbr",
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
            "ND_normalmap_vector3",
        },
        {
            "surface": "mtlx:surface",
        },
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
        ).run()

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
    assert set(expected_output_labels) == {name.split(":")[-1] for name in material_output_names}
    assert set(expected_output_labels.values()) <= material_output_names

    with contextlib.redirect_stdout(stdlib_io.StringIO()):
        traversed_nodes, output_nodes = USDTraverser(
            stage=stage,
            material_prim=material.GetPrim(),
            material_type=target_renderer,
        ).run()

    assert traversed_nodes
    assert output_nodes
    assert set(output_nodes) == set(expected_output_labels)
    assert {key: value["connected_output_name"] for key, value in output_nodes.items()} == expected_output_labels

    assert json.loads(json.dumps(traversed_nodes)) == traversed_nodes
    assert json.loads(json.dumps(output_nodes)) == output_nodes


def test_usd_recreator_sanitizes_material_and_shader_prim_names():
    stage = Usd.Stage.CreateInMemory()
    nodeinfo = NodeInfo(
        node_type="GENERIC::standard_surface",
        node_name="Principled BSDF",
        node_path="/mat/My Material/Principled BSDF",
        parameters=[],
        connection_info={},
        children_list=[],
    )
    output_connection = OutputConnection(
        node_name="Material Output",
        node_path="/mat/My Material/Material Output",
        connected_node_name="Principled BSDF",
        connected_node_path="/mat/My Material/Principled BSDF",
        connected_input_index=0,
        connected_input_name="Surface",
        connected_output_name="surface",
    )

    USDMaterialRecreator(
        stage=stage,
        material_name="My Material",
        nodeinfo_list=[nodeinfo],
        output_connections={"GENERIC::output_surface": output_connection},
        target_renderer="mtlx",
    ).run()

    material = UsdShade.Material.Get(stage, Sdf.Path("/materials/My_Material"))
    shader = UsdShade.Shader.Get(stage, Sdf.Path("/materials/My_Material/Principled_BSDF"))

    assert material.GetPrim().IsValid()
    assert shader.GetPrim().IsValid()
    assert shader.GetIdAttr().Get() == "ND_standard_surface_surfaceshader"
    assert "outputs:mtlx:surface" in {output.GetFullName() for output in material.GetOutputs()}


def test_usd_recreator_maps_blender_texture_coordinate_and_channel_sockets():
    stage = Usd.Stage.CreateInMemory()
    surface = NodeInfo(
        node_type="GENERIC::standard_surface",
        node_name="Principled BSDF",
        node_path="/mat/packed/Principled BSDF",
        parameters=[],
        connection_info={},
        children_list=[],
    )
    separate = NodeInfo(
        node_type="GENERIC::separate_color",
        node_name="Separate Color",
        node_path="/mat/packed/Separate Color",
        parameters=[],
        connection_info={
            "connection_0": NodeConnection(
                input=ConnectionEndpoint(
                    node_name="Separate Color",
                    node_path="/mat/packed/Separate Color",
                    node_type="ShaderNodeSeparateColor",
                    node_index=0,
                    parm_name="b",
                ),
                output=ConnectionEndpoint(
                    node_name="Principled BSDF",
                    node_path="/mat/packed/Principled BSDF",
                    node_type="ShaderNodeBsdfPrincipled",
                    node_index=0,
                    parm_name="metalness",
                ),
            )
        },
        children_list=[],
    )
    image = NodeInfo(
        node_type="GENERIC::image",
        node_name="Packed Texture",
        node_path="/mat/packed/Packed Texture",
        parameters=[
            NodeParameter("filename", "string1", "input", "C:/textures/packed.png"),
            NodeParameter("signature", "string1", "input", "color3"),
        ],
        connection_info={
            "connection_0": NodeConnection(
                input=ConnectionEndpoint(
                    node_name="Packed Texture",
                    node_path="/mat/packed/Packed Texture",
                    node_type="ShaderNodeTexImage",
                    node_index=0,
                    parm_name="rgb",
                ),
                output=ConnectionEndpoint(
                    node_name="Separate Color",
                    node_path="/mat/packed/Separate Color",
                    node_type="ShaderNodeSeparateColor",
                    node_index=0,
                    parm_name="rgb",
                ),
            )
        },
        children_list=[],
    )
    uvmap = NodeInfo(
        node_type="GENERIC::uvmap",
        node_name="UV Map",
        node_path="/mat/packed/UV Map",
        parameters=[NodeParameter("uv_map", "string1", "input", "UVMap")],
        connection_info={
            "connection_0": NodeConnection(
                input=ConnectionEndpoint(
                    node_name="UV Map",
                    node_path="/mat/packed/UV Map",
                    node_type="ShaderNodeUVMap",
                    node_index=0,
                    parm_name="vector",
                ),
                output=ConnectionEndpoint(
                    node_name="Packed Texture",
                    node_path="/mat/packed/Packed Texture",
                    node_type="ShaderNodeTexImage",
                    node_index=0,
                    parm_name="texcoord",
                ),
            )
        },
        children_list=[],
    )
    image.children_list.append(uvmap)
    separate.children_list.append(image)
    surface.children_list.append(separate)
    output_connection = OutputConnection(
        node_name="Material Output",
        node_path="/mat/packed/Material Output",
        connected_node_name="Principled BSDF",
        connected_node_path="/mat/packed/Principled BSDF",
        connected_input_index=0,
        connected_input_name="Surface",
        connected_output_name="surface",
    )

    USDMaterialRecreator(
        stage=stage,
        material_name="packed",
        nodeinfo_list=[surface],
        output_connections={"GENERIC::output_surface": output_connection},
        target_renderer="mtlx",
    ).run()

    assert {
        "ND_standard_surface_surfaceshader",
        "ND_image_color3",
        "ND_geompropvalue_vector2",
        "ND_separate3_color3",
    } <= _shader_ids(stage)

    image_shader = UsdShade.Shader.Get(stage, Sdf.Path("/materials/packed/Packed_Texture"))
    separate_shader = UsdShade.Shader.Get(stage, Sdf.Path("/materials/packed/Separate_Color"))
    surface_shader = UsdShade.Shader.Get(stage, Sdf.Path("/materials/packed/Principled_BSDF"))

    assert image_shader.GetInput("texcoord").GetAttr().GetConnections()[0].pathString.endswith("/UV_Map.outputs:out")
    assert separate_shader.GetInput("in").GetAttr().GetConnections()[0].pathString.endswith(
        "/Packed_Texture.outputs:out"
    )
    assert surface_shader.GetInput("metalness").GetAttr().GetConnections()[0].pathString.endswith(
        "/Separate_Color.outputs:outb"
    )


def test_usd_recreator_maps_blender_texcoord_mapping_and_value_nodes():
    stage = Usd.Stage.CreateInMemory()
    surface = NodeInfo(
        node_type="GENERIC::standard_surface",
        node_name="Principled BSDF",
        node_path="/mat/mapped/Principled BSDF",
        parameters=[],
        connection_info={},
        children_list=[],
    )
    image = NodeInfo(
        node_type="GENERIC::image",
        node_name="Image Texture",
        node_path="/mat/mapped/Image Texture",
        parameters=[
            NodeParameter("filename", "string1", "input", "C:/textures/diffuse.png"),
            NodeParameter("signature", "string1", "input", "color3"),
        ],
        connection_info={
            "connection_0": NodeConnection(
                input=ConnectionEndpoint(
                    node_name="Image Texture",
                    node_path="/mat/mapped/Image Texture",
                    node_type="ShaderNodeTexImage",
                    node_index=0,
                    parm_name="rgb",
                ),
                output=ConnectionEndpoint(
                    node_name="Principled BSDF",
                    node_path="/mat/mapped/Principled BSDF",
                    node_type="ShaderNodeBsdfPrincipled",
                    node_index=0,
                    parm_name="base_color",
                ),
            )
        },
        children_list=[],
    )
    mapping = NodeInfo(
        node_type="GENERIC::mapping",
        node_name="Mapping",
        node_path="/mat/mapped/Mapping",
        parameters=[
            NodeParameter("offset", "vector2", "input", [0.25, 0.5]),
            NodeParameter("scale", "vector2", "input", [2.0, 3.0]),
            NodeParameter("rotate", "float1", "input", 90.0),
        ],
        connection_info={
            "connection_0": NodeConnection(
                input=ConnectionEndpoint(
                    node_name="Mapping",
                    node_path="/mat/mapped/Mapping",
                    node_type="ShaderNodeMapping",
                    node_index=0,
                    parm_name="out",
                ),
                output=ConnectionEndpoint(
                    node_name="Image Texture",
                    node_path="/mat/mapped/Image Texture",
                    node_type="ShaderNodeTexImage",
                    node_index=0,
                    parm_name="texcoord",
                ),
            )
        },
        children_list=[],
    )
    texcoord = NodeInfo(
        node_type="GENERIC::uvmap",
        node_name="Texture Coordinate",
        node_path="/mat/mapped/Texture Coordinate",
        parameters=[],
        connection_info={
            "connection_0": NodeConnection(
                input=ConnectionEndpoint(
                    node_name="Texture Coordinate",
                    node_path="/mat/mapped/Texture Coordinate",
                    node_type="ShaderNodeTexCoord",
                    node_index=0,
                    parm_name="vector",
                ),
                output=ConnectionEndpoint(
                    node_name="Mapping",
                    node_path="/mat/mapped/Mapping",
                    node_type="ShaderNodeMapping",
                    node_index=0,
                    parm_name="texcoord",
                ),
            )
        },
        children_list=[],
    )
    value = NodeInfo(
        node_type="GENERIC::value",
        node_name="Roughness Value",
        node_path="/mat/mapped/Roughness Value",
        parameters=[NodeParameter("value", "float1", "input", 0.42)],
        connection_info={
            "connection_0": NodeConnection(
                input=ConnectionEndpoint(
                    node_name="Roughness Value",
                    node_path="/mat/mapped/Roughness Value",
                    node_type="ShaderNodeValue",
                    node_index=0,
                    parm_name="out",
                ),
                output=ConnectionEndpoint(
                    node_name="Principled BSDF",
                    node_path="/mat/mapped/Principled BSDF",
                    node_type="ShaderNodeBsdfPrincipled",
                    node_index=0,
                    parm_name="specular_roughness",
                ),
            )
        },
        children_list=[],
    )
    mapping.children_list.append(texcoord)
    image.children_list.append(mapping)
    surface.children_list.extend([image, value])
    output_connection = OutputConnection(
        node_name="Material Output",
        node_path="/mat/mapped/Material Output",
        connected_node_name="Principled BSDF",
        connected_node_path="/mat/mapped/Principled BSDF",
        connected_input_index=0,
        connected_input_name="Surface",
        connected_output_name="surface",
    )

    USDMaterialRecreator(
        stage=stage,
        material_name="mapped",
        nodeinfo_list=[surface],
        output_connections={"GENERIC::output_surface": output_connection},
        target_renderer="mtlx",
    ).run()

    assert {
        "ND_standard_surface_surfaceshader",
        "ND_image_color3",
        "ND_geompropvalue_vector2",
        "ND_place2d_vector2",
        "ND_constant_float",
    } <= _shader_ids(stage)

    mapping_shader = UsdShade.Shader.Get(stage, Sdf.Path("/materials/mapped/Mapping"))
    image_shader = UsdShade.Shader.Get(stage, Sdf.Path("/materials/mapped/Image_Texture"))
    surface_shader = UsdShade.Shader.Get(stage, Sdf.Path("/materials/mapped/Principled_BSDF"))

    assert mapping_shader.GetInput("texcoord").GetAttr().GetConnections()[0].pathString.endswith(
        "/Texture_Coordinate.outputs:out"
    )
    assert image_shader.GetInput("texcoord").GetAttr().GetConnections()[0].pathString.endswith(
        "/Mapping.outputs:out"
    )
    assert surface_shader.GetInput("specular_roughness").GetAttr().GetConnections()[0].pathString.endswith(
        "/Roughness_Value.outputs:out"
    )
    assert mapping_shader.GetInput("offset").Get() == (0.25, 0.5)
    assert mapping_shader.GetInput("scale").Get() == (2.0, 3.0)
    assert mapping_shader.GetInput("rotate").Get() == 90.0
    assert UsdShade.Shader.Get(stage, Sdf.Path("/materials/mapped/Roughness_Value")).GetInput(
        "value"
    ).Get() == pytest.approx(0.42)


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


def test_usd_recreator_constructor_does_not_create_material_until_run():
    nodeinfo_list, output_connections = _load_houdini_fixture(HOUDINI_MTLX_FULL)
    stage = Usd.Stage.CreateInMemory()

    recreator = USDMaterialRecreator(
        stage=stage,
        material_name=HOUDINI_MTLX_FULL.material_name,
        nodeinfo_list=nodeinfo_list,
        output_connections=output_connections,
        target_renderer="mtlx",
    )

    assert not stage.GetPrimAtPath(HOUDINI_MTLX_FULL.material_path).IsValid()

    recreator.run()

    assert stage.GetPrimAtPath(HOUDINI_MTLX_FULL.material_path).IsValid()
